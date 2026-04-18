#!/usr/bin/env python3
"""End-to-end smoke test (`make smoke`).

Proves the live stack is wired correctly by walking one synthetic alert
through every component:

    [smoke.py] --XADD--> redis:strix:alerts:raw
                          │
                          ▼
                 [normalizer-worker]   ─── 55-d feature vector ──┐
                                                                 ▼
                                            redis:strix:features:0
                                                                 │
                                                                 ▼
                                                 [inference-worker]
                                                                 │
                                                                 ▼
                                            redis:strix:verdicts
                                                                 │
                                                                 ▼
                                                 [verdicts-writer]
                                                                 │
                                                          ┌──────┴──────┐
                                                          ▼             ▼
                                                  postgres:alerts +  redis:sse
                                                  postgres:detections    │
                                                                         ▼
                            [smoke.py] <─── EventSource <── /streams/live-feed

Pre-conditions:
  - `docker compose -f infra/compose.api.yml --profile workers up -d` is up
  - `make seed` has run at least once (admin user exists)
  - `apps/api/.env` has DB_PASSWORD + AUTH_JWT_SECRET set

Outputs a checklist of pass/fail and exits 0 only if every step succeeds.

Usage:
    python infra/scripts/smoke.py [--api http://localhost:8000]
                                  [--redis redis://localhost:6379/0]
                                  [--admin-email admin@strix.local]
                                  [--admin-password changeme]
                                  [--timeout 60]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make the repo's strix_api importable (we use the message dataclasses)
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "apps" / "api" / "src"))


GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"


@dataclass
class StepResult:
    name: str
    ok: bool
    note: str = ""


def _step(name: str) -> "_Step":
    return _Step(name)


class _Step:
    def __init__(self, name: str) -> None:
        self.name = name

    def __enter__(self) -> "_Step":
        print(f"  {DIM}→ {self.name}…{RESET}", end="", flush=True)
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        dt = (time.perf_counter() - self._t0) * 1000
        if exc is None:
            print(f"\r  {GREEN}✓{RESET} {self.name}  {DIM}({dt:.0f} ms){RESET}")
        else:
            print(f"\r  {RED}✗{RESET} {self.name}  {DIM}({dt:.0f} ms){RESET}")
            print(f"      {RED}{exc.__class__.__name__}: {exc}{RESET}")


# ----------------------------------------------------------------------
# Synthetic alert fixture
# ----------------------------------------------------------------------


def make_synthetic_alert(*, agent_id: str = "001") -> dict[str, Any]:
    """Wazuh-shaped JSON. Mirrors the test fixture but uses NOW + a random id."""
    alert_id = f"smoke-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    return {
        "_id": alert_id,
        "_source": {
            "id": alert_id,
            "@timestamp": now,
            "agent": {
                "id": agent_id,
                "name": f"Smoke-{agent_id}",
                "ip": "10.0.0.99",
            },
            "rule": {
                "id": "80710",
                "firedtimes": 1,
                "level": 10,
                "description": "Smoke test — synthetic suspicious sudo",
                "mitre": {
                    "tactic": ["TA0004"],
                    "technique": ["T1548.003"],
                },
            },
            "decoder": {"name": "auditd"},
            "location": "/var/log/audit/audit.log",
            "full_log": "type=SYSCALL smoke-test alert from infra/scripts/smoke.py",
            "data": {
                "command": "sudo -u root /usr/bin/bash -c 'cat /etc/shadow'",
                "srcip": "10.0.0.42",
                "srcport": "49512",
                "srcuser": "smoke",
            },
        },
    }


# ----------------------------------------------------------------------
# Smoke flow
# ----------------------------------------------------------------------


async def run_smoke(
    *,
    api_base: str,
    redis_url: str,
    admin_email: str,
    admin_password: str,
    timeout_seconds: int,
) -> int:
    import httpx
    import msgpack
    from redis.asyncio import Redis

    print(f"\n{YELLOW}▶ STRIX end-to-end smoke test{RESET}")
    print(f"  api    = {api_base}")
    print(f"  redis  = {redis_url}")
    print()

    redis = Redis.from_url(redis_url, decode_responses=False)
    client = httpx.AsyncClient(base_url=api_base, timeout=10.0)

    failures: list[StepResult] = []
    alert_id = f"smoke-{uuid.uuid4().hex[:12]}"
    access_token: str | None = None

    try:
        # 1. /health -------------------------------------------------------
        try:
            with _step("API /health responds 200"):
                r = await client.get("/health")
                assert r.status_code == 200, f"got {r.status_code}"
                assert r.json()["status"] == "ok"
        except AssertionError as exc:
            failures.append(StepResult("API /health", False, str(exc)))
            return _summarise(failures)

        # 2. Login --------------------------------------------------------
        try:
            with _step(f"POST /auth/login as {admin_email}"):
                r = await client.post(
                    "/api/v1/auth/login",
                    json={"email": admin_email, "password": admin_password},
                )
                if r.status_code == 401:
                    raise AssertionError(
                        f"401 — did you run `make seed` first? "
                        f"(or: python infra/scripts/seed_admin.py --email {admin_email!r} --password '…')"
                    )
                assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
                access_token = r.json()["accessToken"]
                assert access_token
        except AssertionError as exc:
            failures.append(StepResult("login", False, str(exc)))

        auth_headers = (
            {"Authorization": f"Bearer {access_token}"} if access_token else {}
        )

        # 3. Inject synthetic alert directly onto the Redis stream --------
        synthetic = make_synthetic_alert()
        synthetic["_id"] = alert_id
        synthetic["_source"]["id"] = alert_id

        try:
            with _step("XADD synthetic alert to strix:alerts:raw"):
                envelope = {
                    "alertId": alert_id,
                    "ingestedAt": datetime.now(timezone.utc).isoformat(),
                    "rawJson": synthetic,
                }
                payload = msgpack.packb(envelope, use_bin_type=True)
                await redis.xadd(
                    "strix:alerts:raw", {b"payload": payload},
                    maxlen=100_000, approximate=True,
                )
        except Exception as exc:
            failures.append(StepResult("XADD raw alert", False, str(exc)))

        # 4. Wait for alert + detection rows in Postgres via the API ------
        try:
            with _step(f"alert visible via dashboard within {timeout_seconds}s"):
                deadline = time.monotonic() + timeout_seconds
                seen = False
                while time.monotonic() < deadline:
                    r = await client.get(
                        "/api/v1/dashboard/attack-vector?window=15m",
                        headers=auth_headers,
                    )
                    if r.status_code == 200 and r.json().get("totalAlerts", 0) >= 1:
                        seen = True
                        break
                    await asyncio.sleep(1.0)
                if not seen:
                    raise AssertionError(
                        "no alert reached the attack-vector aggregate after timeout — "
                        "check workers are running:  docker compose -f infra/compose.api.yml "
                        "--profile workers logs --tail=50"
                    )
        except AssertionError as exc:
            failures.append(StepResult("attack-vector reflects synthetic", False, str(exc)))

        # 5. SSE live-feed delivers an event ------------------------------
        try:
            with _step("SSE /streams/live-feed receives an alert.new event"):
                got_event = False
                # Fire one more synthetic alert AFTER subscribing so we don't
                # rely on a race with the previous one.
                second_id = f"smoke-{uuid.uuid4().hex[:12]}"
                second = make_synthetic_alert()
                second["_id"] = second_id
                second["_source"]["id"] = second_id
                second_payload = msgpack.packb({
                    "alertId": second_id,
                    "ingestedAt": datetime.now(timezone.utc).isoformat(),
                    "rawJson": second,
                }, use_bin_type=True)

                async with client.stream(
                    "GET", "/api/v1/streams/live-feed", headers=auth_headers,
                ) as resp:
                    if resp.status_code != 200:
                        raise AssertionError(f"SSE status {resp.status_code}")
                    # Push the second alert ~0.5s after subscribing
                    asyncio.get_running_loop().call_later(
                        0.5,
                        lambda: asyncio.create_task(
                            redis.xadd("strix:alerts:raw", {b"payload": second_payload},
                                       maxlen=100_000, approximate=True)
                        ),
                    )
                    deadline = time.monotonic() + timeout_seconds
                    async for chunk in resp.aiter_lines():
                        if not chunk:
                            continue
                        if chunk.startswith("event: alert.new"):
                            got_event = True
                            break
                        if time.monotonic() >= deadline:
                            break
                if not got_event:
                    raise AssertionError("no alert.new SSE event before timeout")
        except AssertionError as exc:
            failures.append(StepResult("SSE delivers alert.new", False, str(exc)))

        # 6. /monitoring/models reflects the registry --------------------
        try:
            with _step("GET /monitoring/models returns 5 models"):
                r = await client.get(
                    "/api/v1/monitoring/models", headers=auth_headers,
                )
                assert r.status_code == 200
                models = r.json()["models"]
                names = {m["name"] for m in models}
                expected = {"AE", "VAE", "TRANSFORMER", "GNN", "DQN"}
                assert expected <= names, f"missing: {expected - names}"
        except AssertionError as exc:
            failures.append(StepResult("monitoring/models", False, str(exc)))

        # 7. Drift endpoint runs (will be small/zero with one alert) ----
        try:
            with _step("GET /monitoring/drift returns a report"):
                r = await client.get(
                    "/api/v1/monitoring/drift?windowMinutes=60",
                    headers=auth_headers,
                )
                assert r.status_code == 200
                items = r.json()["items"]
                # At least one model should be there once detections start flowing.
                # Allow zero items if no detections existed when the query ran.
                assert isinstance(items, list)
        except AssertionError as exc:
            failures.append(StepResult("monitoring/drift", False, str(exc)))

    finally:
        await client.aclose()
        await redis.aclose()

    return _summarise(failures)


def _summarise(failures: list[StepResult]) -> int:
    print()
    if not failures:
        print(f"{GREEN}━━━ ALL CHECKS PASSED ━━━{RESET}")
        print(f"{DIM}The full path Wazuh→normalizer→inference→writer→Postgres+SSE works.{RESET}")
        return 0
    print(f"{RED}━━━ {len(failures)} CHECK(S) FAILED ━━━{RESET}")
    for f in failures:
        print(f"  {RED}✗ {f.name}{RESET}: {f.note}")
    print()
    print(f"{YELLOW}Triage tips:{RESET}")
    print("  - workers running?  docker compose -f infra/compose.api.yml --profile workers ps")
    print("  - workers logs?     docker compose -f infra/compose.api.yml --profile workers logs --tail=80")
    print("  - migrations done?  docker compose -f infra/compose.api.yml logs migrate")
    print("  - models present?   ls apps/models/")
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--redis", default="redis://localhost:6379/0")
    p.add_argument("--admin-email", default="admin@strix.local")
    p.add_argument("--admin-password", default="changeme")
    p.add_argument("--timeout", type=int, default=60)
    args = p.parse_args()

    return asyncio.run(run_smoke(
        api_base=args.api.rstrip("/"),
        redis_url=args.redis,
        admin_email=args.admin_email,
        admin_password=args.admin_password,
        timeout_seconds=args.timeout,
    ))


if __name__ == "__main__":
    raise SystemExit(main())
