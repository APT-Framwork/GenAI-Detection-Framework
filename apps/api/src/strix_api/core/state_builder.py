"""13-dim state vector assembler for the DQN.

The vector is fixed-shape — fed as-is to `QNetwork.network[0]` (Linear in 13).
Element ordering matches the upstream `APTEnvironment._get_observation()`
(rl_apt_system/env/apt_env.py) extended with 3 GNN features (§3.5):

   index  | feature                              | range / units
   -------+--------------------------------------+--------------------------
   0      | ae_anomaly_score                     | [0, 10]   clipped
   1      | ae_recon_error                       | [0, 10]   clipped
   2      | vae_malicious_prob                   | [0, 1]
   3      | vae_uncertainty                      | [0, 10]   clipped
   4      | transformer_pred_ckc                 | [0, 7]    integer cast to float
   5      | transformer_confidence               | [0, 1]
   6      | current_ckc_stage                    | [0, 7]    last observed CKC stage
   7      | time_since_first_event_hours         | [0, 10]   clipped
   8      | time_since_last_event_minutes        | [0, 10]   clipped
   9      | sequence_length_so_far               | [0, 50]   integer cast to float
   10     | gnn_node_risk                        | [0, 1]
   11     | gnn_neighbor_risk                    | [0, 1]
   12     | gnn_risk_growth                      | [-1, 1]   delta of mean risk

Pure-domain — takes typed inputs, returns a `(13,) float32` array. The
inference worker calls this once per step before the DQN forward pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

import numpy as np

from strix_api.core.constants import CHAIN_MAX_STEPS, STATE_VECTOR_DIM

# Per-element clip bounds — mirrors APTEnvironment.observation_space.
_LOW: Final[np.ndarray] = np.array(
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0, 0.0, -1.0],
    dtype=np.float32,
)
_HIGH: Final[np.ndarray] = np.array(
    [10, 10, 1, 10, 7, 1, 7, 10, 10, float(CHAIN_MAX_STEPS), 1.0, 1.0, 1.0],
    dtype=np.float32,
)

# Index labels — useful for debug logs + the OpenAPI doc on state_vector.
STATE_FEATURES: Final[tuple[str, ...]] = (
    "ae_anomaly_score",
    "ae_recon_error",
    "vae_malicious_prob",
    "vae_uncertainty",
    "transformer_pred_ckc",
    "transformer_confidence",
    "current_ckc_stage",
    "time_since_first_event_hours",
    "time_since_last_event_minutes",
    "sequence_length_so_far",
    "gnn_node_risk",
    "gnn_neighbor_risk",
    "gnn_risk_growth",
)
assert len(STATE_FEATURES) == STATE_VECTOR_DIM  # static contract


@dataclass(frozen=True)
class ModelOutputs:
    """Per-alert detection signals from AE / VAE / Transformer / GNN.

    Workers pass these in raw (no clipping); `build_state` does all bounds
    enforcement so the DQN never sees out-of-range values.
    """

    ae_anomaly_score: float
    ae_recon_error: float
    vae_malicious_prob: float
    vae_uncertainty: float
    transformer_pred_ckc: int
    transformer_confidence: float
    current_ckc_stage: int
    gnn_node_risk: float
    gnn_neighbor_risk: float
    gnn_risk_growth: float


def build_state(
    *,
    outputs: ModelOutputs,
    occurred_at: datetime,
    episode_start_at: datetime,
    last_event_at: datetime | None,
    sequence_length_so_far: int,
) -> np.ndarray:
    """Assemble the 13-dim state vector. Result is clipped to bounds."""
    time_since_first_hours = max(0.0, (occurred_at - episode_start_at).total_seconds() / 3600.0)
    if last_event_at is None:
        time_since_last_min = 0.0
    else:
        time_since_last_min = max(0.0, (occurred_at - last_event_at).total_seconds() / 60.0)

    raw = np.array(
        [
            outputs.ae_anomaly_score,
            outputs.ae_recon_error,
            outputs.vae_malicious_prob,
            outputs.vae_uncertainty,
            float(outputs.transformer_pred_ckc),
            outputs.transformer_confidence,
            float(outputs.current_ckc_stage),
            time_since_first_hours,
            time_since_last_min,
            float(sequence_length_so_far),
            outputs.gnn_node_risk,
            outputs.gnn_neighbor_risk,
            outputs.gnn_risk_growth,
        ],
        dtype=np.float32,
    )
    return np.clip(raw, _LOW, _HIGH)


__all__ = ["ModelOutputs", "STATE_FEATURES", "build_state"]
