// -----------------------------------------------------------------------------
// useTopology — host-graph view backed by /topology.
// -----------------------------------------------------------------------------

"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { WindowLiteral } from "./hooks";

export interface TopologyNode {
  id: string;
  label: string;
  type: "server" | "endpoint" | "firewall" | "database" | "manager";
  status: "healthy" | "warning" | "compromised";
  ip: string | null;
  openChains: number;
  maxCkcStage: number;
}

export interface TopologyEdge {
  id: string;
  source: string;
  target: string;
  chainCount: number;
  type: "normal" | "malicious";
}

export interface TopologyResponse {
  window: WindowLiteral;
  generatedAt: string;
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

export function useTopology(window: WindowLiteral = "24h") {
  return useQuery({
    queryKey: ["topology", window],
    queryFn: () =>
      apiFetch<TopologyResponse>(`/topology?window=${window}`),
    staleTime: 30_000,
  });
}
