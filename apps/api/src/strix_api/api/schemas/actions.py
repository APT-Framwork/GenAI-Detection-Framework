"""Response Action Log schemas (Phase 8)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from strix_api.api.schemas.common import DqnActionName, StrixBase


# Derived state — not a column. See actions_service._derive_status().
ActionStatus = Literal[
    "proposed",       # requires_approval=true, not yet applied or declined
    "approved",       # applied=true, not rolled back
    "auto_applied",   # applied=true, requires_approval=false
    "declined",       # rejected_at is set
    "rolled_back",    # row in dqn_action_rollbacks exists
]


class ActorRef(StrixBase):
    user_id: UUID
    name: str


class ActionRollback(StrixBase):
    rollback_id: UUID
    rolled_back_at: str
    rolled_back_by: ActorRef | None = None
    reason: str


class ActionItem(StrixBase):
    action_id: UUID
    chain_id: UUID
    host_id: UUID
    host_name: str | None = None
    decided_at: str
    applied_at: str | None = None
    action: int
    action_name: DqnActionName
    q_values: list[float] = Field(default_factory=list)
    ckc_stage_at_decision: int
    ckc_stage_name: str
    requires_approval: bool
    status: ActionStatus
    applied_by: ActorRef | None = None
    rejected_at: str | None = None
    rejected_by: ActorRef | None = None
    rollback: ActionRollback | None = None


class ActionCounts(StrixBase):
    proposed: int = 0
    approved: int = 0
    auto_applied: int = 0
    declined: int = 0
    rolled_back: int = 0


class ActionsListResponse(StrixBase):
    items: list[ActionItem]
    next_cursor: str | None = None
    counts: ActionCounts


class ApproveRequest(StrixBase):
    note: str | None = Field(default=None, max_length=400)


class DeclineRequest(StrixBase):
    reason: str = Field(min_length=1, max_length=400)


class RollbackRequest(StrixBase):
    reason: str = Field(min_length=1, max_length=400)


class ManualActionRequest(StrixBase):
    """Operator-initiated action — Phase 10. Synthesises a DqnActionRow with
    `q_values=[]` and `requires_approval=False` so the Action Log can show
    it alongside the policy's own decisions."""

    chain_id: UUID
    action: int = Field(ge=0, le=4)
    action_name: DqnActionName
    reason: str = Field(min_length=1, max_length=400)
