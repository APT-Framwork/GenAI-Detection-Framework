"""Dashboard-tab endpoints (§4.1) — Phase 4 wired to Timescale + Redis cache.

Falls back to empty-shape responses when the DB session can't be acquired
(e.g. unit tests that don't spin up Postgres) so the OpenAPI surface
remains stable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.adapters.llm_adapter import LlmAdapter, LlmError
from strix_api.api.deps import SettingsDep, get_db_session
from strix_api.api.schemas.common import WindowLiteral
from strix_api.api.schemas.dashboard import (
    AttackVectorResponse,
    GlobalRiskComponents,
    GlobalRiskResponse,
    SentinelInsightAction,
    SentinelInsightResponse,
    StageBucket,
    VictimGraphResponse,
)
from strix_api.api.schemas.threat_intel import JobAcceptedResponse
from strix_api.observability import get_logger
from strix_api.services.dashboard_service import DashboardService
from strix_api.services.insight_service import InsightService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
log = get_logger("strix_api.api.routes.dashboard")


# Ordering matches `CkcStage` (0=BENIGN, 1..7 attack stages).
_EMPTY_STAGES: list[StageBucket] = [
    StageBucket(ckc_stage=stage, ckc_name=name, count=0, percent=0.0)
    for stage, name in (
        (0, "BENIGN"),
        (1, "RECONNAISSANCE"),
        (2, "WEAPONIZATION"),
        (3, "DELIVERY"),
        (4, "EXPLOITATION"),
        (5, "INSTALLATION"),
        (6, "COMMAND_AND_CONTROL"),
        (7, "ACTIONS_ON_OBJECTIVES"),
    )
]


async def _try_service(
    session: AsyncSession | None,
    handler: callable,  # type: ignore[name-defined]
    fallback: callable,  # type: ignore[name-defined]
):
    """Run `handler(DashboardService(session))`; on any DB error fall back."""
    if session is None:
        return fallback()
    try:
        svc = DashboardService(session)
        return await handler(svc)
    except Exception as exc:  # noqa: BLE001
        log.warning("dashboard_db_error_falling_back", exc_info=exc)
        return fallback()


# ---- attack-vector ----------------------------------------------


@router.get(
    "/attack-vector",
    response_model=AttackVectorResponse,
    summary="CKC stage distribution over a window",
)
async def attack_vector(
    window: WindowLiteral = Query("1h"),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> AttackVectorResponse:
    return await _try_service(
        session,
        lambda svc: svc.attack_vector(window),
        lambda: AttackVectorResponse(
            window=window,
            total_alerts=0,
            stages=_EMPTY_STAGES,
        ),
    )


# ---- global-risk ------------------------------------------------


@router.get(
    "/global-risk",
    response_model=GlobalRiskResponse,
    summary="Threat intensity / Global Risk over window",
)
async def global_risk(
    window: WindowLiteral = Query("1h"),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> GlobalRiskResponse:
    return await _try_service(
        session,
        lambda svc: svc.global_risk(window),
        lambda: GlobalRiskResponse(
            window=window,
            global_risk=0.0,
            components=GlobalRiskComponents(
                vae_mean_prob=0.0,
                gnn_max_node_risk=0.0,
                anomaly_rate=0.0,
                risk_growth=0.0,
            ),
            delta_1h=0.0,
            trend=[],
        ),
    )


# ---- victim-graph -----------------------------------------------


@router.get(
    "/victim-graph",
    response_model=VictimGraphResponse,
    summary="Connected-victims projection of the GNN graph",
)
async def victim_graph(
    window: WindowLiteral = Query("1h"),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> VictimGraphResponse:
    return await _try_service(
        session,
        lambda svc: svc.victim_graph(window),
        lambda: VictimGraphResponse(window=window, nodes=[], edges=[]),
    )


# ---- sentinel-insight ------------------------------------------


def _placeholder_insight(detail: str) -> SentinelInsightResponse:
    return SentinelInsightResponse(
        generated_at=datetime.now(UTC).isoformat(timespec="microseconds"),
        model_version="placeholder",
        insight=detail,
        recommended_actions=[],
        confidence=0.0,
        stale=True,
    )


@router.get(
    "/sentinel-insight",
    response_model=SentinelInsightResponse,
    summary="LLM-generated insight (Opus 4.7) — cached for 5 min per §5.14",
)
async def sentinel_insight(
    settings: SettingsDep,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> SentinelInsightResponse:
    if session is None:
        return _placeholder_insight(
            "Backend running in sandbox mode (no DB) — no insight available.",
        )
    if settings.llm.anthropic_api_key is None:
        return _placeholder_insight(
            "LLM_ANTHROPIC_API_KEY not configured. Set it in .env to enable insights.",
        )

    llm = LlmAdapter.from_settings(settings.llm)
    service = InsightService(session=session, llm=llm)
    try:
        result = await service.get_or_generate(force_refresh=False)
    except LlmError as exc:
        log.warning("sentinel_insight_unavailable", reason=exc.detail)
        return _placeholder_insight(
            f"Sentinel Insight is currently unavailable: {exc.detail or 'unknown error'}",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("sentinel_insight_db_error", exc_info=exc)
        return _placeholder_insight("Insight backend transient error — try again shortly.")

    return SentinelInsightResponse(
        generated_at=result.generated_at.isoformat(timespec="microseconds"),
        model_version=result.model_version,
        insight=result.insight,
        recommended_actions=[
            SentinelInsightAction(label=a["label"], rationale=a.get("rationale", ""))
            for a in result.recommended_actions
        ],
        confidence=result.confidence,
        stale=result.stale,
    )


@router.post(
    "/sentinel-insight/refresh",
    response_model=JobAcceptedResponse,
    status_code=202,
    summary="Force-refresh the Sentinel Insight via Arq; result on /streams/jobs/{jobId}",
)
async def refresh_sentinel_insight(
    settings: SettingsDep,
) -> JobAcceptedResponse:
    job_id = uuid4()
    try:
        from arq import create_pool

        from strix_api.workers.arq_tasks import _redis_settings_from

        pool = await create_pool(_redis_settings_from(settings))
        try:
            await pool.enqueue_job(
                "generate_sentinel_insight",
                job_id=str(job_id),
            )
        finally:
            await pool.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("sentinel_insight_enqueue_failed", exc_info=exc)
    return JobAcceptedResponse(job_id=job_id, status="queued")
