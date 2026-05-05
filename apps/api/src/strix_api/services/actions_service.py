"""Response Action Log service (Phase 8).

Reads `dqn_actions` and `dqn_action_rollbacks` to surface the operator
ledger of DQN-proposed and operator-applied actions. Status is derived
(not a column): see `_derive_status()` for the precedence rules.

Mutations:
- `approve()`   marks `applied=True`, sets `applied_at` + `applied_by`.
- `decline()`   sets `rejected_at` + `rejected_by`. Only valid when
                `requires_approval=True` and the action is still pending.
- `rollback()`  inserts a `dqn_action_rollbacks` row referencing the
                action. Only valid when `applied=True` and no prior
                rollback exists. Audit-only — see model docstring.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.errors import NotFoundError, StrixError
from strix_api.api.schemas.actions import (
    ActionCounts,
    ActionItem,
    ActionRollback,
    ActionStatus,
    ActionsListResponse,
    ActorRef,
)
from strix_api.api.schemas.common import DqnActionName
from strix_api.core.enums import CkcStage, DqnAction
from strix_api.repositories.models import (
    AttackChain,
    DqnActionRollback,
    DqnActionRow,
    Host,
    User,
)


_CKC_NAMES: dict[int, str] = {int(s): s.name for s in CkcStage}


def _stage_name(s: int | None) -> str:
    return _CKC_NAMES.get(int(s or 0), "BENIGN")


def _iso(dt: Any) -> str:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat(timespec="microseconds")
    return str(dt)


def _derive_status(
    *,
    requires_approval: bool,
    applied: bool,
    rejected_at: datetime | None,
    rolled_back: bool,
) -> ActionStatus:
    if rolled_back:
        return "rolled_back"
    if rejected_at is not None:
        return "declined"
    if applied and not requires_approval:
        return "auto_applied"
    if applied:
        return "approved"
    return "proposed"


@dataclass(frozen=True)
class _ActionCursor:
    decided_at: datetime
    action_id: UUID

    def encode(self) -> str:
        raw = f"{self.decided_at.isoformat()}|{self.action_id}".encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    @classmethod
    def decode(cls, encoded: str) -> "_ActionCursor":
        pad = "=" * (-len(encoded) % 4)
        raw = base64.urlsafe_b64decode(encoded + pad).decode()
        ts, aid = raw.split("|", 1)
        return cls(decided_at=datetime.fromisoformat(ts), action_id=UUID(aid))


_VALID_ACTION_NAMES = {a.name for a in DqnAction}


class GuardError(StrixError):
    """Raised when a state transition is not legal (e.g. rollback an
    un-applied action). Mapped to 409 by the route."""


class ActionsService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ---- list ----------------------------------------------------------

    async def list_actions(
        self,
        *,
        statuses: list[ActionStatus] | None = None,
        host_id: UUID | None = None,
        chain_id: UUID | None = None,
        since: datetime | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> ActionsListResponse:
        Applier = User.__table__.alias("u_applier")
        Rejecter = User.__table__.alias("u_rejecter")
        Rollbacker = User.__table__.alias("u_rollbacker")

        stmt = (
            select(
                DqnActionRow,
                Host.agent_name,
                Applier.c.email.label("applier_email"),
                Applier.c.user_id.label("applier_id"),
                Rejecter.c.email.label("rejecter_email"),
                Rejecter.c.user_id.label("rejecter_id"),
                DqnActionRollback.rollback_id,
                DqnActionRollback.rolled_back_at,
                DqnActionRollback.reason,
                Rollbacker.c.email.label("rollbacker_email"),
                Rollbacker.c.user_id.label("rollbacker_id"),
            )
            .select_from(DqnActionRow)
            .join(Host, Host.host_id == DqnActionRow.host_id, isouter=True)
            .join(
                Applier,
                Applier.c.user_id == DqnActionRow.applied_by,
                isouter=True,
            )
            .join(
                Rejecter,
                Rejecter.c.user_id == DqnActionRow.rejected_by,
                isouter=True,
            )
            .join(
                DqnActionRollback,
                DqnActionRollback.action_id == DqnActionRow.action_id,
                isouter=True,
            )
            .join(
                Rollbacker,
                Rollbacker.c.user_id == DqnActionRollback.rolled_back_by,
                isouter=True,
            )
        )
        if host_id is not None:
            stmt = stmt.where(DqnActionRow.host_id == host_id)
        if chain_id is not None:
            stmt = stmt.where(DqnActionRow.chain_id == chain_id)
        if since is not None:
            stmt = stmt.where(DqnActionRow.decided_at >= since)
        if cursor:
            try:
                cur = _ActionCursor.decode(cursor)
            except Exception:  # noqa: BLE001
                cur = None
            if cur is not None:
                stmt = stmt.where(
                    or_(
                        DqnActionRow.decided_at < cur.decided_at,
                        and_(
                            DqnActionRow.decided_at == cur.decided_at,
                            DqnActionRow.action_id < cur.action_id,
                        ),
                    )
                )

        stmt = stmt.order_by(
            desc(DqnActionRow.decided_at), desc(DqnActionRow.action_id)
        ).limit(limit + 1)

        rows = (await self._s.execute(stmt)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]

        # Also derive counts in a separate, lightweight pass that doesn't
        # need any of the joins.
        count_rows = (
            await self._s.execute(
                select(
                    DqnActionRow.requires_approval,
                    DqnActionRow.applied,
                    DqnActionRow.rejected_at,
                    DqnActionRollback.rollback_id,
                    func.count(),
                )
                .select_from(DqnActionRow)
                .join(
                    DqnActionRollback,
                    DqnActionRollback.action_id == DqnActionRow.action_id,
                    isouter=True,
                )
                .group_by(
                    DqnActionRow.requires_approval,
                    DqnActionRow.applied,
                    DqnActionRow.rejected_at,
                    DqnActionRollback.rollback_id,
                )
            )
        ).all()
        counts = ActionCounts()
        for req, applied, rej, rb_id, cnt in count_rows:
            s = _derive_status(
                requires_approval=bool(req),
                applied=bool(applied),
                rejected_at=rej,
                rolled_back=rb_id is not None,
            )
            setattr(counts, s, getattr(counts, s) + int(cnt))

        items: list[ActionItem] = []
        for row in rows:
            (
                action,
                host_name,
                applier_email,
                applier_id,
                rejecter_email,
                rejecter_id,
                rb_id,
                rb_at,
                rb_reason,
                rollbacker_email,
                rollbacker_id,
            ) = row

            action_name = action.action_name
            if action_name not in _VALID_ACTION_NAMES:
                # Defensive: unrecognised name → fallback to MONITOR.
                action_name = "MONITOR"

            status = _derive_status(
                requires_approval=bool(action.requires_approval),
                applied=bool(action.applied),
                rejected_at=action.rejected_at,
                rolled_back=rb_id is not None,
            )

            applied_by = (
                ActorRef(user_id=applier_id, name=applier_email)
                if applier_id is not None and applier_email is not None
                else None
            )
            rejected_by = (
                ActorRef(user_id=rejecter_id, name=rejecter_email)
                if rejecter_id is not None and rejecter_email is not None
                else None
            )
            rollback = (
                ActionRollback(
                    rollback_id=rb_id,
                    rolled_back_at=_iso(rb_at) if rb_at else "",
                    rolled_back_by=ActorRef(
                        user_id=rollbacker_id, name=rollbacker_email
                    )
                    if rollbacker_id is not None and rollbacker_email is not None
                    else None,
                    reason=rb_reason or "",
                )
                if rb_id is not None
                else None
            )

            items.append(
                ActionItem(
                    action_id=action.action_id,
                    chain_id=action.chain_id,
                    host_id=action.host_id,
                    host_name=host_name,
                    decided_at=_iso(action.decided_at),
                    applied_at=_iso(action.applied_at) if action.applied_at else None,
                    action=int(action.action),
                    action_name=action_name,  # type: ignore[arg-type]
                    q_values=list(action.q_values or []),
                    ckc_stage_at_decision=int(action.ckc_stage_at_decision),
                    ckc_stage_name=_stage_name(action.ckc_stage_at_decision),
                    requires_approval=bool(action.requires_approval),
                    status=status,
                    applied_by=applied_by,
                    rejected_at=_iso(action.rejected_at) if action.rejected_at else None,
                    rejected_by=rejected_by,
                    rollback=rollback,
                )
            )

        # Apply status filter post-derivation (counts above are unfiltered).
        if statuses:
            wanted = set(statuses)
            items = [it for it in items if it.status in wanted]

        next_cursor: str | None = None
        if has_more and rows:
            tail_action = rows[-1][0]  # DqnActionRow
            next_cursor = _ActionCursor(
                decided_at=tail_action.decided_at, action_id=tail_action.action_id
            ).encode()

        return ActionsListResponse(
            items=items, next_cursor=next_cursor, counts=counts
        )

    # ---- mutations -----------------------------------------------------

    async def approve(
        self, *, action_id: UUID, actor_user_id: UUID, note: str | None = None
    ) -> ActionItem:
        action = await self._s.get(DqnActionRow, action_id)
        if action is None:
            raise NotFoundError(f"action {action_id} not found")
        if action.applied:
            raise GuardError("action already applied")
        if action.rejected_at is not None:
            raise GuardError("action was declined; cannot approve")
        action.applied = True
        action.applied_at = datetime.now(UTC)
        action.applied_by = actor_user_id
        await self._s.flush()
        return await self._fetch_one(action_id)

    async def decline(
        self, *, action_id: UUID, actor_user_id: UUID, reason: str
    ) -> ActionItem:
        action = await self._s.get(DqnActionRow, action_id)
        if action is None:
            raise NotFoundError(f"action {action_id} not found")
        if not action.requires_approval:
            raise GuardError("action does not require approval; cannot decline")
        if action.applied:
            raise GuardError("action already applied; cannot decline")
        if action.rejected_at is not None:
            raise GuardError("action already declined")
        action.rejected_at = datetime.now(UTC)
        action.rejected_by = actor_user_id
        # Reason is recorded via the audit log in a future revision; for
        # now we store it on the row by appending to a dedicated audit
        # ledger if/when introduced. The schema has `reason` on the body
        # so the route can log it.
        await self._s.flush()
        _ = reason  # currently logged at route layer only
        return await self._fetch_one(action_id)

    async def rollback(
        self, *, action_id: UUID, actor_user_id: UUID, reason: str
    ) -> ActionItem:
        action = await self._s.get(DqnActionRow, action_id)
        if action is None:
            raise NotFoundError(f"action {action_id} not found")
        if not action.applied:
            raise GuardError("action was not applied; nothing to roll back")

        existing = (
            await self._s.execute(
                select(DqnActionRollback).where(
                    DqnActionRollback.action_id == action_id
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise GuardError("action already rolled back")

        self._s.add(
            DqnActionRollback(
                rollback_id=uuid4(),
                action_id=action_id,
                rolled_back_by=actor_user_id,
                reason=reason,
            )
        )
        await self._s.flush()
        return await self._fetch_one(action_id)

    # ---- manual action (Phase 10 — playbook override) ----------------

    async def manual(
        self,
        *,
        chain_id: UUID,
        action: int,
        action_name: str,
        reason: str,
        actor_user_id: UUID,
    ) -> ActionItem:
        """Record an operator-initiated action against a chain. Synthesises
        a `DqnActionRow` with empty q-values + `requires_approval=False` +
        `applied=True` so the Action Log shows it as `auto_applied` (the
        operator IS the authority here, no second approval needed).

        We need an `alert_id` on the row because of the FK; we use the most
        recent alert on the chain. If the chain has no alerts yet (rare),
        we 409 — there's nothing operationally meaningful to attach to.
        """
        chain = await self._s.get(AttackChain, chain_id)
        if chain is None:
            raise NotFoundError(f"chain {chain_id} not found")

        from strix_api.repositories.models import Alert as _Alert

        alert_row = (
            await self._s.execute(
                select(_Alert.alert_id)
                .where(_Alert.chain_id == chain_id)
                .order_by(desc(_Alert.occurred_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        if alert_row is None:
            raise GuardError("chain has no alerts; cannot anchor a manual action")

        action_id = uuid4()
        now = datetime.now(UTC)
        self._s.add(
            DqnActionRow(
                action_id=action_id,
                alert_id=alert_row,
                chain_id=chain_id,
                host_id=chain.host_id,
                decided_at=now,
                action=int(action),
                action_name=action_name,
                q_values=[],
                ckc_stage_at_decision=int(chain.max_ckc_stage),
                requires_approval=False,
                applied=True,
                applied_at=now,
                applied_by=actor_user_id,
            )
        )
        await self._s.flush()
        _ = reason  # captured at route layer in audit log
        return await self._fetch_one(action_id)

    # ---- helpers -------------------------------------------------------

    async def _fetch_one(self, action_id: UUID) -> ActionItem:
        page = await self.list_actions(limit=1, cursor=None)
        for item in page.items:
            if item.action_id == action_id:
                return item
        # Fall back: re-fetch directly without joins (simple shape).
        action = await self._s.get(DqnActionRow, action_id)
        if action is None:
            raise NotFoundError(f"action {action_id} not found")
        rb = (
            await self._s.execute(
                select(DqnActionRollback).where(
                    DqnActionRollback.action_id == action_id
                )
            )
        ).scalar_one_or_none()
        status = _derive_status(
            requires_approval=bool(action.requires_approval),
            applied=bool(action.applied),
            rejected_at=action.rejected_at,
            rolled_back=rb is not None,
        )
        return ActionItem(
            action_id=action.action_id,
            chain_id=action.chain_id,
            host_id=action.host_id,
            host_name=None,
            decided_at=_iso(action.decided_at),
            applied_at=_iso(action.applied_at) if action.applied_at else None,
            action=int(action.action),
            action_name=action.action_name if action.action_name in _VALID_ACTION_NAMES else "MONITOR",  # type: ignore[arg-type]
            q_values=list(action.q_values or []),
            ckc_stage_at_decision=int(action.ckc_stage_at_decision),
            ckc_stage_name=_stage_name(action.ckc_stage_at_decision),
            requires_approval=bool(action.requires_approval),
            status=status,
            applied_by=None,
            rejected_at=_iso(action.rejected_at) if action.rejected_at else None,
            rejected_by=None,
            rollback=None,
        )
