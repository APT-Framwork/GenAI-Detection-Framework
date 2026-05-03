"""XposedOrNot adapter (§4.3 — IOC Registry, email source).

Replaces the previous HIBP adapter. XposedOrNot is a free, no-key public API
that returns the same shape of data we relied on HIBP for: a list of breach
names for a given email. Endpoint:

    GET https://api.xposedornot.com/v1/check-email/{email}

Response shapes observed:
    Hit   → 200 { "breaches": [[name, name, ...]], "email": "...", "status": "success" }
    Clean → 200 { "Error": "Not found", "email": null }
    429   → rate-limited (~1 req/sec global)

We map:
    breaches non-empty → reputation = "malicious"
    "Error: Not found" → reputation = "clean"
    429 / 5xx          → XonError(transient=True)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import pybreaker

from strix_api.api.errors import StrixError
from strix_api.observability import (
    external_api_duration_seconds,
    external_api_errors_total,
    get_logger,
)
from strix_api.settings import ThreatIntelSettings

log = get_logger("strix_api.adapters.xposedornot_adapter")

_XON_URL = "https://api.xposedornot.com/v1/check-email/{account}"
_XON_USER_AGENT_DEFAULT = "strix-platform/1.0"
_REQUEST_TIMEOUT_SECONDS = 5.0


class XonError(StrixError):
    """Raised by the adapter when XposedOrNot fails in a way the caller should know."""

    status_code = 503
    title = "XposedOrNot Unavailable"
    code = "XON_UNAVAILABLE"

    def __init__(self, detail: str | None = None, *, transient: bool = True) -> None:
        super().__init__(detail)
        self.transient = transient


@dataclass(frozen=True)
class XonLookup:
    """Adapter result. `breaches` is a list of `{"Name": str}` dicts (HIBP-shaped)."""

    indicator: str  # the email we queried (lowercased)
    reputation: str  # 'malicious' | 'clean'
    breach_count: int
    breaches: list[dict[str, Any]]


class XonAdapter:
    """Stateless apart from the breaker + httpx pool. One per process."""

    def __init__(
        self,
        settings: ThreatIntelSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": settings.xon_user_agent or _XON_USER_AGENT_DEFAULT},
        )
        self._owns_client = client is None
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=settings.breaker_fail_max,
            reset_timeout=settings.breaker_reset_timeout_seconds,
            name="xon",
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @property
    def breaker_state(self) -> str:
        return self._breaker.current_state

    async def lookup_email(self, email: str) -> XonLookup:
        """Hit XposedOrNot for one email. Raises `XonError` on transient failure."""
        normalized = email.lower().strip()
        url = _XON_URL.format(account=normalized)

        async def _call() -> XonLookup:
            with external_api_duration_seconds.labels(api="xon").time():
                resp = await self._client.get(url, headers={"Accept": "application/json"})
            return self._handle_response(normalized, resp)

        try:
            return await self._breaker.call_async(_call)
        except pybreaker.CircuitBreakerError as exc:
            external_api_errors_total.labels(api="xon", error_kind="breaker_open").inc()
            raise XonError("XposedOrNot circuit breaker open", transient=True) from exc

    def _handle_response(self, indicator: str, resp: httpx.Response) -> XonLookup:
        if resp.status_code == 200:
            try:
                body = resp.json()
            except ValueError as exc:
                external_api_errors_total.labels(api="xon", error_kind="invalid_json").inc()
                raise XonError(f"XposedOrNot returned invalid JSON: {exc}") from exc
            if not isinstance(body, dict):
                external_api_errors_total.labels(api="xon", error_kind="invalid_shape").inc()
                raise XonError("XposedOrNot response is not an object")

            # Clean: {"Error": "Not found", "email": null}
            if "Error" in body or "error" in body:
                return XonLookup(
                    indicator=indicator,
                    reputation="clean",
                    breach_count=0,
                    breaches=[],
                )

            # Hit: {"breaches": [[name, name, ...]], ...}
            raw = body.get("breaches")
            names: list[str] = []
            if isinstance(raw, list):
                # The API nests the names inside a single-element outer list.
                if raw and isinstance(raw[0], list):
                    names = [str(n) for n in raw[0] if n]
                else:
                    names = [str(n) for n in raw if n]

            if not names:
                # Defensive: 200 with no breaches and no Error → treat as clean.
                return XonLookup(
                    indicator=indicator,
                    reputation="clean",
                    breach_count=0,
                    breaches=[],
                )

            return XonLookup(
                indicator=indicator,
                reputation="malicious",
                breach_count=len(names),
                breaches=[{"Name": n} for n in names],
            )

        if resp.status_code == 404:
            # Some malformed inputs return 404 — treat as clean for symmetry with HIBP.
            return XonLookup(
                indicator=indicator,
                reputation="clean",
                breach_count=0,
                breaches=[],
            )
        if resp.status_code == 429:
            external_api_errors_total.labels(api="xon", error_kind="rate_limited").inc()
            raise XonError("XposedOrNot rate-limited", transient=True)
        external_api_errors_total.labels(
            api="xon",
            error_kind=f"http_{resp.status_code}",
        ).inc()
        raise XonError(f"XposedOrNot returned HTTP {resp.status_code}", transient=True)


__all__ = ["XonAdapter", "XonError", "XonLookup"]
