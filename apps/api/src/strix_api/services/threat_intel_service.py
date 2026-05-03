"""Threat-intel orchestrator: cache → adapter → cache (§4.3)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from strix_api.adapters.virustotal_adapter import VirusTotalAdapter, VirusTotalError
from strix_api.adapters.xposedornot_adapter import XonAdapter, XonError
from strix_api.repositories.ioc_repo import CompromisedAssetsRepo, IocRepo
from strix_api.repositories.models import IocLookupCache

_XON_POSITIVE_TTL = timedelta(hours=24)
_XON_NEGATIVE_TTL = timedelta(minutes=5)
_VT_TTL = timedelta(hours=24)

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_IPV4_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
_IPV6_RE = re.compile(r"^[0-9a-fA-F:]+$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


@dataclass(frozen=True)
class IocResult:
    indicator: str
    indicator_type: str  # 'email' | 'ip' | 'domain' | 'hash'
    reputation: str  # 'malicious' | 'suspicious' | 'clean' | 'unknown'
    source: str  # 'xon' | 'virustotal' | 'cache'
    last_checked: datetime
    breach_count: int | None = None
    payload: dict[str, Any] | None = None
    stale: bool = False  # True when breaker is open and we returned a cached row


def detect_indicator_type(value: str) -> str | None:
    """Best-effort regex sniff. None when shape doesn't match anything we know."""
    s = value.strip()
    if not s:
        return None
    if _SHA256_RE.match(s):
        return "hash"
    if _EMAIL_RE.match(s):
        return "email"
    if _IPV4_RE.match(s) or (":" in s and _IPV6_RE.match(s)):
        return "ip"
    if _DOMAIN_RE.match(s):
        return "domain"
    return None


class ThreatIntelService:
    def __init__(
        self,
        *,
        ioc_repo: IocRepo,
        xon: XonAdapter,
        virustotal: VirusTotalAdapter,
        compromised: CompromisedAssetsRepo,
    ) -> None:
        self._iocs = ioc_repo
        self._xon = xon
        self._vt = virustotal
        self._compromised = compromised

    async def lookup(self, indicator: str, indicator_type: str | None = None) -> IocResult:
        """Cache → upstream → cache. Stale cache row served when breaker opens."""
        sniffed = indicator_type or detect_indicator_type(indicator)
        if sniffed is None:
            raise ValueError(f"unrecognized indicator shape: {indicator!r}")

        normalized = indicator.strip().lower()
        source = "xon" if sniffed == "email" else "virustotal"

        cached = await self._iocs.get(
            indicator=normalized,
            indicator_type=sniffed,
            source=source,
        )
        now = datetime.now(UTC)
        if cached and cached.expires_at > now:
            return _result_from_cache(cached)

        try:
            if sniffed == "email":
                hit = await self._xon.lookup_email(normalized)
                ttl = _XON_POSITIVE_TTL if hit.reputation == "malicious" else _XON_NEGATIVE_TTL
                await self._iocs.upsert(
                    indicator=normalized,
                    indicator_type="email",
                    source="xon",
                    reputation=hit.reputation,
                    payload={"breachCount": hit.breach_count, "breaches": hit.breaches},
                    ttl=ttl,
                )
                return IocResult(
                    indicator=normalized,
                    indicator_type="email",
                    reputation=hit.reputation,
                    source="xon",
                    last_checked=now,
                    breach_count=hit.breach_count,
                    payload={"breaches": hit.breaches},
                )

            # VT path — IP / domain / hash
            if sniffed == "ip":
                vt = await self._vt.lookup_ip(normalized)
            elif sniffed == "domain":
                vt = await self._vt.lookup_domain(normalized)
            elif sniffed == "hash":
                vt = await self._vt.lookup_hash(normalized)
            else:  # pragma: no cover — guarded above
                raise ValueError(f"unsupported indicator_type: {sniffed!r}")

            await self._iocs.upsert(
                indicator=normalized,
                indicator_type=sniffed,
                source="virustotal",
                reputation=vt.reputation,
                payload={
                    "counts": {
                        "malicious": vt.counts.malicious,
                        "suspicious": vt.counts.suspicious,
                        "harmless": vt.counts.harmless,
                        "undetected": vt.counts.undetected,
                        "timeout": vt.counts.timeout,
                    },
                    "engines": vt.engines,
                },
                ttl=_VT_TTL,
            )
            return IocResult(
                indicator=normalized,
                indicator_type=sniffed,
                reputation=vt.reputation,
                source="virustotal",
                last_checked=now,
                payload={"counts": vt.counts.__dict__, "engines": vt.engines},
            )

        except (XonError, VirusTotalError) as exc:
            # Transient upstream failure or breaker open — serve stale cache
            # (per §5.14 fallback policy).
            if cached and exc.transient:
                return _result_from_cache(cached, stale=True)
            raise

    async def search(
        self,
        *,
        query: str | None,
        indicator_type: str | None,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[list[IocResult], int]:
        offset = max(0, (page - 1) * limit)
        rows, total = await self._iocs.search(
            query=query,
            indicator_type=indicator_type,
            limit=limit,
            offset=offset,
        )
        return [_result_from_cache(r) for r in rows], total

    async def compromised_assets(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return await self._compromised.list(limit=limit)


def _result_from_cache(row: IocLookupCache, *, stale: bool = False) -> IocResult:
    payload = row.payload or {}
    return IocResult(
        indicator=row.indicator,
        indicator_type=row.indicator_type,
        reputation=row.reputation,
        source=row.source,
        last_checked=row.checked_at,
        breach_count=payload.get("breachCount"),
        payload=payload,
        stale=stale,
    )


__all__ = ["IocResult", "ThreatIntelService", "detect_indicator_type"]
