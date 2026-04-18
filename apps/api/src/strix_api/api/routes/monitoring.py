"""Model-monitoring tab (§4.4) — wired up in Phase 8.

Reads `apps/models/registry.json` for static metadata + Timescale CAGGs
for the confidence trend + DriftService for the KL gauge.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.adapters.model_registry import load_registry
from strix_api.api.deps import SettingsDep, get_db_session, require_admin
from strix_api.api.errors import StrixError
from strix_api.api.schemas.common import WindowLiteral
from strix_api.api.schemas.monitoring import (
    CompositeAccuracyResponse,
    ConfidenceTrendResponse,
    DriftReportItem,
    DriftResponse,
    ModelHealth,
    ModelsResponse,
    RetrainResponse,
    TrendPoint,
)
from strix_api.observability import get_logger
from strix_api.services.drift_service import DriftService

router = APIRouter(prefix="/monitoring", tags=["monitoring"])
log = get_logger("strix_api.api.routes.monitoring")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _registry_models(settings: Any) -> list[ModelHealth]:
    """Read the registry and project to ModelHealth rows."""
    try:
        state = load_registry(
            settings.models.registry_path,
            settings.models.path,
            verify_checksums=False,        # API surface; checksums verified at worker boot
        )
    except StrixError as exc:
        log.warning("monitoring_models_registry_unavailable", reason=exc.detail)
        return []
    out: list[ModelHealth] = []
    for entry in state.models.values():
        status = "degraded" if state.missing_artifacts else "active"
        out.append(ModelHealth(
            name=entry.name,
            version=entry.version,
            weights_sha256=entry.weights_sha256,
            status=status,
            last_health_check=_now_iso(),
        ))
    return out


# ---- /models ---------------------------------------------------------


@router.get(
    "/models",
    response_model=ModelsResponse,
    summary="Per-model health + version + drift KL",
)
async def list_models(
    settings: SettingsDep,
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ModelsResponse:
    models = _registry_models(settings)
    if not models:
        return ModelsResponse(models=[])

    if session is not None:
        try:
            reports = await DriftService(session=session, settings=settings).compute_for_window(
                window_minutes=60,
            )
            kl_by_model = {r.model: r.kl_divergence for r in reports}
            for m in models:
                m_dict = m.model_dump()
                m_dict["drift_kl"] = kl_by_model.get(m.name)
                # Replace the model in-place via reconstruction — Pydantic v2 immutables
            models = [
                ModelHealth(**{**m.model_dump(), "drift_kl": kl_by_model.get(m.name)})
                for m in models
            ]
        except Exception as exc:  # noqa: BLE001
            log.warning("monitoring_drift_unavailable", exc_info=exc)

    return ModelsResponse(models=models)


# ---- /composite-accuracy --------------------------------------------


@router.get(
    "/composite-accuracy",
    response_model=CompositeAccuracyResponse,
)
async def composite_accuracy() -> CompositeAccuracyResponse:
    # Static placeholder until Phase 8 ships per-model offline accuracy in
    # `registry.json`. Real value computed by the training pipeline.
    return CompositeAccuracyResponse(value=0.0, computed_at=_now_iso())


# ---- /confidence-trend ----------------------------------------------


@router.get(
    "/confidence-trend",
    response_model=ConfidenceTrendResponse,
)
async def confidence_trend(
    window: WindowLiteral = Query("7d"),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> ConfidenceTrendResponse:
    if session is None:
        return ConfidenceTrendResponse(window=window, points=[])
    interval = {"15m": "15 minutes", "1h": "1 hour",
                "24h": "24 hours", "7d": "7 days", "all": "100 years"}.get(window, "7 days")
    try:
        result = await session.execute(
            text(
                """
                SELECT bucket, ae_anomaly, vae_prob, transformer_confidence, gnn_risk
                FROM confidence_trend_daily
                WHERE bucket >= NOW() - (:interval)::INTERVAL
                ORDER BY bucket ASC
                """
            ),
            {"interval": interval},
        )
        points = [
            TrendPoint(
                ts=r.bucket.isoformat() if hasattr(r.bucket, "isoformat") else str(r.bucket),
                ae_anomaly=float(r.ae_anomaly or 0.0),
                vae_prob=float(r.vae_prob or 0.0),
                transformer_confidence=float(r.transformer_confidence or 0.0),
                gnn_risk=float(r.gnn_risk or 0.0),
            )
            for r in result.all()
        ]
        return ConfidenceTrendResponse(window=window, points=points)
    except Exception as exc:  # noqa: BLE001
        log.warning("monitoring_trend_db_error", exc_info=exc)
        return ConfidenceTrendResponse(window=window, points=[])


# ---- /drift -----------------------------------------------------------


@router.get(
    "/drift",
    response_model=DriftResponse,
    summary="Score-distribution KL divergence per model (live vs baseline)",
)
async def drift(
    settings: SettingsDep,
    window_minutes: int = Query(60, ge=5, le=24 * 60, alias="windowMinutes"),
    session: Annotated[AsyncSession | None, Depends(get_db_session)] = None,
) -> DriftResponse:
    if session is None:
        return DriftResponse(window_minutes=window_minutes, items=[])
    try:
        reports = await DriftService(session=session, settings=settings).compute_for_window(
            window_minutes=window_minutes,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("monitoring_drift_db_error", exc_info=exc)
        return DriftResponse(window_minutes=window_minutes, items=[])
    return DriftResponse(
        window_minutes=window_minutes,
        items=[
            DriftReportItem(
                model=r.model, samples=r.samples,
                kl_divergence=r.kl_divergence,
                above_threshold=r.above_threshold,
            )
            for r in reports
        ],
    )


# ---- /models/retrain (admin only) ----------------------------------


@router.post(
    "/models/retrain",
    response_model=RetrainResponse,
    status_code=202,
    dependencies=[Depends(require_admin)],
    summary="Placeholder — full retraining pipeline is post-1.0 (§12 Q7)",
)
async def retrain_models() -> RetrainResponse:
    log.warning("retrain_requested_no_pipeline")
    return RetrainResponse(
        accepted=False,
        message=(
            "Automated retraining is post-1.0 scope (§12 Q7). "
            "When this fires, re-run the training notebooks against accumulated "
            "alerts.raw_jsonb data, bump registry.json version, rolling-restart workers."
        ),
    )
