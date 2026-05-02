"""Smoke: BENIGN vs ATTACK distribution comparison through the post-fix pipeline.

Read-only. Sources two disjoint sets from `strix:alerts:raw:list` (the filebeat
list — bridge isn't draining), runs them through the same in-process
build_pipeline() / pipe.transform(...) path the existing post-fix smoke uses,
and compares output distributions for AE / VAE / Transformer / GNN.

Set A — benign-recon: agent in (victim1, victim2), data.audit.exe in a
small benign read-only set (which/grep/ls/cat-of-passwd-or-group), auid != 0.
Falls back to all benign-recon execs if none qualify.

Set B — attack-suspect: rule.id in the STRIX custom range (100100..100700),
or victim agent + offensive exe (cat /etc/shadow, awk /etc/sudoers, ps -eo).

Run from repo root:
  apps/api/.venv/bin/python apps/api/tests/smoke_benign_vs_attack.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from strix_api.adapters.preprocessing_pipeline import build_pipeline  # noqa: E402
from strix_api.adapters.wazuh_adapter import WazuhAlertAdapter  # noqa: E402
from strix_api.core.gnn_window import NodeFact, build_snapshot  # noqa: E402

REDIS_URL = os.environ.get("STRIX_REDIS_URL", "redis://localhost:6380/0")
LIST_KEY = "strix:alerts:raw:list"
MODELS_DIR = REPO_ROOT / "apps" / "models"

TARGET_PER_SET = int(os.environ.get("STRIX_TARGET_PER_SET", "700"))
SCAN_BATCH = 5000
MAX_SCAN = 80_000

BENIGN_EXES = {
    "/usr/bin/which", "/bin/which",
    "/usr/bin/grep", "/bin/grep",
    "/usr/bin/egrep", "/bin/egrep",
    "/usr/bin/ls", "/bin/ls",
}
BENIGN_RECON_FILES = {"/etc/group", "/etc/passwd"}

OFFENSIVE_EXES = {
    "/usr/bin/cat", "/bin/cat",
    "/usr/bin/awk", "/bin/awk", "/usr/bin/gawk",
    "/usr/bin/ps", "/bin/ps",
    "/usr/bin/whoami", "/bin/whoami",
    "/usr/bin/id", "/bin/id",
}


def _get_audit(d: dict) -> dict:
    return ((d.get("data") or {}).get("audit") or {}) if isinstance(d, dict) else {}


def _classify(d: dict) -> str | None:
    """Return 'benign', 'attack', or None."""
    if not isinstance(d, dict):
        return None
    agent = (d.get("agent") or {}).get("name", "")
    rule = d.get("rule") or {}
    rid = rule.get("id", "")
    try:
        rid_i = int(rid)
    except (TypeError, ValueError):
        rid_i = 0
    audit = _get_audit(d)
    exe = audit.get("exe", "") or ""
    auid = audit.get("auid", "") or ""

    # Attack: STRIX custom rules, or victim + offensive exe
    if 100100 <= rid_i <= 100700:
        return "attack"
    if agent in ("victim1", "victim2") and exe in OFFENSIVE_EXES:
        return "attack"

    # Benign: explicit synthetic_benign marker
    if d.get("strix", {}).get("synthetic_benign") is True:
        return "benign"
    # Wazuh manager's own background events
    if agent == "wazuh.manager":
        return "benign"
    # Routine readonly recon: benign exe, auid != 0 (real interactive user)
    if exe in BENIGN_EXES and auid not in ("0", "", "?"):
        return "benign"
    return None


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
        "p50": float(np.percentile(finite, 50)),
        "p90": float(np.percentile(finite, 90)),
        "max": float(np.max(finite)),
        "frac_ge_0.99": float(np.mean(finite >= 0.99)),
        "frac_gt_0.01": float(np.mean(finite > 0.01)),
    }


def _print_stats(s: dict[str, Any]) -> None:
    if s.get("n", 0) == 0:
        print(f"  {s['name']:>22s}  (no data)")
        return
    print(
        f"  {s['name']:>22s}  n={s['n']:5d}  "
        f"mean={s['mean']:+8.4f}  std={s['std']:7.4f}  "
        f"p50={s['p50']:+7.3f}  p90={s['p90']:+7.3f}  max={s['max']:+7.3f}  "
        f"sat>=0.99={s['frac_ge_0.99']:.3f}  >0.01={s['frac_gt_0.01']:.3f}"
    )


def collect_sets(r: redis.Redis) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Walk the list newest-first; classify and harvest until both sets full.

    Returns (benign_docs, attack_docs, benign_examples, attack_examples).
    """
    benign: list[dict] = []
    attack: list[dict] = []
    seen_ids_b: set[str] = set()
    seen_ids_a: set[str] = set()
    total_len = r.llen(LIST_KEY)
    end = max(0, total_len - MAX_SCAN)
    # Walk newest-first in chunks (LRANGE -N..-1 gives oldest-of-tail-first;
    # we iterate chunks from tail backwards toward head)
    pos_end = -1
    pos_start = -SCAN_BATCH
    scanned = 0
    while len(benign) < TARGET_PER_SET or len(attack) < TARGET_PER_SET:
        chunk = r.lrange(LIST_KEY, pos_start, pos_end)
        if not chunk:
            break
        # Reverse so newest first
        for raw in reversed(chunk):
            scanned += 1
            try:
                d = json.loads(raw)
            except Exception:
                continue
            label = _classify(d)
            if label is None:
                continue
            uid = str(d.get("id") or d.get("_id") or scanned)
            if label == "benign" and len(benign) < TARGET_PER_SET and uid not in seen_ids_b:
                benign.append(d)
                seen_ids_b.add(uid)
            elif label == "attack" and len(attack) < TARGET_PER_SET and uid not in seen_ids_a:
                attack.append(d)
                seen_ids_a.add(uid)
            if len(benign) >= TARGET_PER_SET and len(attack) >= TARGET_PER_SET:
                break
        if scanned >= MAX_SCAN:
            break
        pos_end = pos_start - 1
        pos_start = pos_end - SCAN_BATCH + 1
        if -pos_end > total_len:
            break
    print(f"  scanned ~{scanned} of {total_len} list entries (cap {MAX_SCAN})")

    def _ex(d: dict) -> dict:
        au = _get_audit(d)
        return {
            "agent": (d.get("agent") or {}).get("name"),
            "rule_id": (d.get("rule") or {}).get("id"),
            "exe": au.get("exe"),
            "auid": au.get("auid"),
        }

    return benign, attack, [_ex(x) for x in benign[:3]], [_ex(x) for x in attack[:3]]


def transform_set(docs: list[dict], pipe, label: str) -> list[dict[str, Any]]:
    adapter = WazuhAlertAdapter()
    out: list[dict[str, Any]] = []
    skipped = 0
    for d in docs:
        try:
            alert = adapter.parse(d)
            vec = pipe.transform(alert)
            out.append(
                {
                    "alert_id": alert.alert_id,
                    "agent_id": alert.agent.agent_id,
                    "occurred_at": alert.occurred_at,
                    "srcuser": alert.data.srcuser,
                    "srcip": alert.data.srcip,
                    "feature_vector": vec.astype(np.float32),
                }
            )
        except Exception as e:  # noqa: BLE001
            skipped += 1
            if skipped <= 3:
                print(f"    [{label}] parse_skip: {e}", file=sys.stderr)
    print(f"    [{label}] normalized={len(out)} skipped={skipped}")
    return out


def score(events: list[dict], pipe, ae, vae, transformer, gnn, label: str) -> dict[str, Any]:
    if not events:
        return {"label": label, "n": 0}
    X = np.stack([e["feature_vector"] for e in events], axis=0).astype(np.float32)
    BS = 64

    ae_recon: list[float] = []
    ae_latents: list[np.ndarray] = []
    for i in range(0, X.shape[0], BS):
        out = ae.batch_forward(X[i : i + BS])
        ae_recon.extend(out.recon_error.tolist())
        for j in range(out.batch_size):
            ae_latents.append(out.latents[j])

    vae_prob: list[float] = []
    for i in range(0, X.shape[0], BS):
        out = vae.batch_forward(X[i : i + BS])
        vae_prob.extend(out.malicious_prob.tolist())

    pred_ckc: list[int] = []
    for lat in ae_latents:
        seq = np.expand_dims(lat, 0).astype(np.float32)
        out = transformer.predict_sequence(seq)
        pred_ckc.append(int(out.pred_ckc))

    facts: list[NodeFact] = []
    for e in events:
        gnn_perm = pipe.transform_for_gnn(e["feature_vector"])
        facts.append(
            NodeFact(
                alert_id=e["alert_id"],
                agent_id=e["agent_id"],
                occurred_at=e["occurred_at"],
                srcuser=e["srcuser"],
                srcip=e["srcip"],
                features_gnn_order=gnn_perm,
            )
        )
    snap = build_snapshot(facts)
    gnn_out = gnn.score_graph(snap.x, snap.edge_index)
    gnn_risk = np.asarray(gnn_out.risks, dtype=np.float32)

    return {
        "label": label,
        "n": X.shape[0],
        "ae_recon": np.asarray(ae_recon, dtype=np.float32),
        "vae_prob": np.asarray(vae_prob, dtype=np.float32),
        "pred_ckc": np.asarray(pred_ckc, dtype=np.int32),
        "gnn_risk": gnn_risk,
        "snapshot": (snap.num_nodes, snap.num_edges),
    }


def main() -> None:
    print("=" * 90)
    print("STRIX BENIGN vs ATTACK smoke (post-fix pipeline, read-only)")
    print("=" * 90)

    r = redis.Redis.from_url(REDIS_URL)
    print(f"\n[1] Sourcing two sets from {LIST_KEY} @ {REDIS_URL}")
    benign_docs, attack_docs, ben_ex, atk_ex = collect_sets(r)
    print(f"    Set A (benign):  {len(benign_docs)}")
    print(f"    Set B (attack):  {len(attack_docs)}")
    print("    sample benign:")
    for x in ben_ex:
        print(f"      {x}")
    print("    sample attack:")
    for x in atk_ex:
        print(f"      {x}")

    print("\n[2] Building post-fix pipeline ...")
    pipe = build_pipeline(MODELS_DIR, warmup=False)
    print(f"    gnn.threshold={float(pipe.gnn.threshold):.4f}  scaler_n_in={int(pipe.gnn.scaler_55.n_features_in_)}")

    print("\n[3] Loading model loaders ...")
    state = load_registry(MODELS_DIR / "registry.json", MODELS_DIR, verify_checksums=False)
    ae = AutoencoderLoader.load(state.models["ae"].file, version=state.models["ae"].version)
    vae = VaeLoader.load(
        state.models["vae"].file,
        calibrator=pipe.calibrators.active,
        version=state.models["vae"].version,
    )
    gnn = GnnLoader.load(state.models["gnn"].file, metadata=pipe.gnn, version=state.models["gnn"].version)
    transformer = TransformerLoader.load(state.models["transformer"].file, version=state.models["transformer"].version)
    print(f"    ae={ae.version} vae={vae.version} gnn={gnn.version} transformer={transformer.version}")

    print("\n[4] Normalizing Set A ...")
    ben_events = transform_set(benign_docs, pipe, "BENIGN")
    print("\n[4] Normalizing Set B ...")
    atk_events = transform_set(attack_docs, pipe, "ATTACK")

    print("\n[5] Scoring ...")
    bres = score(ben_events, pipe, ae, vae, transformer, gnn, "BENIGN")
    ares = score(atk_events, pipe, ae, vae, transformer, gnn, "ATTACK")

    print("\n" + "=" * 90)
    print("DISTRIBUTION COMPARISON")
    print("=" * 90)
    for lbl, res in [("BENIGN (Set A)", bres), ("ATTACK (Set B)", ares)]:
        print(f"\n--- {lbl}  n={res.get('n')}  snapshot={res.get('snapshot')} ---")
        if res.get("n", 0) == 0:
            continue
        _print_stats(_stats("ae_recon_error", res["ae_recon"]))
        _print_stats(_stats("vae_malicious_prob", res["vae_prob"]))
        _print_stats(_stats("gnn_node_risk", res["gnn_risk"]))
        cnt = Counter(res["pred_ckc"].tolist())
        print(f"    transformer pred_ckc: {dict(sorted(cnt.items()))}  distinct={len(cnt)}")

    print("\n" + "=" * 90)
    print("HEAD-TO-HEAD TABLE")
    print("=" * 90)

    def fmt(arr, key):
        a = np.asarray(arr, dtype=np.float64)
        a = a[np.isfinite(a)]
        if a.size == 0:
            return "n/a"
        if key == "mean_std":
            return f"{a.mean():.4f} / {a.std():.4f}"
        if key == "ge99":
            return f"{(a >= 0.99).mean():.3f}"
        if key == "mean_gt01":
            return f"mean={a.mean():.4f}  >0.01={(a > 0.01).mean():.3f}"
        return ""

    rows = [
        ("ae_recon_error mean / std",
         fmt(bres.get("ae_recon", []), "mean_std"),
         fmt(ares.get("ae_recon", []), "mean_std")),
        ("vae_malicious_prob mean / std",
         fmt(bres.get("vae_prob", []), "mean_std"),
         fmt(ares.get("vae_prob", []), "mean_std")),
        ("vae_malicious_prob frac >= 0.99",
         fmt(bres.get("vae_prob", []), "ge99"),
         fmt(ares.get("vae_prob", []), "ge99")),
        ("gnn_node_risk mean / frac>0.01",
         fmt(bres.get("gnn_risk", []), "mean_gt01"),
         fmt(ares.get("gnn_risk", []), "mean_gt01")),
    ]
    print(f"  {'metric':<40s} {'Set A (benign)':<28s} {'Set B (attack)':<28s}")
    for name, av, bv in rows:
        print(f"  {name:<40s} {av:<28s} {bv:<28s}")

    print("\n  transformer pred_ckc histograms (BENIGN | ATTACK):")
    bcnt = Counter(bres.get("pred_ckc", np.array([])).tolist()) if bres.get("n", 0) else Counter()
    acnt = Counter(ares.get("pred_ckc", np.array([])).tolist()) if ares.get("n", 0) else Counter()
    for stage in range(8):
        print(f"    stage {stage}:  benign={bcnt.get(stage, 0):4d}   attack={acnt.get(stage, 0):4d}")

    print("\n" + "=" * 90)
    print("VERDICT INPUTS")
    print("=" * 90)
    if bres.get("n", 0):
        bsat = float((bres["vae_prob"] >= 0.99).mean())
        bmean = float(bres["vae_prob"].mean())
        print(f"  BENIGN vae sat>=0.99 = {bsat:.3f}  mean = {bmean:.3f}")
    if ares.get("n", 0):
        asat = float((ares["vae_prob"] >= 0.99).mean())
        amean = float(ares["vae_prob"].mean())
        print(f"  ATTACK vae sat>=0.99 = {asat:.3f}  mean = {amean:.3f}")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
