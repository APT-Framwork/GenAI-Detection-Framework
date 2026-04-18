"""Alert query endpoints (M0-B1/B2).

* ``GET  /alerts``                   — keyset-paginated list, severity
                                        filter, optional only_unacknowledged
* ``POST /alerts/{alert_id}/acknowledge`` — mark acked (idempotent)

Both endpoints degrade gracefully when the DB engine isn't initialised
(e.g. unit-test sandbox) by returning empty results / no-op payloads —
same pattern as the dashboard and analysis routes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.deps import get_current_principal, get_db_session
from strix_api.api.errors import StrixError
from strix_api.api.schemas.alerts import (
    AlertAcknowledgeRequest,
    AlertAcknowledgeResponse,
    AlertListResponse,
)
from strix_api.api.schemas.common import Page
from strix_api.repositories.repos import AlertRepo
from strix_api.services.alerts_service import AlertsService
from strix_api.services.auth import Principal


router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertNotFoundError(StrixError):
    status_code = 404
    title = "Alert not found"
    code = "ALERT_NOT_FOUND"


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    _: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    cursor: Annotated[str | None, Query(description="ISO-8601 `occurred_at`; rows strictly older are returned")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    severity: Annotated[
        Literal["all", "critical", "high", "medium", "low", "info"],
        Query(description="Severity bucket from VAE probability"),
    ] = "all",
    only_unacknowledged: Annotated[bool, Query()] = False,
) -> AlertListResponse:
    if session is None:
        return AlertListResponse(
            items=[], page=Page(cursor=None, has_more=False),
        )
    service = AlertsService(AlertRepo(session))
    return await service.list_alerts(
        cursor=cursor,
        limit=limit,
        severity=severity,
        only_unacknowledged=only_unacknowledged,
    )


@router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertAcknowledgeResponse,
)
async def acknowledge_alert(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    body: AlertAcknowledgeRequest,
    alert_id: Annotated[str, Path(min_length=1)],
) -> AlertAcknowledgeResponse:
    if session is None:
        # Sandbox fallback: no DB, return a synthetic idempotent ack.
        now = datetime.now(timezone.utc).isoformat()
        return AlertAcknowledgeResponse(
            alert_id=alert_id,
            occurred_at=body.occurred_at,
            acknowledged_at=now,
            acknowledged_by=principal.user_id,
            already_acknowledged=False,
        )

    service = AlertsService(AlertRepo(session))
    result = await service.acknowledge(
        alert_id=alert_id,
        occurred_at=body.occurred_at,
        user_id=principal.user_id,
    )
    if result is None:
        raise AlertNotFoundError(
            f"no alert with id {alert_id} at {body.occurred_at}"
        )
    await session.commit()
    return result


@router.get("/unacknowledged/count")
async def unacknowledged_count(
    _: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> dict[str, int]:
    if session is None:
        return {"count": 0}
    repo = AlertRepo(session)
    return {"count": await repo.count_unacknowledged()}
