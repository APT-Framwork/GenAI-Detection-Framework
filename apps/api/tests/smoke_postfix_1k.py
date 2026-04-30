"""Smoke: validate the post-fix inference pipeline against ~1k captured features.

Reads ~1k entries from `strix:features:0` (Redis @ localhost:6380), runs them
through the in-process pipeline + AE / VAE / Transformer / GNN exactly as the
inference worker does, then prints distribution stats. Compares to the latest
1k production detections in postgres.

Run from repo root:
  apps/api/.venv/bin/python apps/api/tests/smoke_postfix_1k.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---- repo paths ----------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]
APPS_API_SRC = REPO_ROOT / "apps" / "api" / "src"
sys.path.insert(0, str(APPS_API_SRC))

import numpy as np  # noqa: E402
import redis  # noqa: E402

from strix_api.adapters.model_loaders.autoencoder import AutoencoderLoader  # noqa: E402
from strix_api.adapters.model_loaders.gnn import GnnLoader  # noqa: E402
from strix_api.adapters.model_loaders.transformer import TransformerLoader  # noqa: E402
from strix_api.adapters.model_loaders.vae import VaeLoader  # noqa: E402
from strix_api.adapters.model_registry import load_registry  # noqa: E402
from strix_api.adapters.preprocessing_pipeline import (  # noqa: E402
    FEATURE_COLUMNS,
    build_pipeline,
)
from strix_api.core.gnn_window import (  # noqa: E402
    NodeFact,
    build_snapshot,
)

REDIS_URL = os.environ.get("STRIX_REDIS_URL", "redis://localhost:6380/0")
N_TARGET = 1000
MODELS_DIR = REPO_ROOT / "apps" / "models"


def _decode(d: dict[bytes, bytes]) -> dict[str, Any]:
    """msgpack-decode a Redis stream entry's fields (mirrors redis_adapter.unpack)."""
    import msgpack
    body = d.get(b"payload")
    if body is None:
        raise ValueError("entry missing 'payload' field")
    return msgpack.unpackb(body, raw=False)


def _stats(name: str, arr: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(arr, dtype=np.float64)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return {"name": name, "n": 0}
    return {
        "name": name,
        "n": int(arr.size),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
        "min": float(np.min(finite)),
        "p10": float(np.percentile(finite, 10)),
        "p50": float(np.percentile(finite, 50)),
        "p90": float(np.percentile(finite, 90)),
        "max": float(np.max(finite)),
        "frac_ge_0.99": float(np.mean(finite >= 0.99)),
        "frac_eq_0": float(np.mean(finite == 0.0)),
    }


def _print_stats_row(s: dict[str, Any]) -> None:
    if s.get("n", 0) == 0:
        print(f"  {s['name']:>22s}  (no data)")
        return
    print(
        f"  {s['name']:>22s}  n={s['n']:5d}  "
        f"mean={s['mean']:+8.4f}  std={s['std']:7.4f}  "
        f"min={s['min']:+7.3f}  p10={s['p10']:+7.3f}  p50={s['p50']:+7.3f}  "
        f"p90={s['p90']:+7.3f}  max={s['max']:+7.3f}  "
        f"sat>=0.99={s['frac_ge_0.99']:.3f}  ==0={s['frac_eq_0']:.3f}"
    )


def _parse_iso(s: str) -> datetime:
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=UTC)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def fetch_features(n: int) -> list[dict[str, Any]]:
    """Pre-fix path: read pre-normalized vectors from strix:features:0."""
    r = redis.Redis.from_url(REDIS_URL)
    entries = r.xrange("strix:features:0", min="-", max="+", count=n)
    out: list[dict[str, Any]] = []
    for _id, fields in entries:
        try:
            payload = _decode(fields)
            fv = payload.get("featureVector")
            if fv is None:
                continue
            vec = np.asarray(fv, dtype=np.float32)
            if vec.shape != (55,):
                continue
            out.append(
                {
                    "alert_id": payload.get("alertId", ""),
                    "agent_id": payload.get("agentId", ""),
                    "occurred_at": _parse_iso(payload.get("occurredAt")),
                    "current_ckc_stage": int(payload.get("currentCkcStage") or 0),
                    "srcuser": payload.get("srcuser") or None,
                    "srcip": payload.get("srcip") or None,
                    "feature_vector": vec,
                }
            )
        except Exception as e:  # noqa: BLE001
            print(f"  decode_skip: {e}", file=sys.stderr)
    return out


def fetch_raw_and_normalize(n: int, pipe) -> list[dict[str, Any]]:
    """Post-fix path: source from strix:alerts:raw and re-normalize in-process.

    The host normalizer worker started before our fix; its output in
    strix:features:0 is broken. To validate the fix we re-normalize the
    source-of-truth raw alerts using the freshly-built pipeline.
    """
    import json as _json

    from strix_api.adapters.wazuh_adapter import WazuhAlertAdapter

    r = redis.Redis.from_url(REDIS_URL)
    entries = r.xrevrange("strix:alerts:raw", count=n)
    adapter = WazuhAlertAdapter()
    out: list[dict[str, Any]] = []
    for _id, fields in entries:
        try:
            payload = _decode(fields)
            raw = payload.get("rawJson") or payload.get("raw_json")
            if isinstance(raw, str):
                raw = _json.loads(raw)
            alert = adapter.parse(raw)
            vec = pipe.transform(alert)
            out.append(
                {
                    "alert_id": alert.alert_id,
                    "agent_id": alert.agent.agent_id,
                    "occurred_at": alert.occurred_at,
                    "current_ckc_stage": 0,
                    "srcuser": alert.data.srcuser,
                    "srcip": alert.data.srcip,
                    "feature_vector": vec.astype(np.float32),
                }
            )
        except Exception as e:  # noqa: BLE001
            print(f"  raw_skip: {e}", file=sys.stderr)
    return out


def main() -> None:
    print("=" * 90)
    print("STRIX post-fix 1k smoke")
    print("=" * 90)

    # ---------- 2. Build pipeline + assertions FIRST so we can re-normalize ----------
    print("\n[2] Building post-fix pipeline ...")
    pipe = build_pipeline(MODELS_DIR, warmup=False)

    # ---------- 1. Source events ----------
    use_raw = os.environ.get("STRIX_SMOKE_RAW", "1") not in ("0", "false", "")
    if use_raw:
        print("\n[1] Sourcing RAW events from strix:alerts:raw and re-normalizing ...")
        events = fetch_raw_and_normalize(N_TARGET, pipe)
        print(f"    re-normalized {len(events)} raw events @ {REDIS_URL}")
    else:
        print("\n[1] Sourcing pre-normalized events from strix:features:0 ...")
        events = fetch_features(N_TARGET)
        print(f"    loaded {len(events)} events from strix:features:0 @ {REDIS_URL}")
    if not events:
        print("    ERROR: no events available — aborting.")
        sys.exit(2)
    thr = float(pipe.gnn.threshold)
    n_in = int(pipe.gnn.scaler_55.n_features_in_)
    print(f"    pipe.gnn.threshold              = {thr:.4f}  (expected 0.7743)")
    print(f"    pipe.gnn.scaler_55.n_features_in_ = {n_in}     (expected 55)")
    print(f"    len(FEATURE_COLUMNS)             = {len(FEATURE_COLUMNS)} (expected 55)")
    assert n_in == 55, f"GNN scaler n_features_in_ mismatch: {n_in}"
    assert len(FEATURE_COLUMNS) == 55, f"FEATURE_COLUMNS len: {len(FEATURE_COLUMNS)}"
    if abs(thr - 0.7743) > 1e-3:
        print(f"    !! WARN: gnn threshold {thr} != 0.7743 (Phase E expectation)")

    # ---------- 3. Load model loaders ----------
    print("\n[3] Loading model loaders from registry ...")
    state = load_registry(
        MODELS_DIR / "registry.json", MODELS_DIR, verify_checksums=False
    )
    ae = AutoencoderLoader.load(state.models["ae"].file, version=state.models["ae"].version)
    vae = VaeLoader.load(
        state.models["vae"].file,
        calibrator=pipe.calibrators.active,
        version=state.models["vae"].version,
    )
    gnn = GnnLoader.load(
        state.models["gnn"].file, metadata=pipe.gnn, version=state.models["gnn"].version
    )
    transformer = TransformerLoader.load(
        state.models["transformer"].file, version=state.models["transformer"].version
    )
    print(f"    ae={ae.version}  vae={vae.version}  gnn={gnn.version}  transformer={transformer.version}")

    # ---------- 4. Run inference ----------
    print("\n[4] Running AE / VAE on 55-d feature vectors ...")
    X = np.stack([e["feature_vector"] for e in events], axis=0).astype(np.float32)

    ae_out_all: list[float] = []
    ae_recon_all: list[float] = []
    ae_latents: list[np.ndarray] = []
    BS = 64
    for i in range(0, X.shape[0], BS):
        out = ae.batch_forward(X[i : i + BS])
        ae_out_all.extend(out.anomaly_score.tolist())
        ae_recon_all.extend(out.recon_error.tolist())
        for j in range(out.batch_size):
            ae_latents.append(out.latents[j])
    ae_anom = np.asarray(ae_out_all, dtype=np.float32)

    vae_prob_all: list[float] = []
    vae_unc_all: list[float] = []
    for i in range(0, X.shape[0], BS):
        out = vae.batch_forward(X[i : i + BS])
        vae_prob_all.extend(out.malicious_prob.tolist())
        vae_unc_all.extend(out.uncertainty.tolist())
    vae_prob = np.asarray(vae_prob_all, dtype=np.float32)

    print(f"    AE: {len(ae_anom)} scored. VAE: {len(vae_prob)} scored.")

    # ---- Transformer ----
    print("\n[5] Transformer per-event (single-step sequences) ...")
    pred_ckc: list[int] = []
    conf_all: list[float] = []
    for lat in ae_latents:
        seq = np.expand_dims(lat, 0).astype(np.float32)
        out = transformer.predict_sequence(seq)
        pred_ckc.append(int(out.pred_ckc))
        conf_all.append(float(out.confidence))
    pred_ckc_arr = np.asarray(pred_ckc, dtype=np.int32)
    conf_arr = np.asarray(conf_all, dtype=np.float32)

    # ---- GNN over the whole window ----
    print("\n[6] GNN: building snapshot over all captured events ...")
    facts: list[NodeFact] = []
    for e in events:
        gnn_perm_vec = pipe.transform_for_gnn(e["feature_vector"])
        facts.append(
            NodeFact(
                alert_id=e["alert_id"],
                agent_id=e["agent_id"],
                occurred_at=e["occurred_at"],
                srcuser=e["srcuser"],
                srcip=e["srcip"],
                features_gnn_order=gnn_perm_vec,
            )
        )
    # build_snapshot uses 60-min window filter internally; pass facts directly.
    try:
        snap = build_snapshot(facts)
    except Exception as exc:  # noqa: BLE001
        print(f"    build_snapshot failed: {exc}")
        # fallback: at minimum exercise the GNN with chain edges
        raise

    print(f"    snapshot: nodes={snap.num_nodes}  edges={snap.num_edges}")
    gnn_out = gnn.score_graph(snap.x, snap.edge_index)
    gnn_risk = np.asarray(gnn_out.risks, dtype=np.float32)
    print(f"    gnn risks scored: {gnn_risk.size}")

    # ---------- distributions ----------
    print("\n" + "=" * 90)
    print("POST-FIX DISTRIBUTIONS (in-process, on captured features)")
    print("=" * 90)
    _print_stats_row(_stats("ae_anomaly_score", ae_anom))
    _print_stats_row(_stats("ae_recon_error", np.asarray(ae_recon_all, dtype=np.float32)))
    _print_stats_row(_stats("vae_malicious_prob", vae_prob))
    _print_stats_row(_stats("vae_uncertainty", np.asarray(vae_unc_all, dtype=np.float32)))
    _print_stats_row(_stats("transformer_confidence", conf_arr))
    _print_stats_row(_stats("gnn_node_risk", gnn_risk))

    print("\n  transformer_pred_ckc histogram:")
    cnt = Counter(pred_ckc_arr.tolist())
    for stage in range(8):
        c = cnt.get(stage, 0)
        bar = "#" * min(60, int(60 * c / max(1, len(pred_ckc_arr))))
        print(f"    stage {stage}: {c:5d}  {bar}")
    print(f"  distinct stages: {len(cnt)}")

    # ---------- Pass criteria ----------
    print("\n" + "=" * 90)
    print("PASS / FAIL")
    print("=" * 90)
    results = []

    vae_sat = float(np.mean(vae_prob >= 0.99))
    vae_mean = float(np.mean(vae_prob))
    p_vae = vae_sat < 0.50 and vae_mean < 0.95
    results.append(
        ("VAE not saturated", p_vae,
         f"sat={vae_sat:.3f} (<0.5 expected); mean={vae_mean:.3f} (<0.95 expected)")
    )

    gnn_active = float(np.mean(gnn_risk > 0.01))
    p_gnn = gnn_active >= 0.05
    results.append(
        ("GNN risks not all-zero", p_gnn,
         f"frac>0.01={gnn_active:.3f} (>=0.05 expected); max={float(np.max(gnn_risk)):.4f}")
    )

    ae_std = float(np.std(ae_anom))
    p_ae = ae_std > 1.0
    results.append(
        ("AE has spread", p_ae, f"std={ae_std:.4f} (>1.0 expected)")
    )

    p_tr = len(cnt) >= 3
    results.append(
        ("Transformer >=3 stages", p_tr, f"distinct={len(cnt)}")
    )

    for name, ok, detail in results:
        flag = "PASS" if ok else "FAIL"
        print(f"  [{flag}] {name:30s} {detail}")

    # ---------- Pre-fix (production) postgres comparison ----------
    print("\n" + "=" * 90)
    print("PRE-FIX (production postgres detections — latest 1000)")
    print("=" * 90)
    try:
        import subprocess

        out = subprocess.run(
            [
                "docker", "exec", "strix_postgres",
                "psql", "-U", "strix", "strix", "-At", "-F", ",",
                "-c",
                "SELECT ae_anomaly_score, vae_malicious_prob, "
                "transformer_pred_ckc, gnn_node_risk "
                "FROM detections ORDER BY occurred_at DESC LIMIT 1000;",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        prod_ae: list[float] = []
        prod_vae: list[float] = []
        prod_pck: list[int] = []
        prod_gnn: list[float] = []
        for line in out.stdout.strip().splitlines():
            parts = line.split(",")
            if len(parts) != 4:
                continue
            try:
                if parts[0]:
                    prod_ae.append(float(parts[0]))
                if parts[1]:
                    prod_vae.append(float(parts[1]))
                if parts[2]:
                    prod_pck.append(int(parts[2]))
                if parts[3]:
                    prod_gnn.append(float(parts[3]))
            except ValueError:
                pass
        print(f"    rows parsed: ae={len(prod_ae)} vae={len(prod_vae)} "
              f"pck={len(prod_pck)} gnn={len(prod_gnn)}")
        _print_stats_row(_stats("ae_anomaly_score (PROD)", np.asarray(prod_ae)))
        _print_stats_row(_stats("vae_malicious_prob (PROD)", np.asarray(prod_vae)))
        _print_stats_row(_stats("gnn_node_risk (PROD)", np.asarray(prod_gnn)))
        prod_cnt = Counter(prod_pck)
        print("\n    transformer_pred_ckc histogram (PROD):")
        for stage in range(8):
            print(f"      stage {stage}: {prod_cnt.get(stage, 0):5d}")
        print(f"    distinct stages (PROD): {len(prod_cnt)}")
    except Exception as exc:  # noqa: BLE001
        print(f"    (skipped — could not query postgres: {exc})")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
