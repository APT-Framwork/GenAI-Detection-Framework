"""
Workstream 2 / Phase A — export preprocessing artifacts to apps/models/preprocess/.

This script does NOT retrain anything. It:
  1. Copies/renames the existing 55-col StandardScaler (apps/models/standard_scaler.pkl
     → preprocess/scaler_55.pkl).
  2. Copies the two PCA-16 objects (log/cmd) to canonical names.
  3. Picks the canonical "Beta-VAE (Top 25)" entry from probability_calibrators.pkl
     and saves it as vae_calibrator.pkl (matches registry guidance).
  4. Synthesises the Part-2 GNN propagation metadata pkl from the existing
     gnn_metadata.pkl: slice scaler to 55 cols (drop rule_level), set
     threshold=0.7743, in_ch=55, rule_level_included=False (per Part-2 of
     GNN_Network_Propagation.ipynb).
  5. Saves the SecBERT (jackaduma/SecBERT) tokenizer to preprocess/secbert_tokenizer/
     via HuggingFace save_pretrained.

Run from repo root:
    python apps/models/preprocess/_export_artifacts.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import joblib
import numpy as np
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = REPO_ROOT / "apps" / "models"
SRC = MODELS_DIR
DST = MODELS_DIR / "preprocess"
DST.mkdir(parents=True, exist_ok=True)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    if p.is_dir():
        # hash sorted contents
        for f in sorted(p.rglob("*")):
            if f.is_file():
                h.update(f.relative_to(p).as_posix().encode())
                h.update(f.read_bytes())
        return h.hexdigest()
    h.update(p.read_bytes())
    return h.hexdigest()


def _size(p: Path) -> int:
    if p.is_dir():
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return p.stat().st_size


artifacts: list[dict] = []


# ---------------- 1. scaler_55.pkl ----------------
src_scaler = SRC / "standard_scaler.pkl"
dst_scaler = DST / "scaler_55.pkl"
shutil.copyfile(src_scaler, dst_scaler)
sc = joblib.load(dst_scaler)
assert sc.n_features_in_ == 55, f"scaler_55 has {sc.n_features_in_} features, expected 55"
artifacts.append(
    {
        "path": "preprocess/scaler_55.pkl",
        "sha256": _sha256(dst_scaler),
        "source_notebook": "apps/notebooks/feature_selection_final.ipynb",
        "cell": "derived via infra/scripts/derive_standard_scaler.py from gnn_metadata.pkl scaler",
        "shape_or_keys": f"StandardScaler n_features_in_={sc.n_features_in_}, "
        f"feature_names_in_[:3]={list(sc.feature_names_in_[:3])}",
    }
)

# ---------------- 2. pca_log_secbert.pkl ----------------
src = SRC / "secbert_log_pca.pkl"
dst = DST / "pca_log_secbert.pkl"
shutil.copyfile(src, dst)
p = joblib.load(dst)
assert p.n_components == 16 and p.n_features_in_ == 768
artifacts.append(
    {
        "path": "preprocess/pca_log_secbert.pkl",
        "sha256": _sha256(dst),
        "source_notebook": "apps/notebooks/feature_selection_final.ipynb",
        "cell": "SecBERT log PCA fit cell (n_components=16, random_state=42)",
        "shape_or_keys": f"PCA n_components={p.n_components} n_features_in_={p.n_features_in_}",
    }
)

# ---------------- 3. pca_cmd_secbert.pkl ----------------
src = SRC / "secbert_cmd_pca.pkl"
dst = DST / "pca_cmd_secbert.pkl"
shutil.copyfile(src, dst)
p = joblib.load(dst)
assert p.n_components == 16 and p.n_features_in_ == 768
artifacts.append(
    {
        "path": "preprocess/pca_cmd_secbert.pkl",
        "sha256": _sha256(dst),
        "source_notebook": "apps/notebooks/feature_selection_final.ipynb",
        "cell": "SecBERT cmd PCA fit cell (n_components=16, random_state=42)",
        "shape_or_keys": f"PCA n_components={p.n_components} n_features_in_={p.n_features_in_}",
    }
)

# ---------------- 4. vae_calibrator.pkl ----------------
calibs = joblib.load(SRC / "probability_calibrators.pkl")
key = "Beta-VAE (Top 25)"
assert key in calibs, f"missing key {key} in probability_calibrators.pkl"
calibrator = calibs[key]
dst = DST / "vae_calibrator.pkl"
joblib.dump(calibrator, dst)
artifacts.append(
    {
        "path": "preprocess/vae_calibrator.pkl",
        "sha256": _sha256(dst),
        "source_notebook": "apps/notebooks/TP2_VAE_FeatureSelection.ipynb",
        "cell": "VAE probability calibration cell (LogisticRegression on recon-loss → P(malicious)); "
        "extracted from probability_calibrators.pkl key='Beta-VAE (Top 25)'",
        "shape_or_keys": f"sklearn.linear_model.LogisticRegression coef_.shape={calibrator.coef_.shape} "
        f"intercept_={float(calibrator.intercept_[0]):.4f}",
    }
)

# ---------------- 5. gnn_propagation_metadata.pkl ----------------
# Part-2 retrain (no rule_level): slice the existing 56-col scaler to 55 cols.
# Notebook cell (GNN_Network_Propagation.ipynb): X_scaled_no_rule = X_scaled[:, :-1]
# Threshold from notebook output: 0.7743.
src_meta = joblib.load(SRC / "gnn_metadata.pkl")
old_scaler = src_meta["scaler"]
assert old_scaler.n_features_in_ == 56
new_scaler = StandardScaler()
new_scaler.mean_ = old_scaler.mean_[:55].copy()
new_scaler.scale_ = old_scaler.scale_[:55].copy()
new_scaler.var_ = old_scaler.var_[:55].copy()
new_scaler.n_features_in_ = 55
new_scaler.n_samples_seen_ = old_scaler.n_samples_seen_
if hasattr(old_scaler, "feature_names_in_"):
    fn = np.asarray(old_scaler.feature_names_in_)
    if fn.shape[0] == 56:
        new_scaler.feature_names_in_ = fn[:55].copy()
# preserve flags
new_scaler.with_mean = old_scaler.with_mean
new_scaler.with_std = old_scaler.with_std
new_scaler.copy = old_scaler.copy

new_meta = {
    "features": list(src_meta["features"]),  # already 55, alphabetical SecBERT order
    "rule_level_included": False,
    "scaler": new_scaler,
    "threshold": np.float32(0.7743),
    "metrics": {
        "precision": 0.7902,
        "recall": 0.8020,
        "f1": 0.7961,
        "accuracy": 0.9098,
        "auc_roc": 0.9625,
        "auc_pr": 0.8879,
        "source": "GNN_Network_Propagation.ipynb Part 2 — FINAL TEST RESULTS (NO RULE LEVEL)",
    },
    "model_params": {"in_ch": 55, "hid": 128, "layers": 3, "drop": 0.3},
    "graph_params": copy.deepcopy(src_meta.get("graph_params", {})),
}
assert len(new_meta["features"]) == 55
dst = DST / "gnn_propagation_metadata.pkl"
joblib.dump(new_meta, dst)
artifacts.append(
    {
        "path": "preprocess/gnn_propagation_metadata.pkl",
        "sha256": _sha256(dst),
        "source_notebook": "apps/notebooks/GNN_Network_Propagation.ipynb",
        "cell": "Part 2 'NO RULE LEVEL' retrain (cells around X_scaled[:, :-1]); threshold from "
        "FINAL TEST RESULTS print (0.7743). Scaler derived by slicing Part-1 56-col scaler to "
        "first 55 cols (notebook does not refit the scaler in Part 2).",
        "shape_or_keys": "{features: list[55], rule_level_included: False, scaler: StandardScaler(55), "
        "threshold: 0.7743, model_params: {in_ch:55,hid:128,layers:3,drop:0.3}, metrics, graph_params}",
    }
)

# ---------------- 6. secbert_tokenizer/ ----------------
from transformers import AutoTokenizer  # noqa: E402

tok_dir = DST / "secbert_tokenizer"
if tok_dir.exists():
    shutil.rmtree(tok_dir)
tok_dir.mkdir()
tok = AutoTokenizer.from_pretrained("jackaduma/SecBERT")
tok.save_pretrained(tok_dir.as_posix())
files = sorted(p.name for p in tok_dir.iterdir())
artifacts.append(
    {
        "path": "preprocess/secbert_tokenizer/",
        "sha256": _sha256(tok_dir),
        "source_notebook": "apps/notebooks/feature_selection_final.ipynb",
        "cell": "AutoTokenizer.from_pretrained('jackaduma/SecBERT') — exported via save_pretrained",
        "shape_or_keys": f"HF tokenizer dir, files={files}",
    }
)

# ---------------- MANIFEST ----------------
manifest = {
    "generatedBy": "apps/models/preprocess/_export_artifacts.py",
    "phase": "Workstream 2 / Phase A",
    "artifacts": artifacts,
}
manifest_path = MODELS_DIR / "MANIFEST.json"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
print(f"Wrote {manifest_path}")
for a in artifacts:
    abs_path = MODELS_DIR / a["path"]
    print(f"  {a['path']:50s} {_size(abs_path):>10d} bytes  sha256:{a['sha256'][:12]}")
