"""Per-host detail aggregator (Phase 5).

Surfaces what's actually in `Alert` columns for a single host, bucketed by
decoder family so the operator sees Audit / Network / File events without
us pretending to extract structure that the writer doesn't currently
persist (see verdicts_writer.py — raw_jsonb is `{}`).

When `raw_jsonb` starts carrying decoder-specific data, this service can
grow per-bucket projections (process tree, network connections, etc.)
without breaking the response shape — extra fields on `HostAlertEntry`
are additive.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.errors import NotFoundError
from strix_api.api.schemas.common import DqnActionName
from strix_api.api.schemas.hosts import (
    HostAlertEntry,
    HostChainEntry,
    HostDetailResponse,
    HostOverview,
    HostStatus,
    HostSummary,
)
from strix_api.core.enums import CkcStage, DqnAction
from strix_api.repositories.models import Alert, AttackChain, DqnActionRow, Host

_CKC_NAMES: dict[int, str] = {int(s): s.name for s in CkcStage}


def _stage_name(s: int | None) -> str:
    if s is None:
        return "BENIGN"
    return _CKC_NAMES.get(int(s), "BENIGN")


def _iso(dt: Any) -> str:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat(timespec="microseconds")
    return str(dt)


def _classify(alert: Alert) -> str:
    """Map decoder/location → bucket key for the UI tabs.

    The classification is intentionally coarse — the writer doesn't persist
    structured event data, so we route by signal source rather than by
    activity type.
    """
    decoder = (alert.decoder_name or "").lower()
    location = (alert.location or "").lower()
    if decoder == "auditd" or location.endswith("audit.log"):
        return "audit"
    if decoder == "web-accesslog" or "auth.log" in location:
        return "network"
    if decoder.startswith("syscheck"):
        return "files"
    return "other"


class HostDetailService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def host_detail(
        self,
        *,
        host_id: UUID,
        since: datetime | None,
        limit_per_bucket: int = 100,
    ) -> HostDetailResponse:
        host: Host | None = await self._s.get(Host, host_id)
        if host is None:
            raise NotFoundError(f"host {host_id} not found")

        # ---- Status derivation (mirror topology_service.py rules) -------
        agg_chain = await self._s.execute(
            select(
                func.coalesce(func.max(AttackChain.max_ckc_stage), 0),
                func.count(AttackChain.chain_id).filter(
                    AttackChain.status == "open"
                ),
            ).where(AttackChain.host_id == host_id)
        )
        max_ckc_all, open_n_all = agg_chain.one()
        max_ckc_all = int(max_ckc_all or 0)
        open_n_all = int(open_n_all or 0)
        if max_ckc_all >= 4:
            status: HostStatus = "compromised"
        elif max_ckc_all >= 1 or open_n_all > 0:
            status = "warning"
        else:
            status = "healthy"

        # ---- 24h summary --------------------------------------------------
        cutoff_24h = datetime.now(UTC) - timedelta(hours=24)
        agg_24h = await self._s.execute(
            select(
                func.count(Alert.alert_id),
                func.coalesce(func.max(Alert.ckc_stage), 0),
            )
            .where(Alert.host_id == host_id)
            .where(Alert.occurred_at >= cutoff_24h)
        )
        total_24h, max_ckc_24h = agg_24h.one()

        last_action_stmt = (
            select(DqnActionRow.action_name)
            .where(DqnActionRow.host_id == host_id)
            .order_by(desc(DqnActionRow.decided_at))
            .limit(1)
        )
        last_action_name: str | None = (
            await self._s.execute(last_action_stmt)
        ).scalar_one_or_none()
        last_dqn: DqnActionName | None = (
            last_action_name  # type: ignore[assignment]
            if last_action_name in {a.name for a in DqnAction}
            else None
        )

        summary = HostSummary(
            open_chains=open_n_all,
            total_alerts_24h=int(total_24h or 0),
            max_ckc_stage_24h=int(max_ckc_24h or 0),
            max_ckc_stage_name_24h=_stage_name(int(max_ckc_24h or 0)),
            last_dqn_action=last_dqn,
        )

        # ---- Alerts since `since` (default 24h) --------------------------
        cutoff = since or cutoff_24h
        alert_stmt = (
            select(Alert)
            .where(Alert.host_id == host_id)
            .where(Alert.occurred_at >= cutoff)
            .order_by(desc(Alert.occurred_at))
            .limit(limit_per_bucket * 5)  # generous overall cap, then bucket
        )
        alerts = (await self._s.execute(alert_stmt)).scalars().all()

        buckets: dict[str, list[HostAlertEntry]] = {
            "audit": [],
            "network": [],
            "files": [],
            "other": [],
        }
        for a in alerts:
            entry = HostAlertEntry(
                alert_id=a.alert_id,
                chain_id=a.chain_id,
                occurred_at=_iso(a.occurred_at),
                decoder_name=a.decoder_name,
                location=a.location,
                rule_id=a.rule_id,
                full_log=(a.full_log or "")[:600] or None,
                ckc_stage=a.ckc_stage,
                ckc_stage_name=_stage_name(a.ckc_stage),
                mitre_techniques=list(a.mitre_techniques or []),
            )
            bucket = _classify(a)
            if len(buckets[bucket]) < limit_per_bucket:
                buckets[bucket].append(entry)

        # ---- Chains touching this host -----------------------------------
        chains_stmt = (
            select(AttackChain)
            .where(AttackChain.host_id == host_id)
            .order_by(desc(AttackChain.opened_at))
            .limit(50)
        )
        chains = (await self._s.execute(chains_stmt)).scalars().all()
        chain_entries = [
            HostChainEntry(
                chain_id=c.chain_id,
                opened_at=_iso(c.opened_at),
                closed_at=_iso(c.closed_at) if c.closed_at else None,
                status=c.status,
                triage_status=getattr(c, "triage_status", "new") or "new",
                max_ckc_stage=int(c.max_ckc_stage),
                max_ckc_stage_name=_stage_name(c.max_ckc_stage),
                step_count=int(c.step_count),
            )
            for c in chains
        ]

        return HostDetailResponse(
            host=HostOverview(
                host_id=host.host_id,
                name=host.agent_name,
                ip=str(host.ip_address) if host.ip_address is not None else None,
                agent_id=host.agent_id,
                is_manager=host.is_manager,
                status=status,
                first_seen_at=_iso(host.first_seen_at),
                last_seen_at=_iso(host.last_seen_at),
            ),
            summary=summary,
            audit=buckets["audit"],
            network=buckets["network"],
            files=buckets["files"],
            other=buckets["other"],
            chains=chain_entries,
        )
