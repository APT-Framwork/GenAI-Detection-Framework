"""Live-feed pubsub publisher.

One place that knows the channel name (`strix:sse:live-feed` per §6.4) and
the wire shape — both the inference worker (Phase 3) and the verdicts
writer (Phase 4) publish through here, and `api/routes/streams.py`
subscribes to the same channel.

Wire shape (JSON-encoded utf-8 bytes on the channel):
    {
      "alertId":          str,
      "agentId":          str,
      "chainId":          str | null,    # UUID of the AttackChain this alert belongs to
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

# Phase-2 per-model pubsub channels — multiplexed onto the unified
# /api/v1/logs/stream WebSocket. Only published when the inference worker
# is started with `STRIX_STREAM_PER_MODEL=1`. See PLATFOR_BIG_CHANGES_PLAN.md.
STREAM_AE_CHANNEL = "strix:stream:ae"
STREAM_VAE_CHANNEL = "strix:stream:vae"
STREAM_GNN_CHANNEL = "strix:stream:gnn"
STREAM_RL_CHANNEL = "strix:stream:rl"


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
    # The /ai-engine page renders one panel per model and needs every
    # model's full output, not just the headline score. q_values stays
    # a small list (DqnAction has 5 entries) so the SSE payload remains
    # ~250 bytes — fine for high-frequency streaming.
    q_values_raw = verdict.get("qValues") or []
    try:
        q_values = [float(q) for q in q_values_raw]
    except (TypeError, ValueError):
        q_values = []
    return {
        "alertId": verdict["alertId"],
        "agentId": verdict.get("agentId"),
        "chainId": verdict.get("chainId"),
        "occurredAt": verdict["occurredAt"],
        "ckcStage": ckc_int,
        "ckcStageName": ckc_name,
        # AE
        "aeAnomalyScore": verdict.get("aeAnomalyScore"),
        "aeReconError": verdict.get("aeReconError"),
        # VAE
        "vaeMaliciousProb": verdict.get("vaeMaliciousProb"),
        "vaeUncertainty": verdict.get("vaeUncertainty"),
        # GNN
        "gnnNodeRisk": verdict.get("gnnNodeRisk"),
        "gnnNeighborRisk": verdict.get("gnnNeighborRisk"),
        "gnnRiskGrowth": verdict.get("gnnRiskGrowth"),
        # Transformer
        "transformerPredCkc": verdict.get("transformerPredCkc"),
        "transformerConfidence": verdict.get("transformerConfidence"),
        # DQN
        "dqnAction": verdict.get("dqnAction"),
        "dqnActionName": verdict.get("dqnActionName"),
        "qValues": q_values,
        # MITRE — already exposed
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
    "STREAM_AE_CHANNEL",
    "STREAM_GNN_CHANNEL",
    "STREAM_RL_CHANNEL",
    "STREAM_VAE_CHANNEL",
    "build_live_feed_event",
    "chain_log_channel",
    "publish_live_feed",
]
