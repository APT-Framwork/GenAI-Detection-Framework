"""Thin wrapper around redis.asyncio that enforces our stream conventions.

Every stream name is built from `settings.wazuh` / hard-coded patterns in
§6.4. This adapter is the single place that knows about XADD / XREADGROUP
/ XACK details, so normalizer + verdicts-writer don't each reimplement.
"""

from __future__ import annotations

import socket
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import msgpack
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from strix_api.observability import get_logger, stream_depth

log = get_logger("strix_api.adapters.redis_adapter")


class RedisStreamsClient:
    """All operations are idempotent on startup — safe to restart workers."""

    def __init__(self, url: str, *, max_connections: int = 20) -> None:
        self._url = url
        self._client = Redis.from_url(
            url, max_connections=max_connections, decode_responses=False
        )
        # Human-readable consumer name so XPENDING / XINFO CONSUMERS is useful.
        self._consumer_name = f"{socket.gethostname()}:{id(self):x}"

    @property
    def consumer_name(self) -> str:
        return self._consumer_name

    @property
    def client(self) -> Redis:
        return self._client

    async def close(self) -> None:
        await self._client.aclose()

    # ---- consumer groups ---------------------------------------------

    async def ensure_group(self, stream: str, group: str) -> None:
        """Create the consumer group if it doesn't exist. Idempotent."""
        try:
            await self._client.xgroup_create(stream, group, id="$", mkstream=True)
            log.info("xgroup_created", stream=stream, group=group)
        except ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                return  # already exists — fine
            raise

    # ---- read -----------------------------------------------------

    async def read(
        self,
        stream: str,
        group: str,
        *,
        count: int = 32,
        block_ms: int = 5_000,
    ) -> list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]:
        """Pop up to `count` messages for this consumer, blocking up to `block_ms`.

        Returns the raw redis structure; caller unpacks and XACKs.
        """
        resp = await self._client.xreadgroup(
            groupname=group,
            consumername=self._consumer_name,
            streams={stream: ">"},
            count=count,
            block=block_ms,
        )
        return resp or []

    async def ack(self, stream: str, group: str, *ids: bytes) -> None:
        if ids:
            await self._client.xack(stream, group, *ids)

    # ---- write ----------------------------------------------------

    async def publish(
        self,
        stream: str,
        payload: dict[str, Any],
        *,
        maxlen: int | None = None,
    ) -> bytes:
        """XADD with msgpack-encoded payload. Uses `~` approximate trim when maxlen set."""
        body = msgpack.packb(payload, use_bin_type=True)
        kwargs: dict[str, Any] = {"maxlen": maxlen, "approximate": True} if maxlen else {}
        return await self._client.xadd(stream, {b"payload": body}, **kwargs)

    # ---- depth metric ---------------------------------------------

    async def sample_depth(self, stream: str) -> None:
        """Refresh the `strix_stream_depth{stream}` Prometheus gauge."""
        try:
            info = await self._client.xlen(stream)
            stream_depth.labels(stream=stream).set(info)
        except ResponseError:
            stream_depth.labels(stream=stream).set(0)


# ---- payload helpers ----------------------------------------------


def unpack(message: dict[bytes, bytes]) -> dict[str, Any]:
    """Decode the msgpack payload field of an XREADGROUP entry."""
    body = message.get(b"payload")
    if body is None:
        raise ValueError("redis entry missing 'payload' field")
    unpacked = msgpack.unpackb(body, raw=False)
    if not isinstance(unpacked, dict):
        raise ValueError(f"payload is {type(unpacked).__name__}, expected dict")
    return unpacked


@asynccontextmanager
async def streams_client(url: str, **kwargs: Any) -> AsyncIterator[RedisStreamsClient]:
    c = RedisStreamsClient(url, **kwargs)
    try:
        yield c
    finally:
        await c.close()


__all__ = ["RedisStreamsClient", "streams_client", "unpack"]
