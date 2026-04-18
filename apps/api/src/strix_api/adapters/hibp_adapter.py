"""HaveIBeenPwned adapter (§4.3 — IOC Registry).

Free tier: 1 req/1.5s. The breaker keeps a hot path open for the dashboard
even when HIBP rate-limits us — see §5.14 fallback semantics: breaker open
→ degraded mode + cached response.

Endpoint contract: `GET /api/v3/breachedaccount/{email}` returns 200 + JSON
on hit, 404 on clean, 429 on rate-limit. We map:
    hit       → reputation = "malicious"   + breach details
    clean     → reputation = "clean"
    rate-limited / breaker-open → IocLookupError(transient=True)
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

log = get_logger("strix_api.adapters.hibp_adapter")

_HIBP_URL = "https://haveibeenpwned.com/api/v3/breachedaccount/{account}"
_HIBP_USER_AGENT_DEFAULT = "strix-platform/1.0"
_REQUEST_TIMEOUT_SECONDS = 5.0


class HibpError(StrixError):
    """Raised by the adapter when HIBP fails in a way the caller should know."""

    status_code = 503
    title = "HIBP Unavailable"
    code = "HIBP_UNAVAILABLE"

    def __init__(self, detail: str | None = None, *, transient: bool = True) -> None:
        super().__init__(detail)
        self.transient = transient


@dataclass(frozen=True)
class HibpLookup:
    """Adapter result. `breaches` is the raw HIBP payload list (or empty)."""

    indicator: str           # the email we queried (lowercased)
    reputation: str          # 'malicious' | 'clean'
    breach_count: int
    breaches: list[dict[str, Any]]


class HibpAdapter:
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
            headers={"User-Agent": settings.hibp_user_agent or _HIBP_USER_AGENT_DEFAULT},
        )
        self._owns_client = client is None
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=settings.breaker_fail_max,
            reset_timeout=settings.breaker_reset_timeout_seconds,
            name="hibp",
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @property
    def breaker_state(self) -> str:
        return self._breaker.current_state

    async def lookup_email(self, email: str) -> HibpLookup:
        """Hit HIBP for one email. Raises `HibpError` on transient failure."""
        if self._settings.hibp_api_key is None:
            raise HibpError("HIBP API key not configured", transient=False)

        normalized = email.lower().strip()
        url = _HIBP_URL.format(account=normalized)

        async def _call() -> HibpLookup:
            with external_api_duration_seconds.labels(api="hibp").time():
                resp = await self._client.get(
                    url,
                    headers={
                        "hibp-api-key": self._settings.hibp_api_key.get_secret_value(),
                        "Accept": "application/json",
                    },
                )
            return self._handle_response(normalized, resp)

        try:
            return await self._breaker.call_async(_call)
        except pybreaker.CircuitBreakerError as exc:
            external_api_errors_total.labels(api="hibp", error_kind="breaker_open").inc()
            raise HibpError("HIBP circuit breaker open", transient=True) from exc

    def _handle_response(self, indicator: str, resp: httpx.Response) -> HibpLookup:
        if resp.status_code == 404:
            # No breach — clean.
            return HibpLookup(
                indicator=indicator, reputation="clean",
                breach_count=0, breaches=[],
            )
        if resp.status_code == 200:
            try:
                breaches = resp.json()
            except ValueError as exc:
                external_api_errors_total.labels(api="hibp", error_kind="invalid_json").inc()
                raise HibpError(f"HIBP returned invalid JSON: {exc}") from exc
            if not isinstance(breaches, list):
                external_api_errors_total.labels(api="hibp", error_kind="invalid_shape").inc()
                raise HibpError("HIBP response is not a list")
            return HibpLookup(
                indicator=indicator, reputation="malicious",
                breach_count=len(breaches), breaches=breaches,
            )
        if resp.status_code == 429:
            external_api_errors_total.labels(api="hibp", error_kind="rate_limited").inc()
            raise HibpError("HIBP rate-limited", transient=True)
        if resp.status_code in (401, 403):
            external_api_errors_total.labels(api="hibp", error_kind="unauthorized").inc()
            raise HibpError(
                f"HIBP rejected the API key ({resp.status_code})", transient=False,
            )
        external_api_errors_total.labels(
            api="hibp", error_kind=f"http_{resp.status_code}",
        ).inc()
        raise HibpError(f"HIBP returned HTTP {resp.status_code}", transient=True)


__all__ = ["HibpAdapter", "HibpError", "HibpLookup"]
