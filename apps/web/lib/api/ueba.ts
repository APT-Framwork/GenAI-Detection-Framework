// -----------------------------------------------------------------------------
// lib/api/ueba.ts — top-N risky users.
// Backend: apps/api/src/strix_api/api/routes/ueba.py
// -----------------------------------------------------------------------------

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";

export interface UserChainRef {
  chainId: string;
  maxCkcStage: number;
}

export interface UserRiskItem {
  user: string;
  riskScore: number;        // 0..1
  alertCount: number;
  hostsTouched: number;
  chainCount: number;
  maxCkcStage: number;
  lastSeen: string | null;
  topChains: UserChainRef[];
}

export interface UserRiskResponse {
  items: UserRiskItem[];
  windowStart: string;
  windowEnd: string;
  source: string;           // "alerts.full_log" today; flips when GNN supplies
}

export function useUserRisk(opts: { limit?: number; since?: string } = {}) {
  const p = new URLSearchParams();
  if (opts.limit != null) p.set("limit", String(opts.limit));
  if (opts.since) p.set("since", opts.since);
  const qs = p.toString();
  return useQuery({
    queryKey: ["ueba", "users", qs],
    queryFn: () =>
      apiFetch<UserRiskResponse>(`/ueba/users${qs ? `?${qs}` : ""}`),
    refetchInterval: 60_000,
  });
}
