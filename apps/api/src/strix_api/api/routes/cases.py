"""Cases / Chain Queue routes (Phase 4) — SOC analyst home screen surface.

`GET  /api/v1/cases` — paginated, filterable list of attack chains by triage
                      status, with per-status counts.
`PATCH /api/v1/cases/{chain_id}/status` — operator transition of a chain's
                                          triage state, audit-logged.

All read paths fall back to an empty-shape response when the DB session is
unavailable (matches the pattern in routes/analysis.py); the mutating PATCH
returns 503 instead of fabricating success.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.deps import enforce_csrf, get_current_principal, get_db_session
from strix_api.api.errors import NotFoundError
from strix_api.api.schemas.cases import (
    CaseCounts,
    CaseItem,
    CasesListResponse,
    CaseStatusUpdateRequest,
    TriageStatus,
)
from strix_api.observability import get_logger
from strix_api.services.auth import Principal
from strix_api.services.cases_service import UNSET, CasesService

router = APIRouter(prefix="/cases", tags=["cases"])
log = get_logger("strix_api.api.routes.cases")


# ---- list -----------------------------------------------------------------


@router.get(
    "",
    response_model=CasesListResponse,
    summary="Triage queue of attack chains by status with per-status counts",
)
async def list_cases(
    status: list[TriageStatus] | None = Query(default=None),
    host: UUID | None = Query(default=None),
    min_ckc: int | None = Query(default=None, ge=0, le=7, alias="minCkc"),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> CasesListResponse:
    if session is None:
        return CasesListResponse(items=[], next_cursor=None, counts=CaseCounts())
    try:
        return await CasesService(session).list_cases(
            statuses=status,
            host_id=host,
            min_ckc=min_ckc,
            since=since,
            limit=limit,
            cursor=cursor,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("cases_list_db_error_falling_back", exc_info=exc)
        return CasesListResponse(items=[], next_cursor=None, counts=CaseCounts())


# ---- update triage status -------------------------------------------------


@router.patch(
    "/{chain_id}/status",
    response_model=CaseItem,
    summary="Set the triage status (and optionally the assignee) of a chain",
    dependencies=[Depends(enforce_csrf)],
)
async def update_status(
    chain_id: UUID,
    body: CaseStatusUpdateRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> CaseItem:
    if session is None:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )

    # Pydantic models can't distinguish "field omitted" from "field=None"
    # without exclude_unset gymnastics. We mark assignee as UNSET unless it
    # was explicitly provided in the request body.
    fields_set = body.model_fields_set
    assignee_arg = (
        body.assignee_user_id if "assignee_user_id" in fields_set else UNSET
    )

    try:
        return await CasesService(session).update_status(
            chain_id=chain_id,
            new_status=body.status,
            actor_user_id=principal.user_id,
            assignee_user_id=assignee_arg,
            note=body.note,
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
