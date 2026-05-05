"""Host detail response schemas (Phase 5)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from strix_api.api.schemas.common import DqnActionName, StrixBase


HostStatus = Literal["healthy", "warning", "compromised"]


class HostOverview(StrixBase):
    host_id: UUID
    name: str
    ip: str | None = None
    agent_id: str
    is_manager: bool
    status: HostStatus
    first_seen_at: str
    last_seen_at: str


class HostSummary(StrixBase):
    open_chains: int
    total_alerts_24h: int
    max_ckc_stage_24h: int
    max_ckc_stage_name_24h: str
    last_dqn_action: DqnActionName | None = None


class HostAlertEntry(StrixBase):
    """One alert row, projected for any of the per-decoder tabs."""

    alert_id: str
    chain_id: UUID | None = None
    occurred_at: str
    decoder_name: str | None = None
    location: str | None = None
    rule_id: str | None = None
    full_log: str | None = None
    ckc_stage: int | None = None
    ckc_stage_name: str | None = None
    mitre_techniques: list[str] = Field(default_factory=list)


class HostChainEntry(StrixBase):
    chain_id: UUID
    opened_at: str
    closed_at: str | None = None
    status: str          # lifecycle "open" | "closed"
    triage_status: str   # "new" | "investigating" | "contained" | "closed"
    max_ckc_stage: int
    max_ckc_stage_name: str
    step_count: int


class HostDetailResponse(StrixBase):
    host: HostOverview
    summary: HostSummary
    audit: list[HostAlertEntry] = Field(default_factory=list)
    network: list[HostAlertEntry] = Field(default_factory=list)
    files: list[HostAlertEntry] = Field(default_factory=list)
    other: list[HostAlertEntry] = Field(default_factory=list)
    chains: list[HostChainEntry] = Field(default_factory=list)
