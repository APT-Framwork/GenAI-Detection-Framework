"""Per-chain investigation surface (mig 0015).

  GET    /chains/{chain_id}/tlp
  PATCH  /chains/{chain_id}/tlp
  GET    /chains/{chain_id}/tags
  POST   /chains/{chain_id}/tags
  DELETE /chains/{chain_id}/tags/{tag_name}
  GET    /chains/{chain_id}/notes
  POST   /chains/{chain_id}/notes
  GET    /chains/{chain_id}/activity

The current_principal injection gives us user_id for the audit log
without each route re-querying who the caller is.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.deps import enforce_csrf, get_current_principal, get_db_session
from strix_api.api.schemas.chains import (
    ChainActivityResponse,
    ChainNoteCreateRequest,
    ChainNotesResponse,
    ChainTagsResponse,
    TagAddRequest,
    TlpResponse,
    TlpUpdateRequest,
)
from strix_api.observability import get_logger
from strix_api.services.chain_investigation_service import ChainInvestigationService

router = APIRouter(prefix="/chains", tags=["chains"])
log = get_logger("strix_api.api.routes.chains")


def _empty_tags(chain_id: UUID) -> ChainTagsResponse:
    return ChainTagsResponse(chain_id=chain_id, items=[])


def _empty_notes(chain_id: UUID) -> ChainNotesResponse:
    return ChainNotesResponse(chain_id=chain_id, items=[])


def _empty_activity(chain_id: UUID) -> ChainActivityResponse:
    return ChainActivityResponse(chain_id=chain_id, items=[])


# ---------------------------------------------------------------- TLP


@router.get("/{chain_id}/tlp", response_model=TlpResponse)
async def get_tlp(
    chain_id: UUID,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> TlpResponse:
    if session is None:
        return TlpResponse(chain_id=chain_id, tlp="amber")
    try:
        tlp = await ChainInvestigationService(session).get_tlp(chain_id)
        return TlpResponse(chain_id=chain_id, tlp=tlp)
    except Exception as exc:  # noqa: BLE001
        log.warning("chain_tlp_db_error", exc_info=exc)
        return TlpResponse(chain_id=chain_id, tlp="amber")


@router.patch(
    "/{chain_id}/tlp",
    response_model=TlpResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def set_tlp(
    chain_id: UUID,
    body: TlpUpdateRequest,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
    principal=Depends(get_current_principal),
) -> TlpResponse:
    if session is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    user_id = getattr(principal, "user_id", None)
    new_tlp = await ChainInvestigationService(session).set_tlp(
        chain_id=chain_id, tlp=body.tlp, user_id=user_id,
    )
    return TlpResponse(chain_id=chain_id, tlp=new_tlp)


# ---------------------------------------------------------------- tags


@router.get("/{chain_id}/tags", response_model=ChainTagsResponse)
async def list_chain_tags(
    chain_id: UUID,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ChainTagsResponse:
    if session is None:
        return _empty_tags(chain_id)
    try:
        items = await ChainInvestigationService(session).list_tags(chain_id)
        return ChainTagsResponse(chain_id=chain_id, items=items)
    except Exception as exc:  # noqa: BLE001
        log.warning("chain_tags_db_error", exc_info=exc)
        return _empty_tags(chain_id)


@router.post(
    "/{chain_id}/tags",
    response_model=ChainTagsResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def add_chain_tag(
    chain_id: UUID,
    body: TagAddRequest,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
    principal=Depends(get_current_principal),
) -> ChainTagsResponse:
    if session is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    user_id = getattr(principal, "user_id", None)
    items = await ChainInvestigationService(session).add_tag(
        chain_id=chain_id, name=body.name, colour=body.colour, user_id=user_id,
    )
    return ChainTagsResponse(chain_id=chain_id, items=items)


@router.delete(
    "/{chain_id}/tags/{tag_name}",
    response_model=ChainTagsResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def remove_chain_tag(
    chain_id: UUID,
    tag_name: str,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
    principal=Depends(get_current_principal),
) -> ChainTagsResponse:
    if session is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    user_id = getattr(principal, "user_id", None)
    items = await ChainInvestigationService(session).remove_tag(
        chain_id=chain_id, name=tag_name, user_id=user_id,
    )
    return ChainTagsResponse(chain_id=chain_id, items=items)


# ---------------------------------------------------------------- notes


@router.get("/{chain_id}/notes", response_model=ChainNotesResponse)
async def list_chain_notes(
    chain_id: UUID,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ChainNotesResponse:
    if session is None:
        return _empty_notes(chain_id)
    try:
        items = await ChainInvestigationService(session).list_notes(chain_id)
        return ChainNotesResponse(chain_id=chain_id, items=items)
    except Exception as exc:  # noqa: BLE001
        log.warning("chain_notes_db_error", exc_info=exc)
        return _empty_notes(chain_id)


@router.post(
    "/{chain_id}/notes",
    response_model=ChainNotesResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def add_chain_note(
    chain_id: UUID,
    body: ChainNoteCreateRequest,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
    principal=Depends(get_current_principal),
) -> ChainNotesResponse:
    if session is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    user_id = getattr(principal, "user_id", None)
    items = await ChainInvestigationService(session).add_note(
        chain_id=chain_id, body_md=body.body_md, user_id=user_id,
    )
    return ChainNotesResponse(chain_id=chain_id, items=items)


# ---------------------------------------------------------------- activity


@router.get("/{chain_id}/activity", response_model=ChainActivityResponse)
async def list_chain_activity(
    chain_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ChainActivityResponse:
    if session is None:
        return _empty_activity(chain_id)
    try:
        items = await ChainInvestigationService(session).list_activity(chain_id, limit=limit)
        return ChainActivityResponse(chain_id=chain_id, items=items)
    except Exception as exc:  # noqa: BLE001
        log.warning("chain_activity_db_error", exc_info=exc)
        return _empty_activity(chain_id)
