"""MITRE ATT&CK coverage matrix aggregator (Phase 6).

Reads `Alert.mitre_techniques` (TEXT[]) over a time window, rolls up
sub-techniques to their parent (T1059.004 → T1059) — matching MitreMapper's
parent-fallback in core/mitre.py — and groups counts under each canonical
tactic from data/mitre_catalog.json.

The catalogue is loaded once at module import time and shared across
requests. The matrix shape is stable: all 14 ATT&CK Enterprise tactics
appear as columns even when their counts are zero (Kibana convention —
empty columns are signal too: "we have no detection coverage for X").

Technique IDs not present in any tactic's catalogue (catalog drift) land
in `other_count` with their distinct IDs in `other_unmatched_ids` so the
operator notices.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.schemas.mitre import (
    MitreCoverageResponse,
    TacticCoverage,
    TechniqueCoverage,
)
from strix_api.core.mitre_catalog import (
    catalog_data as _catalog,
    normalise_technique,
)
from strix_api.repositories.models import Alert
from strix_api.observability import get_logger


_log = get_logger("strix_api.services.mitre_service")


def _parent(technique_id: str) -> str:
    """Roll up sub-technique to parent: 'T1059.004' → 'T1059'."""
    if "." in technique_id:
        return technique_id.split(".", 1)[0]
    return technique_id


def _iso(dt: Any) -> str:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat(timespec="microseconds")
    return str(dt)


class MitreService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def coverage(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> MitreCoverageResponse:
        now = datetime.now(UTC)
        window_end = until or now
        window_start = since or (window_end - timedelta(hours=24))

        cat = _catalog()
        tactics_meta: list[dict[str, Any]] = cat["tactics"]

        # Build (parent_technique_id → list of (tactic_id, technique_name)).
        # A technique can legitimately belong to multiple tactics (e.g. T1078
        # Valid Accounts maps to Initial Access, Persistence, Priv Esc,
        # Defense Evasion). We attribute each alert occurrence to ALL of them
        # — so column totals are aggregated coverage, not unique alert count.
        parent_to_attributions: dict[str, list[tuple[str, str]]] = {}
        for t in tactics_meta:
            tid = t["tactic_id"]
            for tech in t["techniques"]:
                parent_to_attributions.setdefault(tech["id"], []).append(
                    (tid, tech["name"])
                )

        # ---- Aggregate alerts in window ---------------------------------
        # `unnest(mitre_techniques)` lets us GROUP BY individual technique
        # while still counting the host_id distinct-set per technique.
        stmt = text(
            """
            SELECT
                technique,
                COUNT(*) AS cnt,
                MAX(occurred_at) AS last_seen,
                COUNT(DISTINCT host_id) AS unique_hosts
              FROM (
                  SELECT
                      UNNEST(mitre_techniques) AS technique,
                      occurred_at,
                      host_id
                    FROM alerts
                   WHERE occurred_at >= :w_start
                     AND occurred_at <= :w_end
                     AND mitre_techniques IS NOT NULL
                     AND array_length(mitre_techniques, 1) > 0
              ) AS u
             GROUP BY technique
            """
        )
        rows = (
            await self._s.execute(
                stmt, {"w_start": window_start, "w_end": window_end}
            )
        ).all()

        # parent_id → {count, last_seen, host_set}
        parent_counts: dict[str, dict[str, Any]] = {}
        unmatched: dict[str, dict[str, Any]] = {}

        for raw_id, cnt, last_seen, uniq_hosts in rows:
            if not raw_id:
                continue
            # Translate names → IDs for backwards compatibility with alerts
            # ingested before the wazuh_adapter normalisation landed. Real
            # IDs pass straight through; sub-techniques (T1078.004) get
            # rolled up to their parent (T1078) by `_parent` next.
            normalised = normalise_technique(str(raw_id))
            parent = _parent(normalised)
            cnt = int(cnt or 0)
            uniq = int(uniq_hosts or 0)
            target = parent_counts if parent in parent_to_attributions else unmatched
            agg = target.setdefault(
                parent, {"count": 0, "last_seen": None, "unique_hosts": 0}
            )
            agg["count"] += cnt
            agg["unique_hosts"] = max(agg["unique_hosts"], uniq)
            if last_seen and (
                agg["last_seen"] is None or last_seen > agg["last_seen"]
            ):
                agg["last_seen"] = last_seen

        # ---- Build response: stable 14 tactic columns ------------------
        tactics: list[TacticCoverage] = []
        for t in tactics_meta:
            tid = t["tactic_id"]
            techniques: list[TechniqueCoverage] = []
            col_total = 0
            for tech in t["techniques"]:
                agg = parent_counts.get(tech["id"])
                tech_desc = str(tech.get("description") or "")
                if agg is None:
                    techniques.append(
                        TechniqueCoverage(
                            technique_id=tech["id"],
                            technique_name=tech["name"],
                            count=0,
                            last_seen=None,
                            unique_hosts=0,
                            description=tech_desc,
                        )
                    )
                else:
                    techniques.append(
                        TechniqueCoverage(
                            technique_id=tech["id"],
                            technique_name=tech["name"],
                            count=agg["count"],
                            last_seen=_iso(agg["last_seen"])
                            if agg["last_seen"]
                            else None,
                            unique_hosts=agg["unique_hosts"],
                            description=tech_desc,
                        )
                    )
                    col_total += agg["count"]
            # Sort techniques by count desc — readability for sparse tactics.
            techniques.sort(key=lambda x: (-x.count, x.technique_id))
            tactics.append(
                TacticCoverage(
                    tactic_id=tid,
                    tactic_name=t["name"],
                    ckc=int(t["ckc"]),
                    techniques=techniques,
                    column_total=col_total,
                    description=str(t.get("description") or ""),
                )
            )

        if unmatched:
            _log.info(
                "mitre_catalog_drift",
                unmatched_count=len(unmatched),
                total_events=sum(v["count"] for v in unmatched.values()),
            )

        return MitreCoverageResponse(
            window_start=_iso(window_start),
            window_end=_iso(window_end),
            tactics=tactics,
            other_count=sum(v["count"] for v in unmatched.values()),
            other_unmatched_ids=sorted(unmatched.keys()),
        )
