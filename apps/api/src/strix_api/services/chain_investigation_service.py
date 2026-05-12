"""Per-chain investigation operations (mig 0015).

  - TLP get/set, with audit trail.
  - Tag attach/detach (idempotent), with audit trail.
  - Notes list/add (append-only), with audit trail.
  - Activity feed read — parses the `<kind>:<value>` convention used
    by the writes here and by `engine_audit` events from elsewhere
    (the verdicts writer's triage transitions, attribution events).

Notes on conventions
--------------------
`case_audit_log.to_status` is the canonical event string. Format:

  - "triage:<state>"          — triage workflow change
                                (from_status carries the previous state)
  - "tag.added:<name>"        — tag added
  - "tag.removed:<name>"      — tag removed
  - "tlp:<old>-><new>"        — TLP changed
  - "note.added"              — analyst note added (no extra payload)
  - "attribution:<actor>"     — auto-attribution attached an actor

The route layer parses this string into a `kind` + `payload` so the UI
doesn't need to know the encoding.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.errors import NotFoundError
from strix_api.api.schemas.chains import (
    ActivityEventItem,
    ChainNoteItem,
    TagItem,
)
from strix_api.repositories.models import (
    AttackChain,
    CaseAuditLog,
    ChainNote,
    Tag,
    TagLink,
    User,
)


_VALID_TLP = {"clear", "green", "amber", "amber+strict", "red"}


class ChainInvestigationService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ---------------------------------------------------------------- TLP

    async def get_tlp(self, chain_id: UUID) -> str:
        chain = await self._s.get(AttackChain, chain_id)
        if chain is None:
            raise NotFoundError(f"chain {chain_id} not found")
        return chain.tlp or "amber"

    async def set_tlp(self, *, chain_id: UUID, tlp: str, user_id: UUID | None) -> str:
        if tlp not in _VALID_TLP:
            raise ValueError(f"invalid tlp: {tlp}")
        chain = await self._s.get(AttackChain, chain_id)
        if chain is None:
            raise NotFoundError(f"chain {chain_id} not found")
        old = chain.tlp or "amber"
        if old == tlp:
            return old
        chain.tlp = tlp
        await self._audit(
            chain_id=chain_id,
            user_id=user_id,
            from_status=old,
            to_status=f"tlp:{old}->{tlp}",
        )
        await self._s.commit()
        return tlp

    # ---------------------------------------------------------------- tags

    async def list_tags(self, chain_id: UUID) -> list[TagItem]:
        rows = (
            await self._s.execute(
                select(Tag.tag_id, Tag.name, Tag.colour, Tag.description)
                .select_from(TagLink)
                .join(Tag, Tag.tag_id == TagLink.tag_id)
                .where(TagLink.entity_type == "chain")
                .where(TagLink.entity_id == chain_id)
                .order_by(Tag.name)
            )
        ).all()
        return [
            TagItem(tag_id=tid, name=name, colour=colour, description=desc)
            for tid, name, colour, desc in rows
        ]

    async def _get_or_create_tag(self, name: str, colour: str | None) -> UUID:
        norm = name.strip().lower()
        if not norm:
            raise ValueError("tag name is empty")
        row = (
            await self._s.execute(select(Tag).where(Tag.name == norm))
        ).scalar_one_or_none()
        if row is not None:
            return row.tag_id
        tag = Tag(
            tag_id=uuid4(),
            name=norm,
            colour=(colour or "cyan").strip().lower(),
        )
        self._s.add(tag)
        await self._s.flush()
        return tag.tag_id

    async def add_tag(
        self,
        *,
        chain_id: UUID,
        name: str,
        colour: str | None,
        user_id: UUID | None,
    ) -> list[TagItem]:
        chain = await self._s.get(AttackChain, chain_id)
        if chain is None:
            raise NotFoundError(f"chain {chain_id} not found")
        tag_id = await self._get_or_create_tag(name, colour)
        # Idempotent — ON CONFLICT DO NOTHING via the unique constraint.
        existing = (
            await self._s.execute(
                select(TagLink.link_id).where(
                    TagLink.entity_type == "chain",
                    TagLink.entity_id == chain_id,
                    TagLink.tag_id == tag_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            self._s.add(
                TagLink(
                    link_id=uuid4(),
                    entity_type="chain",
                    entity_id=chain_id,
                    tag_id=tag_id,
                    created_by=user_id,
                )
            )
            await self._audit(
                chain_id=chain_id,
                user_id=user_id,
                to_status=f"tag.added:{name.strip().lower()}",
            )
            await self._s.commit()
        return await self.list_tags(chain_id)

    async def remove_tag(
        self, *, chain_id: UUID, name: str, user_id: UUID | None
    ) -> list[TagItem]:
        norm = name.strip().lower()
        # Find tag_id
        tag_row = (
            await self._s.execute(select(Tag.tag_id).where(Tag.name == norm))
        ).scalar_one_or_none()
        if tag_row is None:
            return await self.list_tags(chain_id)
        await self._s.execute(
            text(
                """
                DELETE FROM tag_links
                WHERE entity_type = 'chain'
                  AND entity_id = :cid
                  AND tag_id = :tid
                """
            ),
            {"cid": chain_id, "tid": tag_row},
        )
        await self._audit(
            chain_id=chain_id, user_id=user_id, to_status=f"tag.removed:{norm}"
        )
        await self._s.commit()
        return await self.list_tags(chain_id)

    # ---------------------------------------------------------------- notes

    async def list_notes(self, chain_id: UUID) -> list[ChainNoteItem]:
        rows = (
            await self._s.execute(
                select(ChainNote, User.email)
                .join(User, User.user_id == ChainNote.author_user_id, isouter=True)
                .where(ChainNote.chain_id == chain_id)
                .order_by(ChainNote.created_at.desc())
            )
        ).all()
        return [
            ChainNoteItem(
                note_id=n.note_id,
                chain_id=n.chain_id,
                author_user_id=n.author_user_id,
                author_email=email,
                body_md=n.body_md,
                created_at=n.created_at,
            )
            for n, email in rows
        ]

    async def add_note(
        self, *, chain_id: UUID, body_md: str, user_id: UUID | None
    ) -> list[ChainNoteItem]:
        chain = await self._s.get(AttackChain, chain_id)
        if chain is None:
            raise NotFoundError(f"chain {chain_id} not found")
        body = body_md.strip()
        if not body:
            raise ValueError("note body is empty")
        self._s.add(
            ChainNote(
                note_id=uuid4(),
                chain_id=chain_id,
                author_user_id=user_id,
                body_md=body,
            )
        )
        await self._audit(
            chain_id=chain_id, user_id=user_id, to_status="note.added"
        )
        await self._s.commit()
        return await self.list_notes(chain_id)

    # ---------------------------------------------------------------- activity

    async def list_activity(
        self, chain_id: UUID, *, limit: int = 100
    ) -> list[ActivityEventItem]:
        rows = (
            await self._s.execute(
                select(CaseAuditLog, User.email)
                .join(User, User.user_id == CaseAuditLog.user_id, isouter=True)
                .where(CaseAuditLog.chain_id == chain_id)
                .order_by(CaseAuditLog.at.desc())
                .limit(limit)
            )
        ).all()

        out: list[ActivityEventItem] = []
        for row, email in rows:
            kind, payload = _parse_event(row.to_status, row.from_status)
            out.append(
                ActivityEventItem(
                    audit_id=row.audit_id,
                    chain_id=row.chain_id,
                    at=row.at,
                    user_id=row.user_id,
                    user_email=email,
                    kind=kind,
                    payload=payload,
                    from_status=row.from_status,
                    to_status=row.to_status,
                    note=row.note,
                )
            )
        return out

    # ---------------------------------------------------------------- audit helper

    async def _audit(
        self,
        *,
        chain_id: UUID,
        user_id: UUID | None,
        to_status: str,
        from_status: str | None = None,
        note: str | None = None,
    ) -> None:
        self._s.add(
            CaseAuditLog(
                audit_id=uuid4(),
                chain_id=chain_id,
                user_id=user_id,
                from_status=from_status,
                to_status=to_status,
                note=note,
                at=datetime.now(UTC),
            )
        )


def _parse_event(to_status: str, from_status: str | None) -> tuple[str, str | None]:
    """Parse the `<kind>:<value>` convention from `to_status`.

    Falls back to ("triage", to_status) for legacy plain-state writes
    (mig 0006 didn't prefix triage events).
    """
    if to_status.startswith("tag.added:"):
        return ("tag.added", to_status[len("tag.added:"):])
    if to_status.startswith("tag.removed:"):
        return ("tag.removed", to_status[len("tag.removed:"):])
    if to_status.startswith("tlp:"):
        return ("tlp", to_status[len("tlp:"):])
    if to_status == "note.added":
        return ("note.added", None)
    if to_status.startswith("attribution:"):
        return ("attribution", to_status[len("attribution:"):])
    if to_status.startswith("triage:"):
        return ("triage", to_status[len("triage:"):])
    # Legacy: triage transitions from mig 0006 wrote raw status names.
    return ("triage", to_status)


__all__ = ["ChainInvestigationService"]
