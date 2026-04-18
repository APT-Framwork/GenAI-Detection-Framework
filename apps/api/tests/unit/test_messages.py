"""Wire message Pydantic models — round-trip + dimension guards."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from strix_api.core.constants import (
    AE_LATENT_DIM,
    DQN_ACTION_SPACE,
    FEATURE_VECTOR_DIM,
    STATE_VECTOR_DIM,
)
from strix_api.core.messages import FeatureMessage, RawAlertMessage, VerdictMessage


def test_feature_message_roundtrip_via_camelcase() -> None:
    msg = FeatureMessage(
        alert_id="abc",
        agent_id="001",
        host_id=uuid4(),
        occurred_at="2026-04-17T09:00:00.000000+00:00",
        feature_vector=[0.0] * FEATURE_VECTOR_DIM,
    )
    # Outgoing wire format is camelCase
    dumped = msg.model_dump(mode="json", by_alias=True)
    assert "alertId" in dumped
    assert "featureVector" in dumped
    assert "hostId" in dumped
    assert "schemaVersion" in dumped

    # Round-trip
    msg2 = FeatureMessage.model_validate(dumped)
    assert msg2.alert_id == "abc"
    assert len(msg2.feature_vector) == FEATURE_VECTOR_DIM


def test_feature_vector_must_be_exactly_55() -> None:
    with pytest.raises(ValidationError):
        FeatureMessage(
            alert_id="x",
            agent_id="1",
            host_id=uuid4(),
            occurred_at="2026-04-17T09:00:00Z",
            feature_vector=[0.0] * (FEATURE_VECTOR_DIM - 1),
        )
    with pytest.raises(ValidationError):
        FeatureMessage(
            alert_id="x",
            agent_id="1",
            host_id=uuid4(),
            occurred_at="2026-04-17T09:00:00Z",
            feature_vector=[0.0] * (FEATURE_VECTOR_DIM + 1),
        )


def test_verdict_message_dim_constraints() -> None:
    chain_id = uuid4()
    msg = VerdictMessage(
        alert_id="a",
        chain_id=chain_id,
        step_in_chain=0,
        occurred_at="2026-04-17T09:00:00Z",
        ae_anomaly_score=0.1,
        ae_recon_error=0.2,
        ae_latent=[0.0] * AE_LATENT_DIM,
        vae_malicious_prob=0.05,
        vae_uncertainty=0.3,
        transformer_pred_ckc=3,
        transformer_confidence=0.7,
        gnn_node_risk=0.4,
        gnn_neighbor_risk=0.2,
        gnn_risk_growth=0.01,
        state_vector=[0.0] * STATE_VECTOR_DIM,
        dqn_action=0,
        dqn_action_name="MONITOR",
        q_values=[0.0] * DQN_ACTION_SPACE,
        model_versions={"ae": "v1"},
    )
    assert msg.dqn_action == 0
    assert len(msg.state_vector) == STATE_VECTOR_DIM
    assert len(msg.q_values) == DQN_ACTION_SPACE


def test_dqn_action_rejects_out_of_range() -> None:
    with pytest.raises(ValidationError):
        VerdictMessage(
            alert_id="a",
            chain_id=uuid4(),
            step_in_chain=0,
            occurred_at="2026-04-17T09:00:00Z",
            ae_anomaly_score=0,
            ae_recon_error=0,
            ae_latent=[0.0] * AE_LATENT_DIM,
            vae_malicious_prob=0,
            vae_uncertainty=0,
            transformer_pred_ckc=0,
            transformer_confidence=0,
            gnn_node_risk=0,
            gnn_neighbor_risk=0,
            gnn_risk_growth=0,
            state_vector=[0.0] * STATE_VECTOR_DIM,
            dqn_action=DQN_ACTION_SPACE,  # out of range
            dqn_action_name="MONITOR",
            q_values=[0.0] * DQN_ACTION_SPACE,
            model_versions={},
        )


def test_raw_alert_message_has_ingested_at_default() -> None:
    msg = RawAlertMessage(alert_id="x", raw_json={"some": "thing"})
    assert msg.alert_id == "x"
    assert "T" in msg.ingested_at  # ISO-8601
