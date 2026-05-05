// -----------------------------------------------------------------------------
// lib/api/actions.ts — Response Action Log hooks.
// Backend: apps/api/src/strix_api/api/routes/actions.py
// -----------------------------------------------------------------------------

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";

export type ActionStatus =
  | "proposed"
  | "approved"
  | "auto_applied"
  | "declined"
  | "rolled_back";

export interface ActorRef {
  userId: string;
  name: string;
}

export interface ActionRollback {
  rollbackId: string;
  rolledBackAt: string;
  rolledBackBy: ActorRef | null;
  reason: string;
}

export interface ActionItem {
  actionId: string;
  chainId: string;
  hostId: string;
  hostName: string | null;
  decidedAt: string;
  appliedAt: string | null;
  action: number;
  actionName: string;
  qValues: number[];
  ckcStageAtDecision: number;
  ckcStageName: string;
  requiresApproval: boolean;
  status: ActionStatus;
  appliedBy: ActorRef | null;
  rejectedAt: string | null;
  rejectedBy: ActorRef | null;
  rollback: ActionRollback | null;
}

export interface ActionCounts {
  proposed: number;
  approved: number;
  auto_applied: number;
  declined: number;
  rolled_back: number;
}

export interface ActionsListResponse {
  items: ActionItem[];
  nextCursor: string | null;
  counts: ActionCounts;
}

export interface UseActionsOpts {
  status?: ActionStatus[];
  hostId?: string;
  chainId?: string;
  since?: string;
  limit?: number;
  cursor?: string | null;
}

function buildQs(opts: UseActionsOpts): string {
  const p = new URLSearchParams();
  for (const s of opts.status ?? []) p.append("status", s);
  if (opts.hostId) p.set("host", opts.hostId);
  if (opts.chainId) p.set("chain", opts.chainId);
  if (opts.since) p.set("since", opts.since);
  if (opts.limit != null) p.set("limit", String(opts.limit));
  if (opts.cursor) p.set("cursor", opts.cursor);
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function useActions(opts: UseActionsOpts = {}) {
  const qs = buildQs(opts);
  return useQuery({
    queryKey: ["actions", qs],
    queryFn: () => apiFetch<ActionsListResponse>(`/actions${qs}`),
    refetchInterval: 15_000,
  });
}

export function useApproveAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ actionId, note }: { actionId: string; note?: string }) =>
      apiFetch<ActionItem>(`/actions/${actionId}/approve`, {
        method: "POST",
        body: { note },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["actions"] }),
  });
}

export function useDeclineAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ actionId, reason }: { actionId: string; reason: string }) =>
      apiFetch<ActionItem>(`/actions/${actionId}/decline`, {
        method: "POST",
        body: { reason },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["actions"] }),
  });
}

export function useRollbackAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ actionId, reason }: { actionId: string; reason: string }) =>
      apiFetch<ActionItem>(`/actions/${actionId}/rollback`, {
        method: "POST",
        body: { reason },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["actions"] }),
  });
}
