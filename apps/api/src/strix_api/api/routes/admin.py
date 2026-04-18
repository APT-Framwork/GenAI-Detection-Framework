"""Admin-only operational endpoints (P8-8).

  GET  /admin/kill-switch       current state of the auto-response kill switch
  POST /admin/kill-switch       engage / disengage the kill switch
                                (requires admin role + CSRF)

The kill switch is the single piece of operational infra mentioned in
§12 Q3 that's actually live in 1.0. Everything else under
`AUTH_AUTO_RESPONSE_ENABLED` stays OFF — see registry.json + verdicts_writer.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import Field
from redis.asyncio import Redis

from strix_api.api.deps import SettingsDep, require_admin
from strix_api.api.schemas.common import StrixBase
from strix_api.services.auth import Principal
from strix_api.services.kill_switch import KillSwitchService

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


class KillSwitchStateResponse(StrixBase):
    engaged: bool
    set_by: str | None = None
    set_at: str | None = None


class KillSwitchUpdate(StrixBase):
    engaged: bool = Field(..., description="True → block auto-apply; False → allow")


async def _redis(settings) -> Redis:
    return Redis.from_url(
        settings.redis.url,
        max_connections=settings.redis.max_connections,
        decode_responses=False,
    )


@router.get("/kill-switch", response_model=KillSwitchStateResponse)
async def kill_switch_state(settings: SettingsDep) -> KillSwitchStateResponse:
    redis = await _redis(settings)
    try:
        state = await KillSwitchService(redis).state()
    finally:
        await redis.aclose()
    return KillSwitchStateResponse(
        engaged=state.engaged,
        set_by=state.set_by,
        set_at=state.set_at,
    )


@router.post("/kill-switch", response_model=KillSwitchStateResponse)
async def kill_switch_update(
    body: KillSwitchUpdate,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require_admin)],
) -> KillSwitchStateResponse:
    redis = await _redis(settings)
    try:
        svc = KillSwitchService(redis)
        if body.engaged:
            await svc.engage(by=str(principal.user_id))
        else:
            await svc.disengage(by=str(principal.user_id))
        state = await svc.state()
    finally:
        await redis.aclose()
    return KillSwitchStateResponse(
        engaged=state.engaged,
        set_by=state.set_by,
        set_at=state.set_at,
    )
