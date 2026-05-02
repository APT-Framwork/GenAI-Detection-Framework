// -----------------------------------------------------------------------------
// useLatestSimulationRun — initial fetch of `/simulation/runs/latest` so the
// topology panel renders something before the first WebSocket `topology` frame
// arrives. The ws then takes over and refreshes when run_id changes.
// -----------------------------------------------------------------------------

"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { TopologyPayload } from "./ws";

export interface LatestRunResponse {
  run_id: string;
  path: string;
  topology: TopologyPayload;
}

export function useLatestSimulationRun(opts: { enabled?: boolean } = {}) {
  return useQuery<LatestRunResponse>({
    queryKey: ["simulation", "runs", "latest"],
    queryFn: () => apiFetch<LatestRunResponse>("/simulation/runs/latest"),
    enabled: opts.enabled ?? true,
    retry: false,
    staleTime: 30_000,
  });
}
