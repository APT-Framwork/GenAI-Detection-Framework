"""Analysis-tab response schemas (§4.2)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from strix_api.api.schemas.common import (
    DqnActionName,
    Page,
    PaginatedResponse,
    StrixBase,
)

# ---- graph evolution ------------------------------------------------


class GraphSnapshot(StrixBase):
    ts: str
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class GraphEvolutionResponse(StrixBase):
    chain_id: UUID
    snapshots: list[GraphSnapshot]


# ---- ckc progression ------------------------------------------------


class CkcProgressionStep(StrixBase):
    ckc_stage: int
    ckc_stage_name: str
    entered_at: str
    dqn_action: DqnActionName | None = None
    actioned_at: str | None = None


class CkcProgressionResponse(StrixBase):
    chain_id: UUID
    stages: list[CkcProgressionStep]


# ---- AI predictions -------------------------------------------------


class StageProbability(StrixBase):
    ckc_stage: int
    ckc_stage_name: str
    prob: float


class PredictionsResponse(StrixBase):
    chain_id: UUID
    current_stage: int | None
    current_stage_name: str | None
    predicted_next_stage: int | None
    predicted_next_stage_name: str | None
    confidence: float
    probabilities: list[StageProbability]


# ---- forensic logs --------------------------------------------------


class ForensicLogEntry(StrixBase):
    alert_id: str
    ts: str
    agent_name: str | None
    raw_log: str | None
    rule_description: str | None
    decoder: str | None
    location: str | None


class ForensicLogsPage(StrixBase):
    chain_id: UUID
    items: list[ForensicLogEntry]
    page: Page


# ---- infection radius ----------------------------------------------


class InfectedHost(StrixBase):
    host_id: UUID
    host_name: str
    first_seen: str
    current_stage: int | None
    current_stage_name: str | None


class InfectionResponse(StrixBase):
    chain_id: UUID
    infected_count: int
    total_count: int
    percent: float
    infected_hosts: list[InfectedHost]


# ---- dwell time ----------------------------------------------------


class DwellTimeResponse(StrixBase):
    chain_id: UUID
    started_at: str
    closed_at: str | None
    duration_seconds: float
    status: str  # "open" | "closed"
    close_reason: str | None = None


# ---- chain list ----------------------------------------------------


class ChainSummary(StrixBase):
    chain_id: UUID
    host_id: UUID
    opened_at: str
    closed_at: str | None
    status: str
    close_reason: str | None
    max_ckc_stage: int
    max_ckc_stage_name: str
    max_vae_prob: float
    step_count: int


class ChainListResponse(StrixBase):
    items: list[ChainSummary]
    open_count: int


__all__ = [
    "ChainListResponse",
    "ChainSummary",
    "CkcProgressionResponse",
    "CkcProgressionStep",
    "DwellTimeResponse",
    "ForensicLogEntry",
    "ForensicLogsPage",
    "GraphEvolutionResponse",
    "GraphSnapshot",
    "InfectedHost",
    "InfectionResponse",
    "PaginatedResponse",  # re-exported for routes
    "PredictionsResponse",
    "StageProbability",
]
