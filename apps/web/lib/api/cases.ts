// -----------------------------------------------------------------------------
// lib/api/cases.ts — frontend hooks for the Cases / Chain Queue.
// Backend: apps/api/src/strix_api/api/routes/cases.py
// -----------------------------------------------------------------------------

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";

export type TriageStatus = "new" | "investigating" | "contained" | "closed";

export interface CaseAssignee {
  userId: string;
  name: string;
}

export interface CaseItem {
  chainId: string;
  hostId: string;
  hostName: string | null;
  hostIp: string | null;
  openedAt: string;
  lastSeenAt: string;
  status: TriageStatus;
  lifecycleStatus: string;       // "open" | "closed"
  maxCkcStage: number;
  maxCkcStageName: string;
  maxVaeProb: number;
  stepCount: number;
  assignee: CaseAssignee | null;
  mitreTechniques: string[];
  lastDqnAction: string | null;
}

export interface CaseCounts {
  new: number;
  investigating: number;
  contained: number;
  closed: number;
}

export interface CasesListResponse {
  items: CaseItem[];
  nextCursor: string | null;
  counts: CaseCounts;
}

export interface UseCasesOpts {
  status?: TriageStatus[];
  hostId?: string;
  minCkc?: number;
  since?: string;
  limit?: number;
  cursor?: string | null;
}

function buildQs(opts: UseCasesOpts): string {
  const p = new URLSearchParams();
  for (const s of opts.status ?? []) p.append("status", s);
  if (opts.hostId) p.set("host", opts.hostId);
  if (opts.minCkc != null) p.set("minCkc", String(opts.minCkc));
  if (opts.since) p.set("since", opts.since);
  if (opts.limit != null) p.set("limit", String(opts.limit));
  if (opts.cursor) p.set("cursor", opts.cursor);
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function useCases(opts: UseCasesOpts = {}) {
  const qs = buildQs(opts);
  return useQuery({
    queryKey: ["cases", qs],
    queryFn: () => apiFetch<CasesListResponse>(`/cases${qs}`),
    refetchInterval: 15_000,
  });
}

export interface CaseStatusUpdateBody {
  status: TriageStatus;
  assigneeUserId?: string | null;
  note?: string;
}

export function useUpdateCaseStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ chainId, body }: { chainId: string; body: CaseStatusUpdateBody }) =>
      apiFetch<CaseItem>(`/cases/${chainId}/status`, {
        method: "PATCH",
        body,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cases"] });
    },
  });
}
