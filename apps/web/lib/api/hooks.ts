// -----------------------------------------------------------------------------
// Tanstack Query hooks per backend endpoint.
//
// Pattern: every hook returns the bare `useQuery` result so callers can do
//   const { data, isLoading, error } = useAttackVector("1h")
// without re-typing the response shape.
// -----------------------------------------------------------------------------

"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";

// --- response types (kept here as a thin layer; will switch to generated
//     `api-types.ts` once the OpenAPI spec stabilises in Phase 4)

export type WindowLiteral = "15m" | "1h" | "24h" | "7d" | "all";

export interface StageBucket {
  ckcStage: number;
  ckcName: string;
  count: number;
  percent: number;
}
export interface AttackVectorResponse {
  window: WindowLiteral;
  totalAlerts: number;
  stages: StageBucket[];
}

export interface GlobalRiskComponents {
  vaeMeanProb: number;
  gnnMaxNodeRisk: number;
  anomalyRate: number;
  riskGrowth: number;
}
export interface GlobalRiskTrendPoint { ts: string; value: number; }
export interface GlobalRiskResponse {
  window: WindowLiteral;
  globalRisk: number;
  components: GlobalRiskComponents;
  delta1h: number;
  trend: GlobalRiskTrendPoint[];
}

export interface VictimNode {
  hostId: string;
  hostName: string;
  severity: string;
  infected: boolean;
  riskScore: number;
}
export interface VictimEdge {
  from: string;
  to: string;
  edgeType: string;
  sharedIndicator?: string | null;
}
export interface VictimGraphResponse {
  window: WindowLiteral;
  nodes: VictimNode[];
  edges: VictimEdge[];
}

export interface SentinelInsightAction { label: string; rationale: string; }
export interface SentinelInsightResponse {
  generatedAt: string;
  modelVersion: string;
  insight: string;
  recommendedActions: SentinelInsightAction[];
  confidence: number;
  stale?: boolean;
}

// --- 30-second polling matches §12 Q6.
const DASHBOARD_POLL_MS = 30_000;

export function useAttackVector(window: WindowLiteral = "1h") {
  return useQuery({
    queryKey: ["dashboard", "attack-vector", window],
    queryFn: () =>
      apiFetch<AttackVectorResponse>(`/dashboard/attack-vector?window=${window}`),
    refetchInterval: DASHBOARD_POLL_MS,
    refetchIntervalInBackground: false,
  });
}

export function useGlobalRisk(window: WindowLiteral = "1h") {
  return useQuery({
    queryKey: ["dashboard", "global-risk", window],
    queryFn: () =>
      apiFetch<GlobalRiskResponse>(`/dashboard/global-risk?window=${window}`),
    refetchInterval: DASHBOARD_POLL_MS,
    refetchIntervalInBackground: false,
  });
}

export function useVictimGraph(window: WindowLiteral = "1h") {
  return useQuery({
    queryKey: ["dashboard", "victim-graph", window],
    queryFn: () =>
      apiFetch<VictimGraphResponse>(`/dashboard/victim-graph?window=${window}`),
    refetchInterval: 60_000, // §4.1 victim-graph cache TTL
    refetchIntervalInBackground: false,
  });
}

export function useSentinelInsight() {
  return useQuery({
    queryKey: ["dashboard", "sentinel-insight"],
    queryFn: () =>
      apiFetch<SentinelInsightResponse>("/dashboard/sentinel-insight"),
    // 5-min cache TTL matches §5.14
    refetchInterval: 5 * 60_000,
    refetchIntervalInBackground: false,
  });
}

export function useRefreshSentinelInsight() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<SentinelInsightResponse>("/dashboard/sentinel-insight/refresh", {
        method: "POST",
      }),
    onSuccess: (data) => {
      qc.setQueryData(["dashboard", "sentinel-insight"], data);
    },
  });
}
