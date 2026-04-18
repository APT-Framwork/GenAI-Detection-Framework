/**
 * Typed React Query hooks for the STRIX backend.
 *
 * Shape definitions mirror the Pydantic schemas in
 * `apps/api/src/strix_api/api/schemas/` (camelCase via `to_camel`).
 */

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiDelete, apiGet, apiPost } from "./client";

// ---- dashboard --------------------------------------------------------

export type Window = "15m" | "1h" | "24h" | "7d" | "all";

export type StageBucket = {
  ckcStage: number;
  ckcName: string;
  count: number;
};

export type AttackVectorResponse = {
  window: Window;
  totalAlerts: number;
  stages: StageBucket[];
};

export function useAttackVector(window: Window = "1h") {
  return useQuery({
    queryKey: ["dashboard", "attack-vector", window],
    queryFn: () =>
      apiGet<AttackVectorResponse>(`/dashboard/attack-vector?window=${window}`),
    staleTime: 30_000,
  });
}

export type GlobalRiskResponse = {
  window: Window;
  globalRisk: number;
  components: {
    vaeMeanProb: number;
    gnnMaxNodeRisk: number;
    anomalyRate: number;
    riskGrowth: number;
  };
  delta1h: number;
  trend: { ts: string; value: number }[];
};

export function useGlobalRisk(window: Window = "1h") {
  return useQuery({
    queryKey: ["dashboard", "global-risk", window],
    queryFn: () =>
      apiGet<GlobalRiskResponse>(`/dashboard/global-risk?window=${window}`),
    staleTime: 30_000,
    refetchInterval: 60_000,  // dashboards tick once a minute
  });
}

export type SentinelInsightResponse = {
  generatedAt: string;
  modelVersion: string;
  insight: string;
  recommendedActions: { label: string; rationale: string }[];
  confidence: number;
  stale?: boolean;
};

export function useSentinelInsight() {
  return useQuery({
    queryKey: ["dashboard", "sentinel-insight"],
    queryFn: () => apiGet<SentinelInsightResponse>(`/dashboard/sentinel-insight`),
    staleTime: 5 * 60_000,  // matches backend LLM cache TTL
  });
}

export function useRefreshSentinelInsight() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiPost<{ jobId: string }>(`/dashboard/sentinel-insight/refresh`),
    onSuccess: () => {
      // the refresh is async (Arq); invalidate after a short delay to
      // let the worker land the new row, then re-query
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["dashboard", "sentinel-insight"] });
      }, 3_000);
    },
  });
}

// ---- alerts -----------------------------------------------------------

export type Severity = "critical" | "high" | "medium" | "low" | "info";

export type AlertItem = {
  alertId: string;
  occurredAt: string;
  hostId: string | null;
  chainId: string | null;
  ruleId: string | null;
  decoderName: string | null;
  fullLog: string | null;
  mitreTactics: string[];
  mitreTechniques: string[];
  ckcStage: number | null;
  severity: Severity;
  vaeMaliciousProb: number | null;
  aeAnomalyScore: number | null;
  acknowledgedAt: string | null;
  acknowledgedBy: string | null;
};

type AlertListPage = {
  items: AlertItem[];
  page: { cursor: string | null; hasMore: boolean };
};

export type AlertSeverityFilter = "all" | Severity;

export function useAlertsInfinite(opts: {
  severity?: AlertSeverityFilter;
  onlyUnacknowledged?: boolean;
  limit?: number;
} = {}) {
  const severity = opts.severity ?? "all";
  const onlyUnack = opts.onlyUnacknowledged ?? false;
  const limit = opts.limit ?? 30;

  return useInfiniteQuery<AlertListPage>({
    queryKey: ["alerts", { severity, onlyUnack, limit }],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const params = new URLSearchParams({
        severity,
        limit: String(limit),
        only_unacknowledged: String(onlyUnack),
      });
      if (pageParam) params.set("cursor", String(pageParam));
      return apiGet<AlertListPage>(`/alerts?${params.toString()}`);
    },
    getNextPageParam: (last) =>
      last.page.hasMore ? last.page.cursor : undefined,
    staleTime: 10_000,
  });
}

export function useUnacknowledgedCount() {
  return useQuery({
    queryKey: ["alerts", "unack-count"],
    queryFn: () => apiGet<{ count: number }>(`/alerts/unacknowledged/count`),
    staleTime: 10_000,
    refetchInterval: 30_000,
  });
}

export function useAcknowledgeAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { alertId: string; occurredAt: string }) =>
      apiPost(
        `/alerts/${encodeURIComponent(args.alertId)}/acknowledge`,
        { occurredAt: args.occurredAt },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

// ---- analysis (chain detail — for mobile deep link) -------------------

export type ChainSummary = {
  chainId: string;
  hostId: string;
  openedAt: string;
  closedAt: string | null;
  status: string;
  closeReason: string | null;
  maxCkcStage: number | null;
  maxVaeProb: number | null;
  stepCount: number;
};

export type CkcProgressionStep = {
  ckcStage: number;
  ckcStageName: string;
  enteredAt: string;
  dqnAction: string | null;
  actionedAt: string | null;
};

export function useCkcProgression(chainId: string | null) {
  return useQuery({
    queryKey: ["analysis", "ckc-progression", chainId],
    enabled: !!chainId,
    queryFn: () =>
      apiGet<{ chainId: string; stages: CkcProgressionStep[] }>(
        `/analysis/chains/${chainId}/ckc-progression`,
      ),
  });
}

export function useChainInfection(chainId: string | null) {
  return useQuery({
    queryKey: ["analysis", "infection", chainId],
    enabled: !!chainId,
    queryFn: () =>
      apiGet<{
        chainId: string;
        infectedCount: number;
        totalCount: number;
        percent: number;
      }>(`/analysis/chains/${chainId}/infection`),
  });
}

export function useChainDwellTime(chainId: string | null) {
  return useQuery({
    queryKey: ["analysis", "dwell-time", chainId],
    enabled: !!chainId,
    queryFn: () =>
      apiGet<{
        chainId: string;
        startedAt: string;
        closedAt: string | null;
        durationSeconds: number;
        status: string;
        closeReason: string | null;
      }>(`/analysis/chains/${chainId}/dwell-time`),
  });
}

// ---- threat-intel -----------------------------------------------------

export type IocItem = {
  indicator: string;
  type: "email" | "ip" | "domain" | "hash" | string;
  reputation: "malicious" | "suspicious" | "clean" | "unknown" | string;
  source: string;
  lastChecked: string;
  breachCount: number | null;
  stale: boolean;
};

export type IocSearchResponse = {
  items: IocItem[];
  total: number;
  page: number;
};

export function useIocSearch(query: string, type: string | null = null) {
  const q = query.trim();
  return useQuery({
    queryKey: ["threat-intel", "iocs", q, type],
    enabled: q.length > 0,
    queryFn: () => {
      const params = new URLSearchParams({ q });
      if (type) params.set("type", type);
      return apiGet<IocSearchResponse>(`/threat-intel/iocs?${params.toString()}`);
    },
    staleTime: 60_000,
  });
}

// ---- monitoring -------------------------------------------------------

export type ModelHealth = {
  name: string;
  version: string;
  weightsSha256: string;
  status: "active" | "degraded" | string;
  accuracy: number | null;
  f1: number | null;
  p50LatencyMs: number | null;
  p99LatencyMs: number | null;
  driftKl: number | null;
  lastHealthCheck: string;
};

export function useModels() {
  return useQuery({
    queryKey: ["monitoring", "models"],
    queryFn: () => apiGet<{ models: ModelHealth[] }>(`/monitoring/models`),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export type DriftItem = {
  model: string;
  klDivergence: number;
  computedAt: string;
};

export function useDrift(windowMinutes = 60) {
  return useQuery({
    queryKey: ["monitoring", "drift", windowMinutes],
    queryFn: () =>
      apiGet<{ windowMinutes: number; items: DriftItem[] }>(
        `/monitoring/drift?window_minutes=${windowMinutes}`,
      ),
    staleTime: 60_000,
  });
}

// ---- file scan -------------------------------------------------------

export type FileScanResponse = {
  scanId: string;
  sha256: string;
  sizeBytes: number;
  status: "queued" | "scanning" | "complete" | "error" | string;
  filename: string;
};

export function useFileScan() {
  return useMutation<FileScanResponse, unknown, { uri: string; name: string; mime?: string }>({
    mutationFn: async ({ uri, name, mime }) => {
      const form = new FormData();
      // React Native's fetch multipart takes `{ uri, name, type }` — RN's
      // FormData polyfill accepts the object shape even though the
      // global DOM typings only allow Blob/string.
      const filePart = {
        uri,
        name,
        type: mime ?? "application/octet-stream",
      } as unknown as Blob;
      form.append("file", filePart);
      return apiPost<FileScanResponse>(`/threat-intel/files/scan`, form);
    },
  });
}

// ---- devices (for M3 push integration) --------------------------------

export function useRegisterDevice() {
  return useMutation({
    mutationFn: (args: {
      expoPushToken: string;
      platform: "ios" | "android" | "web";
      appVersion?: string;
    }) => apiPost(`/auth/devices`, args),
  });
}

export function useUnregisterDevice() {
  return useMutation({
    mutationFn: (token: string) =>
      apiDelete(`/auth/devices/${encodeURIComponent(token)}`),
  });
}
