"""Phase-5 analysis routes — fall-through-to-empty + cursor encoding."""

from __future__ import annotations

import os
from datetime import UTC
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from strix_api.services.analysis_service import _LogCursor


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DB_PASSWORD", "test")
    from strix_api.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def test_chain_list_returns_empty_shape_without_db(client: TestClient) -> None:
    resp = client.get("/api/v1/analysis/chains")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"items": [], "openCount": 0}


def test_chain_list_rejects_invalid_limit(client: TestClient) -> None:
    resp = client.get("/api/v1/analysis/chains?limit=99999")
    assert resp.status_code == 422


def test_chain_detail_endpoints_return_200_empty_without_db(client: TestClient) -> None:
    chain_id = uuid4()
    paths = [
        f"/api/v1/analysis/chains/{chain_id}/graph-evolution",
        f"/api/v1/analysis/chains/{chain_id}/ckc-progression",
        f"/api/v1/analysis/chains/{chain_id}/predictions",
        f"/api/v1/analysis/chains/{chain_id}/logs",
        f"/api/v1/analysis/chains/{chain_id}/infection",
        f"/api/v1/analysis/chains/{chain_id}/dwell-time",
    ]
    for path in paths:
        resp = client.get(path)
        assert resp.status_code == 200, path
        body = resp.json()
        assert body["chainId"] == str(chain_id), path


def test_chain_detail_rejects_invalid_uuid(client: TestClient) -> None:
    resp = client.get("/api/v1/analysis/chains/not-a-uuid/dwell-time")
    assert resp.status_code == 422


def test_logs_paginate_shape(client: TestClient) -> None:
    chain_id = uuid4()
    resp = client.get(f"/api/v1/analysis/chains/{chain_id}/logs?limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["page"] == {"cursor": None, "hasMore": False}


# ---- log cursor encoding -----------------------------------------------


def test_log_cursor_roundtrip() -> None:
    from datetime import datetime

    cursor = _LogCursor(
        occurred_at=datetime(2026, 4, 18, 12, 34, 56, 123456, tzinfo=UTC),
        alert_id="abc-XYZ-123",
    )
    decoded = _LogCursor.decode(cursor.encode())
    assert decoded.occurred_at == cursor.occurred_at
    assert decoded.alert_id == cursor.alert_id


def test_log_cursor_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        _LogCursor.decode("not-base64!!!@@@")
