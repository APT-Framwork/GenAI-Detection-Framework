"""CTI namespace endpoints.

  GET  /intel/overview                    landing-page hydration in one round-trip
  GET  /intel/actors                      paged list of threat actors
  GET  /intel/actors/{actor_id}           single actor detail
  GET  /intel/campaigns                   paged list of campaigns
  GET  /intel/campaigns/{campaign_id}     single campaign detail
  GET  /intel/attributed-chains           chains with campaign_id set
  GET  /intel/indicators                  query intel_indicators (Tier-1 model)

Follows the same fall-through-to-empty pattern as the other namespaces:
when the DB session is None (unit-test sandbox), return empty/stub
responses instead of crashing.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.deps import get_db_session
from strix_api.api.schemas.intel import (
    AttributedChainListResponse,
    CampaignItem,
    CampaignListResponse,
    ChainAttributionResponse,
    GraphResponse,
    IntelFeedListResponse,
    IntelIndicatorListResponse,
    IntelOverviewCounts,
    IntelOverviewResponse,
    ObservableLookupResponse,
    ThreatActorItem,
    ThreatActorListResponse,
)
from strix_api.observability import get_logger
from strix_api.services.intel_service import IntelService

router = APIRouter(prefix="/intel", tags=["intel"])
log = get_logger("strix_api.api.routes.intel")


def _empty_overview() -> IntelOverviewResponse:
    return IntelOverviewResponse(
        counts=IntelOverviewCounts(
            actors=0, campaigns=0,
            indicators_total=0, indicators_observed_internal=0,
            attributed_chains=0, unattributed_open_chains=0,
        ),
        top_actors=[],
        top_campaigns=[],
        recent_attributions=[],
        top_observed_indicators=[],
        feeds=[],
    )


@router.get(
    "/overview",
    response_model=IntelOverviewResponse,
    summary="One-shot hydration for the CTI landing page",
)
async def get_overview(
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> IntelOverviewResponse:
    if session is None:
        return _empty_overview()
    try:
        return await IntelService(session).overview()
    except Exception as exc:  # noqa: BLE001
        log.warning("intel_overview_db_error_falling_back", exc_info=exc)
        return _empty_overview()


@router.get("/actors", response_model=ThreatActorListResponse)
async def list_actors(
    limit: int = Query(default=50, ge=1, le=500),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ThreatActorListResponse:
    if session is None:
        return ThreatActorListResponse(items=[], total=0)
    try:
        return await IntelService(session).list_actors(limit=limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("intel_actors_db_error", exc_info=exc)
        return ThreatActorListResponse(items=[], total=0)


@router.get("/actors/{actor_id}", response_model=ThreatActorItem)
async def get_actor(
    actor_id: UUID,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ThreatActorItem:
    if session is None:
        raise HTTPException(status_code=404, detail="actor not found")
    actor = await IntelService(session).get_actor(actor_id)
    if actor is None:
        raise HTTPException(status_code=404, detail="actor not found")
    return actor


@router.get("/campaigns", response_model=CampaignListResponse)
async def list_campaigns(
    limit: int = Query(default=50, ge=1, le=500),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> CampaignListResponse:
    if session is None:
        return CampaignListResponse(items=[], total=0)
    try:
        return await IntelService(session).list_campaigns(limit=limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("intel_campaigns_db_error", exc_info=exc)
        return CampaignListResponse(items=[], total=0)


@router.get("/campaigns/{campaign_id}", response_model=CampaignItem)
async def get_campaign(
    campaign_id: UUID,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> CampaignItem:
    if session is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    c = await IntelService(session).get_campaign(campaign_id)
    if c is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return c


@router.get("/attributed-chains", response_model=AttributedChainListResponse)
async def list_attributed_chains(
    actor_id: UUID | None = Query(default=None),
    campaign_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> AttributedChainListResponse:
    if session is None:
        return AttributedChainListResponse(items=[], total=0)
    try:
        return await IntelService(session).list_attributed_chains(
            actor_id=actor_id, campaign_id=campaign_id, limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("intel_attributed_chains_db_error", exc_info=exc)
        return AttributedChainListResponse(items=[], total=0)


@router.get("/graph", response_model=GraphResponse)
async def get_graph(
    chain_limit: int = Query(default=30, ge=1, le=200),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> GraphResponse:
    if session is None:
        return GraphResponse(nodes=[], edges=[])
    try:
        return await IntelService(session).graph(chain_limit=chain_limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("intel_graph_db_error", exc_info=exc)
        return GraphResponse(nodes=[], edges=[])


@router.get("/chains/{chain_id}/attribution", response_model=ChainAttributionResponse)
async def chain_attribution(
    chain_id: UUID,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ChainAttributionResponse:
    if session is None:
        return ChainAttributionResponse(chain_id=chain_id, attributed=False, candidates=[])
    try:
        return await IntelService(session).chain_attribution(chain_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("intel_chain_attribution_error", exc_info=exc)
        return ChainAttributionResponse(chain_id=chain_id, attributed=False, candidates=[])


@router.get("/feeds", response_model=IntelFeedListResponse)
async def list_feeds(
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> IntelFeedListResponse:
    if session is None:
        return IntelFeedListResponse(items=[], total=0)
    try:
        return await IntelService(session).list_feeds()
    except Exception as exc:  # noqa: BLE001
        log.warning("intel_feeds_db_error", exc_info=exc)
        return IntelFeedListResponse(items=[], total=0)


@router.get("/indicators", response_model=IntelIndicatorListResponse)
async def list_indicators(
    source_label: str | None = Query(default=None),
    indicator_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> IntelIndicatorListResponse:
    if session is None:
        return IntelIndicatorListResponse(items=[], total=0)
    try:
        return await IntelService(session).list_indicators(
            source_label=source_label,
            indicator_type=indicator_type,
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("intel_indicators_db_error", exc_info=exc)
        return IntelIndicatorListResponse(items=[], total=0)


@router.get(
    "/observables/lookup",
    response_model=ObservableLookupResponse,
    summary="Single-value pivot — indicator record, chains, actors, campaigns",
)
async def lookup_observable(
    value: str = Query(..., min_length=1, max_length=512),
    chain_limit: int = Query(default=25, ge=1, le=100),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ObservableLookupResponse:
    if session is None:
        return ObservableLookupResponse(value=value, known=False)
    try:
        return await IntelService(session).lookup_observable(value, chain_limit=chain_limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("intel_observable_lookup_error", exc_info=exc, extra={"value": value})
        return ObservableLookupResponse(value=value, known=False)
