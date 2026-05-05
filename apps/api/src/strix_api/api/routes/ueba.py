"""User-risk (UEBA) routes (Phase 9).

`GET /api/v1/ueba/users` — top-N risky users in window. Falls back to an
empty-shape response on DB outage.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.deps import get_db_session
from strix_api.api.schemas.ueba import UserRiskResponse
from strix_api.observability import get_logger
from strix_api.services.ueba_service import UebaService

router = APIRouter(prefix="/ueba", tags=["ueba"])
log = get_logger("strix_api.api.routes.ueba")


def _empty(now: datetime) -> UserRiskResponse:
    return UserRiskResponse(
        items=[],
        window_start=now.isoformat(),
        window_end=now.isoformat(),
        source="alerts.full_log",
    )


@router.get(
    "/users",
    response_model=UserRiskResponse,
    summary="Top-N risky users in window (regex on Alert.full_log).",
)
async def top_users(
    since: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> UserRiskResponse:
    if session is None:
        return _empty(datetime.utcnow())
    try:
        return await UebaService(session).top_users(since=since, limit=limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("ueba_top_users_db_error_falling_back", exc_info=exc)
        return _empty(datetime.utcnow())
