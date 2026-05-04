"""MITRE→CKC mapping (uses the real docs/mitre_to_ckc.json)."""

from __future__ import annotations

from strix_api.core.enums import CkcStage
from strix_api.core.mitre import get_mitre_mapper


def test_singleton_returns_same_instance() -> None:
    a = get_mitre_mapper()
    b = get_mitre_mapper()
    assert a is b  # cached


def test_known_tactic_id_maps() -> None:
    m = get_mitre_mapper()
    # TA0043 = Reconnaissance per docs/mitre_to_ckc.json
    assert m.tactic("TA0043") == CkcStage.RECONNAISSANCE
    # TA0001 = Initial Access → Delivery (S3)
    assert m.tactic("TA0001") == CkcStage.DELIVERY


def test_subtechnique_falls_back_to_parent() -> None:
    m = get_mitre_mapper()
    # If T1059 is mapped, T1059.001 should resolve to the same stage.
    parent = m.technique("T1059")
    sub = m.technique("T1059.001")
    if parent is not None:
        assert sub == parent


def test_unknown_value_returns_none() -> None:
    m = get_mitre_mapper()
    assert m.tactic("TA9999") is None
    assert m.technique("T9999.999") is None


def test_resolve_picks_earliest_stage() -> None:
    m = get_mitre_mapper()
    stage = m.resolve(
        tactics=["TA0007", "TA0043"],  # Discovery (S4) + Reconnaissance (S1)
        techniques=[],
    )
    assert stage == CkcStage.RECONNAISSANCE  # earliest wins


def test_resolve_returns_benign_when_empty() -> None:
    m = get_mitre_mapper()
    assert m.resolve(tactics=[], techniques=[]) == CkcStage.BENIGN


def test_resolve_returns_benign_when_all_unknown() -> None:
    m = get_mitre_mapper()
    assert m.resolve(tactics=["TA9999"], techniques=["T0000"]) == CkcStage.BENIGN
