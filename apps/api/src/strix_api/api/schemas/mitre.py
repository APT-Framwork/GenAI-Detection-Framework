"""MITRE ATT&CK Coverage Matrix response schemas (Phase 6)."""

from __future__ import annotations

from pydantic import Field

from strix_api.api.schemas.common import StrixBase


class TechniqueCoverage(StrixBase):
    technique_id: str
    technique_name: str
    count: int
    last_seen: str | None = None
    unique_hosts: int = 0
    # Concise definition shown on hover in the matrix. Sourced from the
    # bundled catalog (data/mitre_catalog.json); empty string when missing
    # so the response shape is stable.
    description: str = ""


class TacticCoverage(StrixBase):
    tactic_id: str
    tactic_name: str
    ckc: int
    techniques: list[TechniqueCoverage] = Field(default_factory=list)
    column_total: int = 0
    description: str = ""


class MitreCoverageResponse(StrixBase):
    window_start: str
    window_end: str
    tactics: list[TacticCoverage] = Field(default_factory=list)
    other_count: int = 0
    other_unmatched_ids: list[str] = Field(default_factory=list)
