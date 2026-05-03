// -----------------------------------------------------------------------------
// Threat Intel hooks (Phase 6).
//
// IOC search: standard query hook. VT on-demand scan + file scan return a
// `jobId` immediately; the SSE companion `useJobResult(jobId)` listens on
// `/streams/jobs/{jobId}` for the completion event.
// -----------------------------------------------------------------------------

"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { useSseStream } from "./sse";

export interface IocItem {
  indicator: string;
  type: "email" | "ip" | "domain" | "hash";
  reputation: "malicious" | "suspicious" | "clean" | "unknown";
  source: "xon" | "virustotal" | "cache";
  lastChecked: string;
  breachCount?: number | null;
  stale?: boolean;
  payload?: Record<string, unknown> | null;
}

export interface IocSearchResponse {
  items: IocItem[];
  total: number;
  page: number;
  limit: number;
}

export interface CompromisedAsset {
  hostId: string;
  agentName: string | null;
  ipAddress: string | null;
  lastSeenAt: string | null;
  lastDetectionAt: string | null;
  detectionCount: number;
  maxVaeProb: number | null;
  maxGnnRisk: number | null;
  lastActionInt: number | null;
}

export interface CompromisedAssetsResponse { items: CompromisedAsset[]; }

export interface JobAcceptedResponse { jobId: string; status: "queued"; }
export interface FileScanResponse {
  scanId: string;
  sha256: string;
  sizeBytes: number;
  status: "queued" | "scanning" | "complete" | "error";
  filename: string;
}

// -- search ------------------------------------------------------------

export function useIocSearch(opts: {
  q?: string;
  type?: "email" | "ip" | "domain" | "hash";
  page?: number;
  limit?: number;
  enabled?: boolean;
} = {}) {
  const params = new URLSearchParams();
  if (opts.q) params.set("q", opts.q);
  if (opts.type) params.set("type", opts.type);
  if (opts.page) params.set("page", String(opts.page));
  if (opts.limit) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return useQuery({
    enabled: opts.enabled ?? true,
    queryKey: ["threat-intel", "iocs", qs],
    queryFn: () =>
      apiFetch<IocSearchResponse>(`/threat-intel/iocs${qs ? `?${qs}` : ""}`),
    refetchInterval: 60_000,
  });
}

// -- compromised assets -----------------------------------------------

export function useCompromisedAssets(limit = 100) {
  return useQuery({
    queryKey: ["threat-intel", "compromised-assets", limit],
    queryFn: () =>
      apiFetch<CompromisedAssetsResponse>(`/threat-intel/compromised-assets?limit=${limit}`),
    refetchInterval: 60_000,
  });
}

// -- VT on-demand scan ------------------------------------------------

export function useVirusTotalScan() {
  return useMutation({
    mutationFn: (req: { indicator: string; type?: string }) =>
      apiFetch<JobAcceptedResponse>(`/threat-intel/virustotal/scan`, {
        method: "POST", body: req,
      }),
  });
}

// -- file upload scan -------------------------------------------------

export function useFileScan() {
  return useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return apiFetch<FileScanResponse>(`/threat-intel/files/scan`, {
        method: "POST", body: fd,
        headers: {}, // let the browser set the multipart boundary
      });
    },
  });
}

// -- SSE result for an enqueued job -----------------------------------

export interface JobResultEvent {
  jobId: string;
  status: "queued" | "scanning" | "complete" | "error";
  reputation?: string;
  counts?: Record<string, number>;
  engines?: Record<string, string>;
  error?: string;
  scanId?: string;
}

export function useJobResult(jobId: string | null) {
  return useSseStream<JobResultEvent>(
    jobId ? `/streams/jobs/${jobId}` : "/streams/jobs/_",
    { enabled: !!jobId, eventName: "job.complete", maxEvents: 5 },
  );
}
