"""Workstream 2 / Phase F — MITRE technique-name → CKC mapping.

The legacy ``MitreMapper`` only resolved by tactic/technique ID. The
training notebook also keys techniques by their human-readable names
(grouped under stage labels in ``docs/mitre_to_ckc.json``). This test
verifies 20 known names map to the correct CKC stage.
"""
from __future__ import annotations

import pytest

from strix_api.core.enums import CkcStage
from strix_api.core.mitre import get_mitre_mapper


# 20 known technique-name → expected CKC stage. Mix of canonical names and
# colon-prefixed full names (the form Wazuh sometimes emits).
_CASES = [
    ("vulnerability scanning", CkcStage(1)),
    ("active scanning", CkcStage(1)),
    ("password guessing", CkcStage(1)),
    ("brute force: password guessing", CkcStage(1)),
    ("ingress tool transfer", CkcStage(3)),
    ("valid accounts", CkcStage(3)),
    ("exploit public-facing application", CkcStage(4)),
    ("command and scripting interpreter", CkcStage(4)),
    ("unix shell", CkcStage(4)),
    ("javascript", CkcStage(4)),
    ("exploitation for privilege escalation", CkcStage(4)),
    ("native api", CkcStage(4)),
    ("create account", CkcStage(5)),
    ("account manipulation", CkcStage(5)),
    ("masquerading", CkcStage(5)),
    ("remote services", CkcStage(5)),
    ("ssh", CkcStage(5)),
    ("file and directory discovery", CkcStage(7)),
    ("process discovery", CkcStage(7)),
    ("file deletion", CkcStage(7)),
]


@pytest.mark.parametrize("name,expected", _CASES)
def test_technique_name_resolves_to_ckc(name: str, expected: CkcStage) -> None:
    mapper = get_mitre_mapper()
    got = mapper.technique(name)
    assert got == expected, f"technique({name!r}) → {got}, expected {expected}"


def test_tactic_names_resolve() -> None:
    """Spot-check a few tactic names — was already working but guard regression."""
    mapper = get_mitre_mapper()
    assert mapper.tactic("Reconnaissance") == CkcStage(1)
    assert mapper.tactic("Initial Access") == CkcStage(3)
    assert mapper.tactic("Execution") == CkcStage(4)
    assert mapper.tactic("Discovery") == CkcStage(7)


def test_resolve_picks_earliest_stage() -> None:
    """When tactics + techniques mix stages, the EARLIEST non-benign wins."""
    mapper = get_mitre_mapper()
    # 'discovery' (S7) + 'active scanning' (S1) → S1
    out = mapper.resolve(tactics=["discovery"], techniques=["active scanning"])
    assert out == CkcStage(1)


def test_unknown_name_falls_back_to_benign() -> None:
    mapper = get_mitre_mapper()
    assert mapper.resolve(techniques=["this technique does not exist"]) == CkcStage.BENIGN
