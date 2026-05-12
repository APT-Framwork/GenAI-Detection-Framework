"""Aggregator for the /intel namespace.

One service for the CTI landing surface — it joins actors, campaigns,
attributed chains, and observed indicators into the shapes the UI
needs. Designed to satisfy the landing page in a single round-trip
(overview) and back individual list pages with simple paged queries.

Performance notes
-----------------
The catalogues are small (≤ low thousands of actors/campaigns; ≤ tens
of thousands of indicators at lab scale) so we use straightforward
joins and let Postgres' indexes from mig 0012 (ix_attack_chains_
campaign_id, ix_intel_indicators_internal_hit, etc.) do the work.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.schemas.intel import (
    AttributedChainItem,
    AttributedChainListResponse,
    CampaignItem,
    CampaignListResponse,
    ChainAttributionCandidate,
    ChainAttributionResponse,
    GraphEdge,
    GraphNode,
    GraphResponse,
    IntelFeedItem,
    IntelFeedListResponse,
    IntelIndicatorItem,
    IntelIndicatorListResponse,
    IntelOverviewCounts,
    IntelOverviewResponse,
    ObservableActorHit,
    ObservableCampaignHit,
    ObservableChainHit,
    ObservableLookupResponse,
    ThreatActorItem,
    ThreatActorListResponse,
)
from strix_api.repositories.models import (
    AttackChain,
    Campaign,
    Host,
    ThreatActor,
)
from sqlalchemy import text


class IntelService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ---------------------------------------------------------------- actors

    async def list_actors(self, *, limit: int = 50) -> ThreatActorListResponse:
        # Roll up campaign_count, attributed_chain_count, observed_in_env per actor.
        # observed_in_env = "this actor is linked to any chain we've attributed"
        rows = (
            await self._s.execute(
                text(
                    """
                    SELECT
                        ta.actor_id, ta.name, ta.aliases, ta.mitre_group_id,
                        ta.country, ta.motivation, ta.description,
                        COALESCE(camp.campaign_count, 0) AS campaign_count,
                        COALESCE(att.attributed_chain_count, 0) AS attributed_chain_count
                    FROM threat_actors ta
                    LEFT JOIN (
                        SELECT actor_id, COUNT(*) AS campaign_count
                        FROM campaigns
                        WHERE actor_id IS NOT NULL
                        GROUP BY actor_id
                    ) camp ON camp.actor_id = ta.actor_id
                    LEFT JOIN (
                        SELECT c.actor_id, COUNT(*) AS attributed_chain_count
                        FROM attack_chains ac
                        JOIN campaigns c ON c.campaign_id = ac.campaign_id
                        WHERE c.actor_id IS NOT NULL
                        GROUP BY c.actor_id
                    ) att ON att.actor_id = ta.actor_id
                    ORDER BY attributed_chain_count DESC, campaign_count DESC, ta.name
                    LIMIT :lim
                    """
                ),
                {"lim": limit},
            )
        ).mappings().all()

        items = [
            ThreatActorItem(
                actor_id=r["actor_id"],
                name=r["name"],
                aliases=list(r["aliases"] or []),
                mitre_group_id=r["mitre_group_id"],
                country=r["country"],
                motivation=r["motivation"],
                description=r["description"],
                campaign_count=int(r["campaign_count"]),
                attributed_chain_count=int(r["attributed_chain_count"]),
                observed_in_env=int(r["attributed_chain_count"]) > 0,
            )
            for r in rows
        ]
        total = (
            await self._s.execute(select(func.count()).select_from(ThreatActor))
        ).scalar_one()
        return ThreatActorListResponse(items=items, total=int(total))

    async def get_actor(self, actor_id: UUID) -> ThreatActorItem | None:
        result = await self.list_actors(limit=1000)  # small catalogue, fine
        for it in result.items:
            if it.actor_id == actor_id:
                return it
        return None

    # ---------------------------------------------------------------- campaigns

    async def list_campaigns(self, *, limit: int = 50) -> CampaignListResponse:
        rows = (
            await self._s.execute(
                text(
                    """
                    SELECT
                        c.campaign_id, c.name, c.actor_id, c.tactic_chain,
                        c.description, c.first_observed, c.last_observed,
                        ta.name AS actor_name,
                        ta.mitre_group_id AS actor_mitre_group_id,
                        COALESCE(att.attributed_chain_count, 0) AS attributed_chain_count
                    FROM campaigns c
                    LEFT JOIN threat_actors ta ON ta.actor_id = c.actor_id
                    LEFT JOIN (
                        SELECT campaign_id, COUNT(*) AS attributed_chain_count
                        FROM attack_chains
                        WHERE campaign_id IS NOT NULL
                        GROUP BY campaign_id
                    ) att ON att.campaign_id = c.campaign_id
                    ORDER BY attributed_chain_count DESC, c.name
                    LIMIT :lim
                    """
                ),
                {"lim": limit},
            )
        ).mappings().all()

        items = [
            CampaignItem(
                campaign_id=r["campaign_id"],
                name=r["name"],
                actor_id=r["actor_id"],
                actor_name=r["actor_name"],
                actor_mitre_group_id=r["actor_mitre_group_id"],
                tactic_chain=list(r["tactic_chain"] or []),
                description=r["description"],
                first_observed=r["first_observed"],
                last_observed=r["last_observed"],
                attributed_chain_count=int(r["attributed_chain_count"]),
            )
            for r in rows
        ]
        total = (
            await self._s.execute(select(func.count()).select_from(Campaign))
        ).scalar_one()
        return CampaignListResponse(items=items, total=int(total))

    async def get_campaign(self, campaign_id: UUID) -> CampaignItem | None:
        result = await self.list_campaigns(limit=1000)
        for it in result.items:
            if it.campaign_id == campaign_id:
                return it
        return None

    # ---------------------------------------------------------------- attributed chains

    async def list_attributed_chains(
        self,
        *,
        actor_id: UUID | None = None,
        campaign_id: UUID | None = None,
        limit: int = 50,
    ) -> AttributedChainListResponse:
        params: dict[str, Any] = {"lim": limit}
        where_clauses = ["ac.campaign_id IS NOT NULL"]
        if campaign_id is not None:
            where_clauses.append("ac.campaign_id = :campaign_id")
            params["campaign_id"] = campaign_id
        if actor_id is not None:
            where_clauses.append("c.actor_id = :actor_id")
            params["actor_id"] = actor_id

        rows = (
            await self._s.execute(
                text(
                    f"""
                    SELECT
                        ac.chain_id, ac.host_id, ac.opened_at,
                        ac.max_ckc_stage, ac.triage_status, ac.status AS lifecycle_status,
                        ac.campaign_id,
                        c.name AS campaign_name,
                        c.actor_id, ta.name AS actor_name,
                        h.agent_name AS host_name,
                        COALESCE(r.confidence, 50) AS confidence
                    FROM attack_chains ac
                    JOIN campaigns c ON c.campaign_id = ac.campaign_id
                    LEFT JOIN threat_actors ta ON ta.actor_id = c.actor_id
                    LEFT JOIN hosts h ON h.host_id = ac.host_id
                    LEFT JOIN intel_relationships r
                      ON r.from_id = ac.chain_id
                     AND r.from_type = 'chain'
                     AND r.to_id = ac.campaign_id
                     AND r.to_type = 'campaign'
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY ac.opened_at DESC
                    LIMIT :lim
                    """
                ),
                params,
            )
        ).mappings().all()

        items = [
            AttributedChainItem(
                chain_id=r["chain_id"],
                host_id=r["host_id"],
                host_name=r["host_name"],
                opened_at=r["opened_at"],
                max_ckc_stage=int(r["max_ckc_stage"]),
                triage_status=r["triage_status"],
                lifecycle_status=r["lifecycle_status"],
                campaign_id=r["campaign_id"],
                campaign_name=r["campaign_name"],
                actor_id=r["actor_id"],
                actor_name=r["actor_name"],
                confidence=int(r["confidence"]),
            )
            for r in rows
        ]
        total_q = "SELECT COUNT(*) FROM attack_chains ac"
        total_params: dict[str, Any] = {}
        if campaign_id is not None or actor_id is not None:
            total_q += " JOIN campaigns c ON c.campaign_id = ac.campaign_id"
        where_total = ["ac.campaign_id IS NOT NULL"]
        if campaign_id is not None:
            where_total.append("ac.campaign_id = :campaign_id")
            total_params["campaign_id"] = campaign_id
        if actor_id is not None:
            where_total.append("c.actor_id = :actor_id")
            total_params["actor_id"] = actor_id
        total_q += " WHERE " + " AND ".join(where_total)
        total = (
            await self._s.execute(text(total_q), total_params)
        ).scalar_one()

        return AttributedChainListResponse(items=items, total=int(total))

    # ---------------------------------------------------------------- indicators

    async def list_indicators(
        self,
        *,
        source_label: str | None = None,
        indicator_type: str | None = None,
        limit: int = 50,
    ) -> IntelIndicatorListResponse:
        params: dict[str, Any] = {"lim": limit}
        where: list[str] = []
        if source_label:
            where.append("source_label = :source_label")
            params["source_label"] = source_label
        if indicator_type:
            where.append("indicator_type = :indicator_type")
            params["indicator_type"] = indicator_type
        clause = ("WHERE " + " AND ".join(where)) if where else ""

        rows = (
            await self._s.execute(
                text(
                    f"""
                    SELECT
                        indicator_id, indicator, indicator_type, confidence, tlp,
                        source_label, source_feed_id,
                        first_seen, last_seen,
                        first_seen_internal, last_seen_internal, internal_hit_count,
                        valid_from, valid_until, tags, description
                    FROM intel_indicators
                    {clause}
                    ORDER BY
                        COALESCE(last_seen_internal, last_seen) DESC
                    LIMIT :lim
                    """
                ),
                params,
            )
        ).mappings().all()

        items = [
            IntelIndicatorItem(
                indicator_id=r["indicator_id"],
                indicator=r["indicator"],
                indicator_type=r["indicator_type"],
                confidence=int(r["confidence"]),
                tlp=r["tlp"],
                source_label=r["source_label"],
                source_feed_id=r["source_feed_id"],
                first_seen=r["first_seen"],
                last_seen=r["last_seen"],
                first_seen_internal=r["first_seen_internal"],
                last_seen_internal=r["last_seen_internal"],
                internal_hit_count=int(r["internal_hit_count"]),
                valid_from=r["valid_from"],
                valid_until=r["valid_until"],
                tags=list(r["tags"] or []),
                description=r["description"],
            )
            for r in rows
        ]
        total_q = "SELECT COUNT(*) FROM intel_indicators"
        if where:
            total_q += " " + clause
        total = (await self._s.execute(text(total_q), params)).scalar_one()

        return IntelIndicatorListResponse(items=items, total=int(total))

    # ---------------------------------------------------------------- observable lookup
    #
    # Single-value pivot lookup. Used by the analyst's observable drawer to
    # enrich an IP / hash / domain / email with everything we know:
    #   1. the indicator record (if known to intel_indicators)
    #   2. chains where the value appears in alerts.full_log
    #   3. distinct actors + campaigns those chains are attributed to
    #
    # Lab scale (~few thousand alerts) makes the ILIKE on full_log
    # acceptable. At prod scale we'd persist a dedicated alert_indicators
    # join table at IOC-extraction time and query that instead.

    async def lookup_observable(
        self,
        value: str,
        *,
        chain_limit: int = 25,
    ) -> ObservableLookupResponse:
        value = value.strip()
        if not value:
            return ObservableLookupResponse(value=value, known=False)

        # 1) Indicator record — return the row with the strongest signal
        # (prefer 'internal_observation' over a feed-only row).
        ind_row = (
            await self._s.execute(
                text(
                    """
                    SELECT
                        indicator_id, indicator, indicator_type, confidence, tlp,
                        source_label, source_feed_id,
                        first_seen, last_seen,
                        first_seen_internal, last_seen_internal, internal_hit_count,
                        valid_from, valid_until, tags, description
                    FROM intel_indicators
                    WHERE indicator = :v
                    ORDER BY
                        (source_label = 'internal_observation') DESC,
                        internal_hit_count DESC,
                        last_seen DESC
                    LIMIT 1
                    """
                ),
                {"v": value},
            )
        ).mappings().first()

        indicator: IntelIndicatorItem | None = None
        ind_type: str | None = None
        if ind_row is not None:
            ind_type = ind_row["indicator_type"]
            indicator = IntelIndicatorItem(
                indicator_id=ind_row["indicator_id"],
                indicator=ind_row["indicator"],
                indicator_type=ind_row["indicator_type"],
                confidence=int(ind_row["confidence"]),
                tlp=ind_row["tlp"],
                source_label=ind_row["source_label"],
                source_feed_id=ind_row["source_feed_id"],
                first_seen=ind_row["first_seen"],
                last_seen=ind_row["last_seen"],
                first_seen_internal=ind_row["first_seen_internal"],
                last_seen_internal=ind_row["last_seen_internal"],
                internal_hit_count=int(ind_row["internal_hit_count"]),
                valid_from=ind_row["valid_from"],
                valid_until=ind_row["valid_until"],
                tags=list(ind_row["tags"] or []),
                description=ind_row["description"],
            )

        # 2) Chains where the value appears in alert text. Limit to most
        # recent N. Substring search is intentional — IPs / hashes are
        # specific enough that ILIKE '%value%' does not over-match.
        chain_rows = (
            await self._s.execute(
                text(
                    """
                    WITH hits AS (
                        SELECT
                            a.chain_id,
                            a.host_id,
                            MAX(a.occurred_at)        AS occurred_at,
                            MAX(a.ckc_stage)          AS ckc_stage,
                            COUNT(*)                  AS hits
                        FROM alerts a
                        WHERE a.chain_id IS NOT NULL
                          AND a.full_log ILIKE :pat
                        GROUP BY a.chain_id, a.host_id
                        ORDER BY occurred_at DESC
                        LIMIT :lim
                    )
                    SELECT
                        h.chain_id,
                        host.agent_id  AS host_id,
                        host.agent_name AS host_name,
                        h.occurred_at,
                        h.ckc_stage,
                        c.triage_status,
                        c.campaign_id
                    FROM hits h
                    LEFT JOIN attack_chains c ON c.chain_id = h.chain_id
                    LEFT JOIN hosts host      ON host.host_id = h.host_id
                    """
                ),
                {"pat": f"%{value}%", "lim": chain_limit},
            )
        ).mappings().all()

        ckc_names = [
            "BENIGN", "Recon", "Weaponization", "Delivery",
            "Exploitation", "Installation", "C2", "Actions",
        ]
        chains = [
            ObservableChainHit(
                chain_id=r["chain_id"],
                host_id=r["host_id"],
                host_name=r["host_name"],
                occurred_at=r["occurred_at"],
                ckc_stage=int(r["ckc_stage"]) if r["ckc_stage"] is not None else None,
                ckc_stage_name=ckc_names[int(r["ckc_stage"])] if r["ckc_stage"] is not None and 0 <= int(r["ckc_stage"]) < len(ckc_names) else None,
                triage_status=r["triage_status"],
            )
            for r in chain_rows
        ]

        # Total chain hits — independent of the limited list above.
        total_hits = int(
            (
                await self._s.execute(
                    text(
                        """
                        SELECT COUNT(DISTINCT a.chain_id)
                        FROM alerts a
                        WHERE a.chain_id IS NOT NULL
                          AND a.full_log ILIKE :pat
                        """
                    ),
                    {"pat": f"%{value}%"},
                )
            ).scalar_one()
            or 0
        )

        # 3) Distinct actors + campaigns reached via the chain hits.
        campaign_ids = list({r["campaign_id"] for r in chain_rows if r["campaign_id"]})
        actors: list[ObservableActorHit] = []
        campaigns: list[ObservableCampaignHit] = []
        if campaign_ids:
            actor_rows = (
                await self._s.execute(
                    text(
                        """
                        SELECT
                            ta.actor_id,
                            ta.name,
                            ta.mitre_group_id,
                            COUNT(DISTINCT c.chain_id) AS chain_count
                        FROM attack_chains c
                        JOIN campaigns cmp     ON cmp.campaign_id = c.campaign_id
                        JOIN threat_actors ta  ON ta.actor_id = cmp.actor_id
                        WHERE c.campaign_id = ANY(:cids)
                          AND c.chain_id = ANY(:chain_ids)
                        GROUP BY ta.actor_id, ta.name, ta.mitre_group_id
                        ORDER BY chain_count DESC
                        """
                    ),
                    {
                        "cids": campaign_ids,
                        "chain_ids": [r["chain_id"] for r in chain_rows],
                    },
                )
            ).mappings().all()
            actors = [
                ObservableActorHit(
                    actor_id=r["actor_id"],
                    name=r["name"],
                    mitre_group_id=r["mitre_group_id"],
                    chain_count=int(r["chain_count"]),
                )
                for r in actor_rows
            ]

            camp_rows = (
                await self._s.execute(
                    text(
                        """
                        SELECT
                            cmp.campaign_id,
                            cmp.name,
                            ta.name AS actor_name,
                            COUNT(DISTINCT c.chain_id) AS chain_count
                        FROM attack_chains c
                        JOIN campaigns cmp        ON cmp.campaign_id = c.campaign_id
                        LEFT JOIN threat_actors ta ON ta.actor_id = cmp.actor_id
                        WHERE c.campaign_id = ANY(:cids)
                          AND c.chain_id = ANY(:chain_ids)
                        GROUP BY cmp.campaign_id, cmp.name, ta.name
                        ORDER BY chain_count DESC
                        """
                    ),
                    {
                        "cids": campaign_ids,
                        "chain_ids": [r["chain_id"] for r in chain_rows],
                    },
                )
            ).mappings().all()
            campaigns = [
                ObservableCampaignHit(
                    campaign_id=r["campaign_id"],
                    name=r["name"],
                    actor_name=r["actor_name"],
                    chain_count=int(r["chain_count"]),
                )
                for r in camp_rows
            ]

        first_seen = indicator.first_seen if indicator else (chains[-1].occurred_at if chains else None)
        last_seen = indicator.last_seen if indicator else (chains[0].occurred_at if chains else None)

        return ObservableLookupResponse(
            value=value,
            indicator_type=ind_type,
            known=indicator is not None,
            indicator=indicator,
            chains=chains,
            actors=actors,
            campaigns=campaigns,
            total_chain_hits=total_hits,
            first_seen=first_seen,
            last_seen=last_seen,
        )

    # ---------------------------------------------------------------- pivot graph

    async def graph(self, *, chain_limit: int = 30) -> GraphResponse:
        """Build a pivot graph of the intel surface.

        Includes:
          - All actors + campaigns (small catalogues).
          - `attributed-to` edges (actor↔campaign).
          - The N most-recent attributed chains, with edges to their
            campaigns. `chain_limit` keeps the graph readable —
            commercial CTI tools paginate/cluster instead, but for the
            scale of this lab a hard cap is fine.

        Returns nodes + edges suitable for a force-directed layout. The
        UI computes positions client-side.
        """
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        # Actors
        actor_rows = (
            await self._s.execute(
                text(
                    """
                    SELECT ta.actor_id, ta.name, ta.mitre_group_id, ta.country,
                           COALESCE(att.n, 0) AS attributed_n
                    FROM threat_actors ta
                    LEFT JOIN (
                        SELECT c.actor_id, COUNT(*) AS n
                        FROM attack_chains ac
                        JOIN campaigns c ON c.campaign_id = ac.campaign_id
                        WHERE c.actor_id IS NOT NULL
                        GROUP BY c.actor_id
                    ) att ON att.actor_id = ta.actor_id
                    """
                )
            )
        ).mappings().all()
        for a in actor_rows:
            nodes.append(GraphNode(
                id=a["actor_id"],
                type="actor",
                label=a["name"],
                sub_label=a["country"],
                score=int(a["attributed_n"]),
                badge=a["mitre_group_id"],
            ))

        # Campaigns
        campaign_rows = (
            await self._s.execute(
                text(
                    """
                    SELECT c.campaign_id, c.name, c.actor_id,
                           COALESCE(att.n, 0) AS attributed_n
                    FROM campaigns c
                    LEFT JOIN (
                        SELECT campaign_id, COUNT(*) AS n
                        FROM attack_chains
                        WHERE campaign_id IS NOT NULL
                        GROUP BY campaign_id
                    ) att ON att.campaign_id = c.campaign_id
                    """
                )
            )
        ).mappings().all()
        for c in campaign_rows:
            nodes.append(GraphNode(
                id=c["campaign_id"],
                type="campaign",
                label=c["name"][:40],
                score=int(c["attributed_n"]),
            ))
            if c["actor_id"] is not None:
                edges.append(GraphEdge(
                    from_id=c["campaign_id"],
                    to_id=c["actor_id"],
                    rel="attributed-to",
                    confidence=95,
                ))

        # Top chains by recency, attributed only
        chain_rows = (
            await self._s.execute(
                text(
                    """
                    SELECT ac.chain_id, ac.campaign_id, ac.max_ckc_stage,
                           h.agent_name,
                           COALESCE(r.confidence, 50) AS confidence
                    FROM attack_chains ac
                    LEFT JOIN hosts h ON h.host_id = ac.host_id
                    LEFT JOIN intel_relationships r
                      ON r.from_id = ac.chain_id
                     AND r.from_type = 'chain'
                     AND r.to_id = ac.campaign_id
                     AND r.to_type = 'campaign'
                    WHERE ac.campaign_id IS NOT NULL
                    ORDER BY ac.opened_at DESC
                    LIMIT :lim
                    """
                ),
                {"lim": chain_limit},
            )
        ).mappings().all()
        for ch in chain_rows:
            nodes.append(GraphNode(
                id=ch["chain_id"],
                type="chain",
                label=str(ch["chain_id"])[:8],
                sub_label=ch["agent_name"],
                score=int(ch["max_ckc_stage"] or 0),
            ))
            edges.append(GraphEdge(
                from_id=ch["chain_id"],
                to_id=ch["campaign_id"],
                rel="attributed-to",
                confidence=int(ch["confidence"]),
            ))

        return GraphResponse(nodes=nodes, edges=edges)

    # ---------------------------------------------------------------- single-chain attribution

    async def chain_attribution(self, chain_id: UUID) -> ChainAttributionResponse:
        """Resolve a chain's winning campaign + actor, plus up to 3 candidate
        attributions, in one round-trip.

        - `attributed=true` when attack_chains.campaign_id is set (the
          winning match crossed ATTRIBUTION_THRESHOLD).
        - `candidates` always reflects ALL recorded relationship edges
          for this chain, sorted by confidence desc — so the UI can
          show "we thought this looked X% like APT28 too" even when a
          different actor won.
        """
        # Winning attribution (if any)
        win = (
            await self._s.execute(
                text(
                    """
                    SELECT
                        ac.campaign_id,
                        c.name AS campaign_name,
                        c.description AS campaign_description,
                        c.tactic_chain,
                        c.actor_id,
                        ta.name AS actor_name,
                        ta.mitre_group_id AS actor_mitre_group_id,
                        ta.country AS actor_country,
                        ta.motivation AS actor_motivation,
                        ta.aliases AS actor_aliases,
                        r.confidence AS confidence
                    FROM attack_chains ac
                    LEFT JOIN campaigns c ON c.campaign_id = ac.campaign_id
                    LEFT JOIN threat_actors ta ON ta.actor_id = c.actor_id
                    LEFT JOIN intel_relationships r
                      ON r.from_id = ac.chain_id
                     AND r.from_type = 'chain'
                     AND r.to_id = ac.campaign_id
                     AND r.to_type = 'campaign'
                    WHERE ac.chain_id = :cid
                    """
                ),
                {"cid": chain_id},
            )
        ).mappings().first()

        # Candidate (runner-up) edges — always show top 3 by confidence.
        cand_rows = (
            await self._s.execute(
                text(
                    """
                    SELECT
                        r.to_id AS campaign_id,
                        c.name AS campaign_name,
                        ta.name AS actor_name,
                        r.confidence AS confidence
                    FROM intel_relationships r
                    JOIN campaigns c ON c.campaign_id = r.to_id
                    LEFT JOIN threat_actors ta ON ta.actor_id = c.actor_id
                    WHERE r.from_id = :cid
                      AND r.from_type = 'chain'
                      AND r.to_type = 'campaign'
                      AND r.rel = 'attributed-to'
                    ORDER BY r.confidence DESC
                    LIMIT 3
                    """
                ),
                {"cid": chain_id},
            )
        ).mappings().all()
        candidates = [
            ChainAttributionCandidate(
                campaign_id=cr["campaign_id"],
                campaign_name=cr["campaign_name"],
                actor_name=cr["actor_name"],
                confidence=int(cr["confidence"]),
            )
            for cr in cand_rows
        ]

        if win is None:
            return ChainAttributionResponse(chain_id=chain_id, attributed=False, candidates=candidates)

        attributed = win["campaign_id"] is not None
        return ChainAttributionResponse(
            chain_id=chain_id,
            attributed=attributed,
            campaign_id=win["campaign_id"],
            campaign_name=win["campaign_name"],
            campaign_description=win["campaign_description"],
            campaign_tactic_chain=list(win["tactic_chain"] or []),
            actor_id=win["actor_id"],
            actor_name=win["actor_name"],
            actor_mitre_group_id=win["actor_mitre_group_id"],
            actor_country=win["actor_country"],
            actor_motivation=win["actor_motivation"],
            actor_aliases=list(win["actor_aliases"] or []),
            confidence=int(win["confidence"]) if win["confidence"] is not None else None,
            candidates=candidates,
        )

    # ---------------------------------------------------------------- feeds

    async def list_feeds(self) -> IntelFeedListResponse:
        rows = (
            await self._s.execute(
                text(
                    """
                    SELECT
                        f.feed_id, f.name, f.kind, f.url, f.enabled,
                        f.pull_interval_s, f.last_pulled_at, f.last_status,
                        f.last_indicator_count, f.default_confidence, f.default_tlp,
                        COALESCE(ic.indicator_count_total, 0) AS indicator_count_total
                    FROM intel_feeds f
                    LEFT JOIN (
                        SELECT source_feed_id, COUNT(*) AS indicator_count_total
                        FROM intel_indicators
                        WHERE source_feed_id IS NOT NULL
                        GROUP BY source_feed_id
                    ) ic ON ic.source_feed_id = f.feed_id
                    ORDER BY f.enabled DESC, f.name
                    """
                )
            )
        ).mappings().all()
        items = [
            IntelFeedItem(
                feed_id=r["feed_id"],
                name=r["name"],
                kind=r["kind"],
                url=r["url"],
                enabled=bool(r["enabled"]),
                pull_interval_s=int(r["pull_interval_s"]),
                last_pulled_at=r["last_pulled_at"],
                last_status=r["last_status"],
                last_indicator_count=int(r["last_indicator_count"] or 0),
                default_confidence=int(r["default_confidence"]),
                default_tlp=r["default_tlp"],
                indicator_count_total=int(r["indicator_count_total"]),
            )
            for r in rows
        ]
        return IntelFeedListResponse(items=items, total=len(items))

    # ---------------------------------------------------------------- overview

    async def overview(self) -> IntelOverviewResponse:
        # Counts strip
        actor_total = int((await self._s.execute(
            select(func.count()).select_from(ThreatActor)
        )).scalar_one())
        campaign_total = int((await self._s.execute(
            select(func.count()).select_from(Campaign)
        )).scalar_one())
        indicator_total = int((await self._s.execute(
            text("SELECT COUNT(*) FROM intel_indicators")
        )).scalar_one())
        indicator_internal = int((await self._s.execute(
            text("SELECT COUNT(*) FROM intel_indicators WHERE last_seen_internal IS NOT NULL")
        )).scalar_one())
        attributed = int((await self._s.execute(
            select(func.count()).select_from(AttackChain)
            .where(AttackChain.campaign_id.is_not(None))
        )).scalar_one())
        unattributed_open = int((await self._s.execute(
            select(func.count()).select_from(AttackChain)
            .where(and_(AttackChain.campaign_id.is_(None), AttackChain.status == "open"))
        )).scalar_one())

        counts = IntelOverviewCounts(
            actors=actor_total,
            campaigns=campaign_total,
            indicators_total=indicator_total,
            indicators_observed_internal=indicator_internal,
            attributed_chains=attributed,
            unattributed_open_chains=unattributed_open,
        )

        top_actors = (await self.list_actors(limit=6)).items
        top_campaigns = (await self.list_campaigns(limit=6)).items
        recent_attributions = (
            await self.list_attributed_chains(limit=10)
        ).items
        top_indicators = (
            await self.list_indicators(source_label="internal_observation", limit=8)
        ).items
        feeds = (await self.list_feeds()).items

        return IntelOverviewResponse(
            counts=counts,
            top_actors=top_actors,
            top_campaigns=top_campaigns,
            recent_attributions=recent_attributions,
            top_observed_indicators=top_indicators,
            feeds=feeds,
        )


__all__ = ["IntelService"]
