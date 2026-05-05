"""Playbook viewer schemas (Phase 10)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from strix_api.api.schemas.common import StrixBase


PlaybookSeverity = Literal["low", "medium", "high", "critical"]
PlaybookStepKind = Literal["manual", "dqn_override", "isolate_host", "block_ip"]


class PlaybookStepPayload(StrixBase):
    action: str
    chain_id_required: bool = False


class PlaybookStep(StrixBase):
    step_id: str
    title: str
    rationale: str
    kind: PlaybookStepKind
    payload: PlaybookStepPayload | None = None


class Playbook(StrixBase):
    playbook_id: str
    title: str
    description: str
    severity: PlaybookSeverity
    steps: list[PlaybookStep] = Field(default_factory=list)


class PlaybookMatchResponse(StrixBase):
    matched: list[Playbook] = Field(default_factory=list)
    fallback: Playbook | None = None
