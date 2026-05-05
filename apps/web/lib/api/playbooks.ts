// -----------------------------------------------------------------------------
// lib/api/playbooks.ts — playbook lookup + manual-action POST.
// Backend: apps/api/src/strix_api/api/routes/playbooks.py
//          apps/api/src/strix_api/api/routes/actions.py (POST /actions/manual)
// -----------------------------------------------------------------------------

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";
import type { ActionItem } from "@/lib/api/actions";

export type PlaybookSeverity = "low" | "medium" | "high" | "critical";
export type PlaybookStepKind =
  | "manual"
  | "dqn_override"
  | "isolate_host"
  | "block_ip";

export interface PlaybookStepPayload {
  action: string;
  chainIdRequired: boolean;
}

export interface PlaybookStep {
  stepId: string;
  title: string;
  rationale: string;
  kind: PlaybookStepKind;
  payload?: PlaybookStepPayload | null;
}

export interface Playbook {
  playbookId: string;
  title: string;
  description: string;
  severity: PlaybookSeverity;
  steps: PlaybookStep[];
}

export interface PlaybookMatchResponse {
  matched: Playbook[];
  fallback: Playbook | null;
}

export function usePlaybooks(opts: {
  stage?: number | null;
  technique?: string | null;
  enabled?: boolean;
}) {
  const p = new URLSearchParams();
  if (opts.stage != null) p.set("stage", String(opts.stage));
  if (opts.technique) p.set("technique", opts.technique);
  const qs = p.toString();
  return useQuery({
    queryKey: ["playbooks", qs],
    enabled: opts.enabled ?? true,
    queryFn: () =>
      apiFetch<PlaybookMatchResponse>(`/playbooks${qs ? `?${qs}` : ""}`),
    staleTime: 5 * 60_000, // catalog is bundled — stale after 5 min is fine
  });
}

export interface ManualActionRequest {
  chainId: string;
  action: number;        // 0..4
  actionName: string;    // MONITOR | ESCALATE | ISOLATE_HOST | BLOCK_USER_IP …
  reason: string;
}

export function useManualAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ManualActionRequest) =>
      apiFetch<ActionItem>("/actions/manual", { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["actions"] }),
  });
}
