"""Sentinel Insight orchestrator (§5.14).

Inputs to the LLM are deterministic so identical platform states hit the
same `payload_hash` and the same cache row. Hash is SHA-256 of:

    {
      "windowMinutes": int,
      "topMitreTechniques": [{technique, count}, ... up to 10],
      "lastInterventions":  [{ckcStage, action}, ... last 3],
      "globalRisk":         {"value": float, "delta1h": float},
    }

Cache lifetime: §6.3 `LLM_SENTINEL_RESULT_TTL_SECONDS = 300` (5 min).

Failure modes:
  - Cache hit                 → return stored row immediately
  - Cache miss + LLM healthy  → call LLM, cache, return
  - Cache miss + LLM down     → raise so the route can return a 503
                                 with a fallback message
  - Cache stale + LLM down    → return stored row with `stale=true`
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.adapters.llm_adapter import LlmAdapter, LlmError
from strix_api.core.constants import (
    GLOBAL_RISK_WINDOW_MINUTES,
    LLM_SENTINEL_RESULT_TTL_SECONDS,
)
from strix_api.repositories.llm_insight_repo import LlmInsightCacheRepo


@dataclass(frozen=True)
class SentinelResult:
    insight: str
    recommended_actions: list[dict[str, str]]
    confidence: float
    model_version: str
    generated_at: datetime
    payload_hash: str
    stale: bool = False


class InsightService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        llm: LlmAdapter,
    ) -> None:
        self._s = session
        self._llm = llm
        self._repo = LlmInsightCacheRepo(session)

    # ---- snapshot builder ----------------------------------------

    async def build_snapshot(
        self,
        *,
        window_minutes: int = GLOBAL_RISK_WINDOW_MINUTES,
    ) -> dict[str, Any]:
        """Pull the deterministic snapshot the LLM sees.

        Cheap fallback when the DB is empty: returns an empty-shape snapshot
        rather than erroring, so the dashboard renders "no insight yet"."""
        # Top MITRE techniques over window
        mitre_rows = (
            await self._s.execute(
                text(
                    """
                    SELECT unnest(mitre_techniques) AS technique, COUNT(*) AS n
                    FROM alerts
                    WHERE occurred_at >= NOW() - (:window || ' minutes')::INTERVAL
                      AND mitre_techniques <> '{}'
                    GROUP BY technique
                    ORDER BY n DESC
                    LIMIT 10
                    """
                ),
                {"window": str(window_minutes)},
            )
        ).all()

        # Last 3 DQN interventions (action >= ESCALATE)
        from strix_api.core.enums import DqnAction

        intervention_rows = (
            await self._s.execute(
                text(
                    """
                    SELECT action_name, ckc_stage_at_decision, decided_at
                    FROM dqn_actions
                    WHERE action >= :escalate
                    ORDER BY decided_at DESC
                    LIMIT 3
                    """
                ),
                {"escalate": int(DqnAction.ESCALATE)},
            )
        ).all()

        # Current Global Risk + delta
        risk_row = (
            await self._s.execute(
                text(
                    """
                    WITH recent AS (
                        SELECT
                            AVG(vae_mean_prob)::REAL              AS vae_mean,
                            MAX(gnn_max_node_risk)::REAL          AS gnn_max,
                            AVG(anomaly_rate)::REAL               AS anomaly_rate
                        FROM global_risk_minutely
                        WHERE bucket >= NOW() - (:window || ' minutes')::INTERVAL
                    ),
                    prev AS (
                        SELECT AVG(vae_mean_prob)::REAL AS vae_mean
                        FROM global_risk_minutely
                        WHERE bucket >= NOW() - (2 * :window || ' minutes')::INTERVAL
                          AND bucket <  NOW() - (:window || ' minutes')::INTERVAL
                    )
                    SELECT
                        recent.vae_mean,
                        recent.gnn_max,
                        recent.anomaly_rate,
                        COALESCE(recent.vae_mean, 0) - COALESCE(prev.vae_mean, 0) AS delta
                    FROM recent, prev
                    """
                ),
                {"window": str(window_minutes)},
            )
        ).first()

        snapshot: dict[str, Any] = {
            "windowMinutes": window_minutes,
            "topMitreTechniques": [
                {"technique": r.technique, "count": int(r.n)} for r in mitre_rows
            ],
            "lastInterventions": [
                {
                    "ckcStage": int(r.ckc_stage_at_decision),
                    "action": r.action_name,
                    "decidedAt": r.decided_at.isoformat()
                    if isinstance(r.decided_at, datetime)
                    else str(r.decided_at),
                }
                for r in intervention_rows
            ],
            "globalRisk": {
                "vaeMean": float((risk_row.vae_mean if risk_row else 0) or 0),
                "gnnMax": float((risk_row.gnn_max if risk_row else 0) or 0),
                "anomalyRate": float((risk_row.anomaly_rate if risk_row else 0) or 0),
                "delta": float((risk_row.delta if risk_row else 0) or 0),
            },
        }
        return snapshot

    @staticmethod
    def hash_snapshot(snapshot: dict[str, Any]) -> str:
        """Stable SHA-256 for cache lookup. Sort keys so the JSON is canonical."""
        canonical = json.dumps(snapshot, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ---- cache-aware generation ---------------------------------

    async def get_or_generate(
        self,
        *,
        force_refresh: bool = False,
    ) -> SentinelResult:
        snapshot = await self.build_snapshot()
        payload_hash = self.hash_snapshot(snapshot)

        cached = await self._repo.get(payload_hash)
        now = datetime.now(UTC)

        # Fresh cache hit (only when not forcing a refresh)
        if cached is not None and not force_refresh and cached.expires_at > now:
            actions = (cached.recommended_actions or {}).get("items", [])
            return SentinelResult(
                insight=cached.insight,
                recommended_actions=list(actions),
                confidence=1.0,  # we don't store confidence — assume 1 for cache hit
                model_version=cached.model_version,
                generated_at=cached.generated_at,
                payload_hash=payload_hash,
                stale=False,
            )

        # Need to call the LLM. Falls back to stale cache on transient failure.
        try:
            result = await self._llm.sentinel_insight(snapshot)
        except LlmError as exc:
            if cached is not None and exc.transient:
                actions = (cached.recommended_actions or {}).get("items", [])
                return SentinelResult(
                    insight=cached.insight,
                    recommended_actions=list(actions),
                    confidence=0.0,  # be honest — we couldn't refresh
                    model_version=cached.model_version,
                    generated_at=cached.generated_at,
                    payload_hash=payload_hash,
                    stale=True,
                )
            raise

        # Persist the new result.
        await self._repo.upsert(
            payload_hash=payload_hash,
            model_version=result.model_version,
            insight=result.insight,
            recommended_actions=result.recommended_actions,
            ttl=timedelta(seconds=LLM_SENTINEL_RESULT_TTL_SECONDS),
        )
        return SentinelResult(
            insight=result.insight,
            recommended_actions=result.recommended_actions,
            confidence=result.confidence,
            model_version=result.model_version,
            generated_at=now,
            payload_hash=payload_hash,
            stale=False,
        )


__all__ = ["InsightService", "SentinelResult"]
