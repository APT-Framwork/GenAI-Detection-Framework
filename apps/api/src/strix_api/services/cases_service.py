"""Cases / Chain Queue service — read + triage-update side (Phase 4).

This is the SOC analyst's home screen surface. The data sources are:
- `attack_chains` — one row per chain. Triage state lives here in the new
  `triage_status` + `assignee_user_id` columns added by migration 0006.
- `hosts` — joined for hostName / hostIp.
- `alerts` — aggregated for the `lastSeenAt` and union of MITRE techniques.
- `dqn_actions` — most recent action per chain for `lastDqnAction`.
- `users` — joined for assignee display name.
- `case_audit_log` — append-only ledger of state transitions.

The cursor is `(opened_at_iso, chain_id)` base64-encoded, mirroring the
analysis-service log cursor pattern. opened_at alone is not unique under
load, so chain_id breaks ties.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.errors import NotFoundError
from strix_api.api.schemas.cases import (
    CaseAssignee,
    CaseCounts,
    CaseItem,
    CasesListResponse,
    TriageStatus,
)
from strix_api.api.schemas.common import DqnActionName
from strix_api.core.enums import CkcStage, DqnAction
from strix_api.repositories.models import (
    Alert,
    AttackChain,
    CaseAuditLog,
    DqnActionRow,
    Host,
    User,
)


_VALID_TRIAGE: tuple[TriageStatus, ...] = ("new", "investigating", "contained", "closed")
_CKC_NAMES: dict[int, str] = {int(s): s.name for s in CkcStage}
_DQN_NAMES: dict[int, str] = {int(a): a.name for a in DqnAction}


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


# ---- cursor (opened_at, chain_id) ---------------------------------------


@dataclass(frozen=True)
class _CaseCursor:
    opened_at: datetime
    chain_id: UUID

    def encode(self) -> str:
        raw = f"{self.opened_at.isoformat()}|{self.chain_id}".encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    @classmethod
    def decode(cls, encoded: str) -> "_CaseCursor":
        pad = "=" * (-len(encoded) % 4)
        raw = base64.urlsafe_b64decode(encoded + pad).decode()
        ts, cid = raw.split("|", 1)
        return cls(opened_at=datetime.fromisoformat(ts), chain_id=UUID(cid))


# ---- service -------------------------------------------------------------


class CasesService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_cases(
        self,
        *,
        statuses: list[TriageStatus] | None = None,
        host_id: UUID | None = None,
        min_ckc: int | None = None,
        since: datetime | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> CasesListResponse:
        """Returns a page of cases plus a global per-status counter strip.

        The counter strip is unfiltered by `statuses` so the UI's segmented
        control can show all bucket sizes regardless of the active filter.
        """
        # ---- counts (always over the full unfiltered window) -------------
        count_stmt = (
            select(AttackChain.triage_status, func.count())
            .group_by(AttackChain.triage_status)
        )
        count_rows = (await self._s.execute(count_stmt)).all()
        counts = CaseCounts()
        for s, c in count_rows:
            if s in _VALID_TRIAGE:
                setattr(counts, s, int(c))

        # ---- page query -------------------------------------------------
        stmt = (
            select(
                AttackChain,
                Host.agent_name,
                Host.ip_address,
                User.email,
                User.user_id,
            )
            .select_from(AttackChain)
            .join(Host, Host.host_id == AttackChain.host_id, isouter=True)
            .join(
                User, User.user_id == AttackChain.assignee_user_id, isouter=True
            )
        )
        if statuses:
            stmt = stmt.where(AttackChain.triage_status.in_(statuses))
        if host_id is not None:
            stmt = stmt.where(AttackChain.host_id == host_id)
        if min_ckc is not None:
            stmt = stmt.where(AttackChain.max_ckc_stage >= int(min_ckc))
        if since is not None:
            stmt = stmt.where(AttackChain.opened_at >= since)
        if cursor:
            try:
                cur = _CaseCursor.decode(cursor)
            except Exception:
                cur = None
            if cur is not None:
                stmt = stmt.where(
                    or_(
                        AttackChain.opened_at < cur.opened_at,
                        and_(
                            AttackChain.opened_at == cur.opened_at,
                            AttackChain.chain_id < cur.chain_id,
                        ),
                    )
                )
        stmt = stmt.order_by(
            desc(AttackChain.opened_at), desc(AttackChain.chain_id)
        ).limit(limit + 1)

        rows = (await self._s.execute(stmt)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]

        chain_ids = [r[0].chain_id for r in rows]

        # ---- enrich: last alert ts + technique union per chain ----------
        # NB: array_agg(text[]) raises ArraySubscriptError on Postgres when
        # sub-arrays have different lengths (chains routinely have alerts
        # with varying technique counts). Split into two queries: one
        # straight max(occurred_at), one that unnest()s techniques before
        # aggregating so the agg sees a flat text column.
        last_seen_by_chain: dict[UUID, datetime] = {}
        techniques_by_chain: dict[UUID, set[str]] = {}
        if chain_ids:
            last_seen_stmt = (
                select(Alert.chain_id, func.max(Alert.occurred_at))
                .where(Alert.chain_id.in_(chain_ids))
                .group_by(Alert.chain_id)
            )
            for cid, ls in (await self._s.execute(last_seen_stmt)).all():
                last_seen_by_chain[cid] = ls

            from sqlalchemy import text as _sql_text
            tech_stmt = _sql_text(
                """
                SELECT chain_id, array_agg(DISTINCT t) AS techs
                FROM alerts a, unnest(a.mitre_techniques) AS t
                WHERE chain_id = ANY(:cids)
                GROUP BY chain_id
                """
            )
            tech_rows = (
                await self._s.execute(tech_stmt, {"cids": [str(c) for c in chain_ids]})
            ).all()
            for cid, techs in tech_rows:
                techniques_by_chain[cid] = set(techs or [])

            # ---- last DQN action per chain --------------------------
        last_action_by_chain: dict[UUID, str] = {}
        if chain_ids:
            # Distinct-on emulation via ROW_NUMBER would be cleaner; for
            # the queue this group-max-then-rejoin is fine at our scale.
            sub = (
                select(
                    DqnActionRow.chain_id,
                    func.max(DqnActionRow.decided_at).label("max_decided"),
                )
                .where(DqnActionRow.chain_id.in_(chain_ids))
                .group_by(DqnActionRow.chain_id)
                .subquery()
            )
            join_stmt = (
                select(DqnActionRow.chain_id, DqnActionRow.action_name)
                .join(
                    sub,
                    and_(
                        sub.c.chain_id == DqnActionRow.chain_id,
                        sub.c.max_decided == DqnActionRow.decided_at,
                    ),
                )
            )
            for cid, name in (await self._s.execute(join_stmt)).all():
                last_action_by_chain[cid] = name

        items: list[CaseItem] = []
        for chain, host_name, host_ip, assignee_email, assignee_uid in rows:
            last_seen = last_seen_by_chain.get(chain.chain_id) or chain.opened_at
            techniques = sorted(techniques_by_chain.get(chain.chain_id, set()))
            assignee = (
                CaseAssignee(user_id=assignee_uid, name=assignee_email)
                if assignee_uid is not None and assignee_email is not None
                else None
            )
            last_action_name = last_action_by_chain.get(chain.chain_id)
            last_dqn: DqnActionName | None = (
                last_action_name  # type: ignore[assignment]
                if last_action_name in {a.name for a in DqnAction}
                else None
            )
            items.append(
                CaseItem(
                    chain_id=chain.chain_id,
                    host_id=chain.host_id,
                    host_name=host_name,
                    host_ip=str(host_ip) if host_ip is not None else None,
                    opened_at=_iso(chain.opened_at),
                    last_seen_at=_iso(last_seen),
                    status=_normalise_triage(chain.triage_status),
                    lifecycle_status=chain.status,
                    max_ckc_stage=int(chain.max_ckc_stage),
                    max_ckc_stage_name=_stage_name(chain.max_ckc_stage),
                    max_vae_prob=float(chain.max_vae_prob),
                    step_count=int(chain.step_count),
                    assignee=assignee,
                    mitre_techniques=techniques,
                    last_dqn_action=last_dqn,
                )
            )

        next_cursor: str | None = None
        if has_more and rows:
            tail = rows[-1][0]
            next_cursor = _CaseCursor(
                opened_at=tail.opened_at, chain_id=tail.chain_id
            ).encode()

        return CasesListResponse(items=items, next_cursor=next_cursor, counts=counts)

    async def update_status(
        self,
        *,
        chain_id: UUID,
        new_status: TriageStatus,
        actor_user_id: UUID | None,
        assignee_user_id: UUID | None | _Unset,
        note: str | None,
    ) -> CaseItem:
        chain: AttackChain | None = await self._s.get(AttackChain, chain_id)
        if chain is None:
            raise NotFoundError(f"chain {chain_id} not found")

        prev = chain.triage_status
        chain.triage_status = new_status
        if not isinstance(assignee_user_id, _Unset):
            chain.assignee_user_id = assignee_user_id

        # Prefix the to_status with `triage:` so the activity feed
        # parser routes this through the workflow-event lane rather
        # than the legacy raw-string lane. Backwards-compatible —
        # _parse_event() in chain_investigation_service handles both.
        self._s.add(
            CaseAuditLog(
                audit_id=uuid4(),
                chain_id=chain_id,
                user_id=actor_user_id,
                from_status=prev,
                to_status=f"triage:{new_status}",
                note=note,
            )
        )
        await self._s.flush()

        # Re-fetch through the list pipeline so the response shape matches
        # GET /cases — saves the frontend from reconciling two shapes.
        page = await self.list_cases(
            statuses=None, host_id=None, min_ckc=None, since=None, limit=1, cursor=None
        )
        for item in page.items:
            if item.chain_id == chain_id:
                return item

        # Fallback if the chain fell off the first page (shouldn't, but
        # bound the response shape regardless).
        return CaseItem(
            chain_id=chain.chain_id,
            host_id=chain.host_id,
            host_name=None,
            host_ip=None,
            opened_at=_iso(chain.opened_at),
            last_seen_at=_iso(chain.opened_at),
            status=_normalise_triage(chain.triage_status),
            lifecycle_status=chain.status,
            max_ckc_stage=int(chain.max_ckc_stage),
            max_ckc_stage_name=_stage_name(chain.max_ckc_stage),
            max_vae_prob=float(chain.max_vae_prob),
            step_count=int(chain.step_count),
            assignee=None,
            mitre_techniques=[],
            last_dqn_action=None,
        )


def _normalise_triage(value: str | None) -> TriageStatus:
    if value in _VALID_TRIAGE:
        return value  # type: ignore[return-value]
    return "new"


class _Unset:
    """Sentinel for partial PATCH semantics — distinguishes 'not provided'
    from 'explicitly null' on the assignee field."""


UNSET = _Unset()
