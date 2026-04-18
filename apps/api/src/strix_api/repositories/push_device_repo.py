"""Push device registration repo (M0-B5).

Mobile clients register their Expo push token after login; the backend
dispatcher (``workers.verdicts_writer``) fans out ≥ ESCALATE
interventions to every device belonging to the relevant operator.

Re-registration is idempotent: `upsert` keys on (user_id, expo_push_token)
and bumps last_seen_at.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.repositories.models import PushDevice

Platform = Literal["ios", "android", "web"]


class PushDeviceRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert(
        self,
        *,
        user_id: UUID,
        expo_push_token: str,
        platform: Platform,
        app_version: str | None = None,
    ) -> PushDevice:
        now = datetime.now(UTC)
        stmt = (
            pg_insert(PushDevice)
            .values(
                device_id=uuid4(),
                user_id=user_id,
                expo_push_token=expo_push_token,
                platform=platform,
                app_version=app_version,
                registered_at=now,
                last_seen_at=now,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "expo_push_token"],
                set_={
                    "last_seen_at": now,
                    "app_version": app_version,
                    "platform": platform,
                },
            )
            .returning(PushDevice)
        )
        result = await self._s.execute(stmt)
        return result.scalar_one()

    async def delete_by_token(
        self,
        *,
        user_id: UUID,
        expo_push_token: str,
    ) -> int:
        stmt = (
            delete(PushDevice)
            .where(PushDevice.user_id == user_id)
            .where(PushDevice.expo_push_token == expo_push_token)
        )
        result = await self._s.execute(stmt)
        return result.rowcount or 0

    async def list_for_user(self, user_id: UUID) -> list[PushDevice]:
        stmt = (
            select(PushDevice)
            .where(PushDevice.user_id == user_id)
            .order_by(PushDevice.last_seen_at.desc())
        )
        result = await self._s.execute(stmt)
        return list(result.scalars().all())

    async def list_tokens_for_users(
        self,
        user_ids: list[UUID],
    ) -> list[tuple[UUID, str]]:
        """Return (user_id, expo_push_token) pairs for bulk dispatch."""
        if not user_ids:
            return []
        stmt = select(PushDevice.user_id, PushDevice.expo_push_token).where(
            PushDevice.user_id.in_(user_ids)
        )
        result = await self._s.execute(stmt)
        return [(uid, tok) for uid, tok in result.all()]

    async def touch(self, device_id: UUID) -> None:
        stmt = (
            update(PushDevice)
            .where(PushDevice.device_id == device_id)
            .values(last_seen_at=datetime.now(UTC))
        )
        await self._s.execute(stmt)
