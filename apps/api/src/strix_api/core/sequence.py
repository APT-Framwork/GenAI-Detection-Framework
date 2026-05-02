"""Attack-chain lifecycle (§5.4 + §12 Q2/Q5).

Pure-domain. The inference worker calls `decide_chain_action(...)` with
the new alert's signals and the current session state (or None if absent),
and gets back a `ChainDecision` describing what to do.

Malice signal — GNN ONLY. Smoke testing found AE/VAE/Transformer have an
INVERTED signal on this lab (benign rule-80789 → vae_prob ≈ 1.0; attack
custom rules 1001xx → ≈ 0.15). Only the GNN was trained with proper
labels here, so it is the sole gate for OPEN_NEW. AE+VAE+Transformer are
still produced for telemetry — they are anomaly diagnostics surfaced in
the UI, not malice probabilities.

Rules (§5.4, post-fix):
  Open a NEW chain for host H if there is NO open chain AND
      gnn_node_risk >= CHAIN_OPEN_GNN_THRESHOLD.
  Continue the OPEN chain for H if all hold:
      - last_seen_at within CHAIN_IDLE_TIMEOUT_MINUTES
      - no prior intervention (the previous DQN action was < ESCALATE)
      - step_count < CHAIN_MAX_STEPS
  Close on:
      INTERVENTION  - when this step's DQN action >= ESCALATE
      IDLE_TIMEOUT  - prior session is older than the idle window
      MAX_STEPS     - this would be step CHAIN_MAX_STEPS (50)

Benign-only hosts (no current chain AND below the GNN open threshold) are
SKIPPED — the worker still scores AE+VAE for the live feed, but does NOT
run Transformer/DQN and does NOT touch session state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from strix_api.core.constants import (
    CHAIN_IDLE_TIMEOUT_MINUTES,
    CHAIN_MAX_STEPS,
    CHAIN_OPEN_GNN_THRESHOLD,
)
from strix_api.core.enums import DqnAction
from strix_api.core.session import SessionState


class ChainAction(StrEnum):
    """What the worker should do with this alert."""

    OPEN_NEW = "OPEN_NEW"
    CONTINUE = "CONTINUE"
    SKIP_BENIGN = "SKIP_BENIGN"  # AE+VAE only, no Transformer/DQN, no session


class ChainCloseReason(StrEnum):
    """Mirrors the §6.2 close_reason CHECK constraint."""

    INTERVENTION = "INTERVENTION"
    IDLE_TIMEOUT = "IDLE_TIMEOUT"
    MAX_STEPS = "MAX_STEPS"


@dataclass(frozen=True)
class ChainDecision:
    action: ChainAction
    chain_id: UUID | None  # None when SKIP_BENIGN
    step_in_chain: int  # 0 for OPEN_NEW, otherwise prior step_count
    is_first_in_chain: bool  # convenience: action == OPEN_NEW

    @property
    def runs_full_pipeline(self) -> bool:
        """Whether to run Transformer + DQN for this alert."""
        return self.action in (ChainAction.OPEN_NEW, ChainAction.CONTINUE)


# ---------------------------------------------------------------- decisions


def decide_chain_action(
    *,
    session: SessionState | None,
    ae_anomaly: float,
    vae_malicious_prob: float,
    gnn_node_risk: float,
    occurred_at: datetime,
) -> ChainDecision:
    """Pre-DQN gate: decide whether this alert opens / continues / skips a chain.

    `gnn_node_risk` is the sole malice signal (see module docstring on the
    AE/VAE inversion). `ae_anomaly` and `vae_malicious_prob` are still
    accepted because callers compute and emit them for telemetry, but they
    no longer drive open/skip.
    """
    # Idle-timeout takes precedence — a stale session is dead even if scored high.
    if session is not None and _is_idle(session.last_seen_at, occurred_at):
        # Treat as no-session and re-evaluate against the open thresholds.
        session = None

    # Already over the step cap? force a new chain (the old one will be closed
    # on the next verdict-writer pass; see `decide_close_reason`).
    if session is not None and session.step_count >= CHAIN_MAX_STEPS:
        session = None

    # If a prior intervention was taken, the chain is closed too.
    if session is not None and session.last_action is not None:
        if DqnAction(session.last_action).is_intervention:
            session = None

    if session is None:
        if _meets_open_threshold(gnn_node_risk):
            return ChainDecision(
                action=ChainAction.OPEN_NEW,
                chain_id=uuid4(),
                step_in_chain=0,
                is_first_in_chain=True,
            )
        return ChainDecision(
            action=ChainAction.SKIP_BENIGN,
            chain_id=None,
            step_in_chain=0,
            is_first_in_chain=False,
        )

    return ChainDecision(
        action=ChainAction.CONTINUE,
        chain_id=session.chain_id,
        step_in_chain=session.step_count,
        is_first_in_chain=False,
    )


def decide_close_reason(
    *,
    session: SessionState,
    new_step_count: int,
    new_action: DqnAction,
    occurred_at: datetime,
) -> ChainCloseReason | None:
    """Post-DQN: should this verdict close the chain? Returns None if it stays open."""
    if new_action.is_intervention:
        return ChainCloseReason.INTERVENTION
    if new_step_count >= CHAIN_MAX_STEPS:
        return ChainCloseReason.MAX_STEPS
    if _is_idle(session.last_seen_at, occurred_at):
        return ChainCloseReason.IDLE_TIMEOUT
    return None


def find_idle_chains_to_close(
    *,
    sessions: dict[str, SessionState],
    now: datetime,
) -> list[tuple[str, SessionState]]:
    """Sweep helper for the idle-timeout closer (Phase 3 / verdicts writer
    background task). Returns (agent_id, session) pairs whose
    `last_seen_at` exceeded `CHAIN_IDLE_TIMEOUT_MINUTES` before `now`.
    """
    idle: list[tuple[str, SessionState]] = []
    for agent_id, sess in sessions.items():
        if _is_idle(sess.last_seen_at, now):
            idle.append((agent_id, sess))
    return idle


# ---------------------------------------------------------------- helpers


def _meets_open_threshold(gnn_node_risk: float) -> bool:
    # GNN-only gate. AE/VAE thresholds in constants.py are kept as
    # informational anomaly thresholds — see module docstring.
    return gnn_node_risk >= CHAIN_OPEN_GNN_THRESHOLD


def _is_idle(last_seen_at: datetime, now: datetime) -> bool:
    return (now - last_seen_at) > timedelta(minutes=CHAIN_IDLE_TIMEOUT_MINUTES)


__all__ = [
    "ChainAction",
    "ChainCloseReason",
    "ChainDecision",
    "decide_chain_action",
    "decide_close_reason",
    "find_idle_chains_to_close",
]
