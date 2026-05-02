"""Smoke: AE + VAE + GNN on the training-time engineered features.

Reads `apps/models/feature_matrix_no_leakage.parquet` (119 unscaled engineered
features) + `apps/models/labels.parquet` (the binary `malicious` label),
selects the canonical 55 columns from `selected_features_top25.json`, applies
the runtime StandardScaler, and pushes a benign sample + a malicious sample
through the live AE / VAE / GNN loaders.

Bypasses Redis, filebeat, the Wazuh adapter, and SecBERT — the engineered
features are already on disk. So this isolates ONE question: do the model
loaders + scaler + selected-column ordering reproduce training-time benign-vs-
malicious separability? If yes, the contract holds at the model interface.

Run from repo root:
  apps/api/.venv/bin/python apps/api/tests/smoke_models_on_training_features.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
APPS_API_SRC = REPO_ROOT / "apps" / "api" / "src"
sys.path.insert(0, str(APPS_API_SRC))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from strix_api.adapters.model_loaders.autoencoder import AutoencoderLoader  # noqa: E402
from strix_api.adapters.model_loaders.gnn import GnnLoader  # noqa: E402
from strix_api.adapters.model_loaders.vae import VaeLoader  # noqa: E402
from strix_api.adapters.preprocessing_pipeline import GnnMetadata, _load_pickle  # noqa: E402

MODELS_DIR = REPO_ROOT / "apps" / "models"
FEATURE_PARQUET = MODELS_DIR / "feature_matrix_no_leakage.parquet"
LABELS_PARQUET = MODELS_DIR / "labels.parquet"
CANONICAL_JSON = MODELS_DIR / "selected_features_top25.json"
SCALER_PKL = MODELS_DIR / "standard_scaler.pkl"
PER_GROUP = 800


def _stats(name: str, arr: np.ndarray) -> dict:
    arr = np.asarray(arr, dtype=np.float64)
    return {
        "name": name,
        "n": int(arr.size),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "p10": float(np.percentile(arr, 10)),
        "p50": float(np.percentile(arr, 50)),
        "p90": float(np.percentile(arr, 90)),
    }


def _print(label: str, s_b: dict, s_a: dict, expected: str) -> None:
    delta = s_a["mean"] - s_b["mean"]
    direction = "ATTACK > benign" if delta > 0 else "benign > ATTACK" if delta < 0 else "tied"
    ok = expected in direction
    flag = "OK " if ok else "?? "
    print(
        f"  {flag}{label:>22s}  benign  μ={s_b['mean']:+8.4f}  σ={s_b['std']:6.3f}  "
        f"p50={s_b['p50']:+7.3f}  ||  attack  μ={s_a['mean']:+8.4f}  σ={s_a['std']:6.3f}  "
        f"p50={s_a['p50']:+7.3f}  ||  Δ={delta:+7.3f}  ({direction})"
    )


def main() -> int:
    print("=" * 110)
    print("SMOKE — AE / VAE / GNN on training-time engineered features")
    print("=" * 110)

    # 1. Load features + labels.
    print(f"loading {FEATURE_PARQUET.name} ...")
    fmat = pd.read_parquet(FEATURE_PARQUET)
    print(f"  shape={fmat.shape}")
    print(f"loading {LABELS_PARQUET.name} ...")
    labels = pd.read_parquet(LABELS_PARQUET)
    print(f"  shape={labels.shape}  malicious distribution:")
    print(f"   {labels['malicious'].value_counts().to_dict()}")

    # 2. Canonical 55-col selection.
    canon = json.loads(CANONICAL_JSON.read_text())["all_selected_columns"]
    assert len(canon) == 55, len(canon)
    missing = [c for c in canon if c not in fmat.columns]
    if missing:
        print(f"  MISSING columns in parquet: {missing}")
        return 1
    X_55 = fmat[canon].astype(np.float32).values
    print(f"  selected 55 columns; X_55.shape={X_55.shape}")

    # 3. Apply the runtime StandardScaler.
    scaler = _load_pickle(SCALER_PKL, "StandardScaler")
    print(f"  scaler n_features_in_={scaler.n_features_in_}")
    if scaler.n_features_in_ != 55:
        print("  scaler dim mismatch — bailing")
        return 1
    X_scaled = scaler.transform(X_55).astype(np.float32)
    print(f"  scaled; X_scaled.shape={X_scaled.shape}  μ={X_scaled.mean():+.3f}  σ={X_scaled.std():.3f}")

    # 4. Sample benign + malicious.
    rng = np.random.default_rng(42)
    benign_idx = labels.index[labels["malicious"] == 0]
    attack_idx = labels.index[labels["malicious"] == 1]
    n_b = min(PER_GROUP, len(benign_idx))
    n_a = min(PER_GROUP, len(attack_idx))
    sel_b = rng.choice(benign_idx, size=n_b, replace=False)
    sel_a = rng.choice(attack_idx, size=n_a, replace=False)
    X_b = X_scaled[sel_b]
    X_a = X_scaled[sel_a]
    print(f"  sampled benign={n_b}  attack={n_a}")
    print()

    # 5. AE.
    print("AE -----------------------------------------------------------------------------------------")
    ae = AutoencoderLoader.load(MODELS_DIR / "ae_model.pth", version="v1")
    out_b = ae.batch_forward(X_b)
    out_a = ae.batch_forward(X_a)
    _print("ae.anomaly_score", _stats("benign", out_b.anomaly_score), _stats("attack", out_a.anomaly_score), expected="ATTACK > benign")
    _print("ae.recon_error",   _stats("benign", out_b.recon_error),   _stats("attack", out_a.recon_error),   expected="ATTACK > benign")
    print()

    # 6. VAE (calibrated probability).
    print("VAE ----------------------------------------------------------------------------------------")
    calibrators = _load_pickle(MODELS_DIR / "probability_calibrators.pkl", "dict")
    vae = VaeLoader.load(MODELS_DIR / "vae_model.pth", calibrator=calibrators["Beta-VAE (Top 25)"], version="v1")
    out_b = vae.batch_forward(X_b)
    out_a = vae.batch_forward(X_a)
    _print("vae.malicious_prob", _stats("benign", out_b.malicious_prob), _stats("attack", out_a.malicious_prob), expected="ATTACK > benign")
    _print("vae.uncertainty",    _stats("benign", out_b.uncertainty),    _stats("attack", out_a.uncertainty),    expected="ATTACK > benign")
    print()

    # 7. GNN — disconnected nodes (no graph context). Tests the per-node MLP head.
    print("GNN (disconnected nodes — per-node head only) -----------------------------------------------")
    gnn_raw = _load_pickle(MODELS_DIR / "gnn_metadata.pkl", "dict")
    # Slice 56-col scaler to 55 cols when rule_level was included at training
    # time (legacy Part-1 metadata) — the shipped Part-2 weights take 55 cols.
    sliced_scaler = gnn_raw["scaler"]
    if gnn_raw.get("rule_level_included"):
        # Mirror what build_pipeline does: take a sliced view of the 56-d scaler.
        s = gnn_raw["scaler"]
        from copy import deepcopy
        sliced_scaler = deepcopy(s)
        sliced_scaler.mean_ = s.mean_[:55]
        sliced_scaler.scale_ = s.scale_[:55]
        sliced_scaler.var_ = s.var_[:55]
        sliced_scaler.n_features_in_ = 55
    gnn_meta = GnnMetadata(
        features=list(gnn_raw["features"]),
        scaler_55=sliced_scaler,
        threshold=float(gnn_raw["threshold"]),
        rule_level_included=bool(gnn_raw.get("rule_level_included", False)),
        metrics=dict(gnn_raw.get("metrics") or {}),
        raw_metadata=dict(gnn_raw),
    )
    gnn = GnnLoader.load(MODELS_DIR / "gnn_model.pth", metadata=gnn_meta, version="v1")
    # Re-permute X into GNN's alphabetical ordering.
    canon_idx = {c: i for i, c in enumerate(canon)}
    perm = np.array([canon_idx[c] for c in gnn_meta.features], dtype=np.int64)
    Xb_g = X_b[:, perm]
    Xa_g = X_a[:, perm]
    # Score with empty edge_index (no neighbours).
    empty_edges = np.zeros((2, 0), dtype=np.int64)
    risks_b = gnn.score_graph(Xb_g, empty_edges).risks
    risks_a = gnn.score_graph(Xa_g, empty_edges).risks
    _print("gnn.node_risk", _stats("benign", risks_b), _stats("attack", risks_a), expected="ATTACK > benign")
    print()

    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
