// -----------------------------------------------------------------------------
// Analysis-tab hooks (Phase 5).
//
// Chain-detail hooks accept a `chainId` (UUID string). Metric panels poll
// every 5 s as a baseline and additionally invalidate on the SSE
// `chain.alert.new` channel via `useChainLiveRefresh` for sub-second
// updates during a live simulation. `useChainList` and notifications
// stay on the cheaper 30 s cadence.
// -----------------------------------------------------------------------------

"use client";

import { useEffect, useRef } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { useSseStream } from "./sse";

// ---- response types ---------------------------------------------------

export interface ChainSummary {
  chainId: string;
  hostId: string;
  openedAt: string;
  closedAt: string | null;
  status: "open" | "closed";
  closeReason: "INTERVENTION" | "IDLE_TIMEOUT" | "MAX_STEPS" | null;
  maxCkcStage: number;
  maxCkcStageName: string;
  maxVaeProb: number;
  stepCount: number;
}
export interface ChainListResponse {
  items: ChainSummary[];
  openCount: number;
}

export interface GraphSnapshotEntry {
  ts: string;
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
}
export interface GraphEvolutionResponse {
  chainId: string;
  snapshots: GraphSnapshotEntry[];
}

export interface CkcProgressionStep {
  ckcStage: number;
  ckcStageName: string;
  enteredAt: string;
  dqnAction: string | null;
  actionedAt: string | null;
}
export interface CkcProgressionResponse {
  chainId: string;
  stages: CkcProgressionStep[];
}

export interface StageProbability {
  ckcStage: number;
  ckcStageName: string;
  prob: number;
}
export interface PredictionsResponse {
  chainId: string;
  currentStage: number | null;
  currentStageName: string | null;
  predictedNextStage: number | null;
  predictedNextStageName: string | null;
  confidence: number;
  probabilities: StageProbability[];
}

export interface ForensicLogEntry {
  alertId: string;
  ts: string;
  agentName: string | null;
  rawLog: string | null;
  ruleDescription: string | null;
  decoder: string | null;
  location: string | null;
}
export interface ForensicLogsPage {
  chainId: string;
  items: ForensicLogEntry[];
  page: { cursor: string | null; hasMore: boolean };
}

export interface InfectedHost {
  hostId: string;
  hostName: string;
  firstSeen: string;
  currentStage: number | null;
  currentStageName: string | null;
}
export interface InfectionResponse {
  chainId: string;
  infectedCount: number;
  totalCount: number;
  percent: number;
  infectedHosts: InfectedHost[];
}

export interface DwellTimeResponse {
  chainId: string;
  startedAt: string;
  closedAt: string | null;
  durationSeconds: number;
  status: "open" | "closed";
  closeReason: string | null;
}

// ---- hooks -------------------------------------------------------------

const POLL_30S = 30_000;
// Chain-detail panels (predictions, ckc-progression, dwell) need to feel
// live during a simulation; 30 s makes the page look frozen. The SSE
// `chain.alert.new` channel piggybacks on top of this for sub-second
// invalidation — see useChainLiveRefresh below.
const POLL_5S = 5_000;

export function useChainList(opts: { onlyOpen?: boolean; limit?: number } = {}) {
  const params = new URLSearchParams();
  if (opts.onlyOpen) params.set("onlyOpen", "true");
  if (opts.limit) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return useQuery({
    queryKey: ["analysis", "chains", opts.onlyOpen ?? false, opts.limit ?? 50],
    queryFn: () =>
      apiFetch<ChainListResponse>(`/analysis/chains${qs ? `?${qs}` : ""}`),
    refetchInterval: POLL_30S,
  });
}

/** Open-chain count for the sidebar badge. Cheap dedicated query. */
export function useOpenChainCount() {
  const list = useChainList({ onlyOpen: true, limit: 1 });
  return list.data?.openCount ?? 0;
}

export function useChainGraphEvolution(chainId: string | null) {
  return useQuery({
    enabled: !!chainId,
    queryKey: ["analysis", "graph-evolution", chainId],
    queryFn: () =>
      apiFetch<GraphEvolutionResponse>(`/analysis/chains/${chainId}/graph-evolution`),
    refetchInterval: POLL_30S,
  });
}

export function useCkcProgression(chainId: string | null) {
  return useQuery({
    enabled: !!chainId,
    queryKey: ["analysis", "ckc-progression", chainId],
    queryFn: () =>
      apiFetch<CkcProgressionResponse>(`/analysis/chains/${chainId}/ckc-progression`),
    refetchInterval: POLL_5S,
  });
}

export function useChainPredictions(chainId: string | null) {
  return useQuery({
    enabled: !!chainId,
    queryKey: ["analysis", "predictions", chainId],
    queryFn: () =>
      apiFetch<PredictionsResponse>(`/analysis/chains/${chainId}/predictions`),
    refetchInterval: POLL_5S,
  });
}

export function useChainInfection(chainId: string | null) {
  return useQuery({
    enabled: !!chainId,
    queryKey: ["analysis", "infection", chainId],
    queryFn: () =>
      apiFetch<InfectionResponse>(`/analysis/chains/${chainId}/infection`),
    refetchInterval: 60_000,
  });
}

export function useChainDwellTime(chainId: string | null) {
  return useQuery({
    enabled: !!chainId,
    queryKey: ["analysis", "dwell-time", chainId],
    queryFn: () =>
      apiFetch<DwellTimeResponse>(`/analysis/chains/${chainId}/dwell-time`),
    refetchInterval: POLL_5S,
  });
}

/** Infinite-scroll forensic log feed. Pages are 50 items by default. */
export function useChainLogs(chainId: string | null, limit = 50) {
  return useInfiniteQuery({
    enabled: !!chainId,
    queryKey: ["analysis", "logs", chainId, limit],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const qs = new URLSearchParams({ limit: String(limit) });
      if (pageParam) qs.set("cursor", pageParam);
      return apiFetch<ForensicLogsPage>(
        `/analysis/chains/${chainId}/logs?${qs.toString()}`,
      );
    },
    getNextPageParam: (last) => (last.page.hasMore ? last.page.cursor : null),
  });
}

// ---- notifications (intervention feed) -------------------------------

export interface InterventionItem {
  actionId: string;
  alertId: string;
  chainId: string;
  hostId: string;
  agentName: string | null;
  actionName: "ESCALATE" | "ISOLATE_HOST" | "BLOCK_USER_IP" | string;
  ckcStageAtDecision: number;
  ckcStageName: string;
  decidedAt: string;
  requiresApproval: boolean;
  applied: boolean;
}

export interface NotificationsResponse {
  items: InterventionItem[];
}

export function useNotifications(limit = 50) {
  return useQuery({
    queryKey: ["analysis", "notifications", limit],
    queryFn: () =>
      apiFetch<NotificationsResponse>(`/analysis/notifications?limit=${limit}`),
    refetchInterval: 30_000,
  });
}


// ---- RL Intervention Timeline backfill ---------------------------------

export interface RlTimelinePredetected {
  chainId: string;
  hostId: string;
  agentName: string | null;
  maxCkcStage: number;
  openedAt: string;
  closedAt: string | null;
  status: string;
  interventionAt: string;
  actionName: string;
  stageAtDecision: number;
  stageAtDecisionName: string;
}

export interface RlTimelinePostDetected {
  chainId: string;
  hostId: string;
  agentName: string | null;
  maxCkcStage: number;
  openedAt: string;
  closedAt: string | null;
  status: string;
  firstMaliciousAt: string | null;
}

export interface RlTimelineResponse {
  predetected: RlTimelinePredetected[];
  // backend uses snake_case; preserved as-is for honesty about the wire shape.
  post_detected: RlTimelinePostDetected[];
}

/** Backfill source for the dashboard's RL Intervention Timeline widget.
 *  Reads `attack_chains` + `dqn_actions` directly so chains that completed
 *  before the WS connected still show up. Live `chain.alert.new` SSE frames
 *  on top of this remain authoritative for in-flight chains. */
export function useRlTimelineBackfill(sinceISO?: string | null) {
  const since = sinceISO ?? null;
  return useQuery({
    queryKey: ["analysis", "rl-timeline", since],
    queryFn: () => {
      const params = new URLSearchParams();
      if (since) params.set("since", since);
      params.set("limit", "200");
      return apiFetch<RlTimelineResponse>(`/analysis/rl-timeline?${params.toString()}`);
    },
    refetchInterval: POLL_5S,
  });
}

/** Live-tail SSE companion for `useChainLogs` — push events on top of the page. */
export function useChainLogStream(chainId: string | null) {
  return useSseStream<{ alertId: string; agentId?: string; occurredAt: string }>(
    chainId ? `/streams/chains/${chainId}/logs` : "/streams/chains/_/logs",
    { enabled: !!chainId, eventName: "chain.alert.new", maxEvents: 200 },
  );
}

/**
 * Sub-second refresh for the chain-detail panels.
 *
 * The metric hooks above poll on a 5 s interval as a baseline, but during
 * a live simulation that still feels laggy. This hook subscribes to the
 * existing `chain.alert.new` SSE channel and invalidates the chain's
 * React Query caches the moment a new alert lands on the chain — so the
 * predictions / ckc-progression / dwell / infection / logs / graph
 * panels all update within the SSE event itself.
 *
 * Intentionally a thin wrapper over useChainLogStream so we don't open a
 * second EventSource per page.
 */
export function useChainLiveRefresh(chainId: string | null): void {
  const qc = useQueryClient();
  const stream = useChainLogStream(chainId);
  const seenRef = useRef(0);

  useEffect(() => {
    if (!chainId) return;
    if (stream.events.length === seenRef.current) return;
    seenRef.current = stream.events.length;

    // Invalidate everything keyed by this chain. React Query will refetch
    // any *active* (mounted) query and skip the rest, so this is cheap.
    qc.invalidateQueries({ queryKey: ["analysis", "ckc-progression", chainId] });
    qc.invalidateQueries({ queryKey: ["analysis", "predictions", chainId] });
    qc.invalidateQueries({ queryKey: ["analysis", "dwell-time", chainId] });
    qc.invalidateQueries({ queryKey: ["analysis", "infection", chainId] });
    qc.invalidateQueries({ queryKey: ["analysis", "graph-evolution", chainId] });
    qc.invalidateQueries({ queryKey: ["analysis", "logs", chainId] });
  }, [chainId, stream.events.length, qc]);
}
