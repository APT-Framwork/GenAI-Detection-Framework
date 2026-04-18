"""Server-Sent Events endpoints (§5.5 + §6.4).

  /streams/live-feed              broadcasts every alert (newest first) — fed
                                  by the `strix:sse:live-feed` pubsub channel.
  /streams/chains/{id}/logs       per-chain alert stream for the Analysis tab —
                                  fed by `strix:sse:chain:{chain_id}`.

Each connection runs one Redis SUBSCRIBE plus an in-process queue (size 100)
so a slow client can't backpressure the whole fan-out (§7.6). When the queue
fills up the connection is dropped.

Auth: SSE endpoints obey the same auth middleware as everything else.
Browsers natively send cookies on EventSource connections so the access
cookie is honored automatically.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from strix_api.observability import sse_clients_active
from strix_api.services.live_feed import LIVE_FEED_CHANNEL, chain_log_channel
from strix_api.settings import get_settings

router = APIRouter(prefix="/streams", tags=["streams"])

_PER_CLIENT_QUEUE_MAX = 100
_HEARTBEAT_SECONDS = 15.0


async def _pubsub_iterator(
    request: Request,
    *,
    channel: str,
    metric_label: str,
    event_name: str,
    hello_payload: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """Generic SSE iterator backed by Redis pubsub on `channel`.

    `event_name` becomes the SSE `event:` field; sse_starlette serialises
    each `{event, data}` mapping into the wire format.
    """
    from redis.asyncio import Redis  # lazy import — keep route module importable in tests

    settings = get_settings()
    redis = Redis.from_url(
        settings.redis.url,
        max_connections=settings.redis.max_connections,
        decode_responses=False,
    )
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    sse_clients_active.labels(endpoint=metric_label).inc()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_PER_CLIENT_QUEUE_MAX)
    drop_signal = asyncio.Event()

    async def _pump() -> None:
        try:
            async for message in pubsub.listen():
                if message is None or message.get("type") != "message":
                    continue
                if drop_signal.is_set():
                    break
                payload = message.get("data") or b"{}"
                try:
                    data = (
                        payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
                    )
                except Exception:
                    continue
                try:
                    queue.put_nowait({"event": event_name, "data": data})
                except asyncio.QueueFull:
                    drop_signal.set()
                    break
        except Exception:  # noqa: BLE001
            drop_signal.set()

    pump_task = asyncio.create_task(_pump(), name=f"sse-{metric_label}-pump")

    try:
        yield {"event": "hello", "data": json.dumps(hello_payload)}
        while True:
            if await request.is_disconnected():
                break
            if drop_signal.is_set():
                break
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
            except TimeoutError:
                yield {"event": "ping", "data": ""}
                continue
            yield msg
    finally:
        drop_signal.set()
        pump_task.cancel()
        try:
            await pump_task
        except Exception:  # noqa: BLE001
            pass
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await redis.aclose()
        except Exception:  # noqa: BLE001
            pass
        sse_clients_active.labels(endpoint=metric_label).dec()


@router.get("/live-feed", summary="Live alert SSE stream (all chains)")
async def live_feed(request: Request) -> EventSourceResponse:
    return EventSourceResponse(_pubsub_iterator(
        request,
        channel=LIVE_FEED_CHANNEL,
        metric_label="live-feed",
        event_name="alert.new",
        hello_payload={"channel": LIVE_FEED_CHANNEL},
    ))


@router.get(
    "/chains/{chain_id}/logs",
    summary="Per-chain alert SSE stream for the Analysis tab",
)
async def chain_logs(chain_id: UUID, request: Request) -> EventSourceResponse:
    channel = chain_log_channel(str(chain_id))
    return EventSourceResponse(_pubsub_iterator(
        request,
        channel=channel,
        metric_label="chain-logs",
        event_name="chain.alert.new",
        hello_payload={"chainId": str(chain_id), "channel": channel},
    ))


@router.get(
    "/jobs/{job_id}",
    summary="Async-job completion SSE channel (VT scans, file scans, …)",
)
async def job_result(job_id: UUID, request: Request) -> EventSourceResponse:
    """Subscribes to `strix:sse:job:{job_id}` — Arq tasks publish completion
    events here. The connection auto-closes after the first `job.complete`
    event arrives via an explicit close from the client.
    """
    from strix_api.workers.arq_tasks import job_channel

    channel = job_channel(str(job_id))
    return EventSourceResponse(_pubsub_iterator(
        request,
        channel=channel,
        metric_label="jobs",
        event_name="job.complete",
        hello_payload={"jobId": str(job_id), "channel": channel},
    ))
