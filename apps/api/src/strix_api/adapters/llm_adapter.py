"""LLM adapter (§5.14).

One adapter, two methods, two model IDs:
    sentinel_insight()   → Claude Opus 4.7 (deep reasoning, low volume,
                          5-min result cache · prompt caching on the
                          static MITRE+system prefix)
    live_feed_summary()  → Claude Haiku 4.5 (high volume, 1-line text,
                          in-process LRU keyed by SHA-1(mitre+decoder+ruleId))

Prompt caching uses Anthropic's `cache_control: {type: 'ephemeral'}` on the
shared system block — every call pays the per-alert delta only (§5.14
"prompt caching via the Anthropic SDK").

Circuit breaker (`pybreaker`, 5 failures / 60 s → open → 30 s half-open).
Breaker open → `LlmError(transient=True)` → callers fall back to a stale
cached value (`stale: true` in the API response per §5.14 fallback policy).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import pybreaker

from strix_api.api.errors import StrixError
from strix_api.observability import (
    external_api_duration_seconds,
    external_api_errors_total,
    get_logger,
)
from strix_api.settings import LlmSettings

log = get_logger("strix_api.adapters.llm_adapter")


class LlmError(StrixError):
    status_code = 503
    title = "LLM Unavailable"
    code = "LLM_UNAVAILABLE"

    def __init__(self, detail: str | None = None, *, transient: bool = True) -> None:
        super().__init__(detail)
        self.transient = transient


@dataclass(frozen=True)
class LlmInsight:
    """Result of the Sentinel Insight call."""

    insight: str
    recommended_actions: list[dict[str, str]]
    confidence: float
    model_version: str


@dataclass(frozen=True)
class LlmSummary:
    """Result of the per-alert Live-Feed one-liner call."""

    summary: str
    model_version: str


_SENTINEL_SYSTEM_PROMPT = """You are STRIX Sentinel, the AI security analyst embedded in the STRIX
SOC platform. You receive a compact JSON snapshot of the last hour of
platform activity and produce a short, actionable insight for human
analysts on shift.

Output strict JSON with three keys:
    "insight":             string (1-3 sentences, plain English)
    "recommended_actions": list of {"label": str, "rationale": str}, length 1-4
    "confidence":          float in [0, 1]

You see ONLY:
- the latest 10 MITRE techniques observed (with counts),
- the last 3 DQN interventions (action + ckc stage),
- the current Global Risk score and its trend.

Do NOT speculate beyond what's in the snapshot. If the data is sparse,
say so in `insight` and lower the `confidence`. Avoid jargon.
""".strip()


_LIVEFEED_SYSTEM_PROMPT = """You produce 1-line summaries of single Wazuh alerts for the STRIX live
feed. Output ONE sentence, ≤140 characters, no quotes, no JSON. Surface
the MITRE tactic + decoder when both are present. Do not invent details.
""".strip()


class LlmAdapter:
    """Stateless apart from the Anthropic client + breaker."""

    def __init__(
        self,
        settings: LlmSettings,
        *,
        client: Any | None = None,
    ) -> None:
        self._settings = settings
        self._client = client            # `None` when no key — every call raises
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=5,
            reset_timeout=30,
            name="anthropic",
        )
        # Bounded LRU on the Live-Feed one-liner result.
        self._summary_cache = _make_summary_cache(settings.livefeed_lru_size)

    @property
    def breaker_state(self) -> str:
        return self._breaker.current_state

    # ---- factory --------------------------------------------------

    @classmethod
    def from_settings(cls, settings: LlmSettings) -> LlmAdapter:
        if settings.anthropic_api_key is None:
            log.warning("llm_adapter_no_key", note="every call will raise LlmError")
            return cls(settings, client=None)
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover — handled at boot
            raise LlmError(f"anthropic package not installed: {exc}", transient=False) from exc
        client = AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())
        return cls(settings, client=client)

    # ---- Sentinel Insight (Opus) ----------------------------------

    async def sentinel_insight(self, payload: dict[str, Any]) -> LlmInsight:
        if self._client is None:
            raise LlmError("LLM API key not configured", transient=False)

        async def _call() -> LlmInsight:
            with external_api_duration_seconds.labels(api="llm").time():
                resp = await self._client.messages.create(
                    model=self._settings.sentinel_model,
                    max_tokens=512,
                    system=[
                        {
                            "type": "text",
                            "text": _SENTINEL_SYSTEM_PROMPT,
                            # `cache_control: ephemeral` makes every subsequent
                            # call pay only for the per-alert delta (§5.14).
                            "cache_control": {"type": "ephemeral"},
                        },
                    ],
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": _format_sentinel_user_message(payload),
                                }
                            ],
                        }
                    ],
                )
            return _parse_sentinel_response(resp, model_id=self._settings.sentinel_model)

        try:
            return await self._breaker.call_async(_call)
        except pybreaker.CircuitBreakerError as exc:
            external_api_errors_total.labels(api="llm", error_kind="breaker_open").inc()
            raise LlmError("LLM circuit breaker open", transient=True) from exc
        except LlmError:
            raise
        except Exception as exc:  # noqa: BLE001
            external_api_errors_total.labels(api="llm", error_kind="exception").inc()
            raise LlmError(f"LLM call failed: {exc}", transient=True) from exc

    # ---- Live Feed one-liner (Haiku) -----------------------------

    async def live_feed_summary(
        self,
        *,
        mitre_techniques: list[str],
        decoder: str | None,
        rule_id: str | None,
    ) -> LlmSummary:
        if self._client is None:
            raise LlmError("LLM API key not configured", transient=False)

        cache_key = _summary_cache_key(
            mitre_techniques=mitre_techniques,
            decoder=decoder,
            rule_id=rule_id,
        )
        cached = self._summary_cache(cache_key)
        if cached is not _MISSING:
            return cached

        async def _call() -> LlmSummary:
            with external_api_duration_seconds.labels(api="llm").time():
                resp = await self._client.messages.create(
                    model=self._settings.livefeed_model,
                    max_tokens=80,
                    system=_LIVEFEED_SYSTEM_PROMPT,
                    messages=[
                        {
                            "role": "user",
                            "content": _format_livefeed_user_message(
                                mitre_techniques, decoder, rule_id,
                            ),
                        }
                    ],
                )
            text = _extract_first_text(resp)
            return LlmSummary(
                summary=text.strip()[:140] or _fallback_summary(
                    mitre_techniques=mitre_techniques, decoder=decoder,
                ),
                model_version=self._settings.livefeed_model,
            )

        try:
            result: LlmSummary = await self._breaker.call_async(_call)
        except pybreaker.CircuitBreakerError as exc:
            external_api_errors_total.labels(api="llm", error_kind="breaker_open").inc()
            raise LlmError("LLM circuit breaker open", transient=True) from exc
        except Exception as exc:  # noqa: BLE001
            external_api_errors_total.labels(api="llm", error_kind="exception").inc()
            raise LlmError(f"LLM call failed: {exc}", transient=True) from exc

        # Cache the result for the LRU lifetime.
        self._summary_cache(cache_key, _set=result)
        return result


# ---------------------------------------------------------------- helpers


def _format_sentinel_user_message(payload: dict[str, Any]) -> str:
    import json
    return (
        "Here is the latest STRIX activity snapshot. Respond with JSON ONLY.\n\n"
        f"{json.dumps(payload, indent=2, default=str, sort_keys=True)}"
    )


def _format_livefeed_user_message(
    mitre_techniques: list[str], decoder: str | None, rule_id: str | None,
) -> str:
    parts = []
    if mitre_techniques:
        parts.append(f"MITRE techniques: {', '.join(mitre_techniques[:4])}")
    if decoder:
        parts.append(f"Wazuh decoder: {decoder}")
    if rule_id:
        parts.append(f"Rule id: {rule_id}")
    return ("Summarise this single alert in one short sentence:\n"
            + "\n".join(parts))


def _summary_cache_key(
    *, mitre_techniques: list[str], decoder: str | None, rule_id: str | None,
) -> str:
    raw = "|".join([
        ",".join(sorted(mitre_techniques)),
        (decoder or ""),
        (rule_id or ""),
    ]).encode("utf-8")
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()


def _extract_first_text(resp: Any) -> str:
    """Pull the first text block out of an Anthropic Messages API response."""
    content = getattr(resp, "content", None) or []
    for block in content:
        # block can be a model object OR a dict (depends on SDK version).
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text")
        if text:
            return str(text)
    return ""


def _parse_sentinel_response(resp: Any, *, model_id: str) -> LlmInsight:
    import json

    raw = _extract_first_text(resp).strip()
    if not raw:
        raise LlmError("LLM returned empty response", transient=True)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Some models wrap JSON in a fenced code block; try to recover.
        if raw.startswith("```"):
            lines = raw.splitlines()
            inner = "\n".join(l for l in lines if not l.startswith("```"))
            data = json.loads(inner)
        else:
            raise LlmError(f"LLM returned non-JSON: {raw[:80]!r}", transient=True) from None

    insight = str(data.get("insight", "")).strip()
    confidence = float(data.get("confidence", 0.0))
    actions = data.get("recommended_actions") or []
    if not isinstance(actions, list):
        actions = []
    cleaned_actions: list[dict[str, str]] = []
    for a in actions[:4]:
        if isinstance(a, dict):
            label = str(a.get("label", "")).strip()
            rationale = str(a.get("rationale", "")).strip()
            if label:
                cleaned_actions.append({"label": label, "rationale": rationale})

    return LlmInsight(
        insight=insight or "No insight produced — payload may be too sparse.",
        recommended_actions=cleaned_actions,
        confidence=max(0.0, min(1.0, confidence)),
        model_version=model_id,
    )


def _fallback_summary(*, mitre_techniques: list[str], decoder: str | None) -> str:
    """Used when the LLM returns empty text — keep the live-feed flowing."""
    if mitre_techniques:
        return f"MITRE {mitre_techniques[0]}: alert from {decoder or 'unknown decoder'}"
    return f"Alert from decoder {decoder or 'unknown'}"


# -- a tiny LRU helper around `functools.lru_cache` that lets us SET ----
#    (lru_cache doesn't expose .put), implemented as a closure with a dict
#    + insertion-order trim.

_MISSING = object()


def _make_summary_cache(maxsize: int) -> Any:
    """Returns a callable `cache(key, _set=value)`:
       - get: cache(key) → cached value or _MISSING
       - put: cache(key, _set=value) → stores value
    """
    store: dict[str, LlmSummary] = {}

    def _cache(key: str, *, _set: Any = _MISSING) -> Any:
        if _set is not _MISSING:
            if len(store) >= maxsize:
                for stale in list(store.keys())[: maxsize // 10 or 1]:
                    store.pop(stale, None)
            store[key] = _set
            return _set
        return store.get(key, _MISSING)

    _cache.size = lambda: len(store)        # type: ignore[attr-defined]
    return _cache


__all__ = [
    "LlmAdapter",
    "LlmError",
    "LlmInsight",
    "LlmSummary",
]
