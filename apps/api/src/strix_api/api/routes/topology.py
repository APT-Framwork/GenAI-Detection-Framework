"""Topology endpoint — host inventory + attack-chain co-occurrence edges."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.deps import get_db_session
from strix_api.api.schemas.common import WindowLiteral
from strix_api.api.schemas.topology import TopologyResponse
from strix_api.observability import get_logger
from strix_api.services.topology_service import TopologyService

router = APIRouter(prefix="/topology", tags=["topology"])
log = get_logger("strix_api.api.routes.topology")


def _empty(window: WindowLiteral) -> TopologyResponse:
    return TopologyResponse(
        window=window,
        generated_at=datetime.now(UTC).isoformat(),
        nodes=[],
        edges=[],
    )


@router.get("", response_model=TopologyResponse)
async def get_topology(
    window: WindowLiteral = Query("24h"),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> TopologyResponse:
    if session is None:
        return _empty(window)
    try:
        return await TopologyService(session).topology(window)
    except Exception as exc:  # noqa: BLE001
        log.warning("topology_db_error_falling_back", exc_info=exc)
        return _empty(window)
