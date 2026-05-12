// -----------------------------------------------------------------------------
// lib/api/intel.ts — frontend hooks for the /intel namespace (CTI surface).
// Backend: apps/api/src/strix_api/api/routes/intel.py
//
// Pydantic schemas inherit from StrixBase → alias_generator=to_camel, so the
// JSON wire format is camelCase even though the Python models are snake_case.
// -----------------------------------------------------------------------------

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";

export interface ThreatActor {
  actorId: string;
  name: string;
  aliases: string[];
  mitreGroupId: string | null;
  country: string | null;
  motivation: string | null;
  description: string | null;
  campaignCount: number;
  attributedChainCount: number;
  observedInEnv: boolean;
}

export interface Campaign {
  campaignId: string;
  name: string;
  actorId: string | null;
  actorName: string | null;
  actorMitreGroupId: string | null;
  tacticChain: string[];
  description: string | null;
  firstObserved: string | null;
  lastObserved: string | null;
  attributedChainCount: number;
}

export interface AttributedChain {
  chainId: string;
  hostId: string;
  hostName: string | null;
  openedAt: string;
  maxCkcStage: number;
  triageStatus: string;
  lifecycleStatus: string;
  campaignId: string;
  campaignName: string;
  actorId: string | null;
  actorName: string | null;
  confidence: number;
}

export interface IntelIndicator {
  indicatorId: string;
  indicator: string;
  indicatorType: string;
  confidence: number;
  tlp: string;
  sourceLabel: string;
  sourceFeedId: string | null;
  firstSeen: string;
  lastSeen: string;
  firstSeenInternal: string | null;
  lastSeenInternal: string | null;
  internalHitCount: number;
  validFrom: string;
  validUntil: string | null;
  tags: string[];
  description: string | null;
}

export interface IntelOverviewCounts {
  actors: number;
  campaigns: number;
  indicatorsTotal: number;
  indicatorsObservedInternal: number;
  attributedChains: number;
  unattributedOpenChains: number;
}

export interface IntelFeed {
  feedId: string;
  name: string;
  kind: string;
  url: string | null;
  enabled: boolean;
  pullIntervalS: number;
  lastPulledAt: string | null;
  lastStatus: string | null;
  lastIndicatorCount: number;
  defaultConfidence: number;
  defaultTlp: string;
  indicatorCountTotal: number;
}

export interface IntelOverview {
  counts: IntelOverviewCounts;
  topActors: ThreatActor[];
  topCampaigns: Campaign[];
  recentAttributions: AttributedChain[];
  topObservedIndicators: IntelIndicator[];
  feeds: IntelFeed[];
}

// -------------------------------------------------- hooks

export function useIntelOverview() {
  return useQuery<IntelOverview>({
    queryKey: ["intel", "overview"],
    queryFn: () => apiFetch<IntelOverview>("/intel/overview"),
    refetchInterval: 15_000,
  });
}

export function useThreatActors(limit = 50) {
  return useQuery<{ items: ThreatActor[]; total: number }>({
    queryKey: ["intel", "actors", limit],
    queryFn: () =>
      apiFetch<{ items: ThreatActor[]; total: number }>(`/intel/actors?limit=${limit}`),
    refetchInterval: 30_000,
  });
}

export function useThreatActor(actorId: string | null) {
  return useQuery<ThreatActor>({
    queryKey: ["intel", "actors", "one", actorId],
    queryFn: () => apiFetch<ThreatActor>(`/intel/actors/${actorId}`),
    enabled: !!actorId,
  });
}

export function useCampaigns(limit = 50) {
  return useQuery<{ items: Campaign[]; total: number }>({
    queryKey: ["intel", "campaigns", limit],
    queryFn: () =>
      apiFetch<{ items: Campaign[]; total: number }>(`/intel/campaigns?limit=${limit}`),
    refetchInterval: 30_000,
  });
}

export function useCampaign(campaignId: string | null) {
  return useQuery<Campaign>({
    queryKey: ["intel", "campaigns", "one", campaignId],
    queryFn: () => apiFetch<Campaign>(`/intel/campaigns/${campaignId}`),
    enabled: !!campaignId,
  });
}

export function useAttributedChains(opts: {
  actorId?: string;
  campaignId?: string;
  limit?: number;
} = {}) {
  const p = new URLSearchParams();
  if (opts.actorId) p.set("actor_id", opts.actorId);
  if (opts.campaignId) p.set("campaign_id", opts.campaignId);
  if (opts.limit) p.set("limit", String(opts.limit));
  const qs = p.toString() ? `?${p.toString()}` : "";
  return useQuery<{ items: AttributedChain[]; total: number }>({
    queryKey: ["intel", "attributed-chains", opts],
    queryFn: () =>
      apiFetch<{ items: AttributedChain[]; total: number }>(
        `/intel/attributed-chains${qs}`,
      ),
    refetchInterval: 15_000,
  });
}

export interface ChainAttributionCandidate {
  campaignId: string;
  campaignName: string;
  actorName: string | null;
  confidence: number;
}

export interface ChainAttribution {
  chainId: string;
  attributed: boolean;
  campaignId: string | null;
  campaignName: string | null;
  campaignDescription: string | null;
  campaignTacticChain: string[];
  actorId: string | null;
  actorName: string | null;
  actorMitreGroupId: string | null;
  actorCountry: string | null;
  actorMotivation: string | null;
  actorAliases: string[];
  confidence: number | null;
  candidates: ChainAttributionCandidate[];
}

export function useChainAttribution(chainId: string | null) {
  return useQuery<ChainAttribution>({
    queryKey: ["intel", "chains", chainId, "attribution"],
    queryFn: () =>
      apiFetch<ChainAttribution>(`/intel/chains/${chainId}/attribution`),
    enabled: !!chainId,
    refetchInterval: 15_000,
  });
}

export interface GraphNode {
  id: string;
  type: "actor" | "campaign" | "chain" | "indicator" | "host";
  label: string;
  subLabel: string | null;
  score: number;
  badge: string | null;
}

export interface GraphEdge {
  fromId: string;
  toId: string;
  rel: string;
  confidence: number;
}

export interface IntelGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export function useIntelGraph(chainLimit = 30) {
  return useQuery<IntelGraph>({
    queryKey: ["intel", "graph", chainLimit],
    queryFn: () => apiFetch<IntelGraph>(`/intel/graph?chain_limit=${chainLimit}`),
    refetchInterval: 30_000,
  });
}

export function useIntelFeeds() {
  return useQuery<{ items: IntelFeed[]; total: number }>({
    queryKey: ["intel", "feeds"],
    queryFn: () =>
      apiFetch<{ items: IntelFeed[]; total: number }>("/intel/feeds"),
    refetchInterval: 15_000,
  });
}

export function useIntelIndicators(opts: {
  sourceLabel?: string;
  indicatorType?: string;
  limit?: number;
} = {}) {
  const p = new URLSearchParams();
  if (opts.sourceLabel) p.set("source_label", opts.sourceLabel);
  if (opts.indicatorType) p.set("indicator_type", opts.indicatorType);
  if (opts.limit) p.set("limit", String(opts.limit));
  const qs = p.toString() ? `?${p.toString()}` : "";
  return useQuery<{ items: IntelIndicator[]; total: number }>({
    queryKey: ["intel", "indicators", opts],
    queryFn: () =>
      apiFetch<{ items: IntelIndicator[]; total: number }>(
        `/intel/indicators${qs}`,
      ),
    refetchInterval: 30_000,
  });
}

// -------------------------------------------------- observable lookup

export interface ObservableChainHit {
  chainId: string;
  hostId: string | null;
  hostName: string | null;
  occurredAt: string;
  ckcStage: number | null;
  ckcStageName: string | null;
  triageStatus: string | null;
}

export interface ObservableActorHit {
  actorId: string;
  name: string;
  mitreGroupId: string | null;
  chainCount: number;
}

export interface ObservableCampaignHit {
  campaignId: string;
  name: string;
  actorName: string | null;
  chainCount: number;
}

export interface ObservableLookup {
  value: string;
  indicatorType: string | null;
  known: boolean;
  indicator: IntelIndicator | null;
  chains: ObservableChainHit[];
  actors: ObservableActorHit[];
  campaigns: ObservableCampaignHit[];
  totalChainHits: number;
  firstSeen: string | null;
  lastSeen: string | null;
}

export function useObservableLookup(value: string | null) {
  return useQuery<ObservableLookup>({
    queryKey: ["intel", "observables", value],
    queryFn: () =>
      apiFetch<ObservableLookup>(
        `/intel/observables/lookup?value=${encodeURIComponent(value!)}`,
      ),
    enabled: !!value,
    staleTime: 10_000,
  });
}
