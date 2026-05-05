"""User-risk (UEBA) response schemas (Phase 9)."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from strix_api.api.schemas.common import StrixBase


class UserChainRef(StrixBase):
    chain_id: UUID
    max_ckc_stage: int


class UserRiskItem(StrixBase):
    user: str
    risk_score: float                  # 0..1, derivation documented in service
    alert_count: int
    hosts_touched: int
    chain_count: int
    max_ckc_stage: int
    last_seen: str | None = None
    top_chains: list[UserChainRef] = Field(default_factory=list)


class UserRiskResponse(StrixBase):
    items: list[UserRiskItem] = Field(default_factory=list)
    window_start: str
    window_end: str
    source: str = "alerts.full_log"   # provenance — flips when GNN signal lands
