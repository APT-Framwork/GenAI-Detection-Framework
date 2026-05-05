"""Cases / Chain Queue response schemas (Phase 4)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from strix_api.api.schemas.common import DqnActionName, StrixBase


TriageStatus = Literal["new", "investigating", "contained", "closed"]


class CaseAssignee(StrixBase):
    user_id: UUID
    name: str


class CaseItem(StrixBase):
    chain_id: UUID
    host_id: UUID
    host_name: str | None = None
    host_ip: str | None = None
    opened_at: str
    last_seen_at: str
    status: TriageStatus
    lifecycle_status: str  # "open" | "closed" — engine-owned, exposed for context
    max_ckc_stage: int
    max_ckc_stage_name: str
    max_vae_prob: float
    step_count: int
    assignee: CaseAssignee | None = None
    mitre_techniques: list[str] = Field(default_factory=list)
    last_dqn_action: DqnActionName | None = None


class CaseCounts(StrixBase):
    new: int = 0
    investigating: int = 0
    contained: int = 0
    closed: int = 0


class CasesListResponse(StrixBase):
    items: list[CaseItem]
    next_cursor: str | None = None
    counts: CaseCounts


class CaseStatusUpdateRequest(StrixBase):
    status: TriageStatus
    assignee_user_id: UUID | None = None
    note: str | None = Field(default=None, max_length=500)
