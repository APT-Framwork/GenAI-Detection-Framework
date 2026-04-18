"""GNN loader (APTPropagationGNN).

§5.10 fix applied: threshold comes from the metadata pickle (no hardcoded
0.918 fallback). Threshold is exposed but the live 13-d state pipeline uses
raw sigmoid risks per cell-11 of the GNN notebook (Part 3 RL features).

The graph builder (rolling 60-min sliding window over recent alerts) lives
in `core/gnn_window.py` (Phase 2 P2-4). This loader is graph-shape-agnostic
— pass any (x, edge_index) and it returns alert risks.

Public API:
    loader = GnnLoader.load(path, metadata=pipe.gnn)
    risks  = loader.score_graph(x_55_perm, edge_index)   # (N,) sigmoid in [0,1]
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from strix_api.adapters.model_loaders._arch import APTPropagationGNN
from strix_api.adapters.preprocessing_pipeline import GnnMetadata
from strix_api.api.errors import ModelRegistryError
from strix_api.core.constants import FEATURE_VECTOR_DIM
from strix_api.observability import get_logger

log = get_logger("strix_api.adapters.model_loaders.gnn")


@dataclass(frozen=True)
class GnnScoreOutput:
    """Per-node risks. The inference worker aggregates these into the 3 GNN
    features (`node_risk`, `neighbor_risk`, `risk_growth`) of the 13-d state.
    """

    risks: np.ndarray             # (N,) sigmoid in [0,1] — one per alert/node
    threshold: float              # decision threshold from the metadata pickle


class GnnLoader:
    """APTPropagationGNN wrapper. Stateless except for model weights."""

    def __init__(
        self,
        model: APTPropagationGNN,
        *,
        metadata: GnnMetadata,
        device: torch.device,
        version: str,
    ) -> None:
        self._model = model
        self.metadata = metadata
        self._device = device
        self.version = version

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        metadata: GnnMetadata,
        expected_input_dim: int = FEATURE_VECTOR_DIM,
        device: str = "cpu",
        version: str = "v1",
    ) -> GnnLoader:
        if not path.exists():
            raise ModelRegistryError(f"GNN checkpoint missing: {path}")

        dev = torch.device(device)
        sd = torch.load(path, map_location=dev, weights_only=False)
        if isinstance(sd, dict) and "model_state_dict" in sd:
            sd = sd["model_state_dict"]
        if isinstance(sd, dict) and "state_dict" in sd:
            sd = sd["state_dict"]

        # Detect input width from convs.0.lin_l.weight or convs.0.lin_r.weight
        # (SAGEConv has separate L/R linear layers). Either tells us in_ch.
        in_ch = None
        for key in ("convs.0.lin_l.weight", "convs.0.lin_r.weight"):
            w = sd.get(key)
            if w is not None:
                in_ch = w.shape[1]
                break
        if in_ch is None:
            raise ModelRegistryError(
                "GNN state_dict missing convs.0 weights — wrong architecture? "
                "(expected APTPropagationGNN with SAGEConv)"
            )
        if in_ch != expected_input_dim:
            raise ModelRegistryError(
                f"GNN in_ch={in_ch}, expected {expected_input_dim}"
            )

        # Number of conv layers: count keys like convs.{i}.lin_l.weight
        layer_count = sum(1 for k in sd if k.startswith("convs.") and k.endswith(".lin_l.weight"))
        if layer_count == 0:
            layer_count = sum(1 for k in sd if k.startswith("convs.") and k.endswith(".lin_r.weight"))
        if layer_count == 0:
            raise ModelRegistryError("could not infer GNN layer count from state_dict")

        model = APTPropagationGNN(in_ch=in_ch, hid=128, layers=layer_count, drop=0.3)
        model.load_state_dict(sd, strict=True)
        model.to(dev).eval()

        log.info(
            "gnn_loaded",
            path=str(path),
            in_ch=in_ch,
            layers=layer_count,
            threshold=metadata.threshold,
            version=version,
            device=str(dev),
        )

        loader = cls(model, metadata=metadata, device=dev, version=version)
        loader._warmup()
        return loader

    @torch.inference_mode()
    def score_graph(
        self, x: np.ndarray, edge_index: np.ndarray
    ) -> GnnScoreOutput:
        """Run the GNN on a graph snapshot.

        Args:
            x: (N, 55) float32 — node features in GNN's alphabetical SecBERT order
               (use `PreprocessingPipeline.transform_for_gnn(scaled_canonical)` per node)
            edge_index: (2, E) int64 — directed edges (PyG convention; include
               self-loops if you want them)
        """
        if x.ndim != 2 or x.shape[1] != FEATURE_VECTOR_DIM:
            raise ValueError(
                f"GNN expects x shape (N, {FEATURE_VECTOR_DIM}), got {x.shape}"
            )
        if edge_index.ndim != 2 or edge_index.shape[0] != 2:
            raise ValueError(
                f"GNN expects edge_index shape (2, E), got {edge_index.shape}"
            )

        x_t = torch.from_numpy(x.astype(np.float32, copy=False)).to(self._device)
        ei_t = torch.from_numpy(edge_index.astype(np.int64, copy=False)).to(self._device)

        logits = self._model(x_t, ei_t)           # (N,)
        risks = torch.sigmoid(logits).cpu().numpy().astype(np.float32, copy=False)
        return GnnScoreOutput(risks=risks, threshold=self.metadata.threshold)

    def _warmup(self) -> None:
        # Tiny graph: 2 nodes with a self-loop each. Triggers the SAGEConv
        # message-passing JIT path so the first real graph doesn't pay the cost.
        x = np.zeros((2, FEATURE_VECTOR_DIM), dtype=np.float32)
        edge_index = np.array([[0, 1], [0, 1]], dtype=np.int64)
        self.score_graph(x, edge_index)


__all__ = ["GnnLoader", "GnnScoreOutput"]
