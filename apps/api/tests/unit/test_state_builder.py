"""13-dim state-vector assembler — bounds + ordering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from strix_api.core.constants import STATE_VECTOR_DIM
from strix_api.core.state_builder import STATE_FEATURES, ModelOutputs, build_state


def _outputs(**overrides: float) -> ModelOutputs:
    base = dict(
        ae_anomaly_score=1.0, ae_recon_error=0.5,
        vae_malicious_prob=0.3, vae_uncertainty=0.2,
        transformer_pred_ckc=2, transformer_confidence=0.7,
        current_ckc_stage=1, gnn_node_risk=0.4,
        gnn_neighbor_risk=0.2, gnn_risk_growth=0.05,
    )
    base.update(overrides)
    return ModelOutputs(**base)  # type: ignore[arg-type]


def test_state_has_13_dimensions() -> None:
    s = build_state(
        outputs=_outputs(),
        occurred_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
        episode_start_at=datetime(2026, 4, 18, 11, 30, 0, tzinfo=timezone.utc),
        last_event_at=datetime(2026, 4, 18, 11, 50, 0, tzinfo=timezone.utc),
        sequence_length_so_far=4,
    )
    assert s.shape == (STATE_VECTOR_DIM,)
    assert s.dtype == np.float32
    assert len(STATE_FEATURES) == STATE_VECTOR_DIM


def test_state_ordering_matches_features_table() -> None:
    s = build_state(
        outputs=_outputs(
            ae_anomaly_score=1.5, ae_recon_error=0.6,
            vae_malicious_prob=0.4, vae_uncertainty=0.3,
            transformer_pred_ckc=3, transformer_confidence=0.8,
            current_ckc_stage=2, gnn_node_risk=0.5,
            gnn_neighbor_risk=0.25, gnn_risk_growth=0.1,
        ),
        occurred_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
        episode_start_at=datetime(2026, 4, 18, 11, 0, 0, tzinfo=timezone.utc),
        last_event_at=datetime(2026, 4, 18, 11, 55, 0, tzinfo=timezone.utc),
        sequence_length_so_far=7,
    )
    assert s[0] == 1.5
    assert s[1] == 0.6
    assert s[2] == 0.4
    assert s[3] == 0.3
    assert s[4] == 3.0
    assert s[5] == 0.8
    assert s[6] == 2.0
    # time_since_first = 1h
    assert s[7] == 1.0
    # time_since_last = 5min
    assert s[8] == 5.0
    assert s[9] == 7.0
    assert s[10] == 0.5
    assert s[11] == 0.25
    assert abs(s[12] - 0.1) < 1e-6


def test_clipping_to_observation_bounds() -> None:
    s = build_state(
        outputs=_outputs(
            ae_anomaly_score=999.0,        # clipped to 10
            ae_recon_error=-5.0,           # clipped to 0
            vae_malicious_prob=2.0,        # clipped to 1
            vae_uncertainty=42.0,          # clipped to 10
            transformer_pred_ckc=99,       # clipped to 7
            transformer_confidence=-1.0,   # clipped to 0
            current_ckc_stage=99,          # clipped to 7
            gnn_node_risk=2.0,             # clipped to 1
            gnn_neighbor_risk=-0.5,        # clipped to 0
            gnn_risk_growth=2.5,           # clipped to 1
        ),
        occurred_at=datetime(2026, 4, 18, 23, 59, 59, tzinfo=timezone.utc),
        episode_start_at=datetime(2026, 4, 18, 0, 0, 0, tzinfo=timezone.utc),
        last_event_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
        sequence_length_so_far=200,        # clipped to CHAIN_MAX_STEPS=50
    )
    assert s[0] == 10.0
    assert s[1] == 0.0
    assert s[2] == 1.0
    assert s[3] == 10.0
    assert s[4] == 7.0
    assert s[5] == 0.0
    assert s[6] == 7.0
    assert s[7] == 10.0   # 24h → clipped to 10
    assert s[8] == 10.0
    assert s[9] == 50.0
    assert s[10] == 1.0
    assert s[11] == 0.0
    assert s[12] == 1.0


def test_first_step_has_no_last_event() -> None:
    s = build_state(
        outputs=_outputs(),
        occurred_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
        episode_start_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
        last_event_at=None,
        sequence_length_so_far=0,
    )
    assert s[8] == 0.0   # time_since_last
    assert s[9] == 0.0   # sequence_length
