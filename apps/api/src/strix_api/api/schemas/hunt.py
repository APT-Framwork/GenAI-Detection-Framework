"""Hunt query schemas (Phase 7)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from strix_api.api.schemas.common import StrixBase


HuntField = Literal["host", "user", "technique", "time", "text"]
HuntOp = Literal["eq", "contains"]
HuntSort = Literal["ts_desc", "ts_asc", "ckc_desc"]


class HuntToken(StrixBase):
    field: HuntField
    op: HuntOp
    value: str


class HuntParsed(StrixBase):
    tokens: list[HuntToken] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class HuntResultItem(StrixBase):
    alert_id: str
    ts: str
    chain_id: UUID | None = None
    host_id: UUID | None = None
    host_name: str | None = None
    rule_id: str | None = None
    description: str | None = None  # full_log truncated
    ckc_stage: int | None = None
    ckc_stage_name: str | None = None
    mitre_techniques: list[str] = Field(default_factory=list)


class HuntQueryRequest(StrixBase):
    q: str = ""
    limit: int = 100
    cursor: str | None = None
    sort: HuntSort = "ts_desc"


class HuntQueryResponse(StrixBase):
    parsed: HuntParsed
    items: list[HuntResultItem] = Field(default_factory=list)
    total: int = 0
    next_cursor: str | None = None


class SavedQuery(StrixBase):
    saved_id: UUID
    name: str
    q: str
    created_at: str


class SavedQueriesResponse(StrixBase):
    items: list[SavedQuery] = Field(default_factory=list)


class SaveQueryRequest(StrixBase):
    name: str = Field(min_length=1, max_length=80)
    q: str = Field(min_length=1, max_length=600)
