"""Smoke tests that guard the Phase-0 scaffold.

Every test here must pass without Postgres, Redis, or any model file. Tests
that need real infra belong under `tests/integration/` and are marked
`@pytest.mark.integration`.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    # Provide the one required env var (DB password) so Settings boots.
    os.environ.setdefault("DB_PASSWORD", "test")
    from strix_api.main import create_app

    app = create_app()
    return TestClient(app)


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_openapi_is_served(client: TestClient) -> None:
    resp = client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["info"]["title"] == "STRIX API"
    # Phase-0 guarantees the stub routers are registered.
    paths = spec["paths"]
    assert "/api/v1/dashboard/attack-vector" in paths
    assert "/api/v1/dashboard/global-risk" in paths
    assert "/api/v1/monitoring/models" in paths


def test_alerts_route_live(client: TestClient) -> None:
    # As of M0-B1, /alerts is a real endpoint. With no DB initialised
    # (test sandbox), it falls back to an empty paginated shape.
    resp = client.get("/api/v1/alerts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["page"]["hasMore"] is False


def test_metrics_endpoint_exposed(client: TestClient) -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"# HELP" in resp.content


def test_dqn_action_invariants() -> None:
    """Domain enum guards: intervention threshold matches §5.4."""
    from strix_api.core.enums import DqnAction

    assert not DqnAction.MONITOR.is_intervention
    assert not DqnAction.LOW_ALERT.is_intervention
    assert DqnAction.ESCALATE.is_intervention
    assert DqnAction.ISOLATE_HOST.is_intervention
    assert DqnAction.BLOCK_USER_IP.is_intervention

    # §12 Q3: only ISOLATE_HOST + BLOCK_USER_IP require approval.
    assert DqnAction.ISOLATE_HOST.requires_approval
    assert DqnAction.BLOCK_USER_IP.requires_approval
    assert not DqnAction.ESCALATE.requires_approval


def test_core_has_no_outward_imports() -> None:
    """§3.4 dependency rule — core/ never imports api/, repos/, adapters/."""
    import pathlib

    core_root = pathlib.Path(__file__).resolve().parents[2] / "src" / "strix_api" / "core"
    forbidden = ("strix_api.api", "strix_api.repositories", "strix_api.adapters")
    for py in core_root.rglob("*.py"):
        text = py.read_text()
        for bad in forbidden:
            assert f"from {bad}" not in text and f"import {bad}" not in text, (
                f"{py} violates core/ isolation: imports {bad}"
            )
