"""Playbook lookup (Phase 10).

Static read of `data/playbooks/index.json` at import time. Match a
(stage, technique) request against each playbook's `match_techniques` and
`match_stages` lists; return all matches plus the fallback playbook.

Sub-techniques roll up to their parent (`T1059.004 → T1059`) so the
catalogue can stay compact.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from strix_api.api.schemas.playbooks import (
    Playbook,
    PlaybookMatchResponse,
    PlaybookStep,
    PlaybookStepPayload,
)


_PLAYBOOKS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "playbooks" / "index.json"
)


def _parent_technique(t: str) -> str:
    return t.split(".", 1)[0] if "." in t else t


def _to_step(raw: dict[str, Any]) -> PlaybookStep:
    payload_raw = raw.get("payload")
    payload: PlaybookStepPayload | None = None
    if isinstance(payload_raw, dict):
        payload = PlaybookStepPayload(
            action=str(payload_raw.get("action", "")),
            chain_id_required=bool(payload_raw.get("chain_id_required", False)),
        )
    return PlaybookStep(
        step_id=str(raw.get("step_id", "")),
        title=str(raw.get("title", "")),
        rationale=str(raw.get("rationale", "")),
        kind=raw.get("kind", "manual"),
        payload=payload,
    )


def _to_playbook(raw: dict[str, Any]) -> Playbook:
    return Playbook(
        playbook_id=str(raw["playbook_id"]),
        title=str(raw.get("title", "")),
        description=str(raw.get("description", "")),
        severity=raw.get("severity", "medium"),
        steps=[_to_step(s) for s in raw.get("steps", []) if isinstance(s, dict)],
    )


@lru_cache(maxsize=1)
def _load_catalog() -> dict[str, Any]:
    return json.loads(_PLAYBOOKS_PATH.read_text(encoding="utf-8"))


def find_playbooks(
    *, stage: int | None, technique: str | None
) -> PlaybookMatchResponse:
    cat = _load_catalog()
    raw_books: list[dict[str, Any]] = list(cat.get("playbooks", []))

    parent = _parent_technique((technique or "").upper().strip()) if technique else None
    stage_int = int(stage) if stage is not None else None

    matched: list[Playbook] = []
    fallback: Playbook | None = None
    for raw in raw_books:
        is_fallback = bool(raw.get("is_fallback", False))
        techniques = [t.upper() for t in raw.get("match_techniques", [])]
        stages = [int(s) for s in raw.get("match_stages", [])]

        technique_hit = parent is not None and parent in techniques
        stage_hit = stage_int is not None and stage_int in stages

        if is_fallback:
            fallback = _to_playbook(raw)
            continue

        # A playbook matches if EITHER its technique list or its stage list
        # is hit. This is intentionally permissive — multiple playbooks can
        # apply to the same chain (e.g. PrivEsc + Discovery overlap on
        # stage 4) and the operator picks which steps to follow.
        if technique_hit or stage_hit:
            matched.append(_to_playbook(raw))

    return PlaybookMatchResponse(matched=matched, fallback=fallback)
