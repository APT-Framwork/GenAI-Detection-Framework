// -----------------------------------------------------------------------------
// Analysis-tab hooks (Phase 5).
//
// All chain-detail hooks accept a `chainId` (UUID string) and short-poll
// every 30 s except `useChainLogs` which is paged on demand and gets live
// updates via the SSE companion `useChainLogStream`.
// -----------------------------------------------------------------------------

"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

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
    refetchInterval: POLL_30S,
  });
}

export function useChainPredictions(chainId: string | null) {
  return useQuery({
    enabled: !!chainId,
    queryKey: ["analysis", "predictions", chainId],
    queryFn: () =>
      apiFetch<PredictionsResponse>(`/analysis/chains/${chainId}/predictions`),
    refetchInterval: POLL_30S,
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
    refetchInterval: POLL_30S,
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


/** Live-tail SSE companion for `useChainLogs` — push events on top of the page. */
export function useChainLogStream(chainId: string | null) {
  return useSseStream<{ alertId: string; agentId?: string; occurredAt: string }>(
    chainId ? `/streams/chains/${chainId}/logs` : "/streams/chains/_/logs",
    { enabled: !!chainId, eventName: "chain.alert.new", maxEvents: 200 },
  );
}
