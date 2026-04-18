"""Dashboard read-side queries — Timescale CAGGs + helpers.

Public surface:
    DashboardService(session)                    construct with an AsyncSession
    .attack_vector(window)                       → AttackVectorResponse
    .global_risk(window)                         → GlobalRiskResponse
    .victim_graph(window)                        → VictimGraphResponse

Each method targets a specific CAGG / view from migration `0002`. Windows
are translated to a `time_bucket(...)` interval choice and a `WHERE bucket
>= NOW() - INTERVAL` predicate. Cache layer is added by the route, not
here — keeps the service unit-testable against a fake session.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.schemas.common import WindowLiteral
from strix_api.api.schemas.dashboard import (
    AttackVectorResponse,
    GlobalRiskComponents,
    GlobalRiskResponse,
    GlobalRiskTrendPoint,
    StageBucket,
    VictimEdge,
    VictimGraphResponse,
    VictimNode,
)
from strix_api.core.constants import (
    GLOBAL_RISK_COEF_ANOMALY_RATE,
    GLOBAL_RISK_COEF_GNN_MAX,
    GLOBAL_RISK_COEF_RISK_GROWTH,
    GLOBAL_RISK_COEF_VAE_MEAN,
)
from strix_api.core.enums import CkcStage

# Window → timedelta. asyncpg requires a real timedelta when binding to an
# INTERVAL parameter; passing a string ('15 minutes') triggers
# 'str' object has no attribute 'days' deep in the codec.
from datetime import timedelta

_WINDOW_TO_INTERVAL: Mapping[str, timedelta] = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    # `all` → effectively unbounded.
    "all": timedelta(days=365 * 100),
}

_CKC_NAMES: dict[int, str] = {int(s): s.name for s in CkcStage}


def _interval_for(window: WindowLiteral) -> timedelta:
    return _WINDOW_TO_INTERVAL.get(window, timedelta(hours=1))


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ---- attack-vector -----------------------------------------------

    async def attack_vector(self, window: WindowLiteral) -> AttackVectorResponse:
        interval = _interval_for(window)
        # `bucket` is the START of an hourly time_bucket — a partial-hour
        # window like 15m must include the bucket whose hour is in progress
        # (otherwise just-arrived alerts stay invisible until the top of the
        # next hour). date_trunc('hour', NOW() - interval) gives us the
        # start of the bucket whose interior overlaps the window.
        result = await self._s.execute(
            text(
                """
                SELECT ckc_stage, SUM(alert_count) AS alert_count
                FROM ckc_stage_hourly
                WHERE bucket >= date_trunc('hour', NOW() - (:interval)::INTERVAL)
                GROUP BY ckc_stage
                ORDER BY ckc_stage
                """
            ),
            {"interval": interval},
        )
        rows = result.all()
        counts: dict[int, int] = {int(r.ckc_stage): int(r.alert_count) for r in rows}

        total = sum(counts.values())
        stages: list[StageBucket] = []
        for stage_int in sorted(_CKC_NAMES):
            count = counts.get(stage_int, 0)
            percent = (count / total * 100.0) if total else 0.0
            stages.append(StageBucket(
                ckc_stage=stage_int,
                ckc_name=_CKC_NAMES[stage_int],
                count=count,
                percent=round(percent, 2),
            ))

        return AttackVectorResponse(
            window=window, total_alerts=total, stages=stages,
        )

    # ---- global-risk -------------------------------------------------

    async def global_risk(self, window: WindowLiteral) -> GlobalRiskResponse:
        interval = _interval_for(window)
        # Aggregate the entire window for the components.
        result = await self._s.execute(
            text(
                """
                SELECT
                    AVG(vae_mean_prob)::REAL                   AS vae_mean_prob,
                    MAX(gnn_max_node_risk)::REAL               AS gnn_max_node_risk,
                    AVG(anomaly_rate)::REAL                    AS anomaly_rate,
                    SUM(alert_count)                           AS total_alerts
                FROM global_risk_minutely
                WHERE bucket >= NOW() - (:interval)::INTERVAL
                """
            ),
            {"interval": interval},
        )
        row = result.one()
        vae_mean = float(row.vae_mean_prob or 0.0)
        gnn_max = float(row.gnn_max_node_risk or 0.0)
        anomaly_rate = float(row.anomaly_rate or 0.0)

        # Risk growth: compare second half of the window to first half.
        # For window=15m → 7.5min vs 7.5min. Cheap, avoids a separate query.
        growth_result = await self._s.execute(
            text(
                """
                WITH halves AS (
                    SELECT
                        CASE WHEN bucket < NOW() - (:half_interval)::INTERVAL
                             THEN 'first' ELSE 'second' END AS half,
                        AVG(vae_mean_prob)::REAL AS mean_prob
                    FROM global_risk_minutely
                    WHERE bucket >= NOW() - (:interval)::INTERVAL
                    GROUP BY 1
                )
                SELECT
                    COALESCE(MAX(mean_prob) FILTER (WHERE half = 'second'), 0)
                  - COALESCE(MAX(mean_prob) FILTER (WHERE half = 'first'), 0)
                  AS growth
                FROM halves
                """
            ),
            {"interval": interval, "half_interval": _half_interval(interval)},
        )
        growth = float(growth_result.scalar() or 0.0)

        components = GlobalRiskComponents(
            vae_mean_prob=round(vae_mean, 6),
            gnn_max_node_risk=round(gnn_max, 6),
            anomaly_rate=round(anomaly_rate, 6),
            risk_growth=round(growth, 6),
        )
        global_risk = (
            GLOBAL_RISK_COEF_VAE_MEAN     * vae_mean
            + GLOBAL_RISK_COEF_GNN_MAX    * gnn_max
            + GLOBAL_RISK_COEF_ANOMALY_RATE * anomaly_rate
            + GLOBAL_RISK_COEF_RISK_GROWTH  * growth
        )

        # Trend: down-sample to ≤ 60 points across the window.
        trend_result = await self._s.execute(
            text(
                """
                SELECT bucket AS ts,
                       AVG(vae_mean_prob)::REAL AS value
                FROM global_risk_minutely
                WHERE bucket >= NOW() - (:interval)::INTERVAL
                GROUP BY bucket
                ORDER BY bucket
                """
            ),
            {"interval": interval},
        )
        trend_rows = trend_result.all()
        trend = [
            GlobalRiskTrendPoint(
                ts=_iso(r.ts), value=round(float(r.value or 0.0), 6),
            )
            for r in trend_rows[-60:]
        ]

        return GlobalRiskResponse(
            window=window,
            global_risk=round(max(0.0, min(1.0, global_risk)), 6),
            components=components,
            delta_1h=round(growth, 6),
            trend=trend,
        )

    # ---- victim-graph ------------------------------------------------

    async def victim_graph(self, window: WindowLiteral) -> VictimGraphResponse:
        """Latest GNN snapshot projection — hosts as nodes, shared
        attacker/IOC links as edges. We re-aggregate from the snapshot
        table rather than re-running the GNN here.
        """
        interval = _interval_for(window)
        snap_result = await self._s.execute(
            text(
                """
                SELECT nodes, edges, taken_at
                FROM gnn_graph_snapshots
                WHERE taken_at >= NOW() - (:interval)::INTERVAL
                ORDER BY taken_at DESC
                LIMIT 1
                """
            ),
            {"interval": interval},
        )
        snap = snap_result.first()

        if snap is None or snap.nodes is None:
            return VictimGraphResponse(window=window, nodes=[], edges=[])

        nodes = [
            VictimNode(
                host_id=str(n["hostId"]),
                host_name=str(n.get("hostName", n["hostId"])),
                severity=str(n.get("severity", "info")),
                infected=bool(n.get("infected", False)),
                risk_score=float(n.get("riskScore", 0.0)),
            )
            for n in (snap.nodes or [])
        ]
        edges = [
            VictimEdge(
                from_=str(e["from"]),
                to=str(e["to"]),
                edge_type=str(e.get("edgeType", "unknown")),
                shared_indicator=e.get("sharedIndicator"),
            )
            for e in (snap.edges or [])
        ]
        return VictimGraphResponse(window=window, nodes=nodes, edges=edges)


# ---- helpers ------------------------------------------------------------


def _iso(dt: Any) -> str:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat(timespec="microseconds")
    return str(dt)


def _half_interval(interval: timedelta) -> timedelta:
    """Return half the window — used to split into first/second halves for
    the risk-growth comparison."""
    return interval / 2


__all__ = ["DashboardService"]
