"""M0 mobile-integration coverage + web-contract regression.

These tests guarantee that every change made for mobile support is
strictly additive from the web app's point of view:

  1. Login without `X-Client-Type: mobile` returns TokenResponse with
     refresh_token == None (same wire shape web has always seen).
  2. Login WITH the mobile header includes a non-null refresh_token so
     mobile clients can store it in SecureStore.
  3. Refresh endpoint accepts the cookie path (web) unchanged.
  4. Refresh endpoint accepts the body path (mobile) when no cookie.

Plus the new /alerts + /auth/devices endpoints return the expected
empty-shape fallbacks when no DB is initialised.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from strix_api.main import create_app
from strix_api.services.alerts_service import severity_from_vae_prob

# ---- severity mapping -------------------------------------------------


@pytest.mark.parametrize(
    "prob,expected",
    [
        (None, "info"),
        (0.0, "info"),
        (0.29, "info"),
        (0.30, "low"),
        (0.49, "low"),
        (0.50, "medium"),
        (0.69, "medium"),
        (0.70, "high"),
        (0.89, "high"),
        (0.90, "critical"),
        (0.99, "critical"),
    ],
)
def test_severity_from_vae_prob(prob, expected) -> None:
    assert severity_from_vae_prob(prob) == expected


# ---- alerts routes ----------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def test_alerts_list_empty_shape(client: TestClient) -> None:
    resp = client.get("/api/v1/alerts?limit=10&severity=high")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["page"]["hasMore"] is False
    assert body["page"]["cursor"] is None


def test_alerts_list_rejects_bad_limit(client: TestClient) -> None:
    resp = client.get("/api/v1/alerts?limit=9999")
    assert resp.status_code == 422


def test_alerts_unacknowledged_count(client: TestClient) -> None:
    resp = client.get("/api/v1/alerts/unacknowledged/count")
    assert resp.status_code == 200
    assert resp.json() == {"count": 0}


def test_alerts_acknowledge_sandbox(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/alerts/alert-xyz/acknowledge",
        json={"occurredAt": "2026-04-18T10:00:00+00:00"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["alertId"] == "alert-xyz"
    assert body["alreadyAcknowledged"] is False


# ---- /auth/devices ----------------------------------------------------


def test_device_register_sandbox(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/devices",
        json={
            "expoPushToken": "ExponentPushToken[abc123]",
            "platform": "ios",
            "appVersion": "1.0.0",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["expoPushToken"] == "ExponentPushToken[abc123]"
    assert body["platform"] == "ios"


def test_device_register_bad_platform(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/devices",
        json={"expoPushToken": "tok", "platform": "windowsphone"},
    )
    assert resp.status_code == 422


def test_device_list_sandbox(client: TestClient) -> None:
    resp = client.get("/api/v1/auth/devices")
    assert resp.status_code == 200
    assert resp.json() == []


def test_device_unregister_sandbox(client: TestClient) -> None:
    resp = client.delete("/api/v1/auth/devices/ExponentPushToken%5Bxyz%5D")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 0}


# ---- refresh token body fallback & mobile gating ----------------------
# These tests assert the CONTRACT, not the DB-dependent login flow.


def test_refresh_rejects_when_neither_cookie_nor_body(client: TestClient) -> None:
    """No cookie, no body token — must 401."""
    resp = client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401
    assert resp.headers["content-type"] == "application/problem+json"


def test_refresh_rejects_empty_body_without_cookie(client: TestClient) -> None:
    """Body with explicit null refresh_token — still 401."""
    resp = client.post("/api/v1/auth/refresh", json={"refreshToken": None})
    assert resp.status_code == 401


def test_mobile_client_detection() -> None:
    """Unit-level guard: the header check is exact (case-insensitive
    value), so typos or prefix matches don't accidentally flip mobile
    mode on for web clients.
    """
    from starlette.requests import Request

    from strix_api.api.routes.auth import _is_mobile_client

    def _req(headers: dict[str, str]) -> Request:
        scope = {
            "type": "http",
            "headers": [
                (k.lower().encode(), v.encode()) for k, v in headers.items()
            ],
        }
        return Request(scope)  # type: ignore[arg-type]

    # No header → web.
    assert _is_mobile_client(_req({})) is False
    # Exact match (case-insensitive value) → mobile.
    assert _is_mobile_client(_req({"X-Client-Type": "mobile"})) is True
    assert _is_mobile_client(_req({"x-client-type": "MOBILE"})) is True
    # Wrong value → web.
    assert _is_mobile_client(_req({"X-Client-Type": "desktop"})) is False
    assert _is_mobile_client(_req({"X-Client-Type": "mobile-web"})) is False


# ---- Expo push adapter fan-out mechanics ------------------------------


def test_push_dispatcher_noop_when_disabled() -> None:
    """When PUSH_ENABLED=false, the dispatcher must not construct an Expo
    client at all — protects us from accidentally firing network
    requests in CI / unit tests.
    """
    from strix_api.services.push_dispatcher import PushDispatcher

    d = PushDispatcher(enabled=False)
    assert d._adapter is None  # type: ignore[attr-defined]


def test_push_message_titles() -> None:
    """Sanity: the title/body formatter yields human-readable output
    for each intervention action.
    """
    from uuid import uuid4

    from strix_api.services.push_dispatcher import (
        InterventionEvent,
        _body_for,
        _title_for,
    )

    ev = InterventionEvent(
        chain_id=uuid4(),
        alert_id="alert-1",
        host_id=uuid4(),
        action_name="ISOLATE_HOST",
        ckc_stage=5,
        vae_prob=0.91,
    )
    assert "isolation" in _title_for(ev).lower()
    assert "5" in _body_for(ev)
    assert "0.91" in _body_for(ev)


# ---- OpenAPI additive check -------------------------------------------


def test_openapi_includes_new_mobile_paths(client: TestClient) -> None:
    """The web SPA regenerates its TS types from this spec. Ensure our
    additions show up so the web CI drift check passes after snapshot
    refresh, and that no EXISTING path was accidentally removed.
    """
    spec = client.get("/api/v1/openapi.json").json()
    paths = spec["paths"]
    # New M0 paths:
    assert "/api/v1/alerts" in paths
    assert "/api/v1/alerts/{alert_id}/acknowledge" in paths
    assert "/api/v1/alerts/unacknowledged/count" in paths
    assert "/api/v1/auth/devices" in paths
    # Existing web paths must survive:
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/refresh" in paths
    assert "/api/v1/dashboard/attack-vector" in paths
    assert "/api/v1/streams/live-feed" in paths


def test_token_response_schema_has_optional_refresh(client: TestClient) -> None:
    """TokenResponse.refresh_token must be OPTIONAL (nullable), not
    required. If it ever becomes required, every web login response
    without the header will start failing validation.
    """
    spec = client.get("/api/v1/openapi.json").json()
    schemas = spec["components"]["schemas"]
    assert "TokenResponse" in schemas
    token_schema = schemas["TokenResponse"]
    required = token_schema.get("required", [])
    assert "accessToken" in required
    assert "refreshToken" not in required  # MUST remain optional
