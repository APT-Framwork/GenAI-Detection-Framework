"""Push-notification dispatcher (M0-B6).

Called by ``workers.verdicts_writer`` after a successful DB flush: for
every DQN action ≥ ESCALATE in the batch, fan out a push message to
every registered operator device. The flag ``PUSH_ENABLED`` (env:
``PUSH_ENABLED``) must be true — defaults to false so unit tests and
the current stack don't hit the Expo API.

Delivery is best-effort: the main inference pipeline never blocks on
push, and any failure short of a raised exception is logged only. When
the Expo circuit breaker is open (5 fails / 60 s), this silently drops.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Iterable
from uuid import UUID

import structlog

from strix_api.adapters.expo_push_adapter import ExpoPushAdapter, PushMessage
from strix_api.repositories.database import session_scope
from strix_api.repositories.push_device_repo import PushDeviceRepo
from strix_api.repositories.user_repo import UserRepo

_log = structlog.get_logger(__name__)


@dataclass(slots=True, frozen=True)
class InterventionEvent:
    chain_id: UUID
    alert_id: str
    host_id: UUID
    action_name: str
    ckc_stage: int
    vae_prob: float | None


class PushDispatcher:
    """Holds the Expo client + a cached set of admin/analyst user ids.

    The set is refreshed lazily every ``_USER_CACHE_TTL_SECONDS`` — the
    user base churns rarely and we don't want to join on every batch.
    """

    _USER_CACHE_TTL_SECONDS = 300

    def __init__(
        self, *, enabled: bool, expo_access_token: str | None = None,
    ) -> None:
        self._enabled = enabled
        self._adapter: ExpoPushAdapter | None = (
            ExpoPushAdapter(access_token=expo_access_token) if enabled else None
        )
        self._user_cache: list[UUID] = []
        self._user_cache_ts: float = 0.0
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        if self._adapter:
            await self._adapter.close()

    async def _operator_user_ids(self) -> list[UUID]:
        now = asyncio.get_running_loop().time()
        if now - self._user_cache_ts < self._USER_CACHE_TTL_SECONDS and self._user_cache:
            return self._user_cache
        async with self._lock:
            if now - self._user_cache_ts < self._USER_CACHE_TTL_SECONDS and self._user_cache:
                return self._user_cache
            try:
                async with session_scope() as session:
                    users = await UserRepo(session).list_active()
                    self._user_cache = [
                        u.user_id
                        for u in users
                        if u.role in ("admin", "analyst")
                    ]
                    self._user_cache_ts = now
            except Exception as exc:  # pragma: no cover — best-effort only
                _log.warning("push_user_lookup_failed", error=str(exc))
                return self._user_cache  # stale cache beats no push
        return self._user_cache

    async def dispatch_interventions(
        self, events: Iterable[InterventionEvent],
    ) -> None:
        if not self._enabled or self._adapter is None:
            return

        events_list = list(events)
        if not events_list:
            return

        try:
            user_ids = await self._operator_user_ids()
            if not user_ids:
                return
            async with session_scope() as session:
                device_repo = PushDeviceRepo(session)
                pairs = await device_repo.list_tokens_for_users(user_ids)
            if not pairs:
                return

            messages = [
                PushMessage(
                    to=token,
                    title=_title_for(ev),
                    body=_body_for(ev),
                    data={
                        "type": "intervention",
                        "chainId": str(ev.chain_id),
                        "alertId": ev.alert_id,
                        "action": ev.action_name,
                        "ckcStage": ev.ckc_stage,
                    },
                )
                for _, token in pairs
                for ev in events_list
            ]

            result = await self._adapter.send(messages)
            _log.info(
                "push_dispatched",
                interventions=len(events_list),
                recipients=len(pairs),
                ok=result.ok,
                failed=result.failed,
                invalid=len(result.invalid_tokens),
            )

            if result.invalid_tokens:
                # Best-effort cleanup: remove tokens Expo rejected as
                # DeviceNotRegistered so we stop paying the failure cost.
                await self._prune_invalid_tokens(
                    [(uid, tok) for uid, tok in pairs if tok in result.invalid_tokens],
                )
        except Exception as exc:  # pragma: no cover — never blocks writes
            _log.warning("push_dispatch_failed", error=str(exc))

    async def _prune_invalid_tokens(
        self, pairs: list[tuple[UUID, str]],
    ) -> None:
        if not pairs:
            return
        try:
            async with session_scope() as session:
                repo = PushDeviceRepo(session)
                for user_id, token in pairs:
                    await repo.delete_by_token(
                        user_id=user_id, expo_push_token=token,
                    )
                await session.commit()
        except Exception as exc:  # pragma: no cover
            _log.warning("push_prune_failed", error=str(exc))


def _title_for(ev: InterventionEvent) -> str:
    if ev.action_name == "ISOLATE_HOST":
        return "Host isolation recommended"
    if ev.action_name == "BLOCK_USER_IP":
        return "User/IP block recommended"
    return "Attack escalation detected"


def _body_for(ev: InterventionEvent) -> str:
    prob_txt = (
        f" (p={ev.vae_prob:.2f})"
        if ev.vae_prob is not None
        else ""
    )
    return f"CKC stage {ev.ckc_stage} — {ev.action_name.replace('_', ' ').title()}{prob_txt}"
