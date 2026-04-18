"""Register endpoint — route contract + schema guarantees.

The register route is CSRF-exempt (sits under `/api/v1/auth/`) and
returns a full token pair so the client can land on the dashboard
without a second round-trip.

Unit tests here exercise the DB-less fallback path (no real Postgres
session) and the OpenAPI contract — DB-round-trip integration coverage
lives in the integration suite.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from strix_api.main import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def test_register_rejects_short_password(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "new@strix.local", "password": "short"},
    )
    # min_length=8 on RegisterRequest.password
    assert resp.status_code == 422


def test_register_rejects_bad_email(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "correcthorsebattery"},
    )
    assert resp.status_code == 422


def test_register_is_open_path(client: TestClient) -> None:
    """Register must be reachable without an access token — it's how the
    user gets one in the first place.
    """
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "new@strix.local",
            "password": "correcthorsebattery",
            "designation": "OP-ALPHA-7",
        },
    )
    # With DB unavailable we don't want a 401 back from the middleware —
    # that would mean register is auth-gated, which is wrong.
    assert resp.status_code != 401


def test_openapi_lists_register_path(client: TestClient) -> None:
    spec = client.get("/api/v1/openapi.json").json()
    paths = spec["paths"]
    assert "/api/v1/auth/register" in paths
    post = paths["/api/v1/auth/register"]["post"]
    # Route responds with TokenResponse, same shape as /login.
    responses = post["responses"]
    assert "201" in responses


def test_me_response_has_designation_field(client: TestClient) -> None:
    """Mobile profile screen binds to `designation`. Make sure the field
    stays declared in OpenAPI so the TS types stay in sync.
    """
    spec = client.get("/api/v1/openapi.json").json()
    me_schema = spec["components"]["schemas"]["MeResponse"]
    assert "designation" in me_schema["properties"]
    assert "designation" not in me_schema.get("required", [])


def test_register_request_password_min_length() -> None:
    """Password policy must stay ≥8 chars. Guards against a well-meaning
    relaxation slipping into the schema.
    """
    from strix_api.api.schemas.auth import RegisterRequest

    with pytest.raises(ValueError):
        RegisterRequest(email="a@b.co", password="1234567")
    # 8 chars — valid
    r = RegisterRequest(email="a@b.co", password="12345678")
    assert r.password == "12345678"


def test_email_already_registered_error_status() -> None:
    """Regression guard — must be a 409, not a 401, so the mobile/web
    clients can display "email taken" rather than "bad credentials".
    """
    from strix_api.services.auth import EmailAlreadyRegisteredError

    assert EmailAlreadyRegisteredError.status_code == 409
    assert EmailAlreadyRegisteredError.code == "EMAIL_ALREADY_REGISTERED"
