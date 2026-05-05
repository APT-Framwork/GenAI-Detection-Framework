// -----------------------------------------------------------------------------
// lib/api/hosts.ts — host detail hook.
// Backend: apps/api/src/strix_api/api/routes/hosts.py
// -----------------------------------------------------------------------------

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";

export type HostStatus = "healthy" | "warning" | "compromised";

export interface HostOverview {
  hostId: string;
  name: string;
  ip: string | null;
  agentId: string;
  isManager: boolean;
  status: HostStatus;
  firstSeenAt: string;
  lastSeenAt: string;
}

export interface HostSummary {
  openChains: number;
  totalAlerts24h: number;
  maxCkcStage24h: number;
  maxCkcStageName24h: string;
  lastDqnAction: string | null;
}

export interface HostAlertEntry {
  alertId: string;
  chainId: string | null;
  occurredAt: string;
  decoderName: string | null;
  location: string | null;
  ruleId: string | null;
  fullLog: string | null;
  ckcStage: number | null;
  ckcStageName: string | null;
  mitreTechniques: string[];
}

export interface HostChainEntry {
  chainId: string;
  openedAt: string;
  closedAt: string | null;
  status: string;
  triageStatus: string;
  maxCkcStage: number;
  maxCkcStageName: string;
  stepCount: number;
}

export interface HostDetailResponse {
  host: HostOverview;
  summary: HostSummary;
  audit: HostAlertEntry[];
  network: HostAlertEntry[];
  files: HostAlertEntry[];
  other: HostAlertEntry[];
  chains: HostChainEntry[];
}

export function useHostDetail(
  hostId: string | undefined,
  opts: { since?: string; limit?: number } = {},
) {
  const p = new URLSearchParams();
  if (opts.since) p.set("since", opts.since);
  if (opts.limit != null) p.set("limit", String(opts.limit));
  const qs = p.toString();

  return useQuery({
    queryKey: ["host", hostId, qs],
    enabled: !!hostId,
    queryFn: () =>
      apiFetch<HostDetailResponse>(
        `/hosts/${hostId}/detail${qs ? `?${qs}` : ""}`,
      ),
    refetchInterval: 30_000,
  });
}
