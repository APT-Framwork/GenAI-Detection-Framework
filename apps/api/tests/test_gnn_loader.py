"""Workstream 2 / Phase E — GNN loader threshold + filename wiring.

Asserts that the build pipeline:
  * picks up ``apps/models/preprocess/gnn_propagation_metadata.pkl`` (Phase A)
  * yields threshold 0.7743 (NOT the legacy 0.918 from Part-1)
  * passes a clean 55-col scaler (no slicing artefacts)
  * the GNN forward pass on synthetic graph snapshots produces deterministic
    risks within [0,1] and the in_ch matches 55.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = REPO_ROOT / "apps" / "models"


@pytest.mark.skipif(
    not (MODELS_DIR / "preprocess" / "gnn_propagation_metadata.pkl").exists(),
    reason="Phase A propagation metadata missing",
)
def test_pipeline_uses_phase_a_gnn_metadata_with_threshold_7743() -> None:
    from strix_api.adapters.preprocessing_pipeline import build_pipeline

    pipe = build_pipeline(MODELS_DIR, warmup=False)
    assert abs(pipe.gnn.threshold - 0.7743) < 1e-4, (
        f"GNN threshold should be 0.7743 (Part-2 NO RULE LEVEL); got {pipe.gnn.threshold}"
    )
    assert pipe.gnn.scaler_55.n_features_in_ == 55
    assert len(pipe.gnn.features) == 55
    assert pipe.gnn.rule_level_included is False


def _has_torch_geometric() -> bool:
    try:
        import torch_geometric  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not (MODELS_DIR / "gnn_model.pth").exists()
    or not (MODELS_DIR / "preprocess" / "gnn_propagation_metadata.pkl").exists()
    or not _has_torch_geometric(),
    reason="GNN checkpoint, Phase A metadata, or torch_geometric missing",
)
def test_gnn_loader_in_ch_is_55_and_forward_runs_on_snapshots() -> None:
    """50 synthetic graph snapshots; assert risks are in [0,1] and deterministic."""
    from strix_api.adapters.model_loaders.gnn import GnnLoader
    from strix_api.adapters.preprocessing_pipeline import build_pipeline

    pipe = build_pipeline(MODELS_DIR, warmup=False)
    loader = GnnLoader.load(
        MODELS_DIR / "gnn_model.pth",
        metadata=pipe.gnn,
        version="test",
    )

    rng = np.random.default_rng(seed=42)
    all_risks: list[np.ndarray] = []
    for _ in range(50):
        n_nodes = int(rng.integers(3, 12))
        x = rng.standard_normal((n_nodes, 55)).astype(np.float32)
        # random directed edges + self-loops
        n_edges = max(n_nodes, int(rng.integers(n_nodes, n_nodes * 3)))
        src = rng.integers(0, n_nodes, size=n_edges)
        dst = rng.integers(0, n_nodes, size=n_edges)
        edge_index = np.stack([src, dst], axis=0).astype(np.int64)
        out = loader.score_graph(x, edge_index)
        assert out.risks.shape == (n_nodes,)
        assert ((out.risks >= 0.0) & (out.risks <= 1.0)).all()
        assert abs(out.threshold - 0.7743) < 1e-4
        all_risks.append(out.risks)

    # Determinism: run a fixed snapshot twice and compare bit-exact.
    x = rng.standard_normal((6, 55)).astype(np.float32)
    edge_index = np.array([[0, 1, 2, 3, 4, 5, 0, 1], [1, 2, 3, 4, 5, 0, 0, 1]], dtype=np.int64)
    r1 = loader.score_graph(x, edge_index).risks
    r2 = loader.score_graph(x, edge_index).risks
    np.testing.assert_allclose(r1, r2, atol=1e-6)
