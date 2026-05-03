"""Threat-intel schemas (§4.3)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from strix_api.api.schemas.common import StrixBase


class IocItem(StrixBase):
    indicator: str
    type: str  # 'email' | 'ip' | 'domain' | 'hash'
    reputation: str  # 'malicious' | 'suspicious' | 'clean' | 'unknown'
    source: str  # 'xon' | 'virustotal' | 'cache'
    last_checked: str
    breach_count: int | None = None
    stale: bool = False
    payload: dict[str, Any] | None = None


class IocSearchResponse(StrixBase):
    items: list[IocItem]
    total: int
    page: int
    limit: int


class CompromisedAsset(StrixBase):
    host_id: UUID
    agent_name: str | None = None
    ip_address: str | None = None
    last_seen_at: str | None = None
    last_detection_at: str | None = None
    detection_count: int
    max_vae_prob: float | None = None
    max_gnn_risk: float | None = None
    last_action_int: int | None = Field(default=None, alias="lastActionInt")


class CompromisedAssetsResponse(StrixBase):
    items: list[CompromisedAsset]


class VtScanRequest(StrixBase):
    indicator: str
    type: str | None = None  # auto-detect if absent


class JobAcceptedResponse(StrixBase):
    job_id: UUID
    status: str = "queued"


class FileScanResponse(StrixBase):
    scan_id: UUID
    sha256: str
    size_bytes: int
    status: str  # 'queued' | 'scanning' | 'complete' | 'error'
    filename: str


__all__ = [
    "CompromisedAsset",
    "CompromisedAssetsResponse",
    "FileScanResponse",
    "IocItem",
    "IocSearchResponse",
    "JobAcceptedResponse",
    "VtScanRequest",
]
