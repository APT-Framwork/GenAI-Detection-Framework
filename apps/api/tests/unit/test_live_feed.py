"""Live-feed envelope projection."""

from __future__ import annotations

from strix_api.services.live_feed import LIVE_FEED_CHANNEL, build_live_feed_event


def test_channel_name_matches_plan_64() -> None:
    """§6.4 Redis key schema."""
    assert LIVE_FEED_CHANNEL == "strix:sse:live-feed"


def test_envelope_has_required_fields() -> None:
    verdict = {
        "alertId": "abc-123",
        "agentId": "001",
        "occurredAt": "2026-04-18T09:00:00Z",
        "currentCkcStage": 4,  # EXPLOITATION
        "vaeMaliciousProb": 0.82,
        "aeAnomalyScore": 1.2,
        "gnnNodeRisk": 0.45,
        "dqnAction": 2,
        "dqnActionName": "ESCALATE",
        "mitreTechniques": ["T1059", "T1566"],
    }
    event = build_live_feed_event(verdict)
    assert event["alertId"] == "abc-123"
    assert event["agentId"] == "001"
    assert event["ckcStage"] == 4
    assert event["ckcStageName"] == "EXPLOITATION"
    assert event["vaeMaliciousProb"] == 0.82
    assert event["dqnActionName"] == "ESCALATE"
    assert event["mitreTechniques"] == ["T1059", "T1566"]


def test_envelope_handles_unknown_stage_gracefully() -> None:
    verdict = {
        "alertId": "x",
        "agentId": "1",
        "occurredAt": "2026-04-18T09:00:00Z",
        "currentCkcStage": 999,
        "mitreTechniques": [],
    }
    event = build_live_feed_event(verdict)
    assert event["ckcStage"] == 999
    assert event["ckcStageName"] == "UNKNOWN"


def test_envelope_tolerates_missing_optional_fields() -> None:
    verdict = {
        "alertId": "x",
        "agentId": "1",
        "occurredAt": "2026-04-18T09:00:00Z",
        "currentCkcStage": 0,
    }
    event = build_live_feed_event(verdict)
    assert event["ckcStageName"] == "BENIGN"
    assert event["vaeMaliciousProb"] is None
    assert event["aeAnomalyScore"] is None
    assert event["mitreTechniques"] == []
