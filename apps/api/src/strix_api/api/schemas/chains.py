"""Schemas for the per-chain investigation surface (mig 0015).

Covers four feature groups, all served under `/chains/{chain_id}/...`:
  - TLP marking
  - Tags
  - Notes (analyst journal)
  - Activity feed (case_audit_log)
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from strix_api.api.schemas.common import StrixBase


Tlp = Literal["clear", "green", "amber", "amber+strict", "red"]


# ---------------------------------------------------------------- tlp


class TlpUpdateRequest(StrixBase):
    tlp: Tlp


class TlpResponse(StrixBase):
    chain_id: UUID
    tlp: Tlp


# ---------------------------------------------------------------- tags


class TagItem(StrixBase):
    tag_id: UUID
    name: str
    colour: str = "cyan"
    description: str | None = None


class ChainTagsResponse(StrixBase):
    chain_id: UUID
    items: list[TagItem]


class TagAddRequest(StrixBase):
    name: str = Field(min_length=1, max_length=64)
    colour: str | None = None


# ---------------------------------------------------------------- notes


class ChainNoteItem(StrixBase):
    note_id: UUID
    chain_id: UUID
    author_user_id: UUID | None = None
    author_email: str | None = None
    body_md: str
    created_at: datetime


class ChainNotesResponse(StrixBase):
    chain_id: UUID
    items: list[ChainNoteItem]


class ChainNoteCreateRequest(StrixBase):
    body_md: str = Field(min_length=1, max_length=10_000)


# ---------------------------------------------------------------- activity


class ActivityEventItem(StrixBase):
    audit_id: UUID
    chain_id: UUID
    at: datetime
    user_id: UUID | None = None
    user_email: str | None = None
    # Free-form event kind, parsed from to_status. Examples:
    #   "triage"        -> triage status change (from_status / to_status raw)
    #   "tag.added"     -> tag added; payload is tag name
    #   "tag.removed"   -> tag removed; payload is tag name
    #   "tlp"           -> TLP changed; payload is "{old}->{new}"
    #   "note.added"    -> analyst note added; payload is empty
    #   "attribution"   -> chain attributed; payload is "{actor}"
    kind: str
    payload: str | None = None
    from_status: str | None = None
    to_status: str
    note: str | None = None


class ChainActivityResponse(StrixBase):
    chain_id: UUID
    items: list[ActivityEventItem]
