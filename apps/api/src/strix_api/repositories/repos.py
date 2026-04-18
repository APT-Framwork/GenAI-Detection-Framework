"""Phase 2 repositories: Hosts, Alerts, Detections, AttackChains.

Async SQLAlchemy 2.x style. Each repo takes an `AsyncSession` and exposes
intent-revealing methods (`upsert_host`, `bulk_insert_alerts`, …) — no
`session.execute(select(...))` in services or workers.

`bulk_insert_*` use Postgres `INSERT ... ON CONFLICT DO NOTHING` so a
re-delivered Redis Stream entry doesn't duplicate rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.repositories.models import (
    Alert,
    AttackChain,
    Detection,
    DqnActionRow,
    Host,
)

# ---------------------------------------------------------------- Hosts


class HostRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert_host(
        self,
        *,
        host_id: UUID,
        agent_id: str,
        agent_name: str | None,
        ip_address: str | None,
        first_seen_at: datetime,
        last_seen_at: datetime,
    ) -> None:
        """Insert if absent, else bump last_seen_at + name/ip if they changed."""
        stmt = (
            pg_insert(Host)
            .values(
                host_id=host_id,
                agent_id=agent_id,
                agent_name=agent_name or agent_id,
                ip_address=ip_address,
                first_seen_at=first_seen_at,
                last_seen_at=last_seen_at,
            )
            .on_conflict_do_update(
                index_elements=[Host.agent_id],
                set_={
                    "last_seen_at": last_seen_at,
                    "agent_name": agent_name or agent_id,
                    "ip_address": ip_address,
                },
            )
        )
        await self._s.execute(stmt)

    async def get_by_agent_id(self, agent_id: str) -> Host | None:
        result = await self._s.execute(select(Host).where(Host.agent_id == agent_id))
        return result.scalar_one_or_none()


# ---------------------------------------------------------------- Alerts


class AlertRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def bulk_insert(self, rows: list[dict[str, Any]]) -> int:
        """Idempotent bulk insert — duplicates (alert_id, occurred_at) skipped."""
        if not rows:
            return 0
        stmt = pg_insert(Alert).values(rows).on_conflict_do_nothing()
        result = await self._s.execute(stmt)
        return result.rowcount or 0

    async def list_page(
        self,
        *,
        limit: int,
        before: datetime | None = None,
        min_vae_prob: float | None = None,
        only_unacknowledged: bool = False,
    ) -> list[dict[str, Any]]:
        """Keyset-paginated alert list joined with latest detection.

        Cursor = `occurred_at` (descending). `before` is the cursor value —
        rows strictly older are returned. `min_vae_prob` filters on the
        joined detection row (None means include alerts with no detection
        yet, e.g. pre-inference).
        """
        stmt = (
            select(
                Alert.alert_id,
                Alert.occurred_at,
                Alert.host_id,
                Alert.chain_id,
                Alert.rule_id,
                Alert.decoder_name,
                Alert.full_log,
                Alert.mitre_tactics,
                Alert.mitre_techniques,
                Alert.ckc_stage,
                Alert.acknowledged_at,
                Alert.acknowledged_by,
                Detection.vae_malicious_prob,
                Detection.ae_anomaly_score,
            )
            .select_from(Alert)
            .outerjoin(
                Detection,
                and_(
                    Detection.alert_id == Alert.alert_id,
                    Detection.occurred_at == Alert.occurred_at,
                ),
            )
            .order_by(Alert.occurred_at.desc())
            .limit(limit)
        )
        if before is not None:
            stmt = stmt.where(Alert.occurred_at < before)
        if min_vae_prob is not None:
            stmt = stmt.where(Detection.vae_malicious_prob >= min_vae_prob)
        if only_unacknowledged:
            stmt = stmt.where(Alert.acknowledged_at.is_(None))

        result = await self._s.execute(stmt)
        return [dict(row._mapping) for row in result.all()]

    async def acknowledge(
        self,
        *,
        alert_id: str,
        occurred_at: datetime,
        user_id: UUID,
        now: datetime,
    ) -> bool:
        """Mark the (alert_id, occurred_at) row acknowledged. Idempotent —
        returns True if a row was updated, False if already acked or missing.
        """
        stmt = (
            update(Alert)
            .where(Alert.alert_id == alert_id)
            .where(Alert.occurred_at == occurred_at)
            .where(Alert.acknowledged_at.is_(None))
            .values(acknowledged_at=now, acknowledged_by=user_id)
        )
        result = await self._s.execute(stmt)
        return (result.rowcount or 0) > 0

    async def get(
        self,
        *,
        alert_id: str,
        occurred_at: datetime,
    ) -> Alert | None:
        stmt = (
            select(Alert)
            .where(Alert.alert_id == alert_id)
            .where(Alert.occurred_at == occurred_at)
            .limit(1)
        )
        result = await self._s.execute(stmt)
        return result.scalar_one_or_none()

    async def count_unacknowledged(self, *, since: datetime | None = None) -> int:
        stmt = select(func.count()).select_from(Alert).where(Alert.acknowledged_at.is_(None))
        if since is not None:
            stmt = stmt.where(Alert.occurred_at >= since)
        result = await self._s.execute(stmt)
        return int(result.scalar_one())


# ---------------------------------------------------------------- Detections


class DetectionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def bulk_insert(self, rows: list[dict[str, Any]]) -> int:
        """Hypertable insert. (alert_id, occurred_at) is the conflict key."""
        if not rows:
            return 0
        stmt = pg_insert(Detection).values(rows).on_conflict_do_nothing()
        result = await self._s.execute(stmt)
        return result.rowcount or 0


# ---------------------------------------------------------------- Attack Chains


class AttackChainRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, chain_id: UUID) -> AttackChain | None:
        return await self._s.get(AttackChain, chain_id)

    async def get_open_for_host(self, host_id: UUID) -> AttackChain | None:
        result = await self._s.execute(
            select(AttackChain)
            .where(AttackChain.host_id == host_id)
            .where(AttackChain.status == "open")
            .order_by(AttackChain.opened_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count_open(self) -> int:
        from sqlalchemy import func as _func

        result = await self._s.execute(
            select(_func.count()).select_from(AttackChain).where(AttackChain.status == "open")
        )
        return int(result.scalar_one())

    async def list_recent(
        self,
        *,
        limit: int = 50,
        only_open: bool = False,
    ) -> list[AttackChain]:
        stmt = select(AttackChain)
        if only_open:
            stmt = stmt.where(AttackChain.status == "open")
        stmt = stmt.order_by(AttackChain.opened_at.desc()).limit(limit)
        result = await self._s.execute(stmt)
        return list(result.scalars().all())

    async def insert(self, chain: AttackChain) -> AttackChain:
        self._s.add(chain)
        await self._s.flush()
        return chain

    async def update_max_stage_and_prob(
        self,
        *,
        chain_id: UUID,
        ckc_stage: int,
        vae_prob: float,
        last_step: int,
    ) -> None:
        """Single-row update — `step_count = last_step + 1`, monotonic max-stage/prob."""
        chain: AttackChain | None = await self._s.get(AttackChain, chain_id)
        if chain is None:
            return
        chain.max_ckc_stage = max(chain.max_ckc_stage, ckc_stage)
        chain.max_vae_prob = max(chain.max_vae_prob, vae_prob)
        chain.step_count = last_step + 1
        await self._s.flush()

    async def close(
        self,
        *,
        chain_id: UUID,
        closed_at: datetime,
        close_reason: str,
        intervention_action_id: UUID | None = None,
    ) -> None:
        chain: AttackChain | None = await self._s.get(AttackChain, chain_id)
        if chain is None or chain.status == "closed":
            return
        chain.status = "closed"
        chain.closed_at = closed_at
        chain.close_reason = close_reason
        if intervention_action_id is not None:
            chain.intervention_action_id = intervention_action_id
        await self._s.flush()


# ---------------------------------------------------------------- DQN actions


class DqnActionRepo:
    """Phase 3 fully-uses this; Phase 2 has it ready for the verdicts writer."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def bulk_insert(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        stmt = pg_insert(DqnActionRow).values(rows).on_conflict_do_nothing()
        result = await self._s.execute(stmt)
        return result.rowcount or 0


__all__ = [
    "AlertRepo",
    "AttackChainRepo",
    "DetectionRepo",
    "DqnActionRepo",
    "HostRepo",
]
