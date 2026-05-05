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
    build_live_feed_event,
    chain_log_channel,
)
from strix_api.settings import get_settings

# Same key the inference worker XADDs verdicts to. Kept private to that
# module historically; we read from it here for the live-feed backfill
# endpoint so the dashboard can show recent inferences when a client
# arrives mid-run (or after a sim ended).
_VERDICTS_STREAM = "strix:verdicts"

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
    "/live-feed/recent",
    summary="Recent live-feed verdicts (backfill for late-joining clients)",
)
async def live_feed_recent(limit: int = 200) -> dict[str, Any]:
    """Return the last `limit` verdicts XADDed by the inference worker to
    `strix:verdicts`, projected through `build_live_feed_event` so the
    wire shape matches the SSE channel exactly.

    Use case: the dashboard's Live Inference Stream is empty after a page
    reload because SSE is future-only. Calling this once on mount lets the
    UI seed a real history before the live stream starts. The Redis Stream
    is capped at 1M entries by the inference worker so this is bounded.
    """
    from redis.asyncio import Redis  # lazy import — keep route module importable in tests

    limit = max(1, min(int(limit), 5_000))
    settings = get_settings()
    redis = Redis.from_url(
        settings.redis.url,
        max_connections=settings.redis.max_connections,
        decode_responses=False,
    )
    try:
        # XREVRANGE returns newest-first.
        rows = await redis.xrevrange(_VERDICTS_STREAM, "+", "-", count=limit)
    finally:
        try:
            await redis.aclose()
        except Exception:  # noqa: BLE001
            pass

    # The inference worker XADDs verdicts with msgpack encoding under the
    # field name b"payload" (see RedisStreamsClient.publish). We try msgpack
    # first and fall back to JSON for forward-compat / synthetic test rows.
    import msgpack  # local import — avoid cost when this endpoint is unused

    events: list[dict[str, Any]] = []
    for stream_id, fields in rows:
        try:
            payload_bytes: bytes | None = None
            for k, v in fields.items():
                key = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                if key in ("payload", "data", "verdict"):
                    payload_bytes = v if isinstance(v, bytes) else str(v).encode()
                    break
            if payload_bytes is None and fields:
                first = next(iter(fields.values()))
                payload_bytes = first if isinstance(first, bytes) else str(first).encode()
            if payload_bytes is None:
                continue
            try:
                verdict = msgpack.unpackb(payload_bytes, raw=False)
            except Exception:  # noqa: BLE001
                verdict = json.loads(payload_bytes.decode("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        try:
            ev = build_live_feed_event(verdict)
        except Exception:  # noqa: BLE001
            continue
        sid = stream_id.decode("utf-8") if isinstance(stream_id, bytes) else str(stream_id)
        events.append({"id": sid, "data": ev})

    # Newest-first → oldest-first so frontend can append in chronological order.
    events.reverse()
    return {"channel": LIVE_FEED_CHANNEL, "count": len(events), "events": events}


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
    events here.

    Race-condition guard: VT free-tier responses can land in <100 ms, often
    before the browser's EventSource has finished connecting. Pubsub doesn't
    replay past messages, so we'd miss the result. The worker mirrors every
    completion to a TTL'd Redis key (see `_publish_job_event`); on connect
    we GET that key and emit it as a synthetic `job.complete` event before
    the live subscriber loop begins.
    """
    from strix_api.workers.arq_tasks import job_channel, job_result_key

    channel = job_channel(str(job_id))
    backfill_key = job_result_key(str(job_id))
    hello_payload = {"jobId": str(job_id), "channel": channel}

    async def _stream() -> AsyncIterator[dict[str, Any]]:
        # Try to drain a persisted result first, then attach to live pubsub
        # for any later updates (e.g. status:scanning → status:complete).
        from redis.asyncio import Redis

        settings = get_settings()
        redis = Redis.from_url(
            settings.redis.url,
            max_connections=settings.redis.max_connections,
            decode_responses=False,
        )
        try:
            cached = await redis.get(backfill_key)
        except Exception:  # noqa: BLE001
            cached = None
        finally:
            try:
                await redis.aclose()
            except Exception:  # noqa: BLE001
                pass

        yield {"event": "hello", "data": json.dumps(hello_payload)}
        if cached:
            data = cached.decode("utf-8") if isinstance(cached, bytes) else str(cached)
            yield {"event": "job.complete", "data": data}

        # Continue with the live channel — _pubsub_iterator emits its own
        # hello, which the client's EventSource ignores (different event
        # name from "job.complete"). Cheap and consistent with the other
        # SSE routes.
        async for msg in _pubsub_iterator(
            request,
            channel=channel,
            metric_label="jobs",
            event_name="job.complete",
            hello_payload=hello_payload,
        ):
            yield msg

    return EventSourceResponse(_stream())


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

    NOTE: only the GNN score is a real malice probability on this lab.
    AE/VAE were found to have an inverted signal (benign rule-80789 →
    vae_prob ≈ 1.0). Callers should pass `score` from a GNN frame; AE/VAE
    frames inherit the GNN-derived label via `_attach_label` rather than
    calling `derive_label` themselves.

    Source attribution priority:
      1. `payload.synthetic_benign` (or `payload.tags.strix.synthetic_benign`)
         → benign ground truth.
      2. `payload.srcip` matches `topology.attacker_ip` → malicious ground truth.
      3. Otherwise unknown.
    """
    if score is None:
        return "unknown"

    # Explicit benign tag (set by filebeat enrichment when the synthetic
    # benign-traffic generator runs as user `strixbenign`, or by the sidecar
    # ground-truth file). Strongest benign signal.
    is_benign_gt = bool(
        payload.get("synthetic_benign")
        or (payload.get("tags") or {}).get("strix.synthetic_benign")
    )
    attacker_ip = (topology or {}).get("attacker_ip")
    srcip = payload.get("srcip") or payload.get("src_ip")

    # Primary malice signal — direct srcip match against the lab's attacker.
    is_malicious_gt = bool(attacker_ip and srcip and srcip == attacker_ip)

    # Caldera-driven attacks usually run *locally* on the victim (sandcat
    # spawns a child process) — the audit event has no network srcip, or
    # srcip is the victim's own IP. Fall back to:
    #   - mitre_tactics on the frame (propagated from FeatureMessage by the
    #     inference worker for AE/VAE/GNN fan-out frames)
    #   - rule.id in the STRIX custom range (100xxx) on raw_log frames
    #   - rule.mitre.tactic non-empty on raw_log frames
    # Detection-quality logic that follows: "anything MITRE-flagged is the
    # malicious class; everything else from a known host is the benign
    # baseline." This gives us balanced TP/FP/TN/FN even when the synthetic
    # benign generator isn't running, which is essential for the AE/VAE
    # panel to populate during real Caldera runs (where the rule mix is
    # ~99% generic auditd 80789 and ~1% STRIX 100xxx attack rules).
    have_mitre = False
    if not is_malicious_gt and not is_benign_gt:
        # Inference fan-out shape: tactics on the payload root.
        tactics_root = payload.get("mitre_tactics") or payload.get("mitreTactics")
        if isinstance(tactics_root, list) and len(tactics_root) > 0:
            is_malicious_gt = True
            have_mitre = True
        else:
            # raw_log shape: nested rule.mitre.tactic + rule.id.
            rule = payload.get("rule") or {}
            rule_id_raw = rule.get("id") or payload.get("rule_id")
            try:
                rule_id_int = int(rule_id_raw) if rule_id_raw is not None else None
            except (TypeError, ValueError):
                rule_id_int = None
            if rule_id_int is not None and 100_000 <= rule_id_int <= 100_999:
                is_malicious_gt = True
                have_mitre = True
            else:
                mitre = rule.get("mitre") or {}
                tactics_nested = mitre.get("tactic") or []
                if isinstance(tactics_nested, list) and len(tactics_nested) > 0:
                    is_malicious_gt = True
                    have_mitre = True

    # Default-benign fallback. Once we've ruled out malicious and explicit
    # benign, treat the event as the benign baseline class IF we can
    # confidently attribute it to a known host (the inference fan-out
    # always carries `host_id`). This is what lets the AE/VAE panel
    # actually compute precision/recall on real Caldera runs — without
    # this fallback, ~99% of events from generic auditd rule 80789 land
    # in `unknown` and get dropped from the metrics.
    has_host = bool(payload.get("host_id") or payload.get("agent_id") or payload.get("agentId"))
    if not is_malicious_gt and not is_benign_gt and not have_mitre and has_host:
        is_benign_gt = True

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
    """Mutate-and-return: attach `label` for AE/VAE/GNN frames.

    Malice attribution is GNN-ONLY: smoke testing on this lab found AE/VAE
    scores are inverted (benign rule-80789 → vae_prob ≈ 1.0; attack
    rule-1001xx → ≈ 0.15), so they are anomaly diagnostics, not malice
    probabilities. AE and VAE frames inherit the label of the GNN score
    for the same `alert_id` via `_GNN_LABEL_BY_ALERT`. If no GNN score
    has arrived yet (cache miss) the label stays `unknown`.

    RL + raw_log keep `unknown` because score-vs-threshold semantics
    don't apply (RL is an action, raw_log is pre-inference).
    """
    alert_id = payload.get("alert_id") or payload.get("alertId")
    if type_ == "gnn":
        score = payload.get("node_risk")
        label = derive_label(
            payload=payload,
            score=float(score) if score is not None else None,
            threshold=_GNN_RISK_LABEL_THRESHOLD,
            topology=topology,
        )
        payload["label"] = label
        if alert_id is not None and label != "unknown":
            _GNN_LABEL_BY_ALERT[str(alert_id)] = label
            # Cap the dict to avoid unbounded growth on long-lived sessions.
            if len(_GNN_LABEL_BY_ALERT) > _GNN_LABEL_CACHE_MAX:
                # Drop ~10% oldest insertions (dict preserves insertion order).
                drop = len(_GNN_LABEL_BY_ALERT) - int(_GNN_LABEL_CACHE_MAX * 0.9)
                for k in list(_GNN_LABEL_BY_ALERT.keys())[:drop]:
                    _GNN_LABEL_BY_ALERT.pop(k, None)
    elif type_ in ("ae", "vae"):
        # AE/VAE are anomaly diagnostics — prefer the GNN-derived label for
        # the same alert. If the GNN frame hasn't arrived yet (ordering: AE
        # and VAE are published before GNN in inference.py), fall back to
        # deriving the *ground truth only* from topology + srcip / synthetic
        # flags — passing score=0 / threshold=1 collapses derive_label to
        # ground truth (fn for malicious, tn for benign, unknown otherwise).
        # Without this fallback the detection-quality panel sees every event
        # as `unknown` and reports zero labelled events.
        cached = _GNN_LABEL_BY_ALERT.get(str(alert_id)) if alert_id is not None else None
        if cached is not None:
            payload["label"] = cached
        else:
            payload["label"] = derive_label(
                payload=payload,
                score=0.0,
                threshold=1.0,
                topology=topology,
            )
    return payload


# Per-alert GNN label cache (FIFO-bounded). AE/VAE frames borrow from this.
_GNN_LABEL_BY_ALERT: dict[str, str] = {}
_GNN_LABEL_CACHE_MAX = 10_000


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
