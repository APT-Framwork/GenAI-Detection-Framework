"""Domain DTO for an in-memory snapshot of a host's session.

Lives in `core/` (not adapters) because both `core/sequence.py` (chain
lifecycle) and `adapters/session_store.py` (Redis serialisation) need to
agree on the shape — and core/ must not import from adapters/.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class SessionState:
    """Snapshot read from Redis (or constructed in-memory by tests)."""

    chain_id: UUID
    episode_start_at: datetime
    opened_at: datetime
    last_seen_at: datetime
    step_count: int
    last_ckc_stage: int | None
    last_action: int | None
    max_vae_prob: float
    max_ckc_stage: int
    # Server wall-clock at the moment the worker opened this chain (i.e. the
    # moment the chain-opening alert was *processed*, not when it occurred at
    # the source). Pairs with `opened_at` (event-time) so the dashboard can
    # show two stories: event-time gap (how deep into the chain the agent
    # fired) and wall-clock gap (real latency our pipeline added). May be
    # None for sessions written by older code that predates this field.
    pipeline_opened_at: datetime | None = None

    @property
    def next_step(self) -> int:
        return self.step_count


__all__ = ["SessionState"]
