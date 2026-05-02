"""Chain lifecycle decisions (§5.4 + §12 Q2/Q5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from strix_api.core.constants import (
    CHAIN_IDLE_TIMEOUT_MINUTES,
    CHAIN_MAX_STEPS,
    CHAIN_OPEN_AE_THRESHOLD,
    CHAIN_OPEN_GNN_THRESHOLD,
    CHAIN_OPEN_VAE_THRESHOLD,
)
from strix_api.core.enums import DqnAction
from strix_api.core.sequence import (
    ChainAction,
    ChainCloseReason,
    decide_chain_action,
    decide_close_reason,
)
from strix_api.core.session import SessionState

_NOW = datetime(2026, 4, 18, 12, 0, 0, tzinfo=UTC)


def _session(
    *,
    last_seen_minutes_ago: int = 0,
    step_count: int = 1,
    last_action: int | None = 0,
    max_vae_prob: float = 0.0,
    max_ckc_stage: int = 0,
) -> SessionState:
    last_seen = _NOW - timedelta(minutes=last_seen_minutes_ago)
    return SessionState(
        chain_id=uuid4(),
        episode_start_at=last_seen - timedelta(minutes=10),
        opened_at=last_seen - timedelta(minutes=10),
        last_seen_at=last_seen,
        step_count=step_count,
        last_ckc_stage=None,
        last_action=last_action,
        max_vae_prob=max_vae_prob,
        max_ckc_stage=max_ckc_stage,
    )


# ---- decide_chain_action ----------------------------------------------


def test_skip_benign_when_below_thresholds_and_no_session() -> None:
    decision = decide_chain_action(
        session=None,
        ae_anomaly=0.1,
        vae_malicious_prob=0.1,
        gnn_node_risk=0.0,
        occurred_at=_NOW,
    )
    assert decision.action is ChainAction.SKIP_BENIGN
    assert decision.chain_id is None
    assert not decision.runs_full_pipeline


def test_open_new_when_gnn_threshold_met() -> None:
    decision = decide_chain_action(
        session=None,
        ae_anomaly=0.0,
        vae_malicious_prob=0.0,
        gnn_node_risk=CHAIN_OPEN_GNN_THRESHOLD + 0.01,
        occurred_at=_NOW,
    )
    assert decision.action is ChainAction.OPEN_NEW
    assert decision.chain_id is not None
    assert decision.is_first_in_chain
    assert decision.runs_full_pipeline


def test_high_ae_vae_low_gnn_skips_benign() -> None:
    """Inversion guard: AE/VAE saturating must NOT open a chain on its own.
    This is the symptom we saw on rule-80789 (benign vae≈1.0)."""
    decision = decide_chain_action(
        session=None,
        ae_anomaly=10.0,
        vae_malicious_prob=1.0,
        gnn_node_risk=0.0,
        occurred_at=_NOW,
    )
    assert decision.action is ChainAction.SKIP_BENIGN


def test_low_ae_vae_high_gnn_opens_new() -> None:
    """Mirror: pure GNN signal must open even when AE/VAE are quiet."""
    decision = decide_chain_action(
        session=None,
        ae_anomaly=0.0,
        vae_malicious_prob=0.0,
        gnn_node_risk=CHAIN_OPEN_GNN_THRESHOLD + 0.05,
        occurred_at=_NOW,
    )
    assert decision.action is ChainAction.OPEN_NEW


def test_all_low_skips_benign() -> None:
    decision = decide_chain_action(
        session=None,
        ae_anomaly=0.0,
        vae_malicious_prob=0.0,
        gnn_node_risk=0.0,
        occurred_at=_NOW,
    )
    assert decision.action is ChainAction.SKIP_BENIGN


def test_continue_when_session_open_and_within_idle_window() -> None:
    session = _session(last_seen_minutes_ago=5, step_count=3, last_action=DqnAction.MONITOR.value)
    decision = decide_chain_action(
        session=session,
        ae_anomaly=0.0,
        vae_malicious_prob=0.0,
        gnn_node_risk=0.0,
        occurred_at=_NOW,
    )
    assert decision.action is ChainAction.CONTINUE
    assert decision.chain_id == session.chain_id
    assert decision.step_in_chain == 3


def test_idle_timeout_promotes_to_skip_or_new() -> None:
    """Past 2h without activity, the session is treated as gone — re-evaluate
    against open thresholds."""
    session = _session(last_seen_minutes_ago=CHAIN_IDLE_TIMEOUT_MINUTES + 10)
    # Below threshold → SKIP_BENIGN
    d1 = decide_chain_action(
        session=session,
        ae_anomaly=0.0,
        vae_malicious_prob=0.0,
        gnn_node_risk=0.0,
        occurred_at=_NOW,
    )
    assert d1.action is ChainAction.SKIP_BENIGN
    # Above GNN threshold → OPEN_NEW (different chain_id from the stale session)
    d2 = decide_chain_action(
        session=session,
        ae_anomaly=0.0,
        vae_malicious_prob=0.0,
        gnn_node_risk=CHAIN_OPEN_GNN_THRESHOLD + 0.1,
        occurred_at=_NOW,
    )
    assert d2.action is ChainAction.OPEN_NEW
    assert d2.chain_id != session.chain_id


def test_max_steps_reached_forces_new_chain_evaluation() -> None:
    session = _session(
        last_seen_minutes_ago=1, step_count=CHAIN_MAX_STEPS, last_action=DqnAction.MONITOR.value
    )
    decision = decide_chain_action(
        session=session,
        ae_anomaly=CHAIN_OPEN_AE_THRESHOLD + 1,
        vae_malicious_prob=CHAIN_OPEN_VAE_THRESHOLD + 0.1,
        gnn_node_risk=CHAIN_OPEN_GNN_THRESHOLD + 0.1,
        occurred_at=_NOW,
    )
    assert decision.action is ChainAction.OPEN_NEW
    assert decision.chain_id != session.chain_id


def test_prior_intervention_kills_continuation() -> None:
    """If the previous DQN action was ESCALATE/ISOLATE/BLOCK, the chain
    is logically closed even if it's still in Redis. New alerts re-evaluate
    against open thresholds."""
    for closed_by in (DqnAction.ESCALATE, DqnAction.ISOLATE_HOST, DqnAction.BLOCK_USER_IP):
        session = _session(last_seen_minutes_ago=1, step_count=2, last_action=closed_by.value)
        # Below threshold → SKIP
        below = decide_chain_action(
            session=session,
            ae_anomaly=0,
            vae_malicious_prob=0,
            gnn_node_risk=0.0,
            occurred_at=_NOW,
        )
        assert below.action is ChainAction.SKIP_BENIGN, closed_by
        # Above threshold → OPEN_NEW
        above = decide_chain_action(
            session=session,
            ae_anomaly=0,
            vae_malicious_prob=0,
            gnn_node_risk=CHAIN_OPEN_GNN_THRESHOLD + 0.1,
            occurred_at=_NOW,
        )
        assert above.action is ChainAction.OPEN_NEW, closed_by


# ---- decide_close_reason ----------------------------------------------


def test_close_on_intervention() -> None:
    sess = _session(last_seen_minutes_ago=1, step_count=2)
    reason = decide_close_reason(
        session=sess,
        new_step_count=3,
        new_action=DqnAction.ESCALATE,
        occurred_at=_NOW,
    )
    assert reason is ChainCloseReason.INTERVENTION


def test_close_on_max_steps() -> None:
    sess = _session(last_seen_minutes_ago=1, step_count=CHAIN_MAX_STEPS - 1)
    reason = decide_close_reason(
        session=sess,
        new_step_count=CHAIN_MAX_STEPS,
        new_action=DqnAction.MONITOR,
        occurred_at=_NOW,
    )
    assert reason is ChainCloseReason.MAX_STEPS


def test_close_on_idle_timeout() -> None:
    sess = _session(last_seen_minutes_ago=CHAIN_IDLE_TIMEOUT_MINUTES + 1, step_count=3)
    reason = decide_close_reason(
        session=sess,
        new_step_count=4,
        new_action=DqnAction.MONITOR,
        occurred_at=_NOW,
    )
    assert reason is ChainCloseReason.IDLE_TIMEOUT


def test_no_close_in_steady_state() -> None:
    sess = _session(last_seen_minutes_ago=1, step_count=5)
    assert (
        decide_close_reason(
            session=sess,
            new_step_count=6,
            new_action=DqnAction.LOW_ALERT,
            occurred_at=_NOW,
        )
        is None
    )
