"""Phase-2 dashboard endpoints — empty but valid shapes."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DB_PASSWORD", "test")
    from strix_api.main import create_app
    return TestClient(create_app())


def test_attack_vector_returns_8_stages(client: TestClient) -> None:
    resp = client.get("/api/v1/dashboard/attack-vector")
    assert resp.status_code == 200
    body = resp.json()
    assert body["window"] == "1h"
    assert body["totalAlerts"] == 0
    assert len(body["stages"]) == 8
    # Stages are ordered 0..7 and named per CkcStage (0=BENIGN, 1..7=attack)
    expected_names = (
        "BENIGN", "RECONNAISSANCE", "WEAPONIZATION", "DELIVERY",
        "EXPLOITATION", "INSTALLATION", "COMMAND_AND_CONTROL", "ACTIONS_ON_OBJECTIVES",
    )
    for i, stage in enumerate(body["stages"]):
        assert stage["ckcStage"] == i
        assert stage["ckcName"] == expected_names[i]
        assert stage["count"] == 0
        assert stage["percent"] == 0.0


def test_attack_vector_window_param_echoed(client: TestClient) -> None:
    resp = client.get("/api/v1/dashboard/attack-vector?window=24h")
    assert resp.status_code == 200
    assert resp.json()["window"] == "24h"


def test_attack_vector_rejects_unknown_window(client: TestClient) -> None:
    resp = client.get("/api/v1/dashboard/attack-vector?window=42m")
    assert resp.status_code == 422


def test_global_risk_default_window(client: TestClient) -> None:
    resp = client.get("/api/v1/dashboard/global-risk")
    assert resp.status_code == 200
    body = resp.json()
    assert body["window"] == "1h"
    assert body["globalRisk"] == 0.0
    assert body["components"]["vaeMeanProb"] == 0.0
    assert body["trend"] == []


def test_victim_graph_empty(client: TestClient) -> None:
    resp = client.get("/api/v1/dashboard/victim-graph?window=24h")
    assert resp.status_code == 200
    body = resp.json()
    assert body["window"] == "24h"
    assert body["nodes"] == []
    assert body["edges"] == []


def test_sentinel_insight_marked_stale(client: TestClient) -> None:
    """Phase 7 wires the LLM, but the sandbox has no DB — the route returns
    a placeholder with `stale: true` so the dashboard card renders something
    instead of erroring."""
    resp = client.get("/api/v1/dashboard/sentinel-insight")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stale"] is True
    assert body["confidence"] == 0.0
    assert body["modelVersion"] == "placeholder"
