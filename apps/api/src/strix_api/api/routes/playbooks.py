"""Playbook routes (Phase 10) — bundled response runbooks for the
Attack Analysis right rail.

`GET /api/v1/playbooks?stage=&technique=` — returns matched + fallback.

Read-only and DB-free; the catalogue is bundled JSON loaded once at import.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from strix_api.api.schemas.playbooks import PlaybookMatchResponse
from strix_api.services.playbooks_service import find_playbooks

router = APIRouter(prefix="/playbooks", tags=["playbooks"])


@router.get(
    "",
    response_model=PlaybookMatchResponse,
    summary="Lookup matched + fallback playbook(s) for (stage, technique).",
)
async def list_playbooks(
    stage: int | None = Query(default=None, ge=0, le=7),
    technique: str | None = Query(default=None, max_length=20),
) -> PlaybookMatchResponse:
    return find_playbooks(stage=stage, technique=technique)
