"""Per-chain read-side queries for the Analysis tab (§4.2).

Each method maps 1:1 to one of the 6 endpoints in `routes/analysis.py`.
Pure SQL/ORM — no caching, no SSE; that lives at the route + adapter layer.

The infection rule (§6.3) is implemented in `infection()`:
    A host H is infected at time t in chain C iff
        H is in C.hosts AND
        ∃ alert on H within [opened_at, t] s.t.
            detections.vae_malicious_prob ≥ INFECTION_VAE_PROB_THRESHOLD
            OR a dqn_actions.action ≥ ACTION_ESCALATE was emitted on H.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.errors import NotFoundError
from strix_api.api.schemas.analysis import (
    ChainListResponse,
    ChainSummary,
    CkcProgressionResponse,
    CkcProgressionStep,
    DwellTimeResponse,
    ForensicLogEntry,
    ForensicLogsPage,
    GraphEvolutionResponse,
    GraphSnapshot,
    InfectedHost,
    InfectionResponse,
    PredictionsResponse,
    StageProbability,
)
from strix_api.api.schemas.common import Page
from strix_api.core.constants import INFECTION_VAE_PROB_THRESHOLD
from strix_api.core.enums import CkcStage, DqnAction
from strix_api.repositories.repos import AttackChainRepo

_CKC_NAMES: dict[int, str] = {int(s): s.name for s in CkcStage}


def _stage_name(s: int | None) -> str | None:
    if s is None:
        return None
    return _CKC_NAMES.get(int(s))


def _iso(dt: Any) -> str:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat(timespec="microseconds")
    return str(dt)


# ---- cursor encoding -------------------------------------------------


@dataclass(frozen=True)
class _LogCursor:
    """Opaque cursor — `(occurred_at_iso, alert_id)` lex-order keyset."""

    occurred_at: datetime
    alert_id: str

    def encode(self) -> str:
        raw = f"{self.occurred_at.isoformat()}|{self.alert_id}".encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    @classmethod
    def decode(cls, encoded: str) -> _LogCursor:
        try:
            padded = encoded + "=" * (-len(encoded) % 4)
            raw = base64.urlsafe_b64decode(padded.encode()).decode()
            ts_str, alert_id = raw.split("|", 1)
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            return cls(occurred_at=ts, alert_id=alert_id)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError(f"invalid cursor: {encoded!r}") from exc


# ---- service ---------------------------------------------------------


class AnalysisService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ---- notifications (recent interventions) -------------------

    async def list_interventions(
        self,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fuels the Notifications tab. Two distinct sources:

        1. Any DQN action ≥ ESCALATE — true automated decisions worth flagging.
        2. Any DQN action on a chain step at CKC ≥ EXPLOITATION (4) — even if
           the agent picked LOW_ALERT/MONITOR, a step deep in the kill chain
           is something an analyst should sanity-check.

        Joined with hosts so the UI gets a friendly agent name."""
        from strix_api.core.enums import CkcStage, DqnAction

        result = await self._s.execute(
            text(
                """
                SELECT
                    a.action_id, a.alert_id, a.chain_id, a.host_id,
                    a.action_name, a.action,
                    a.ckc_stage_at_decision, a.decided_at,
                    a.requires_approval, a.applied,
                    h.agent_name
                FROM dqn_actions a
                LEFT JOIN hosts h ON h.host_id = a.host_id
                WHERE a.action >= :escalate
                   OR a.ckc_stage_at_decision >= :high_ckc
                ORDER BY a.decided_at DESC
                LIMIT :limit
                """
            ),
            {
                "escalate": int(DqnAction.ESCALATE),
                "high_ckc": int(CkcStage.EXPLOITATION),
                "limit": limit,
            },
        )
        return [
            {
                "actionId": str(r.action_id),
                "alertId": r.alert_id,
                "chainId": str(r.chain_id),
                "hostId": str(r.host_id),
                "agentName": r.agent_name,
                "actionName": r.action_name,
                "ckcStageAtDecision": int(r.ckc_stage_at_decision),
                "ckcStageName": _stage_name(r.ckc_stage_at_decision) or "BENIGN",
                "decidedAt": _iso(r.decided_at),
                "requiresApproval": bool(r.requires_approval),
                "applied": bool(r.applied),
            }
            for r in result.all()
        ]

    # ---- chain list (sidebar) ------------------------------------

    async def list_chains(
        self,
        *,
        limit: int = 50,
        only_open: bool = False,
    ) -> ChainListResponse:
        repo = AttackChainRepo(self._s)
        chains = await repo.list_recent(limit=limit, only_open=only_open)
        open_count = await repo.count_open()
        items = [
            ChainSummary(
                chain_id=c.chain_id,
                host_id=c.host_id,
                opened_at=_iso(c.opened_at),
                closed_at=_iso(c.closed_at) if c.closed_at else None,
                status=c.status,
                close_reason=c.close_reason,
                max_ckc_stage=int(c.max_ckc_stage),
                max_ckc_stage_name=_stage_name(c.max_ckc_stage) or "BENIGN",
                max_vae_prob=float(c.max_vae_prob),
                step_count=int(c.step_count),
            )
            for c in chains
        ]
        return ChainListResponse(items=items, open_count=open_count)

    # ---- helpers ---------------------------------------------------

    async def _get_chain_or_404(self, chain_id: UUID) -> Any:
        chain = await AttackChainRepo(self._s).get(chain_id)
        if chain is None:
            raise NotFoundError(f"attack chain {chain_id} not found")
        return chain

    # ---- graph evolution ----------------------------------------

    async def graph_evolution(self, chain_id: UUID) -> GraphEvolutionResponse:
        chain = await self._get_chain_or_404(chain_id)
        # Per §4.2: gnn_graph_snapshots filtered to the chain's hosts.
        # Cheap proxy: snapshots taken between opened_at and (closed_at or now).
        # Cast :closed_at to TIMESTAMPTZ explicitly — asyncpg can't infer
        # the type when the bound value is Python None.
        result = await self._s.execute(
            text(
                """
                SELECT taken_at, nodes, edges
                FROM gnn_graph_snapshots
                WHERE taken_at >= :opened_at
                  AND (
                       CAST(:closed_at AS TIMESTAMPTZ) IS NULL
                       OR taken_at <= CAST(:closed_at AS TIMESTAMPTZ)
                  )
                ORDER BY taken_at ASC
                LIMIT 24
                """
            ),
            {"opened_at": chain.opened_at, "closed_at": chain.closed_at},
        )
        snaps = [
            GraphSnapshot(
                ts=_iso(r.taken_at),
                nodes=list(r.nodes or []),
                edges=list(r.edges or []),
            )
            for r in result.all()
        ]
        return GraphEvolutionResponse(chain_id=chain_id, snapshots=snaps)

    # ---- ckc progression ----------------------------------------

    async def ckc_progression(self, chain_id: UUID) -> CkcProgressionResponse:
        await self._get_chain_or_404(chain_id)
        # For each distinct CKC stage in the chain, take the FIRST detection
        # that hit that stage, and any DQN action recorded at that step.
        result = await self._s.execute(
            text(
                """
                WITH stage_first AS (
                    SELECT
                        d.transformer_pred_ckc          AS ckc_stage,
                        MIN(d.occurred_at)              AS entered_at,
                        MIN(d.alert_id) FILTER (WHERE d.transformer_pred_ckc IS NOT NULL)
                                                        AS first_alert_id
                    FROM detections d
                    WHERE d.chain_id = :chain_id
                      AND d.transformer_pred_ckc IS NOT NULL
                    GROUP BY d.transformer_pred_ckc
                )
                SELECT
                    s.ckc_stage,
                    s.entered_at,
                    a.action_name AS dqn_action,
                    a.decided_at  AS actioned_at
                FROM stage_first s
                LEFT JOIN dqn_actions a
                       ON a.alert_id = s.first_alert_id
                ORDER BY s.entered_at ASC
                """
            ),
            {"chain_id": chain_id},
        )
        steps = [
            CkcProgressionStep(
                ckc_stage=int(r.ckc_stage),
                ckc_stage_name=_stage_name(r.ckc_stage) or "BENIGN",
                entered_at=_iso(r.entered_at),
                dqn_action=r.dqn_action,
                actioned_at=_iso(r.actioned_at) if r.actioned_at else None,
            )
            for r in result.all()
        ]
        return CkcProgressionResponse(chain_id=chain_id, stages=steps)

    # ---- AI predictions -----------------------------------------

    async def predictions(self, chain_id: UUID) -> PredictionsResponse:
        await self._get_chain_or_404(chain_id)
        # Last detection in the chain — its Transformer output is the
        # "what comes next" prediction the dashboard cares about.
        result = await self._s.execute(
            text(
                """
                SELECT
                    transformer_pred_ckc,
                    transformer_confidence
                FROM detections
                WHERE chain_id = :chain_id
                ORDER BY occurred_at DESC
                LIMIT 1
                """
            ),
            {"chain_id": chain_id},
        )
        row = result.first()

        # Current stage = the chain's max-observed CKC stage so far.
        max_result = await self._s.execute(
            text(
                """
                SELECT MAX(transformer_pred_ckc) AS current_stage
                FROM detections
                WHERE chain_id = :chain_id
                """
            ),
            {"chain_id": chain_id},
        )
        current_stage = max_result.scalar()

        if row is None:
            return PredictionsResponse(
                chain_id=chain_id,
                current_stage=None,
                current_stage_name=None,
                predicted_next_stage=None,
                predicted_next_stage_name=None,
                confidence=0.0,
                probabilities=[
                    StageProbability(
                        ckc_stage=s,
                        ckc_stage_name=_stage_name(s) or "BENIGN",
                        prob=0.0,
                    )
                    for s in sorted(_CKC_NAMES)
                ],
            )

        confidence = float(row.transformer_confidence or 0.0)
        next_stage = int(row.transformer_pred_ckc) if row.transformer_pred_ckc is not None else None

        # We don't store the full softmax in the detections row — just the
        # argmax + confidence. Reconstruct a degenerate distribution:
        # `prob[predicted_stage] = confidence`, evenly spread the remainder.
        n_others = max(1, len(_CKC_NAMES) - 1)
        spread = (1.0 - confidence) / n_others if confidence < 1.0 else 0.0
        probs = []
        for s in sorted(_CKC_NAMES):
            p = confidence if s == next_stage else spread
            probs.append(
                StageProbability(
                    ckc_stage=s,
                    ckc_stage_name=_stage_name(s) or "BENIGN",
                    prob=round(p, 6),
                )
            )

        return PredictionsResponse(
            chain_id=chain_id,
            current_stage=int(current_stage) if current_stage is not None else None,
            current_stage_name=_stage_name(current_stage),
            predicted_next_stage=next_stage,
            predicted_next_stage_name=_stage_name(next_stage),
            confidence=round(confidence, 6),
            probabilities=probs,
        )

    # ---- forensic logs -----------------------------------------

    async def logs_page(
        self,
        chain_id: UUID,
        *,
        cursor: str | None,
        limit: int = 50,
    ) -> ForensicLogsPage:
        await self._get_chain_or_404(chain_id)
        limit = max(1, min(int(limit), 200))

        params: dict[str, Any] = {"chain_id": chain_id, "limit": limit + 1}
        cursor_clause = ""
        if cursor:
            try:
                c = _LogCursor.decode(cursor)
            except ValueError as exc:
                raise NotFoundError(str(exc)) from exc
            cursor_clause = """
                AND (a.occurred_at, a.alert_id)
                  < (:cursor_ts, :cursor_id)
            """
            params["cursor_ts"] = c.occurred_at
            params["cursor_id"] = c.alert_id

        result = await self._s.execute(
            text(
                f"""
                SELECT
                    a.alert_id,
                    a.occurred_at,
                    h.agent_name AS agent_name,
                    a.full_log,
                    a.rule_id,
                    a.decoder_name,
                    a.location
                FROM alerts a
                LEFT JOIN hosts h ON h.host_id = a.host_id
                WHERE a.chain_id = :chain_id
                  {cursor_clause}
                ORDER BY a.occurred_at DESC, a.alert_id DESC
                LIMIT :limit
                """
            ),
            params,
        )
        rows = result.all()
        has_more = len(rows) > limit
        kept = rows[:limit]
        next_cursor: str | None = None
        if has_more:
            last = kept[-1]
            next_cursor = _LogCursor(
                occurred_at=last.occurred_at,
                alert_id=last.alert_id,
            ).encode()

        items = [
            ForensicLogEntry(
                alert_id=r.alert_id,
                ts=_iso(r.occurred_at),
                agent_name=r.agent_name,
                raw_log=r.full_log,
                # `rule_description` is non-stored at the moment (skeleton alert
                # rows in P3); fall back to rule_id so the column isn't blank.
                rule_description=r.rule_id,
                decoder=r.decoder_name,
                location=r.location,
            )
            for r in kept
        ]
        return ForensicLogsPage(
            chain_id=chain_id,
            items=items,
            page=Page(cursor=next_cursor, has_more=has_more),
        )

    # ---- infection radius ---------------------------------------

    async def infection(self, chain_id: UUID) -> InfectionResponse:
        chain = await self._get_chain_or_404(chain_id)
        upper = chain.closed_at or datetime.now(UTC)

        # All hosts in the chain
        all_hosts = await self._s.execute(
            text(
                """
                SELECT DISTINCT a.host_id, h.agent_name
                FROM alerts a
                LEFT JOIN hosts h ON h.host_id = a.host_id
                WHERE a.chain_id = :chain_id
                """
            ),
            {"chain_id": chain_id},
        )
        host_rows = list(all_hosts.all())
        host_names = {r.host_id: (r.agent_name or str(r.host_id)) for r in host_rows}
        total_count = len(host_rows)

        if total_count == 0:
            return InfectionResponse(
                chain_id=chain_id,
                infected_count=0,
                total_count=0,
                percent=0.0,
                infected_hosts=[],
            )

        # Hosts that crossed the infection threshold (§6.3)
        infected_result = await self._s.execute(
            text(
                """
                WITH infected AS (
                    SELECT DISTINCT d.host_id
                    FROM detections d
                    WHERE d.chain_id = :chain_id
                      AND d.occurred_at <= :upper
                      AND d.vae_malicious_prob >= :prob_threshold
                    UNION
                    SELECT DISTINCT a.host_id
                    FROM dqn_actions a
                    WHERE a.chain_id = :chain_id
                      AND a.decided_at <= :upper
                      AND a.action >= :escalate
                ),
                first_seen AS (
                    SELECT host_id, MIN(occurred_at) AS first_at,
                           MAX(transformer_pred_ckc) AS current_stage
                    FROM detections
                    WHERE chain_id = :chain_id
                    GROUP BY host_id
                )
                SELECT
                    i.host_id,
                    f.first_at,
                    f.current_stage
                FROM infected i
                JOIN first_seen f ON f.host_id = i.host_id
                """
            ),
            {
                "chain_id": chain_id,
                "upper": upper,
                "prob_threshold": INFECTION_VAE_PROB_THRESHOLD,
                "escalate": int(DqnAction.ESCALATE),
            },
        )
        infected_rows = list(infected_result.all())
        infected_hosts = [
            InfectedHost(
                host_id=r.host_id,
                host_name=host_names.get(r.host_id, str(r.host_id)),
                first_seen=_iso(r.first_at),
                current_stage=int(r.current_stage) if r.current_stage is not None else None,
                current_stage_name=_stage_name(r.current_stage),
            )
            for r in infected_rows
        ]
        infected_count = len(infected_hosts)
        percent = round(infected_count / total_count, 6)
        return InfectionResponse(
            chain_id=chain_id,
            infected_count=infected_count,
            total_count=total_count,
            percent=percent,
            infected_hosts=infected_hosts,
        )

    # ---- dwell time -------------------------------------------

    async def dwell_time(self, chain_id: UUID) -> DwellTimeResponse:
        chain = await self._get_chain_or_404(chain_id)
        now = datetime.now(UTC)
        end = chain.closed_at or now
        # Use first_malicious_at as the start (§4.2 — intrusion-start)
        start = chain.first_malicious_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        duration = max(0.0, (end - start).total_seconds())
        return DwellTimeResponse(
            chain_id=chain_id,
            started_at=_iso(start),
            closed_at=_iso(chain.closed_at) if chain.closed_at else None,
            duration_seconds=duration,
            status=chain.status,
            close_reason=chain.close_reason,
        )


__all__ = ["AnalysisService"]
