"""MITRE ATT&CK Coverage Matrix routes (Phase 6).

`GET /api/v1/mitre/coverage` — 14-tactic technique heatmap aggregated over
a time window. Falls back to an empty-shape response (with the 14 tactic
columns still present, all counts zero) when the DB session is unavailable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.deps import get_db_session
from strix_api.api.schemas.mitre import (
    MitreCoverageResponse,
    TacticCoverage,
    TechniqueCoverage,
)
from strix_api.observability import get_logger
from strix_api.services.mitre_service import MitreService, _catalog

router = APIRouter(prefix="/mitre", tags=["mitre"])
log = get_logger("strix_api.api.routes.mitre")


def _empty_shape() -> MitreCoverageResponse:
    """All 14 tactic columns present, all counts zero — shape stays stable
    when DB is down so the UI doesn't degrade to a different layout."""
    cat = _catalog()
    tactics = [
        TacticCoverage(
            tactic_id=t["tactic_id"],
            tactic_name=t["name"],
            ckc=int(t["ckc"]),
            techniques=[
                TechniqueCoverage(
                    technique_id=tech["id"],
                    technique_name=tech["name"],
                    count=0,
                    last_seen=None,
                    unique_hosts=0,
                    description=str(tech.get("description") or ""),
                )
                for tech in t["techniques"]
            ],
            column_total=0,
            description=str(t.get("description") or ""),
        )
        for t in cat["tactics"]
    ]
    return MitreCoverageResponse(
        window_start="",
        window_end="",
        tactics=tactics,
        other_count=0,
        other_unmatched_ids=[],
    )


@router.get(
    "/coverage",
    response_model=MitreCoverageResponse,
    summary="14-tactic ATT&CK coverage matrix with technique-level counts",
)
async def coverage(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> MitreCoverageResponse:
    if session is None:
        return _empty_shape()
    try:
        return await MitreService(session).coverage(since=since, until=until)
    except Exception as exc:  # noqa: BLE001
        log.warning("mitre_coverage_db_error_falling_back", exc_info=exc)
        return _empty_shape()
