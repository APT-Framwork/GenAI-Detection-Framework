"""`llm_insight_cache` reads/writes (§6.2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.repositories.models import LlmInsightCache


class LlmInsightCacheRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, payload_hash: str) -> LlmInsightCache | None:
        return await self._s.get(LlmInsightCache, payload_hash)

    async def upsert(
        self,
        *,
        payload_hash: str,
        model_version: str,
        insight: str,
        recommended_actions: list[dict[str, str]],
        ttl: timedelta,
    ) -> None:
        now = datetime.now(timezone.utc)
        expires = now + ttl
        stmt = (
            pg_insert(LlmInsightCache)
            .values(
                payload_hash=payload_hash,
                generated_at=now,
                model_version=model_version,
                insight=insight,
                recommended_actions={"items": recommended_actions},
                expires_at=expires,
            )
            .on_conflict_do_update(
                index_elements=[LlmInsightCache.payload_hash],
                set_={
                    "generated_at": now,
                    "model_version": model_version,
                    "insight": insight,
                    "recommended_actions": {"items": recommended_actions},
                    "expires_at": expires,
                },
            )
        )
        await self._s.execute(stmt)


__all__ = ["LlmInsightCacheRepo"]
