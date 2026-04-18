#!/usr/bin/env python3
"""Derive apps/models/standard_scaler.pkl from gnn_metadata.pkl.

Rationale (see apps/models/registry.json → preprocessingArtifacts.standard_scaler):
`StandardScaler` stores per-column `mean_` and `scale_` that are functions of
the training data only — not of column order. So if we have a scaler fit on
the 55 Top-25 columns under one ordering, we can derive the scaler for the
same columns under a different ordering by permuting those arrays.

gnn_metadata.pkl has:
  - features: list[55] in the GNN's alphabetical SecBERT order
  - scaler:   StandardScaler(n_features_in_=56)  ← 55 Top-25 cols + rule_level
              (Part-2 retraining slices X_scaled[:, :-1] and never refits.)

We slice the first 55 entries and re-permute them into the AE/VAE numeric
SecBERT order (selected_features_top25.json all_selected_columns).

Usage:
    python infra/scripts/derive_standard_scaler.py
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO_ROOT / "apps" / "models"

GNN_META_PATH = MODELS_DIR / "gnn_metadata.pkl"
FEATURES_JSON_PATH = MODELS_DIR / "selected_features_top25.json"
OUT_PATH = MODELS_DIR / "standard_scaler.pkl"


def main() -> int:
    if not GNN_META_PATH.exists():
        print(f"ERROR: {GNN_META_PATH} not found", file=sys.stderr)
        return 1
    if not FEATURES_JSON_PATH.exists():
        print(f"ERROR: {FEATURES_JSON_PATH} not found", file=sys.stderr)
        return 1

    gnn = pickle.load(GNN_META_PATH.open("rb"))
    info = json.load(FEATURES_JSON_PATH.open())

    gnn_features: list[str] = list(gnn["features"])
    canonical_order: list[str] = info["all_selected_columns"]

    if len(gnn_features) != 55:
        print(f"ERROR: gnn.features has {len(gnn_features)} entries, expected 55", file=sys.stderr)
        return 1
    if len(canonical_order) != 55:
        print(f"ERROR: canonical_order has {len(canonical_order)} entries, expected 55", file=sys.stderr)
        return 1

    # Confirm both orderings contain the same 55 col names.
    if set(gnn_features) != set(canonical_order):
        diff_gnn_only = set(gnn_features) - set(canonical_order)
        diff_canon_only = set(canonical_order) - set(gnn_features)
        print("ERROR: gnn_metadata.features and selected_features_top25 disagree on the 55-col set:")
        print(f"  only in gnn_metadata:            {sorted(diff_gnn_only)}")
        print(f"  only in selected_features_top25: {sorted(diff_canon_only)}")
        return 1

    # Build permutation: for each col in canonical_order, find its index in gnn_features.
    perm = np.array([gnn_features.index(c) for c in canonical_order], dtype=np.int64)
    assert perm.shape == (55,)

    src = gnn["scaler"]
    # Sanity: the GNN scaler should be 56-dim (55 Top-25 + rule_level).
    assert src.n_features_in_ == 56, f"expected 56-dim scaler, got {src.n_features_in_}"

    # Slice to first 55 (drop rule_level), then permute into canonical order.
    mean_55 = src.mean_[:55][perm]
    scale_55 = src.scale_[:55][perm]
    var_55 = src.var_[:55][perm]

    out = StandardScaler()
    out.mean_ = mean_55.astype(np.float64)
    out.scale_ = scale_55.astype(np.float64)
    out.var_ = var_55.astype(np.float64)
    out.n_features_in_ = 55
    out.feature_names_in_ = np.array(canonical_order, dtype=object)
    # n_samples_seen_: copy from source; the scaler doesn't use it at transform time
    # but some sklearn checks expect it.
    if hasattr(src, "n_samples_seen_"):
        out.n_samples_seen_ = src.n_samples_seen_
    out.with_mean = True
    out.with_std = True
    out.copy = True

    # Round-trip sanity: create a random 55-col row, transform it, and verify
    # per-column z = (x - mean) / scale.
    rng = np.random.default_rng(0)
    x = rng.standard_normal((3, 55)).astype(np.float64)
    z_actual = out.transform(x)
    z_expected = (x - out.mean_) / out.scale_
    assert np.allclose(z_actual, z_expected), "derived scaler transform inconsistent"

    with OUT_PATH.open("wb") as f:
        pickle.dump(out, f)

    print(f"✅ wrote {OUT_PATH.relative_to(REPO_ROOT)}")
    print(f"   n_features_in_ : 55")
    print(f"   ordering       : selected_features_top25.json (numeric SecBERT)")
    print(f"   first 5 means  : {out.mean_[:5]}")
    print(f"   first 5 scales : {out.scale_[:5]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
