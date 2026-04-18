#!/usr/bin/env python3
"""Mobile-contract smoke test (`make smoke-mobile`).

Validates every piece of the mobile integration path against the live
backend — without needing the React Native stack or a real device.

What it proves, in order:

    1. POST /auth/register with `X-Client-Type: mobile` returns 201 AND
       the response body carries a refresh_token (the M0-B4 contract).
       Without it, mobile clients would have no way to re-auth after
       the 15-minute access token expires.

    2. GET /auth/me with the Bearer token returns `designation` (M4-A1).

    3. POST /auth/devices registers a synthetic Expo push token.
       Subsequent GET /auth/devices must return the row, then
       DELETE /auth/devices/{token} clears it.

    4. POST /auth/refresh with a body (no cookie) returns a fresh
       access token — the M0-B3 mobile fallback path.

    5. Representative authenticated calls on Bearer:
         GET /dashboard/attack-vector
         GET /alerts

    6. Live-feed SSE handshake — opens the stream, reads the initial
       'open' event, closes. Doesn't wait for a real verdict (that's
       covered by `make smoke`); just proves auth + content-type are
       correct.

    7. POST /auth/logout teardown.

Exits 0 only if every step passes. Suitable for CI as well as local
dev — runs in under 10 seconds against a warm stack.

Usage:
    python infra/scripts/smoke_mobile.py [--api http://localhost:8000]
                                          [--timeout 15]
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
import time
import uuid
from dataclasses import dataclass

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


MOBILE_HEADERS = {"X-Client-Type": "mobile"}


async def run(
    *,
    api_base: str,
    timeout_seconds: int,
) -> int:
    import httpx

    print(f"\n{YELLOW}▶ STRIX mobile-contract smoke test{RESET}")
    print(f"  api = {api_base}")
    print()

    failures: list[StepResult] = []

    # Brand-new analyst every run — avoids conflicts with prior runs
    # and with the seeded admin.
    email = f"mobile-smoke-{uuid.uuid4().hex[:10]}@strix.local"
    password = secrets.token_urlsafe(16)
    designation = "OP-MOBILE-SMOKE"
    fake_expo_token = f"ExponentPushToken[smoke-{uuid.uuid4().hex[:12]}]"

    access_token: str | None = None
    refresh_token: str | None = None

    async with httpx.AsyncClient(
        base_url=api_base, timeout=float(timeout_seconds),
    ) as client:
        # 1. health
        try:
            with _Step("API /health responds 200"):
                r = await client.get("/health")
                assert r.status_code == 200, f"got {r.status_code}"
        except Exception as exc:
            failures.append(StepResult("health", False, str(exc)))
            return _summarise(failures)

        # 2. Register a fresh analyst (mobile path)
        try:
            with _Step(f"POST /auth/register (X-Client-Type: mobile)"):
                r = await client.post(
                    "/api/v1/auth/register",
                    json={
                        "email": email,
                        "password": password,
                        "designation": designation,
                    },
                    headers=MOBILE_HEADERS,
                )
                assert r.status_code == 201, f"got {r.status_code}: {r.text[:200]}"
                body = r.json()
                access_token = body.get("accessToken")
                refresh_token = body.get("refreshToken")
                assert access_token, "missing accessToken"
                assert refresh_token, (
                    "missing refreshToken — mobile contract violated! "
                    "backend must populate refresh_token when X-Client-Type=mobile"
                )
        except Exception as exc:
            failures.append(StepResult("register", False, str(exc)))
            return _summarise(failures)

        # 3. Web-safety regression — same register WITHOUT the mobile
        #    header must NOT leak a refresh token in the body. Using a
        #    different email so we don't trip the 409.
        try:
            with _Step("register without mobile header omits refreshToken"):
                alt_email = f"web-smoke-{uuid.uuid4().hex[:10]}@strix.local"
                r = await client.post(
                    "/api/v1/auth/register",
                    json={"email": alt_email, "password": password},
                )
                assert r.status_code == 201
                web_body = r.json()
                assert web_body.get("accessToken"), "missing accessToken"
                assert web_body.get("refreshToken") in (None, "", False), (
                    f"web client leaked refresh_token in body: "
                    f"{web_body.get('refreshToken')!r} — this breaks the "
                    f"httpOnly cookie contract"
                )
        except Exception as exc:
            failures.append(StepResult("web-safety", False, str(exc)))

        auth_headers = {
            "Authorization": f"Bearer {access_token}",
            **MOBILE_HEADERS,
        }

        # 4. /auth/me returns designation
        try:
            with _Step("GET /auth/me includes designation"):
                r = await client.get("/api/v1/auth/me", headers=auth_headers)
                assert r.status_code == 200, f"got {r.status_code}"
                me = r.json()
                assert me["email"] == email
                assert me["role"] == "analyst", f"expected analyst, got {me['role']}"
                assert me.get("designation") == designation, (
                    f"designation not stored; got {me.get('designation')!r}"
                )
        except Exception as exc:
            failures.append(StepResult("me", False, str(exc)))

        # 5. Register a push device
        try:
            with _Step("POST /auth/devices registers an Expo token"):
                r = await client.post(
                    "/api/v1/auth/devices",
                    json={
                        "expoPushToken": fake_expo_token,
                        "platform": "ios",
                        "appVersion": "1.0.0-smoke",
                    },
                    headers=auth_headers,
                )
                assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
                device = r.json()
                assert device["expoPushToken"] == fake_expo_token
                assert device["platform"] == "ios"
        except Exception as exc:
            failures.append(StepResult("device-register", False, str(exc)))

        # 6. GET /auth/devices lists the row
        try:
            with _Step("GET /auth/devices returns the registered token"):
                r = await client.get(
                    "/api/v1/auth/devices", headers=auth_headers,
                )
                assert r.status_code == 200, f"got {r.status_code}"
                devices = r.json()
                tokens = [d["expoPushToken"] for d in devices]
                assert fake_expo_token in tokens, (
                    f"upserted token missing; got {tokens}"
                )
        except Exception as exc:
            failures.append(StepResult("device-list", False, str(exc)))

        # 7. Body-based refresh (M0-B3) — no cookie available in httpx
        try:
            with _Step("POST /auth/refresh accepts refresh_token in body"):
                r = await client.post(
                    "/api/v1/auth/refresh",
                    json={"refreshToken": refresh_token},
                    headers=MOBILE_HEADERS,
                )
                assert r.status_code == 200, (
                    f"got {r.status_code}: {r.text[:200]}"
                )
                body = r.json()
                new_access = body.get("accessToken")
                new_refresh = body.get("refreshToken")
                assert new_access and new_access != access_token, (
                    "refresh didn't rotate accessToken"
                )
                assert new_refresh, (
                    "refresh didn't return a new refreshToken in body"
                )
                # Use the rotated token for subsequent calls.
                access_token = new_access
                refresh_token = new_refresh
                auth_headers = {
                    "Authorization": f"Bearer {access_token}",
                    **MOBILE_HEADERS,
                }
        except Exception as exc:
            failures.append(StepResult("refresh", False, str(exc)))

        # 8. Authenticated dashboard fetch
        try:
            with _Step("GET /dashboard/attack-vector with Bearer"):
                r = await client.get(
                    "/api/v1/dashboard/attack-vector?window=1h",
                    headers=auth_headers,
                )
                assert r.status_code == 200, f"got {r.status_code}"
                assert "stages" in r.json()
        except Exception as exc:
            failures.append(StepResult("attack-vector", False, str(exc)))

        # 9. /alerts list (M0-B1)
        try:
            with _Step("GET /alerts paginated list"):
                r = await client.get(
                    "/api/v1/alerts?limit=5", headers=auth_headers,
                )
                assert r.status_code == 200, f"got {r.status_code}"
                body = r.json()
                assert "items" in body and "page" in body
        except Exception as exc:
            failures.append(StepResult("alerts", False, str(exc)))

        # 10. SSE handshake — we stream the response just long enough
        #     to confirm status + content-type.
        try:
            with _Step("GET /streams/live-feed opens SSE with Bearer"):
                async with client.stream(
                    "GET", "/api/v1/streams/live-feed", headers=auth_headers,
                ) as resp:
                    assert resp.status_code == 200, (
                        f"got {resp.status_code}"
                    )
                    ct = resp.headers.get("content-type", "")
                    assert "text/event-stream" in ct, (
                        f"wrong content-type: {ct!r}"
                    )
                    # Read a short slice; a comment / retry line or real
                    # event is fine. Don't block forever.
                    try:
                        async with asyncio.timeout(2.5):
                            async for _chunk in resp.aiter_raw():
                                break
                    except TimeoutError:
                        # No heartbeat within 2.5s is OK for smoke — the
                        # handshake is the guarantee we need.
                        pass
        except Exception as exc:
            failures.append(StepResult("sse", False, str(exc)))

        # 11. Cleanup — unregister device
        try:
            with _Step("DELETE /auth/devices/{token}"):
                from urllib.parse import quote

                r = await client.request(
                    "DELETE",
                    f"/api/v1/auth/devices/{quote(fake_expo_token, safe='')}",
                    headers=auth_headers,
                )
                assert r.status_code == 200, f"got {r.status_code}"
                assert r.json().get("deleted") == 1
        except Exception as exc:
            failures.append(StepResult("device-unregister", False, str(exc)))

        # 12. Logout — must clear cookies server-side (body path has no
        #     cookie to clear, but endpoint must still return 200).
        try:
            with _Step("POST /auth/logout"):
                r = await client.post(
                    "/api/v1/auth/logout", headers=auth_headers,
                )
                assert r.status_code == 200, f"got {r.status_code}"
        except Exception as exc:
            failures.append(StepResult("logout", False, str(exc)))

    return _summarise(failures)


def _summarise(failures: list[StepResult]) -> int:
    print()
    if not failures:
        print(f"{GREEN}━━━ ALL CHECKS PASSED ━━━{RESET}")
        print(f"  {GREEN}Mobile contract is live and correct.{RESET}\n")
        return 0
    print(f"{RED}━━━ {len(failures)} FAILURE(S) ━━━{RESET}")
    for f in failures:
        print(f"  {RED}✗{RESET} {f.name}: {f.note}")
    print()
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    try:
        import httpx  # noqa: F401
    except ImportError:
        print(
            f"{RED}httpx is required:{RESET} pip install httpx",
            file=sys.stderr,
        )
        return 2

    return asyncio.run(
        run(api_base=args.api.rstrip("/"), timeout_seconds=args.timeout),
    )


if __name__ == "__main__":
    raise SystemExit(main())
