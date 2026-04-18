"""Tiny Redis-backed JSON cache for dashboard responses (§7.2).

Pattern: workers write fresh values via the cache when the underlying
data is stale. Routes use `get_or_compute(...)` — cache hit → return; miss
→ run the loader, set, return. TTLs match §7.2 (30-60 s for dashboard
widgets).

Avoids `redis-pool` proliferation by accepting a `Redis` client passed in
from the FastAPI dep — same connection pool as the Streams adapter.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from strix_api.observability import cache_hits_total, cache_misses_total

T = TypeVar("T")


class JsonCache:
    """Stateless. One instance per FastAPI app, instantiated in lifespan."""

    def __init__(self, redis: Any) -> None:
        self._r = redis

    async def get(self, key: str) -> Any | None:
        raw = await self._r.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    async def set(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        await self._r.set(key, json.dumps(value, default=str), ex=ttl_seconds)

    async def invalidate(self, *keys: str) -> int:
        if not keys:
            return 0
        return int(await self._r.delete(*keys))

    async def get_or_compute(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        ttl_seconds: int,
        metric_label: str | None = None,
    ) -> Any:
        label = metric_label or key.split(":", 1)[0]
        hit = await self.get(key)
        if hit is not None:
            cache_hits_total.labels(cache=label).inc()
            return hit
        cache_misses_total.labels(cache=label).inc()
        value = await loader()
        await self.set(key, value, ttl_seconds=ttl_seconds)
        return value


__all__ = ["JsonCache"]
