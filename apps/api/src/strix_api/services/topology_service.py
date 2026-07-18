"""Topology service — derive nodes (hosts) + edges (chain co-occurrence).

Edges are inferred from `attack_chains.host_id` co-occurrence within the
requested window: two hosts share an edge if they have an open chain
each within the window AND the chains overlap in time. Cheap; doesn't
need a real graph store.

Status rules per node:
    compromised — any open chain at CKC ≥ 4 (EXPLOITATION+) within window
    warning     — any open chain at CKC 1..3 within window
    healthy     — otherwise

Host inclusion: only hosts whose `last_seen_at` falls inside the window are
returned, so stale/decommissioned agents from past runs don't inflate the
denominator (e.g. System Integrity counting 10 enrolled hosts when only 2 are
live). Any host with chain activity in the window necessarily has a
`last_seen_at` in the window too, so this never drops a compromised host.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.schemas.common import WindowLiteral
from strix_api.api.schemas.topology import (
    TopologyEdge,
    TopologyNode,
    TopologyResponse,
)

_WINDOW: dict[str, timedelta] = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "all": timedelta(days=365 * 10),
}


def _interval(window: WindowLiteral) -> timedelta:
    return _WINDOW.get(window, timedelta(hours=24))


class TopologyService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def topology(self, window: WindowLiteral) -> TopologyResponse:
        interval = _interval(window)
        # Each host with its worst open chain.
        node_rows = await self._s.execute(
            text(
                """
                SELECT h.host_id::text         AS id,
                       h.agent_name           AS label,
                       host(h.ip_address)     AS ip,
                       h.is_manager           AS is_manager,
                       COALESCE(MAX(c.max_ckc_stage), 0) AS max_ckc,
                       COUNT(c.chain_id) FILTER (WHERE c.status = 'open')
                                              AS open_chains
                  FROM hosts h
             LEFT JOIN attack_chains c
                    ON c.host_id = h.host_id
                   AND c.opened_at >= NOW() - (:interval)::INTERVAL
                 WHERE h.last_seen_at >= NOW() - (:interval)::INTERVAL
              GROUP BY h.host_id, h.agent_name, h.ip_address, h.is_manager
              ORDER BY max_ckc DESC, open_chains DESC, h.agent_name
                """
            ),
            {"interval": interval},
        )

        nodes: list[TopologyNode] = []
        for r in node_rows.all():
            max_ckc = int(r.max_ckc or 0)
            open_n = int(r.open_chains or 0)
            if max_ckc >= 4:
                status: Literal["compromised", "warning", "healthy"] = "compromised"
            elif max_ckc >= 1 or open_n > 0:
                status = "warning"
            else:
                status = "healthy"
            kind = "manager" if r.is_manager else "endpoint"
            nodes.append(
                TopologyNode(
                    id=r.id,
                    label=r.label,
                    type=kind,
                    status=status,
                    ip=r.ip,
                    open_chains=open_n,
                    max_ckc_stage=max_ckc,
                )
            )

        # Edges: hosts whose chains overlapped in time within the window.
        # We aggregate chains to one row per host BEFORE the self-join so
        # the cross product is hosts^2 (hundreds), not chains^2 (50k+) —
        # the chain-level join was tripping `DiskFullError` on big runs.
        edge_rows = await self._s.execute(
            text(
                """
                WITH per_host AS (
                    SELECT host_id,
                           MIN(opened_at)                       AS first_opened,
                           MAX(COALESCE(closed_at, NOW()))      AS last_seen,
                           COUNT(*)                             AS chain_count,
                           MAX(max_ckc_stage)                   AS max_ckc
                      FROM attack_chains
                     WHERE opened_at >= NOW() - (:interval)::INTERVAL
                  GROUP BY host_id
                )
                SELECT a.host_id::text                          AS source,
                       b.host_id::text                          AS target,
                       LEAST(a.chain_count, b.chain_count)::int AS chain_count,
                       GREATEST(a.max_ckc, b.max_ckc)::int      AS max_ckc
                  FROM per_host a
                  JOIN per_host b
                    ON a.host_id < b.host_id
                   AND tstzrange(a.first_opened, a.last_seen)
                       && tstzrange(b.first_opened, b.last_seen)
              ORDER BY chain_count DESC, max_ckc DESC
                 LIMIT 200
                """
            ),
            {"interval": interval},
        )
        edges: list[TopologyEdge] = []
        for r in edge_rows.all():
            edges.append(
                TopologyEdge(
                    id=f"{r.source}::{r.target}",
                    source=r.source,
                    target=r.target,
                    chain_count=int(r.chain_count),
                    type="malicious" if int(r.max_ckc or 0) >= 4 else "normal",
                )
            )

        return TopologyResponse(
            window=window,
            generated_at=datetime.now(UTC).isoformat(),
            nodes=nodes,
            edges=edges,
        )


__all__ = ["TopologyService"]
