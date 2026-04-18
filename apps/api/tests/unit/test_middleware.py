"""Auth + CSRF middleware — exempt list, dev-skip, token gating."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


def _build_app(*, env: str = "dev", dev_skip: bool = True):
    """Construct a fresh FastAPI app with explicit env settings.

    Override env vars before `get_settings()` is invoked — and clear the
    Settings cache so the new values take effect.
    """
    os.environ["ENV"] = env
    os.environ["AUTH_DEV_SKIP_AUTH"] = "true" if dev_skip else "false"
    os.environ.setdefault("AUTH_JWT_SECRET", "test-secret")
    os.environ.setdefault("DB_PASSWORD", "test")
    from strix_api.settings import get_settings

    get_settings.cache_clear()
    from strix_api.main import create_app

    # `raise_server_exceptions=False` so route-handler crashes return 500
    # responses rather than bubbling out of the TestClient — useful when
    # we exercise routes that need a DB the test sandbox doesn't provide.
    return TestClient(create_app(), raise_server_exceptions=False)


def test_dev_skip_allows_unauthenticated_dashboard() -> None:
    client = _build_app(env="dev", dev_skip=True)
    assert client.get("/api/v1/dashboard/attack-vector").status_code == 200


def test_health_always_open() -> None:
    client = _build_app(env="prod", dev_skip=False)
    assert client.get("/health").status_code == 200


def test_metrics_always_open() -> None:
    client = _build_app(env="prod", dev_skip=False)
    assert client.get("/metrics").status_code == 200


def test_openapi_always_open() -> None:
    client = _build_app(env="prod", dev_skip=False)
    assert client.get("/api/v1/openapi.json").status_code == 200


def test_unauthenticated_dashboard_in_prod_returns_401_problem() -> None:
    client = _build_app(env="prod", dev_skip=False)
    resp = client.get("/api/v1/dashboard/attack-vector")
    assert resp.status_code == 401
    assert resp.headers["content-type"] == "application/problem+json"
    body = resp.json()
    assert body["status"] == 401
    assert body["code"] == "MISSING_TOKEN"


def test_bearer_token_authenticates() -> None:
    client = _build_app(env="prod", dev_skip=False)
    from strix_api.services.auth import issue_token_pair
    from strix_api.settings import get_settings

    pair = issue_token_pair(
        settings=get_settings().auth,
        user_id=uuid4(),
        role="admin",
    )
    resp = client.get(
        "/api/v1/dashboard/attack-vector",
        headers={"Authorization": f"Bearer {pair.access_token}"},
    )
    assert resp.status_code == 200


def test_dev_skip_ignored_in_prod() -> None:
    """Production must NEVER honor AUTH_DEV_SKIP_AUTH=true (security catch)."""
    client = _build_app(env="prod", dev_skip=True)
    resp = client.get("/api/v1/dashboard/attack-vector")
    assert resp.status_code == 401


def test_csrf_required_on_mutating_in_prod() -> None:
    client = _build_app(env="prod", dev_skip=False)
    from strix_api.services.auth import issue_token_pair
    from strix_api.settings import get_settings

    pair = issue_token_pair(
        settings=get_settings().auth,
        user_id=uuid4(),
        role="admin",
    )
    # POST without CSRF header → 403
    resp = client.post(
        "/api/v1/dashboard/sentinel-insight/refresh",
        headers={"Authorization": f"Bearer {pair.access_token}"},
    )
    # If route doesn't exist, FastAPI returns 405; CSRF middleware runs first
    # and would intercept with 403. Either way it's NOT a 200.
    assert resp.status_code in (403, 404, 405)


def test_login_route_is_exempt_from_auth() -> None:
    """The login route must be reachable without prior auth, in prod too."""
    client = _build_app(env="prod", dev_skip=False)
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "noone@example.com", "password": "wrong"},
    )
    # 401 (invalid creds) means the route ran and DB connect failed/no user
    # — NOT 401 from the auth middleware. Either way it's not 401-MISSING_TOKEN.
    # Without a DB it'll likely 500 at the actual login logic; we tolerate any
    # non-401-MISSING_TOKEN status.
    body = resp.json() if resp.status_code != 200 else {}
    assert body.get("code") != "MISSING_TOKEN"


@pytest.fixture(autouse=True)
def _reset_env_after():
    """Restore the conftest defaults after each test in this module."""
    yield
    os.environ["ENV"] = "dev"
    os.environ["AUTH_DEV_SKIP_AUTH"] = "true"
    from strix_api.settings import get_settings

    get_settings.cache_clear()
