// -----------------------------------------------------------------------------
// lib/api/mitre.ts — MITRE ATT&CK coverage matrix hook.
// Backend: apps/api/src/strix_api/api/routes/mitre.py
// -----------------------------------------------------------------------------

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";

export interface TechniqueCoverage {
  techniqueId: string;
  techniqueName: string;
  count: number;
  lastSeen: string | null;
  uniqueHosts: number;
  /** Concise definition shown on hover. Empty string when unset (catalog
   *  entry doesn't carry a description). */
  description: string;
}

export interface TacticCoverage {
  tacticId: string;
  tacticName: string;
  ckc: number;
  techniques: TechniqueCoverage[];
  columnTotal: number;
  description: string;
}

export interface MitreCoverageResponse {
  windowStart: string;
  windowEnd: string;
  tactics: TacticCoverage[];
  otherCount: number;
  otherUnmatchedIds: string[];
}

export function useMitreCoverage(opts: { since?: string; until?: string } = {}) {
  const p = new URLSearchParams();
  if (opts.since) p.set("since", opts.since);
  if (opts.until) p.set("until", opts.until);
  const qs = p.toString();
  return useQuery({
    queryKey: ["mitre", "coverage", qs],
    queryFn: () =>
      apiFetch<MitreCoverageResponse>(
        `/mitre/coverage${qs ? `?${qs}` : ""}`,
      ),
    refetchInterval: 60_000,
  });
}
