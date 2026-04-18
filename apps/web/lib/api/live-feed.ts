// -----------------------------------------------------------------------------
// useLiveFeed — typed SSE consumer for `/streams/live-feed`.
//
// Wire shape mirrors `services/live_feed.py::build_live_feed_event` on the
// backend.
// -----------------------------------------------------------------------------

"use client";

import { useSseStream } from "./sse";

export interface LiveFeedEvent {
  alertId: string;
  agentId: string | null;
  occurredAt: string;
  ckcStage: number;          // 0=BENIGN, 1..7 attack stages
  ckcStageName: string;
  vaeMaliciousProb: number | null;
  aeAnomalyScore: number | null;
  gnnNodeRisk: number | null;
  dqnAction: number | null;
  dqnActionName: string | null;
  mitreTechniques: string[];
}

export function useLiveFeed(opts: { enabled?: boolean; maxEvents?: number } = {}) {
  return useSseStream<LiveFeedEvent>("/streams/live-feed", {
    enabled: opts.enabled,
    maxEvents: opts.maxEvents ?? 100,
    eventName: "alert.new",
  });
}
