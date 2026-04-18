"""Auto-response kill switch (P8-8)."""

from __future__ import annotations

import os
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from strix_api.services.kill_switch import KillSwitchService

# ---- service-level (in-memory fake redis) ----------------------------


class _FakeRedis:
    """Tiny stand-in that supports the subset of Redis ops KillSwitchService uses."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str):
        v = self._store.get(key)
        return v.encode() if v is not None else None

    def pipeline(self, transaction: bool = False):  # noqa: ARG002
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, parent: _FakeRedis) -> None:
        self._parent = parent
        self._queue: list[tuple[str, ...]] = []

    async def __aenter__(self) -> _FakePipeline:
        return self

    async def __aexit__(self, *a) -> None:
        pass

    async def set(self, key: str, value: str) -> None:
        self._queue.append(("set", key, value))

    async def execute(self) -> None:
        for op in self._queue:
            if op[0] == "set":
                self._parent._store[op[1]] = op[2]
        self._queue.clear()


@pytest.mark.asyncio
async def test_default_state_is_engaged_for_safety() -> None:
    """A fresh deploy must default to ENGAGED — no auto-apply on day 1."""
    svc = KillSwitchService(_FakeRedis())
    assert await svc.is_engaged() is True


@pytest.mark.asyncio
async def test_engage_disengage_roundtrip() -> None:
    redis = _FakeRedis()
    svc = KillSwitchService(redis)
    await svc.disengage(by="test-user")
    assert await svc.is_engaged() is False
    state = await svc.state()
    assert state.set_by == "test-user"

    await svc.engage(by="test-user-2")
    assert await svc.is_engaged() is True


@pytest.mark.asyncio
async def test_engage_records_metadata() -> None:
    redis = _FakeRedis()
    svc = KillSwitchService(redis)
    await svc.engage(by="op-1")
    state = await svc.state()
    assert state.engaged is True
    assert state.set_by == "op-1"
    # Set timestamp parses as ISO-8601 UTC
    assert state.set_at is not None
    parsed = datetime.fromisoformat(state.set_at.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


@pytest.mark.asyncio
async def test_explicit_off_string_is_disengaged() -> None:
    """'off', '0', 'false' all count as disengaged for ops convenience."""
    redis = _FakeRedis()
    redis._store["strix:auto_response:kill_switch"] = "off"
    assert await KillSwitchService(redis).is_engaged() is False
    redis._store["strix:auto_response:kill_switch"] = "0"
    assert await KillSwitchService(redis).is_engaged() is False
    redis._store["strix:auto_response:kill_switch"] = "false"
    assert await KillSwitchService(redis).is_engaged() is False


# ---- route-level ------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DB_PASSWORD", "test")
    from strix_api.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def test_admin_routes_registered(client: TestClient) -> None:
    """The kill-switch endpoints exist (auth gating tested separately)."""
    spec = client.get("/api/v1/openapi.json").json()
    paths = spec["paths"]
    assert "/api/v1/admin/kill-switch" in paths
    assert "post" in paths["/api/v1/admin/kill-switch"]
    assert "get" in paths["/api/v1/admin/kill-switch"]


def test_admin_routes_marked_with_admin_dependency(client: TestClient) -> None:
    """In dev (sandbox), the dev-skip principal is admin so we can call them."""
    resp = client.get("/api/v1/admin/kill-switch")
    # The route reaches Redis, fails (no Redis in sandbox) → 500 response.
    # That's acceptable for this test — we just want to confirm the route
    # passes RBAC gating rather than 401/403'ing first.
    assert resp.status_code != 401
    assert resp.status_code != 403
