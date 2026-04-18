"""IOC lookup cache (Postgres) and `compromised_assets_view` reader.

§4.3 cache rules:
    HIBP positive  → 24 h
    HIBP negative  → 5 min (stays negative-cached briefly so we don't
                            re-hit a slow upstream on every poll, but
                            short enough to pick up new breaches)
    VirusTotal     → 24 h regardless of result (matches free-tier rate limits)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.repositories.models import IocLookupCache


class IocRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(
        self, *, indicator: str, indicator_type: str, source: str,
    ) -> IocLookupCache | None:
        result = await self._s.execute(
            select(IocLookupCache)
            .where(IocLookupCache.indicator == indicator)
            .where(IocLookupCache.indicator_type == indicator_type)
            .where(IocLookupCache.source == source)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        indicator: str,
        indicator_type: str,
        source: str,
        reputation: str,
        payload: dict[str, Any],
        ttl: timedelta,
    ) -> None:
        now = datetime.now(timezone.utc)
        expires = now + ttl
        stmt = (
            pg_insert(IocLookupCache)
            .values(
                indicator=indicator,
                indicator_type=indicator_type,
                source=source,
                reputation=reputation,
                payload=payload,
                checked_at=now,
                expires_at=expires,
            )
            .on_conflict_do_update(
                index_elements=[
                    IocLookupCache.indicator,
                    IocLookupCache.indicator_type,
                    IocLookupCache.source,
                ],
                set_={
                    "reputation": reputation,
                    "payload": payload,
                    "checked_at": now,
                    "expires_at": expires,
                },
            )
        )
        await self._s.execute(stmt)

    async def search(
        self, *, query: str | None, indicator_type: str | None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[IocLookupCache], int]:
        stmt = select(IocLookupCache)
        count_stmt = select(func.count()).select_from(IocLookupCache)
        if query:
            like = f"%{query.strip()}%"
            stmt = stmt.where(IocLookupCache.indicator.ilike(like))
            count_stmt = count_stmt.where(IocLookupCache.indicator.ilike(like))
        if indicator_type:
            stmt = stmt.where(IocLookupCache.indicator_type == indicator_type)
            count_stmt = count_stmt.where(IocLookupCache.indicator_type == indicator_type)
        stmt = stmt.order_by(IocLookupCache.checked_at.desc()).limit(limit).offset(offset)
        result = await self._s.execute(stmt)
        items = list(result.scalars().all())
        total = int((await self._s.execute(count_stmt)).scalar_one())
        return items, total


class CompromisedAssetsRepo:
    """Reader for the materialized view created in migration 0002."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        result = await self._s.execute(
            text(
                """
                SELECT
                    v.host_id,
                    h.agent_name,
                    h.ip_address,
                    h.last_seen_at,
                    v.max_vae_prob,
                    v.max_gnn_risk,
                    v.last_seen_at AS last_detection_at,
                    v.detection_count,
                    v.max_action_int
                FROM compromised_assets_view v
                LEFT JOIN hosts h ON h.host_id = v.host_id
                ORDER BY v.max_vae_prob DESC NULLS LAST
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        return [dict(r._mapping) for r in result.all()]


__all__ = ["CompromisedAssetsRepo", "IocRepo"]
