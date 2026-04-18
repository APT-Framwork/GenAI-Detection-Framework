"""LLM adapter + insight service — pure-domain bits."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from strix_api.adapters.llm_adapter import (
    _MISSING,
    LlmAdapter,
    LlmError,
    LlmInsight,
    _format_sentinel_user_message,
    _make_summary_cache,
    _parse_sentinel_response,
    _summary_cache_key,
)
from strix_api.services.insight_service import InsightService
from strix_api.settings import LlmSettings


def _llm_settings(*, key: str | None = None) -> LlmSettings:
    return LlmSettings(
        anthropic_api_key=key,
        sentinel_model="claude-opus-4-7",
        livefeed_model="claude-haiku-4-5-20251001",
        sentinel_cache_ttl_seconds=300,
        livefeed_lru_size=100,
    )


# ---- prompt builders --------------------------------------------------


def test_sentinel_user_message_is_canonical_json() -> None:
    payload = {"b": 2, "a": 1, "nested": {"z": True, "y": False}}
    msg1 = _format_sentinel_user_message(payload)
    msg2 = _format_sentinel_user_message({"a": 1, "b": 2, "nested": {"y": False, "z": True}})
    assert msg1 == msg2  # sort_keys + same content → identical


def test_summary_cache_key_is_order_insensitive_for_techniques() -> None:
    a = _summary_cache_key(
        mitre_techniques=["T1059", "T1566"], decoder="auditd", rule_id="80710",
    )
    b = _summary_cache_key(
        mitre_techniques=["T1566", "T1059"], decoder="auditd", rule_id="80710",
    )
    assert a == b


def test_summary_cache_key_changes_with_decoder() -> None:
    a = _summary_cache_key(
        mitre_techniques=["T1059"], decoder="auditd", rule_id="x",
    )
    b = _summary_cache_key(
        mitre_techniques=["T1059"], decoder="syscheck", rule_id="x",
    )
    assert a != b


# ---- LRU helper -------------------------------------------------------


def test_make_summary_cache_get_set_and_eviction() -> None:
    cache = _make_summary_cache(maxsize=4)
    assert cache("missing-key") is _MISSING

    from strix_api.adapters.llm_adapter import LlmSummary
    s1 = LlmSummary(summary="a", model_version="m")
    s2 = LlmSummary(summary="b", model_version="m")
    cache("k1", _set=s1)
    cache("k2", _set=s2)
    assert cache("k1") is s1
    assert cache("k2") is s2

    # Fill to capacity → triggers eviction next set
    cache("k3", _set=s1)
    cache("k4", _set=s2)
    cache("k5", _set=s1)   # at this point one of the oldest is dropped
    assert cache.size() <= 4   # type: ignore[attr-defined]


# ---- response parser --------------------------------------------------


class _FakeContent:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeContent(text)]


def test_parse_sentinel_response_happy_path() -> None:
    raw = '{"insight":"All quiet","recommended_actions":[{"label":"Watch","rationale":"low risk"}],"confidence":0.42}'
    out = _parse_sentinel_response(_FakeResponse(raw), model_id="claude-opus-4-7")
    assert isinstance(out, LlmInsight)
    assert out.insight == "All quiet"
    assert out.confidence == 0.42
    assert out.recommended_actions == [{"label": "Watch", "rationale": "low risk"}]


def test_parse_sentinel_response_handles_fenced_json() -> None:
    raw = "```json\n" + '{"insight":"x","confidence":0.1,"recommended_actions":[]}' + "\n```"
    out = _parse_sentinel_response(_FakeResponse(raw), model_id="m")
    assert out.insight == "x"


def test_parse_sentinel_response_clips_confidence_to_unit_interval() -> None:
    raw = '{"insight":"x","confidence":99,"recommended_actions":[]}'
    out = _parse_sentinel_response(_FakeResponse(raw), model_id="m")
    assert out.confidence == 1.0


def test_parse_sentinel_response_empty_text_raises() -> None:
    with pytest.raises(LlmError):
        _parse_sentinel_response(_FakeResponse(""), model_id="m")


def test_parse_sentinel_response_non_json_raises() -> None:
    with pytest.raises(LlmError):
        _parse_sentinel_response(_FakeResponse("just plain text, no JSON"), model_id="m")


# ---- adapter without API key ----------------------------------------


@pytest.mark.asyncio
async def test_sentinel_insight_no_key_is_permanent_error() -> None:
    adapter = LlmAdapter.from_settings(_llm_settings(key=None))
    with pytest.raises(LlmError) as exc_info:
        await adapter.sentinel_insight({"some": "payload"})
    assert exc_info.value.transient is False


@pytest.mark.asyncio
async def test_live_feed_summary_no_key_is_permanent_error() -> None:
    adapter = LlmAdapter.from_settings(_llm_settings(key=None))
    with pytest.raises(LlmError) as exc_info:
        await adapter.live_feed_summary(
            mitre_techniques=["T1059"], decoder="auditd", rule_id="x",
        )
    assert exc_info.value.transient is False


# ---- payload hash determinism --------------------------------------


def test_insight_service_hash_is_canonical() -> None:
    p1 = {"a": [1, 2], "b": {"x": 0.1, "y": "z"}, "c": None}
    p2 = {"c": None, "b": {"y": "z", "x": 0.1}, "a": [1, 2]}
    h1 = InsightService.hash_snapshot(p1)
    h2 = InsightService.hash_snapshot(p2)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_insight_service_hash_changes_when_data_changes() -> None:
    h1 = InsightService.hash_snapshot({"globalRisk": {"value": 0.5}})
    h2 = InsightService.hash_snapshot({"globalRisk": {"value": 0.6}})
    assert h1 != h2


# ---- route returns placeholder when LLM not configured -------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DB_PASSWORD", "test")
    from strix_api.main import create_app
    return TestClient(create_app(), raise_server_exceptions=False)


def test_sentinel_insight_returns_placeholder_in_sandbox(client: TestClient) -> None:
    resp = client.get("/api/v1/dashboard/sentinel-insight")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stale"] is True
    assert body["confidence"] == 0.0
    assert body["modelVersion"] == "placeholder"


def test_refresh_sentinel_insight_returns_job_id(client: TestClient) -> None:
    """Even when Arq enqueue fails (no Redis in sandbox), the route still
    returns a valid jobId so the SPA can subscribe to the SSE channel."""
    resp = client.post("/api/v1/dashboard/sentinel-insight/refresh")
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert "jobId" in body and len(body["jobId"]) == 36
