"""Chaos tests against the toxiproxy compose extension.

Skipped automatically when `STRIX_CHAOS_REDIS_URL` is unset — every test
in this module is `pytest.mark.chaos`. Nightly CI starts the chaos compose
profile and runs these.

Scenarios (per §9.2):
  - Redis unavailable: workers retry with exponential backoff; API
    returns degraded-mode response (empty Live Feed + banner).
  - Redis slow (added latency): API still responds within budget.
  - Redis intermittent failures: dashboard endpoints fall back to
    empty-shape responses gracefully.
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [
    pytest.mark.chaos,
    pytest.mark.skipif(
        "STRIX_CHAOS_REDIS_URL" not in os.environ,
        reason="set STRIX_CHAOS_REDIS_URL to enable chaos tests",
    ),
]

TOXIPROXY = os.environ.get("STRIX_TOXIPROXY", "http://localhost:8474")
API_BASE = os.environ.get("STRIX_API_BASE", "http://localhost:8000")


def _toxic(name: str, attrs: dict[str, int]) -> dict:
    return {"name": name, "type": name, "stream": "downstream", "attributes": attrs}


@pytest.fixture
def latency_500ms_then_clear():
    """Inject 500ms latency into the redis-proxy, then remove on teardown."""
    with httpx.Client(timeout=5.0) as c:
        c.post(
            f"{TOXIPROXY}/proxies/redis-proxy/toxics",
            json=_toxic("latency", {"latency": 500, "jitter": 100}),
        )
        try:
            yield
        finally:
            c.delete(f"{TOXIPROXY}/proxies/redis-proxy/toxics/latency")


def test_dashboard_still_responds_under_redis_latency(latency_500ms_then_clear):
    """Even with 500ms Redis latency, the dashboard must respond <2s."""
    with httpx.Client(base_url=API_BASE, timeout=5.0) as c:
        r = c.get("/api/v1/dashboard/attack-vector")
        assert r.status_code == 200
        # 500ms toxic + budget — total still well under 2s.
        assert r.elapsed.total_seconds() < 2.0


def test_dashboard_falls_back_when_redis_down():
    """Drop the redis-proxy entirely; routes return empty shapes, not 500s."""
    with httpx.Client(timeout=5.0) as admin:
        admin.post(
            f"{TOXIPROXY}/proxies/redis-proxy",
            json={"enabled": False, "listen": "0.0.0.0:26379", "upstream": "redis:6379"},
        )
    try:
        with httpx.Client(base_url=API_BASE, timeout=5.0) as c:
            r = c.get("/api/v1/dashboard/attack-vector")
            assert r.status_code == 200
            body = r.json()
            assert body["totalAlerts"] == 0
    finally:
        with httpx.Client(timeout=5.0) as admin:
            admin.post(
                f"{TOXIPROXY}/proxies/redis-proxy",
                json={"enabled": True, "listen": "0.0.0.0:26379", "upstream": "redis:6379"},
            )
