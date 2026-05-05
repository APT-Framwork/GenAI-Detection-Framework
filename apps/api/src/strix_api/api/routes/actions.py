"""Response Action Log routes (Phase 8) — operator-facing DQN action ledger."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.deps import enforce_csrf, get_current_principal, get_db_session
from strix_api.api.errors import NotFoundError
from strix_api.api.schemas.actions import (
    ActionCounts,
    ActionItem,
    ActionStatus,
    ActionsListResponse,
    ApproveRequest,
    DeclineRequest,
    ManualActionRequest,
    RollbackRequest,
)
from strix_api.observability import get_logger
from strix_api.services.actions_service import ActionsService, GuardError
from strix_api.services.auth import Principal

router = APIRouter(prefix="/actions", tags=["actions"])
log = get_logger("strix_api.api.routes.actions")


@router.get(
    "",
    response_model=ActionsListResponse,
    summary="List DQN actions with derived approval status + counts",
)
async def list_actions(
    status: list[ActionStatus] | None = Query(default=None),
    host: UUID | None = Query(default=None),
    chain: UUID | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ActionsListResponse:
    if session is None:
        return ActionsListResponse(items=[], next_cursor=None, counts=ActionCounts())
    try:
        return await ActionsService(session).list_actions(
            statuses=status,
            host_id=host,
            chain_id=chain,
            since=since,
            limit=limit,
            cursor=cursor,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("actions_list_db_error_falling_back", exc_info=exc)
        return ActionsListResponse(items=[], next_cursor=None, counts=ActionCounts())


def _require_session(session: AsyncSession | None) -> AsyncSession:
    if session is None:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )
    return session


@router.post(
    "/{action_id}/approve",
    response_model=ActionItem,
    summary="Approve a pending DQN action — applies it.",
    dependencies=[Depends(enforce_csrf)],
)
async def approve(
    action_id: UUID,
    body: ApproveRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ActionItem:
    s = _require_session(session)
    try:
        return await ActionsService(s).approve(
            action_id=action_id, actor_user_id=principal.user_id, note=body.note
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GuardError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{action_id}/decline",
    response_model=ActionItem,
    summary="Decline a pending DQN action — records the rejection + reason.",
    dependencies=[Depends(enforce_csrf)],
)
async def decline(
    action_id: UUID,
    body: DeclineRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ActionItem:
    s = _require_session(session)
    try:
        return await ActionsService(s).decline(
            action_id=action_id,
            actor_user_id=principal.user_id,
            reason=body.reason,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GuardError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/manual",
    response_model=ActionItem,
    summary="Record an operator-initiated action (playbook override).",
    dependencies=[Depends(enforce_csrf)],
)
async def manual(
    body: ManualActionRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ActionItem:
    s = _require_session(session)
    try:
        return await ActionsService(s).manual(
            chain_id=body.chain_id,
            action=body.action,
            action_name=body.action_name,
            reason=body.reason,
            actor_user_id=principal.user_id,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GuardError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{action_id}/rollback",
    response_model=ActionItem,
    summary="Mark a previously-applied action as rolled back. Audit-only.",
    dependencies=[Depends(enforce_csrf)],
)
async def rollback(
    action_id: UUID,
    body: RollbackRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ActionItem:
    s = _require_session(session)
    try:
        return await ActionsService(s).rollback(
            action_id=action_id,
            actor_user_id=principal.user_id,
            reason=body.reason,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GuardError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
