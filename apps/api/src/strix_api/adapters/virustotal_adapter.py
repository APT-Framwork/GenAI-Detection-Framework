"""VirusTotal v3 adapter (§4.3).

Free tier: 4 req/min. Same circuit-breaker pattern as HIBP.

Three lookup paths supported:
  - lookup_ip(ip)          → /api/v3/ip_addresses/{ip}
  - lookup_domain(domain)  → /api/v3/domains/{domain}
  - lookup_hash(sha256)    → /api/v3/files/{sha256}

Each maps the per-engine verdict counts → reputation label:
    malicious > 0          → 'malicious'
    suspicious > 0         → 'suspicious'
    harmless > 0           → 'clean'
    otherwise              → 'unknown'
"""

from __future__ import annotations

from dataclasses import dataclass, field
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

log = get_logger("strix_api.adapters.virustotal_adapter")

_VT_BASE = "https://www.virustotal.com/api/v3"
_REQUEST_TIMEOUT_SECONDS = 8.0


class VirusTotalError(StrixError):
    status_code = 503
    title = "VirusTotal Unavailable"
    code = "VT_UNAVAILABLE"

    def __init__(self, detail: str | None = None, *, transient: bool = True) -> None:
        super().__init__(detail)
        self.transient = transient


@dataclass(frozen=True)
class EngineCounts:
    malicious: int = 0
    suspicious: int = 0
    harmless: int = 0
    undetected: int = 0
    timeout: int = 0


@dataclass(frozen=True)
class VtLookup:
    indicator: str
    indicator_type: str  # 'ip' | 'domain' | 'hash'
    reputation: str  # 'malicious' | 'suspicious' | 'clean' | 'unknown'
    counts: EngineCounts
    engines: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


def _classify(counts: EngineCounts) -> str:
    if counts.malicious > 0:
        return "malicious"
    if counts.suspicious > 0:
        return "suspicious"
    if counts.harmless > 0:
        return "clean"
    return "unknown"


class VirusTotalAdapter:
    def __init__(
        self,
        settings: ThreatIntelSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS)
        self._owns_client = client is None
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=settings.breaker_fail_max,
            reset_timeout=settings.breaker_reset_timeout_seconds,
            name="virustotal",
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @property
    def breaker_state(self) -> str:
        return self._breaker.current_state

    async def lookup_ip(self, ip: str) -> VtLookup:
        return await self._lookup(f"/ip_addresses/{ip.strip()}", indicator=ip, indicator_type="ip")

    async def lookup_domain(self, domain: str) -> VtLookup:
        return await self._lookup(
            f"/domains/{domain.strip().lower()}",
            indicator=domain.strip().lower(),
            indicator_type="domain",
        )

    async def lookup_hash(self, sha256: str) -> VtLookup:
        return await self._lookup(
            f"/files/{sha256.strip().lower()}",
            indicator=sha256.strip().lower(),
            indicator_type="hash",
        )

    # ---- internals --------------------------------------------------

    async def _lookup(self, path: str, *, indicator: str, indicator_type: str) -> VtLookup:
        if self._settings.virustotal_api_key is None:
            raise VirusTotalError("VirusTotal API key not configured", transient=False)

        url = f"{_VT_BASE}{path}"
        headers = {
            "x-apikey": self._settings.virustotal_api_key.get_secret_value(),
            "Accept": "application/json",
        }

        async def _call() -> VtLookup:
            with external_api_duration_seconds.labels(api="virustotal").time():
                resp = await self._client.get(url, headers=headers)
            return self._handle_response(indicator, indicator_type, resp)

        try:
            return await self._breaker.call_async(_call)
        except pybreaker.CircuitBreakerError as exc:
            external_api_errors_total.labels(api="virustotal", error_kind="breaker_open").inc()
            raise VirusTotalError("VirusTotal circuit breaker open", transient=True) from exc

    def _handle_response(
        self,
        indicator: str,
        indicator_type: str,
        resp: httpx.Response,
    ) -> VtLookup:
        if resp.status_code == 200:
            try:
                payload = resp.json()
            except ValueError as exc:
                external_api_errors_total.labels(api="virustotal", error_kind="invalid_json").inc()
                raise VirusTotalError(f"VT returned invalid JSON: {exc}") from exc
            attrs = (payload.get("data") or {}).get("attributes") or {}
            stats = attrs.get("last_analysis_stats") or {}
            counts = EngineCounts(
                malicious=int(stats.get("malicious", 0)),
                suspicious=int(stats.get("suspicious", 0)),
                harmless=int(stats.get("harmless", 0)),
                undetected=int(stats.get("undetected", 0)),
                timeout=int(stats.get("timeout", 0)),
            )
            engines: dict[str, str] = {
                k: (v.get("result") or v.get("category") or "")
                for k, v in (attrs.get("last_analysis_results") or {}).items()
            }
            return VtLookup(
                indicator=indicator,
                indicator_type=indicator_type,
                reputation=_classify(counts),
                counts=counts,
                engines=engines,
                raw=payload,
            )
        if resp.status_code == 404:
            # Not in VT's database → unknown reputation, not an error.
            return VtLookup(
                indicator=indicator,
                indicator_type=indicator_type,
                reputation="unknown",
                counts=EngineCounts(),
                engines={},
                raw={},
            )
        if resp.status_code == 429:
            external_api_errors_total.labels(api="virustotal", error_kind="rate_limited").inc()
            raise VirusTotalError("VT rate-limited", transient=True)
        if resp.status_code in (401, 403):
            external_api_errors_total.labels(api="virustotal", error_kind="unauthorized").inc()
            raise VirusTotalError(
                f"VT rejected the API key ({resp.status_code})",
                transient=False,
            )
        external_api_errors_total.labels(
            api="virustotal",
            error_kind=f"http_{resp.status_code}",
        ).inc()
        raise VirusTotalError(f"VT returned HTTP {resp.status_code}", transient=True)


__all__ = ["EngineCounts", "VirusTotalAdapter", "VirusTotalError", "VtLookup"]
