"""Hunt routes (Phase 7).

`POST /api/v1/hunt/query`        — execute a parsed query, paginated.
`GET  /api/v1/hunt/saved`        — list this user's saved queries.
`POST /api/v1/hunt/saved`        — save (upsert by name).
`DELETE /api/v1/hunt/saved/{id}` — delete a saved query.

Saved-query routes require an authenticated principal. The query route is
read-only and tolerates the unauthenticated case so the empty-shape /
DB-down fallback can render.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.deps import enforce_csrf, get_current_principal, get_db_session
from strix_api.api.errors import NotFoundError
from strix_api.api.schemas.hunt import (
    HuntParsed,
    HuntQueryRequest,
    HuntQueryResponse,
    SaveQueryRequest,
    SavedQueriesResponse,
    SavedQuery,
)
from strix_api.observability import get_logger
from strix_api.services.auth import Principal
from strix_api.services.hunt_service import HuntService, parse_query

router = APIRouter(prefix="/hunt", tags=["hunt"])
log = get_logger("strix_api.api.routes.hunt")


# ---- query --------------------------------------------------------------


@router.post(
    "/query",
    response_model=HuntQueryResponse,
    summary="Execute a Hunt query (KQL-lite). Permissive parsing.",
    dependencies=[Depends(enforce_csrf)],
)
async def query(
    body: HuntQueryRequest,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> HuntQueryResponse:
    if session is None:
        # Still parse so the UI can underline tokens even when offline.
        return HuntQueryResponse(
            parsed=parse_query(body.q),
            items=[],
            total=0,
            next_cursor=None,
        )
    try:
        return await HuntService(session).query(
            q=body.q,
            limit=body.limit,
            cursor=body.cursor,
            sort=body.sort,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("hunt_query_db_error_falling_back", exc_info=exc)
        return HuntQueryResponse(
            parsed=parse_query(body.q), items=[], total=0, next_cursor=None
        )


# ---- saved queries ------------------------------------------------------


@router.get(
    "/saved",
    response_model=SavedQueriesResponse,
    summary="List the caller's saved Hunt queries",
)
async def list_saved(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> SavedQueriesResponse:
    if session is None:
        return SavedQueriesResponse(items=[])
    try:
        return await HuntService(session).list_saved(user_id=principal.user_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("hunt_saved_list_db_error_falling_back", exc_info=exc)
        return SavedQueriesResponse(items=[])


@router.post(
    "/saved",
    response_model=SavedQuery,
    summary="Save (or overwrite by name) a Hunt query",
    dependencies=[Depends(enforce_csrf)],
)
async def save(
    body: SaveQueryRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> SavedQuery:
    if session is None:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )
    return await HuntService(session).save(
        user_id=principal.user_id, name=body.name, q=body.q
    )


@router.delete(
    "/saved/{saved_id}",
    summary="Delete a saved Hunt query",
    dependencies=[Depends(enforce_csrf)],
)
async def delete_saved(
    saved_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> dict[str, str]:
    if session is None:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )
    try:
        await HuntService(session).delete(
            user_id=principal.user_id, saved_id=saved_id
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return {"status": "deleted"}


# Re-export for convenience (and to keep `parse_query` imports tight).
__all__ = ["router", "HuntParsed"]
