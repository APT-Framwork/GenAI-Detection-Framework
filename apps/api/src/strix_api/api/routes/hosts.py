"""Host detail routes (Phase 5) — per-host drill-down for the Topology + Cases pages.

`GET /api/v1/hosts/{host_id}/detail` aggregates Wazuh alerts + attack-chain
membership for a single host. Falls back to an empty-shape response when the
DB is unavailable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.deps import get_db_session
from strix_api.api.errors import NotFoundError
from strix_api.api.schemas.hosts import (
    HostDetailResponse,
    HostOverview,
    HostSummary,
)
from strix_api.observability import get_logger
from strix_api.services.host_detail_service import HostDetailService

router = APIRouter(prefix="/hosts", tags=["hosts"])
log = get_logger("strix_api.api.routes.hosts")


def _empty(host_id: UUID) -> HostDetailResponse:
    return HostDetailResponse(
        host=HostOverview(
            host_id=host_id,
            name="(unknown)",
            ip=None,
            agent_id="—",
            is_manager=False,
            status="healthy",
            first_seen_at="",
            last_seen_at="",
        ),
        summary=HostSummary(
            open_chains=0,
            total_alerts_24h=0,
            max_ckc_stage_24h=0,
            max_ckc_stage_name_24h="BENIGN",
            last_dqn_action=None,
        ),
        audit=[],
        network=[],
        files=[],
        other=[],
        chains=[],
    )


@router.get(
    "/{host_id}/detail",
    response_model=HostDetailResponse,
    summary="Per-host drill-down: status, 24h summary, alerts by decoder, chains",
)
async def host_detail(
    host_id: UUID,
    since: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500, alias="limit"),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> HostDetailResponse:
    if session is None:
        return _empty(host_id)
    try:
        return await HostDetailService(session).host_detail(
            host_id=host_id, since=since, limit_per_bucket=limit
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.warning("host_detail_db_error_falling_back", exc_info=exc)
        return _empty(host_id)
