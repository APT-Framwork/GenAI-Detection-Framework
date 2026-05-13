// -----------------------------------------------------------------------------
// lib/api/chains.ts — investigation surface hooks for the per-chain page.
// Backend: apps/api/src/strix_api/api/routes/chains.py
// -----------------------------------------------------------------------------

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";

export type Tlp = "clear" | "green" | "amber" | "amber+strict" | "red";

export interface TagItem {
  tagId: string;
  name: string;
  colour: string;
  description: string | null;
}

export interface ChainNote {
  noteId: string;
  chainId: string;
  authorUserId: string | null;
  authorEmail: string | null;
  bodyMd: string;
  createdAt: string;
  /** Same as `createdAt` for never-edited notes; later for edited ones. */
  updatedAt: string | null;
}

export interface ActivityEvent {
  auditId: string;
  chainId: string;
  at: string;
  userId: string | null;
  userEmail: string | null;
  kind: string;          // triage | tag.added | tag.removed | tlp | note.added | attribution
  payload: string | null;
  fromStatus: string | null;
  toStatus: string;
  note: string | null;
}

// ---------------------------------------------------------------- TLP

export function useChainTlp(chainId: string | null) {
  return useQuery<{ chainId: string; tlp: Tlp }>({
    queryKey: ["chain", chainId, "tlp"],
    queryFn: () => apiFetch(`/chains/${chainId}/tlp`),
    enabled: !!chainId,
  });
}

export function useSetChainTlp(chainId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tlp: Tlp) =>
      apiFetch<{ chainId: string; tlp: Tlp }>(`/chains/${chainId}/tlp`, {
        method: "PATCH",
        body: { tlp },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chain", chainId, "tlp"] });
      qc.invalidateQueries({ queryKey: ["chain", chainId, "activity"] });
    },
  });
}

// ---------------------------------------------------------------- tags

export function useChainTags(chainId: string | null) {
  return useQuery<{ chainId: string; items: TagItem[] }>({
    queryKey: ["chain", chainId, "tags"],
    queryFn: () => apiFetch(`/chains/${chainId}/tags`),
    enabled: !!chainId,
  });
}

export function useAddChainTag(chainId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      apiFetch<{ chainId: string; items: TagItem[] }>(`/chains/${chainId}/tags`, {
        method: "POST",
        body: { name },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chain", chainId, "tags"] });
      qc.invalidateQueries({ queryKey: ["chain", chainId, "activity"] });
    },
  });
}

export function useRemoveChainTag(chainId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      apiFetch<{ chainId: string; items: TagItem[] }>(
        `/chains/${chainId}/tags/${encodeURIComponent(name)}`,
        { method: "DELETE" },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chain", chainId, "tags"] });
      qc.invalidateQueries({ queryKey: ["chain", chainId, "activity"] });
    },
  });
}

// ---------------------------------------------------------------- notes

export function useChainNotes(chainId: string | null) {
  return useQuery<{ chainId: string; items: ChainNote[] }>({
    queryKey: ["chain", chainId, "notes"],
    queryFn: () => apiFetch(`/chains/${chainId}/notes`),
    enabled: !!chainId,
  });
}

export function useAddChainNote(chainId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (bodyMd: string) =>
      apiFetch<{ chainId: string; items: ChainNote[] }>(`/chains/${chainId}/notes`, {
        method: "POST",
        body: { bodyMd },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chain", chainId, "notes"] });
      qc.invalidateQueries({ queryKey: ["chain", chainId, "activity"] });
    },
  });
}

export function useUpdateChainNote(chainId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ noteId, bodyMd }: { noteId: string; bodyMd: string }) =>
      apiFetch<{ chainId: string; items: ChainNote[] }>(
        `/chains/${chainId}/notes/${noteId}`,
        { method: "PATCH", body: { bodyMd } },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chain", chainId, "notes"] });
      qc.invalidateQueries({ queryKey: ["chain", chainId, "activity"] });
    },
  });
}

export function useDeleteChainNote(chainId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (noteId: string) =>
      apiFetch<{ chainId: string; items: ChainNote[] }>(
        `/chains/${chainId}/notes/${noteId}`,
        { method: "DELETE" },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chain", chainId, "notes"] });
      qc.invalidateQueries({ queryKey: ["chain", chainId, "activity"] });
    },
  });
}

// ---------------------------------------------------------------- activity

export function useChainActivity(chainId: string | null, limit = 100) {
  return useQuery<{ chainId: string; items: ActivityEvent[] }>({
    queryKey: ["chain", chainId, "activity", limit],
    queryFn: () => apiFetch(`/chains/${chainId}/activity?limit=${limit}`),
    enabled: !!chainId,
    refetchInterval: 15_000,
  });
}
