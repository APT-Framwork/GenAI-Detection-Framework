"""Phase-2 unified WebSocket multiplex (`/api/v1/logs/stream`).

Covers:
  - WebSocket connect → initial `status: connected` envelope.
  - Envelope shape `{type, ts, payload}` for each multiplexed type.
  - Backpressure: drop-oldest semantics + `dropped:N` status emission.
  - Label derivation TP/FP/TN/FN/unknown from topology ground truth.

Redis is mocked via a stub pubsub object — no live Redis required.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("ENV", "dev")
os.environ.setdefault("AUTH_DEV_SKIP_AUTH", "true")
os.environ.setdefault("AUTH_JWT_SECRET", "test-secret-not-for-prod")


# ---------------------------------------------------------------------------
# Pure-unit tests — no FastAPI app needed
# ---------------------------------------------------------------------------


def test_envelope_shape() -> None:
    from strix_api.api.routes.streams import _envelope

    env = _envelope("ae", {"alert_id": "x", "recon_error": 0.4})
    assert set(env.keys()) == {"type", "ts", "payload"}
    assert env["type"] == "ae"
    assert env["payload"]["alert_id"] == "x"
    # ISO-8601 sanity (ends with Z, has 'T').
    assert "T" in env["ts"]


def test_label_tp_fp_tn_fn_unknown() -> None:
    from strix_api.api.routes.streams import derive_label

    topo = {"attacker_ip": "10.0.0.5"}

    # TP — malicious src + score over threshold
    assert (
        derive_label(payload={"srcip": "10.0.0.5"}, score=0.9, threshold=0.5, topology=topo)
        == "tp"
    )
    # FN — malicious src + below threshold
    assert (
        derive_label(payload={"srcip": "10.0.0.5"}, score=0.1, threshold=0.5, topology=topo)
        == "fn"
    )
    # FP — synthetic_benign tag + above threshold
    assert (
        derive_label(
            payload={"srcip": "10.0.0.99", "synthetic_benign": True},
            score=0.9,
            threshold=0.5,
            topology=topo,
        )
        == "fp"
    )
    # TN — synthetic_benign + below
    assert (
        derive_label(
            payload={"srcip": "10.0.0.99", "synthetic_benign": True},
            score=0.1,
            threshold=0.5,
            topology=topo,
        )
        == "tn"
    )
    # unknown — neither tagged
    assert (
        derive_label(payload={"srcip": "10.0.0.99"}, score=0.9, threshold=0.5, topology=topo)
        == "unknown"
    )
    # unknown — score is None
    assert (
        derive_label(payload={"srcip": "10.0.0.5"}, score=None, threshold=0.5, topology=topo)
        == "unknown"
    )


def test_multiplex_queue_drops_oldest() -> None:
    """Push N+1 frames into a queue of size N → first frame dropped, dropped
    counter increments by 1, newest frame is reachable last."""
    from strix_api.api.routes.streams import _MultiplexQueue

    q = _MultiplexQueue(maxsize=3)
    q.put({"i": 1})
    q.put({"i": 2})
    q.put({"i": 3})
    assert q.dropped_since_status == 0
    q.put({"i": 4})  # forces a drop
    assert q.dropped_since_status == 1
    assert q.qsize() == 3


@pytest.mark.asyncio
async def test_multiplex_queue_drops_oldest_under_load() -> None:
    """Push 1000 frames into a 500-slot queue → exactly 500 oldest dropped,
    last frame still reachable, get() returns frames in FIFO from current head."""
    from strix_api.api.routes.streams import _MultiplexQueue

    q = _MultiplexQueue(maxsize=500)
    for i in range(1000):
        q.put({"i": i})
    assert q.dropped_since_status == 500
    assert q.qsize() == 500
    head = await q.get(timeout=0.1)
    assert head is not None
    # Drop-oldest means the oldest 500 (i=0..499) were evicted; head should
    # be one of i ∈ [500, 999].
    assert head["i"] >= 500


# ---------------------------------------------------------------------------
# Integration test — TestClient WebSocket against a stubbed Redis pubsub
# ---------------------------------------------------------------------------


class _StubPubSub:
    def __init__(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._queue = queue
        self._closed = False

    async def subscribe(self, *channels: str) -> None:
        return None

    async def unsubscribe(self, *channels: str) -> None:
        return None

    async def aclose(self) -> None:
        self._closed = True

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        while not self._closed:
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except TimeoutError:
                if self._closed:
                    break
                continue
            yield msg


class _StubRedis:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def pubsub(self) -> _StubPubSub:
        return _StubPubSub(self.queue)

    async def aclose(self) -> None:
        return None


def _push(stub: _StubRedis, channel: str, payload: dict[str, Any]) -> None:
    stub.queue.put_nowait(
        {
            "type": "message",
            "channel": channel.encode("utf-8"),
            "data": json.dumps(payload).encode("utf-8"),
        }
    )


@pytest.fixture()
def app_and_stub() -> Any:
    """Fresh stub Redis + patched `redis.asyncio` per test. The handler does
    `from redis.asyncio import Redis` inside the function body, so swapping
    the module entry between tests is enough for isolation."""
    import sys

    from strix_api.api.routes import streams as streams_mod
    from strix_api.main import create_app

    stub = _StubRedis()

    class _RedisFactory:
        @staticmethod
        def from_url(*args: Any, **kwargs: Any) -> _StubRedis:
            return stub

    saved = sys.modules.get("redis.asyncio")

    class _FakeAsyncioMod:
        Redis = _RedisFactory  # type: ignore[assignment]

    sys.modules["redis.asyncio"] = _FakeAsyncioMod  # type: ignore[assignment]

    try:
        app = create_app()
        yield app, stub, streams_mod
    finally:
        if saved is not None:
            sys.modules["redis.asyncio"] = saved
        else:
            sys.modules.pop("redis.asyncio", None)


def test_websocket_connect_emits_connected_status(app_and_stub: Any) -> None:
    app, _stub, _ = app_and_stub
    client = TestClient(app)
    with client.websocket_connect("/api/v1/logs/stream") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "status"
        assert msg["payload"]["state"] == "connected"


def test_websocket_relays_each_envelope_type(app_and_stub: Any) -> None:
    app, stub, _ = app_and_stub
    client = TestClient(app)
    with client.websocket_connect("/api/v1/logs/stream") as ws:
        # Drain the initial status (and possibly topology).
        first = ws.receive_json()
        assert first["type"] == "status"

        # Push one frame on each per-model channel.
        _push(stub, "strix:sse:live-feed", {"alertId": "a1"})
        _push(stub, "strix:stream:ae", {"alert_id": "a1", "recon_error": 0.2})
        _push(stub, "strix:stream:vae", {"alert_id": "a1", "malicious_prob": 0.8})
        _push(stub, "strix:stream:gnn", {"alert_id": "a1", "node_risk": 0.9})
        _push(stub, "strix:stream:rl", {"alert_id": "a1", "action": 2})

        seen: set[str] = set()
        # Tolerate intervening `topology` / `heartbeat` frames.
        for _ in range(15):
            try:
                m = ws.receive_json()
            except Exception:
                break
            seen.add(m["type"])
            if {"raw_log", "ae", "vae", "gnn", "rl"}.issubset(seen):
                break

        for t in ("raw_log", "ae", "vae", "gnn", "rl"):
            assert t in seen, f"missing {t}; saw {seen}"


def test_backpressure_emits_dropped_status(app_and_stub: Any) -> None:
    """Stuff the per-client queue past capacity by pushing many frames before
    the websocket reads any of them, then assert we observe a `dropped:N`
    status frame and that the queue settles at max capacity."""
    app, stub, streams_mod = app_and_stub

    # Sanity check: queue size is the documented 500.
    assert streams_mod._WS_QUEUE_MAX == 500

    client = TestClient(app)
    with client.websocket_connect("/api/v1/logs/stream") as ws:
        # Drain initial status.
        ws.receive_json()
        # Flood — 1000 frames > 500 cap.
        for i in range(1000):
            _push(stub, "strix:stream:ae", {"alert_id": f"a{i}", "recon_error": 0.1})

        saw_dropped = False
        for _ in range(50):
            m = ws.receive_json()
            if (
                m["type"] == "status"
                and isinstance(m["payload"].get("state"), str)
                and m["payload"]["state"].startswith("dropped:")
            ):
                saw_dropped = True
                # N must be an integer > 0.
                n = int(m["payload"]["state"].split(":", 1)[1])
                assert n > 0
                break
        assert saw_dropped, "expected a `status: dropped:N` frame after flooding"
