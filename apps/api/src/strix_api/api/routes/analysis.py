"""Analysis tab — per-chain detail + chain list (§4.2).

All chain-detail routes 404 cleanly when the chain id is unknown. Database
errors fall back to empty-shape responses (consistent with §4.2 cache /
graceful-degradation pattern from Phase 4).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.deps import get_db_session
from strix_api.api.errors import NotFoundError
from strix_api.api.schemas.analysis import (
    ChainListResponse,
    CkcProgressionResponse,
    DwellTimeResponse,
    ForensicLogsPage,
    GraphEvolutionResponse,
    InfectionResponse,
    PredictionsResponse,
)
from strix_api.observability import get_logger
from strix_api.services.analysis_service import AnalysisService

router = APIRouter(prefix="/analysis", tags=["analysis"])
log = get_logger("strix_api.api.routes.analysis")

T = TypeVar("T")


async def _service_or_fallback(
    session: AsyncSession | None,
    handler: Callable[[AnalysisService], Awaitable[T]],
    fallback: Callable[[], T],
) -> T:
    if session is None:
        return fallback()
    try:
        return await handler(AnalysisService(session))
    except NotFoundError:
        raise  # 404s are real, not "DB unavailable"
    except Exception as exc:  # noqa: BLE001
        log.warning("analysis_db_error_falling_back", exc_info=exc)
        return fallback()


# ---- chain list (sidebar) -----------------------------------------


@router.get(
    "/chains",
    response_model=ChainListResponse,
    summary="Recent attack chains + open count for the sidebar badge",
)
async def list_chains(
    only_open: bool = Query(False, alias="onlyOpen"),
    limit: int = Query(50, ge=1, le=200),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ChainListResponse:
    return await _service_or_fallback(
        session,
        lambda svc: svc.list_chains(limit=limit, only_open=only_open),
        lambda: ChainListResponse(items=[], open_count=0),
    )


# ---- per-chain endpoints ------------------------------------------


@router.get(
    "/chains/{chain_id}/graph-evolution",
    response_model=GraphEvolutionResponse,
)
async def graph_evolution(
    chain_id: UUID,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> GraphEvolutionResponse:
    return await _service_or_fallback(
        session,
        lambda svc: svc.graph_evolution(chain_id),
        lambda: GraphEvolutionResponse(chain_id=chain_id, snapshots=[]),
    )


@router.get(
    "/chains/{chain_id}/ckc-progression",
    response_model=CkcProgressionResponse,
)
async def ckc_progression(
    chain_id: UUID,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> CkcProgressionResponse:
    return await _service_or_fallback(
        session,
        lambda svc: svc.ckc_progression(chain_id),
        lambda: CkcProgressionResponse(chain_id=chain_id, stages=[]),
    )


@router.get(
    "/chains/{chain_id}/predictions",
    response_model=PredictionsResponse,
)
async def predictions(
    chain_id: UUID,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> PredictionsResponse:
    return await _service_or_fallback(
        session,
        lambda svc: svc.predictions(chain_id),
        lambda: PredictionsResponse(
            chain_id=chain_id,
            current_stage=None,
            current_stage_name=None,
            predicted_next_stage=None,
            predicted_next_stage_name=None,
            confidence=0.0,
            probabilities=[],
        ),
    )


@router.get(
    "/chains/{chain_id}/logs",
    response_model=ForensicLogsPage,
)
async def chain_logs(
    chain_id: UUID,
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ForensicLogsPage:
    from strix_api.api.schemas.common import Page

    return await _service_or_fallback(
        session,
        lambda svc: svc.logs_page(chain_id, cursor=cursor, limit=limit),
        lambda: ForensicLogsPage(
            chain_id=chain_id,
            items=[],
            page=Page(cursor=None, has_more=False),
        ),
    )


@router.get(
    "/chains/{chain_id}/infection",
    response_model=InfectionResponse,
)
async def infection(
    chain_id: UUID,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> InfectionResponse:
    return await _service_or_fallback(
        session,
        lambda svc: svc.infection(chain_id),
        lambda: InfectionResponse(
            chain_id=chain_id,
            infected_count=0,
            total_count=0,
            percent=0.0,
            infected_hosts=[],
        ),
    )


@router.get(
    "/chains/{chain_id}/dwell-time",
    response_model=DwellTimeResponse,
)
async def dwell_time(
    chain_id: UUID,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> DwellTimeResponse:
    return await _service_or_fallback(
        session,
        lambda svc: svc.dwell_time(chain_id),
        lambda: DwellTimeResponse(
            chain_id=chain_id,
            started_at="",
            closed_at=None,
            duration_seconds=0.0,
            status="open",
            close_reason=None,
        ),
    )


# ---- notifications (interventions feed for the Notifications tab) ----


@router.get(
    "/notifications",
    summary="Recent interventions (DQN action ≥ ESCALATE) — fuels the Notifications tab",
)
async def notifications(
    limit: int = Query(50, ge=1, le=200),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
):
    if session is None:
        return {"items": []}
    try:
        items = await AnalysisService(session).list_interventions(limit=limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("notifications_db_error", exc_info=exc)
        return {"items": []}
    return {"items": items}


# ---- RL Intervention Timeline backfill (dashboard widget) ----


@router.get(
    "/rl-timeline",
    summary="Predetected + post-detected chains for the RL Intervention Timeline widget",
)
async def rl_timeline(
    since: datetime | None = Query(None, description="ISO8601; filter by chain.created_at"),
    limit: int = Query(200, ge=1, le=500),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
):
    if session is None:
        return {"predetected": [], "post_detected": []}
    try:
        return await AnalysisService(session).list_rl_timeline(since=since, limit=limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("rl_timeline_db_error", exc_info=exc)
        return {"predetected": [], "post_detected": []}
