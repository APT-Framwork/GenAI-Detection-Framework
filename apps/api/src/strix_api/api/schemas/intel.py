"""Pydantic schemas for the /intel namespace (CTI surface).

Mirrors the tables added in migration 0012_cti_core. The actor/campaign
objects are wide enough to render an analyst-grade detail card without
a follow-up request; lists return the same shape so the landing page
can hydrate without N+1 fetches.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from strix_api.api.schemas.common import StrixBase


# ---------------------------------------------------------------- actors


class ThreatActorItem(StrixBase):
    actor_id: UUID
    name: str
    aliases: list[str] = Field(default_factory=list)
    mitre_group_id: str | None = None
    country: str | None = None
    motivation: str | None = None
    description: str | None = None
    # Roll-ups for the actor card. Computed by the service.
    campaign_count: int = 0
    attributed_chain_count: int = 0
    observed_in_env: bool = False


class ThreatActorListResponse(StrixBase):
    items: list[ThreatActorItem]
    total: int


# ---------------------------------------------------------------- campaigns


class CampaignItem(StrixBase):
    campaign_id: UUID
    name: str
    actor_id: UUID | None = None
    actor_name: str | None = None
    actor_mitre_group_id: str | None = None
    tactic_chain: list[str] = Field(default_factory=list)
    description: str | None = None
    first_observed: datetime | None = None
    last_observed: datetime | None = None
    attributed_chain_count: int = 0


class CampaignListResponse(StrixBase):
    items: list[CampaignItem]
    total: int


# ---------------------------------------------------------------- attributed chains


class AttributedChainItem(StrixBase):
    chain_id: UUID
    host_name: str | None = None
    host_id: UUID
    opened_at: datetime
    max_ckc_stage: int
    triage_status: str
    lifecycle_status: str
    campaign_id: UUID
    campaign_name: str
    actor_id: UUID | None = None
    actor_name: str | None = None
    confidence: int


class AttributedChainListResponse(StrixBase):
    items: list[AttributedChainItem]
    total: int


# ---------------------------------------------------------------- indicators (Tier-1 superset)


IndicatorType = Literal["ip", "domain", "url", "email", "hash", "user", "host", "process"]


class IntelIndicatorItem(StrixBase):
    indicator_id: UUID
    indicator: str
    indicator_type: IndicatorType
    confidence: int
    tlp: str
    source_label: str
    source_feed_id: UUID | None = None
    first_seen: datetime
    last_seen: datetime
    first_seen_internal: datetime | None = None
    last_seen_internal: datetime | None = None
    internal_hit_count: int
    valid_from: datetime
    valid_until: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    description: str | None = None


class IntelIndicatorListResponse(StrixBase):
    items: list[IntelIndicatorItem]
    total: int


# ---------------------------------------------------------------- observable lookup
#
# A single-value lookup that drives the analyst's pivot drawer. Given an
# IP / domain / hash / email value, return everything the platform
# knows about it: the indicator record (if any), the chains it appears
# in, and the actors / campaigns those chains are attributed to.


class ObservableChainHit(StrixBase):
    chain_id: UUID
    host_id: str | None = None
    host_name: str | None = None
    occurred_at: datetime
    ckc_stage: int | None = None
    ckc_stage_name: str | None = None
    triage_status: str | None = None


class ObservableActorHit(StrixBase):
    actor_id: UUID
    name: str
    mitre_group_id: str | None = None
    chain_count: int


class ObservableCampaignHit(StrixBase):
    campaign_id: UUID
    name: str
    actor_name: str | None = None
    chain_count: int


class ObservableLookupResponse(StrixBase):
    value: str
    indicator_type: str | None = None  # 'ip' | 'hash' | 'domain' | 'email' — None if unknown
    known: bool                         # exists in intel_indicators?
    indicator: IntelIndicatorItem | None = None
    chains: list[ObservableChainHit] = Field(default_factory=list)
    actors: list[ObservableActorHit] = Field(default_factory=list)
    campaigns: list[ObservableCampaignHit] = Field(default_factory=list)
    total_chain_hits: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None


# ---------------------------------------------------------------- pivot graph


class GraphNode(StrixBase):
    id: UUID
    type: str  # 'actor' | 'campaign' | 'indicator' | 'chain' | 'host'
    label: str
    sub_label: str | None = None
    score: int = 0          # for sizing (chains attributed, hit count, etc.)
    badge: str | None = None  # MITRE Group ID, TLP, etc.


class GraphEdge(StrixBase):
    from_id: UUID
    to_id: UUID
    rel: str
    confidence: int = 70


class GraphResponse(StrixBase):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


# ---------------------------------------------------------------- single-chain attribution


class ChainAttributionResponse(StrixBase):
    chain_id: UUID
    attributed: bool
    campaign_id: UUID | None = None
    campaign_name: str | None = None
    campaign_description: str | None = None
    campaign_tactic_chain: list[str] = Field(default_factory=list)
    actor_id: UUID | None = None
    actor_name: str | None = None
    actor_mitre_group_id: str | None = None
    actor_country: str | None = None
    actor_motivation: str | None = None
    actor_aliases: list[str] = Field(default_factory=list)
    # Jaccard% from the attribution edge — surfaces "how strongly we
    # think this chain matches the campaign's known playbook". NULL if
    # no relationship edge was recorded (legacy attribution).
    confidence: int | None = None
    # Other candidate campaigns the chain partially matched, surfaced
    # as runner-up hypotheses (sorted by confidence desc, max 3).
    candidates: list["ChainAttributionCandidate"] = Field(default_factory=list)


class ChainAttributionCandidate(StrixBase):
    campaign_id: UUID
    campaign_name: str
    actor_name: str | None = None
    confidence: int


ChainAttributionResponse.model_rebuild()


# ---------------------------------------------------------------- feeds


class IntelFeedItem(StrixBase):
    feed_id: UUID
    name: str
    kind: str
    url: str | None = None
    enabled: bool
    pull_interval_s: int
    last_pulled_at: datetime | None = None
    last_status: str | None = None
    last_indicator_count: int
    default_confidence: int
    default_tlp: str
    indicator_count_total: int = 0


class IntelFeedListResponse(StrixBase):
    items: list[IntelFeedItem]
    total: int


# ---------------------------------------------------------------- overview (landing page)


class IntelOverviewCounts(StrixBase):
    actors: int
    campaigns: int
    indicators_total: int
    indicators_observed_internal: int
    attributed_chains: int
    unattributed_open_chains: int


class IntelOverviewResponse(StrixBase):
    counts: IntelOverviewCounts
    top_actors: list[ThreatActorItem]
    top_campaigns: list[CampaignItem]
    recent_attributions: list[AttributedChainItem]
    top_observed_indicators: list[IntelIndicatorItem]
    feeds: list[IntelFeedItem] = Field(default_factory=list)
