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

import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

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

// ---- cases / triage --------------------------------------------------

export type TriageStatus =
  | "new"
  | "investigating"
  | "contained"
  | "closed"
  | string;

export type CaseItem = {
  chainId: string;
  hostId: string | null;
  hostName: string | null;
  openedAt: string;
  closedAt: string | null;
  maxCkcStage: number | null;
  maxVaeProb: number | null;
  status: string;
  triageStatus: TriageStatus;
  assignee: string | null;
  stepCount: number;
  lastSeenAt: string;
};

export type CasesResponse = {
  items: CaseItem[];
  counts: Record<string, number>;
};

export function useCases(opts: { status?: TriageStatus | "all"; limit?: number } = {}) {
  const status = opts.status ?? "all";
  const limit = opts.limit ?? 50;
  return useQuery({
    queryKey: ["cases", { status, limit }],
    queryFn: () => {
      const params = new URLSearchParams({ limit: String(limit) });
      if (status !== "all") params.set("status", status);
      return apiGet<CasesResponse>(`/cases?${params.toString()}`);
    },
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
}

export function useSetTriageStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      chainId: string;
      triageStatus: TriageStatus;
      assignee?: string | null;
    }) =>
      apiPatch(
        `/cases/${encodeURIComponent(args.chainId)}/status`,
        { triageStatus: args.triageStatus, assignee: args.assignee ?? null },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cases"] });
      qc.invalidateQueries({ queryKey: ["analysis"] });
    },
  });
}

// ---- DQN actions / approvals ------------------------------------------

export type DqnAction = {
  actionId: string;
  chainId: string | null;
  hostId: string | null;
  action: string;
  decidedAt: string;
  approvedAt: string | null;
  approvedBy: string | null;
  declinedAt: string | null;
  declineReason: string | null;
  rolledBackAt: string | null;
  status: "pending" | "approved" | "declined" | "rolled_back" | string;
  rationale: string | null;
  payload: Record<string, unknown> | null;
};

export type ActionsResponse = {
  items: DqnAction[];
  counts: { pending: number; approved: number; declined: number };
};

export function useActions(status: "pending" | "approved" | "declined" | "all" = "pending") {
  return useQuery({
    queryKey: ["actions", status],
    queryFn: () => {
      const params = new URLSearchParams();
      if (status !== "all") params.set("status", status);
      return apiGet<ActionsResponse>(`/actions?${params.toString()}`);
    },
    staleTime: 10_000,
    refetchInterval: 20_000,
  });
}

export function useApproveAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (actionId: string) =>
      apiPost(`/actions/${encodeURIComponent(actionId)}/approve`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["actions"] }),
  });
}

export function useDeclineAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { actionId: string; reason: string }) =>
      apiPost(
        `/actions/${encodeURIComponent(args.actionId)}/decline`,
        { reason: args.reason },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["actions"] }),
  });
}

// ---- MITRE coverage ---------------------------------------------------

export type MitreTactic = {
  tacticId: string;
  tacticName: string;
  techniques: { techniqueId: string; techniqueName: string; count: number }[];
  totalCount: number;
};

export type MitreCoverageResponse = {
  window: Window;
  tactics: MitreTactic[];
};

export function useMitreCoverage(window: Window = "24h") {
  return useQuery({
    queryKey: ["mitre", "coverage", window],
    queryFn: () =>
      apiGet<MitreCoverageResponse>(`/mitre/coverage?window=${window}`),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

// ---- chain investigation tools ---------------------------------------

export type ChainTag = { name: string; addedBy: string; addedAt: string };
export type ChainNote = {
  noteId: string;
  body: string;
  authorEmail: string;
  authorRole: string;
  createdAt: string;
};
export type ChainActivity = {
  id: string;
  kind: string;
  actorEmail: string | null;
  occurredAt: string;
  detail: string | null;
};

export function useChainTags(chainId: string | null) {
  return useQuery({
    queryKey: ["chain", "tags", chainId],
    enabled: !!chainId,
    queryFn: () =>
      apiGet<{ chainId: string; tags: ChainTag[] }>(
        `/chains/${chainId}/tags`,
      ),
  });
}

export function useChainNotes(chainId: string | null) {
  return useQuery({
    queryKey: ["chain", "notes", chainId],
    enabled: !!chainId,
    queryFn: () =>
      apiGet<{ chainId: string; notes: ChainNote[] }>(
        `/chains/${chainId}/notes`,
      ),
  });
}

export function useAddChainNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { chainId: string; body: string }) =>
      apiPost(`/chains/${args.chainId}/notes`, { body: args.body }),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["chain", "notes", vars.chainId] });
      qc.invalidateQueries({ queryKey: ["chain", "activity", vars.chainId] });
    },
  });
}

export function useChainActivity(chainId: string | null) {
  return useQuery({
    queryKey: ["chain", "activity", chainId],
    enabled: !!chainId,
    queryFn: () =>
      apiGet<{ chainId: string; events: ChainActivity[] }>(
        `/chains/${chainId}/activity`,
      ),
    refetchInterval: 20_000,
  });
}

// ---- analysis predictions (next stage / RL timeline) -----------------

export type ChainPredictions = {
  chainId: string;
  currentStage: number | null;
  predictions: {
    ckcStage: number;
    ckcStageName: string;
    probability: number;
  }[];
  generatedAt: string;
};

export function useChainPredictions(chainId: string | null) {
  return useQuery({
    queryKey: ["analysis", "predictions", chainId],
    enabled: !!chainId,
    queryFn: () =>
      apiGet<ChainPredictions>(`/analysis/chains/${chainId}/predictions`),
    refetchInterval: 30_000,
  });
}

// ---- playbooks --------------------------------------------------------

export type PlaybookStep = {
  stepId: string;
  kind: string;
  title: string;
  description: string | null;
  payload: Record<string, unknown> | null;
};

export type Playbook = {
  playbookId: string;
  name: string;
  description: string | null;
  isFallback: boolean;
  steps: PlaybookStep[];
};

export function usePlaybooks(opts: {
  stage?: number | null;
  technique?: string | null;
}) {
  const params = new URLSearchParams();
  if (opts.stage != null) params.set("stage", String(opts.stage));
  if (opts.technique) params.set("technique", opts.technique);
  const qs = params.toString();
  return useQuery({
    queryKey: ["playbooks", opts.stage ?? null, opts.technique ?? null],
    queryFn: () =>
      apiGet<{ playbooks: Playbook[] }>(`/playbooks${qs ? `?${qs}` : ""}`),
    staleTime: 5 * 60_000,
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
