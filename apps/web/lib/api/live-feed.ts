// -----------------------------------------------------------------------------
// useLiveFeed — typed SSE consumer for `/streams/live-feed`.
//
// Wire shape mirrors `services/live_feed.py::build_live_feed_event` on the
// backend.
// -----------------------------------------------------------------------------

"use client";

import { apiFetch } from "./client";
import { useSseStream } from "./sse";

export interface LiveFeedEvent {
  alertId: string;
  agentId: string | null;
  chainId: string | null;
  occurredAt: string;
  ckcStage: number;          // 0=BENIGN, 1..7 attack stages
  ckcStageName: string;
  // AE
  aeAnomalyScore: number | null;
  aeReconError: number | null;
  // VAE
  vaeMaliciousProb: number | null;
  vaeUncertainty: number | null;
  // GNN
  gnnNodeRisk: number | null;
  gnnNeighborRisk: number | null;
  gnnRiskGrowth: number | null;
  // Transformer
  transformerPredCkc: number | null;
  transformerConfidence: number | null;
  // DQN
  dqnAction: number | null;
  dqnActionName: string | null;
  qValues: number[];
  // MITRE
  mitreTechniques: string[];
}

interface RecentResponse {
  channel: string;
  count: number;
  events: Array<{ id: string; data: LiveFeedEvent }>;
}

export function useLiveFeed(
  opts: { enabled?: boolean; maxEvents?: number; backfillLimit?: number } = {},
) {
  const max = opts.maxEvents ?? 200;
  const seedLimit = opts.backfillLimit ?? Math.min(max, 200);
  return useSseStream<LiveFeedEvent>("/streams/live-feed", {
    enabled: opts.enabled,
    maxEvents: max,
    eventName: "alert.new",
    // Seed from the verdict stream's recent history so a fresh page
    // load doesn't show "Waiting for verdicts…" when prior inferences
    // already happened. Best-effort — silent on failure.
    backfill: async () => {
      try {
        const res = await apiFetch<RecentResponse>(
          `/streams/live-feed/recent?limit=${seedLimit}`,
        );
        return res.events ?? [];
      } catch {
        return [];
      }
    },
  });
}
