"""Live-feed pubsub publisher.

One place that knows the channel name (`strix:sse:live-feed` per §6.4) and
the wire shape — both the inference worker (Phase 3) and the verdicts
writer (Phase 4) publish through here, and `api/routes/streams.py`
subscribes to the same channel.

Wire shape (JSON-encoded utf-8 bytes on the channel):
    {
      "alertId":          str,
      "agentId":          str,
      "occurredAt":       ISO-8601,
      "ckcStage":         int (0..7),
      "ckcStageName":     str,
      "vaeMaliciousProb": float | null,
      "aeAnomalyScore":   float | null,
      "gnnNodeRisk":      float | null,
      "dqnAction":        int | null,
      "dqnActionName":    str | null,
      "mitreTechniques":  list[str],
    }
"""

from __future__ import annotations

import json
from typing import Any

from strix_api.core.enums import CkcStage

LIVE_FEED_CHANNEL = "strix:sse:live-feed"


def chain_log_channel(chain_id: str) -> str:
    """Per-chain pubsub channel for the Analysis-tab forensic log SSE."""
    return f"strix:sse:chain:{chain_id}"


def build_live_feed_event(verdict: dict[str, Any]) -> dict[str, Any]:
    """Project a `VerdictMessage` payload into the SSE envelope shape."""
    ckc_int = int(verdict.get("currentCkcStage", 0))
    try:
        ckc_name = CkcStage(ckc_int).name
    except ValueError:
        ckc_name = "UNKNOWN"
    return {
        "alertId": verdict["alertId"],
        "agentId": verdict.get("agentId"),
        "chainId": verdict.get("chainId"),
        "occurredAt": verdict["occurredAt"],
        "ckcStage": ckc_int,
        "ckcStageName": ckc_name,
        "vaeMaliciousProb": verdict.get("vaeMaliciousProb"),
        "aeAnomalyScore": verdict.get("aeAnomalyScore"),
        "gnnNodeRisk": verdict.get("gnnNodeRisk"),
        "dqnAction": verdict.get("dqnAction"),
        "dqnActionName": verdict.get("dqnActionName"),
        "mitreTechniques": list(verdict.get("mitreTechniques") or []),
    }


async def publish_live_feed(redis: Any, verdict: dict[str, Any]) -> None:
    """Publish ONE verdict event. Caller decides whether to swallow errors —
    most call sites log + continue (an SSE drop must NEVER block ingestion)."""
    payload = build_live_feed_event(verdict)
    body = json.dumps(payload).encode("utf-8")
    await redis.publish(LIVE_FEED_CHANNEL, body)
    chain_id = verdict.get("chainId")
    if chain_id:
        # Same payload to the per-chain channel — Analysis page subscribers.
        await redis.publish(chain_log_channel(str(chain_id)), body)


__all__ = [
    "LIVE_FEED_CHANNEL",
    "build_live_feed_event",
    "chain_log_channel",
    "publish_live_feed",
]
