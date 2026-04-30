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
import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse

from strix_api.observability import sse_clients_active
from strix_api.services.live_feed import (
    LIVE_FEED_CHANNEL,
    STREAM_AE_CHANNEL,
    STREAM_GNN_CHANNEL,
    STREAM_RL_CHANNEL,
    STREAM_VAE_CHANNEL,
    chain_log_channel,
)
from strix_api.settings import get_settings

router = APIRouter(prefix="/streams", tags=["streams"])

# Second router — mounted under /api/v1/logs. Holds the unified multiplexed
# WebSocket added in Phase 2. Kept separate from the SSE router so the
# legacy SSE endpoints remain untouched.
logs_router = APIRouter(prefix="/logs", tags=["logs"])

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
                    data = payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
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
    return EventSourceResponse(
        _pubsub_iterator(
            request,
            channel=LIVE_FEED_CHANNEL,
            metric_label="live-feed",
            event_name="alert.new",
            hello_payload={"channel": LIVE_FEED_CHANNEL},
        )
    )


@router.get(
    "/chains/{chain_id}/logs",
    summary="Per-chain alert SSE stream for the Analysis tab",
)
async def chain_logs(chain_id: UUID, request: Request) -> EventSourceResponse:
    channel = chain_log_channel(str(chain_id))
    return EventSourceResponse(
        _pubsub_iterator(
            request,
            channel=channel,
            metric_label="chain-logs",
            event_name="chain.alert.new",
            hello_payload={"chainId": str(chain_id), "channel": channel},
        )
    )


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
    return EventSourceResponse(
        _pubsub_iterator(
            request,
            channel=channel,
            metric_label="jobs",
            event_name="job.complete",
            hello_payload={"jobId": str(job_id), "channel": channel},
        )
    )


# ============================================================================
# Phase 2 — unified multiplexed WebSocket at /api/v1/logs/stream
# ============================================================================

# Thresholds used to derive the per-frame TP/FP/TN/FN label. Defaults match
# PLATFOR_BIG_CHANGES_PLAN.md §4-Phase-2; can be overridden per-process via env.
_AE_RECON_LABEL_THRESHOLD = float(os.environ.get("STRIX_AE_LABEL_THRESHOLD", "1.0"))
_VAE_PROB_LABEL_THRESHOLD = float(os.environ.get("STRIX_VAE_LABEL_THRESHOLD", "0.5"))
_GNN_RISK_LABEL_THRESHOLD = float(os.environ.get("STRIX_GNN_LABEL_THRESHOLD", "0.7743"))

_WS_QUEUE_MAX = 500
_WS_HEARTBEAT_SECONDS = 15.0
_TOPOLOGY_POLL_SECONDS = 5.0

# Channel → envelope `type` for the multiplexer.
_CHANNEL_TYPE_MAP = {
    LIVE_FEED_CHANNEL: "raw_log",
    STREAM_AE_CHANNEL: "ae",
    STREAM_VAE_CHANNEL: "vae",
    STREAM_GNN_CHANNEL: "gnn",
    STREAM_RL_CHANNEL: "rl",
}


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _envelope(type_: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": type_, "ts": _now_iso(), "payload": payload}


def derive_label(
    *,
    payload: dict[str, Any],
    score: float | None,
    threshold: float,
    topology: dict[str, Any] | None,
) -> str:
    """Map a per-event score + topology ground truth → tp|fp|tn|fn|unknown.

    Source attribution priority:
      1. `payload.synthetic_benign` (or `payload.tags.strix.synthetic_benign`)
         → benign ground truth.
      2. `payload.srcip` matches `topology.attacker_ip` → malicious ground truth.
      3. Otherwise unknown.
    """
    if score is None:
        return "unknown"

    is_benign_gt = bool(
        payload.get("synthetic_benign")
        or (payload.get("tags") or {}).get("strix.synthetic_benign")
    )
    attacker_ip = (topology or {}).get("attacker_ip")
    srcip = payload.get("srcip") or payload.get("src_ip")
    is_malicious_gt = bool(attacker_ip and srcip and srcip == attacker_ip)

    triggered = score >= threshold
    if is_malicious_gt and triggered:
        return "tp"
    if is_malicious_gt and not triggered:
        return "fn"
    if is_benign_gt and triggered:
        return "fp"
    if is_benign_gt and not triggered:
        return "tn"
    return "unknown"


def _runs_dir() -> Any:
    """Same resolution as simulation route — kept local to avoid a circular
    import via api.routes.simulation."""
    from pathlib import Path

    override = os.environ.get("STRIX_SIMULATION_RUNS_DIR")
    if override:
        return Path(override)
    # streams.py lives at apps/api/src/strix_api/api/routes/streams.py;
    # parents[6] = repo root (parents[5] resolved to `apps/` which is wrong
    # and silently produced an empty topology — no `topology` frames on the
    # multiplex WS).
    return Path(__file__).resolve().parents[6] / "infra" / "simulation" / "runs"


def _load_latest_topology() -> dict[str, Any] | None:
    """Read the newest `infra/simulation/runs/*/topology.json`. Returns None
    on any error — the WS still works without a topology, labels just become
    `unknown`."""
    try:
        runs = _runs_dir()
        if not runs.exists() or not runs.is_dir():
            return None
        candidates = [p for p in runs.iterdir() if p.is_dir()]
        if not candidates:
            return None
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        topo_path = latest / "topology.json"
        if not topo_path.exists():
            return None
        return json.loads(topo_path.read_text())
    except Exception:  # noqa: BLE001
        return None


def _attach_label(
    type_: str,
    payload: dict[str, Any],
    topology: dict[str, Any] | None,
) -> dict[str, Any]:
    """Mutate-and-return: attach `label` for AE/VAE/GNN frames. RL + raw_log
    keep `unknown` because the score-vs-threshold semantics don't apply
    cleanly (RL is an action, raw_log is pre-inference)."""
    if type_ == "ae":
        score = payload.get("recon_error") or payload.get("anomaly_score")
        payload["label"] = derive_label(
            payload=payload,
            score=float(score) if score is not None else None,
            threshold=_AE_RECON_LABEL_THRESHOLD,
            topology=topology,
        )
    elif type_ == "vae":
        score = payload.get("malicious_prob")
        payload["label"] = derive_label(
            payload=payload,
            score=float(score) if score is not None else None,
            threshold=_VAE_PROB_LABEL_THRESHOLD,
            topology=topology,
        )
    elif type_ == "gnn":
        score = payload.get("node_risk")
        payload["label"] = derive_label(
            payload=payload,
            score=float(score) if score is not None else None,
            threshold=_GNN_RISK_LABEL_THRESHOLD,
            topology=topology,
        )
    return payload


class _MultiplexQueue:
    """Per-WS-client bounded queue with drop-oldest semantics.

    On overflow we evict the oldest frame and bump `dropped_since_status`.
    The WS sender flushes a `status: dropped:N` frame opportunistically
    when it sees a non-zero counter.
    """

    def __init__(self, maxsize: int = _WS_QUEUE_MAX) -> None:
        self._q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self.dropped_since_status = 0

    def put(self, frame: dict[str, Any]) -> None:
        try:
            self._q.put_nowait(frame)
        except asyncio.QueueFull:
            try:
                # Drop-oldest: evict head, then push the newcomer.
                self._q.get_nowait()
                self.dropped_since_status += 1
            except asyncio.QueueEmpty:  # pragma: no cover — race only
                pass
            try:
                self._q.put_nowait(frame)
            except asyncio.QueueFull:  # pragma: no cover — race only
                self.dropped_since_status += 1

    async def get(self, timeout: float) -> dict[str, Any] | None:  # noqa: ASYNC109
        try:
            return await asyncio.wait_for(self._q.get(), timeout=timeout)
        except TimeoutError:
            return None

    def qsize(self) -> int:
        return self._q.qsize()


@logs_router.websocket("/stream")
async def logs_stream(websocket: WebSocket) -> None:
    """Unified multiplexed live stream.

    Subscribes to all five Redis pubsub channels (raw_log + per-model) and
    forwards them, plus a periodic topology refresh and connection status,
    on a single WebSocket.

    Backpressure: per-client bounded queue (size 500, drop-oldest). On drop
    the next outbound frame is preceded by `{"type":"status","payload":
    {"state":"dropped:N"}}`.
    """
    from redis.asyncio import Redis  # lazy import — keep route importable

    await websocket.accept()
    settings = get_settings()
    redis = Redis.from_url(
        settings.redis.url,
        max_connections=settings.redis.max_connections,
        decode_responses=False,
    )
    pubsub = redis.pubsub()
    await pubsub.subscribe(*_CHANNEL_TYPE_MAP.keys())

    queue = _MultiplexQueue()
    topology: dict[str, Any] | None = _load_latest_topology()

    # Initial frames: connected status + latest topology (if any).
    queue.put(_envelope("status", {"state": "connected"}))
    if topology is not None:
        queue.put(_envelope("topology", topology))

    stop = asyncio.Event()

    async def _pubsub_pump() -> None:
        try:
            async for message in pubsub.listen():
                if stop.is_set():
                    break
                if message is None or message.get("type") != "message":
                    continue
                channel_raw = message.get("channel")
                channel = (
                    channel_raw.decode("utf-8")
                    if isinstance(channel_raw, bytes)
                    else str(channel_raw)
                )
                type_ = _CHANNEL_TYPE_MAP.get(channel)
                if type_ is None:
                    continue
                raw = message.get("data") or b"{}"
                try:
                    payload = json.loads(
                        raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                    )
                except Exception:  # noqa: BLE001
                    continue
                if not isinstance(payload, dict):
                    payload = {"value": payload}
                _attach_label(type_, payload, topology)
                queue.put(_envelope(type_, payload))
        except Exception:  # noqa: BLE001
            stop.set()

    async def _topology_poll() -> None:
        nonlocal topology
        last_run_id = topology.get("run_id") if topology else None
        while not stop.is_set():
            try:
                await asyncio.sleep(_TOPOLOGY_POLL_SECONDS)
                fresh = _load_latest_topology()
                if fresh is None:
                    continue
                if fresh.get("run_id") != last_run_id:
                    last_run_id = fresh.get("run_id")
                    topology = fresh
                    queue.put(_envelope("topology", fresh))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                continue

    pump_task = asyncio.create_task(_pubsub_pump(), name="ws-logs-pump")
    poll_task = asyncio.create_task(_topology_poll(), name="ws-logs-topo-poll")

    try:
        while not stop.is_set():
            # Flush a backpressure status frame before the next data frame
            # if drops have accumulated since last status.
            if queue.dropped_since_status > 0:
                n = queue.dropped_since_status
                queue.dropped_since_status = 0
                await websocket.send_json(
                    _envelope("status", {"state": f"dropped:{n}"})
                )

            frame = await queue.get(timeout=_WS_HEARTBEAT_SECONDS)
            if frame is None:
                # Heartbeat — keeps proxies happy + lets clients detect liveness.
                await websocket.send_json(_envelope("status", {"state": "heartbeat"}))
                continue
            await websocket.send_json(frame)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        # Best-effort send shutdown notice; ignore failures during teardown.
        try:
            await websocket.send_json(_envelope("status", {"state": "shutdown"}))
        except Exception:  # noqa: BLE001
            pass
    finally:
        stop.set()
        for task in (pump_task, poll_task):
            task.cancel()
            try:
                await task
            except Exception:  # noqa: BLE001
                pass
        try:
            await pubsub.unsubscribe(*_CHANNEL_TYPE_MAP.keys())
            await pubsub.aclose()
            await redis.aclose()
        except Exception:  # noqa: BLE001
            pass
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
