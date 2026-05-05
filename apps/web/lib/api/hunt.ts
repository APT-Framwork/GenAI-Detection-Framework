// -----------------------------------------------------------------------------
// lib/api/hunt.ts — Hunt query + saved queries.
// Backend: apps/api/src/strix_api/api/routes/hunt.py
// -----------------------------------------------------------------------------

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";

export type HuntField = "host" | "user" | "technique" | "time" | "text";
export type HuntOp = "eq" | "contains";
export type HuntSort = "ts_desc" | "ts_asc" | "ckc_desc";

export interface HuntToken {
  field: HuntField;
  op: HuntOp;
  value: string;
}

export interface HuntParsed {
  tokens: HuntToken[];
  errors: string[];
}

export interface HuntResultItem {
  alertId: string;
  ts: string;
  chainId: string | null;
  hostId: string | null;
  hostName: string | null;
  ruleId: string | null;
  description: string | null;
  ckcStage: number | null;
  ckcStageName: string | null;
  mitreTechniques: string[];
}

export interface HuntQueryRequest {
  q: string;
  limit?: number;
  cursor?: string | null;
  sort?: HuntSort;
}

export interface HuntQueryResponse {
  parsed: HuntParsed;
  items: HuntResultItem[];
  total: number;
  nextCursor: string | null;
}

export interface SavedQuery {
  savedId: string;
  name: string;
  q: string;
  createdAt: string;
}

export interface SavedQueriesResponse {
  items: SavedQuery[];
}

export function useHuntQuery() {
  return useMutation({
    mutationFn: (body: HuntQueryRequest) =>
      apiFetch<HuntQueryResponse>("/hunt/query", {
        method: "POST",
        body,
      }),
  });
}

export function useSavedQueries(enabled = true) {
  return useQuery({
    queryKey: ["hunt", "saved"],
    enabled,
    queryFn: () => apiFetch<SavedQueriesResponse>("/hunt/saved"),
    refetchOnWindowFocus: false,
  });
}

export function useSaveQuery() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; q: string }) =>
      apiFetch<SavedQuery>("/hunt/saved", { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["hunt", "saved"] }),
  });
}

export function useDeleteSavedQuery() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (savedId: string) =>
      apiFetch<{ status: string }>(`/hunt/saved/${savedId}`, {
        method: "DELETE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["hunt", "saved"] }),
  });
}
