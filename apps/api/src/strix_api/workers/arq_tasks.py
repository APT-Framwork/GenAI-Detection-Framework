"""Arq async-job worker (§5.6).

Tasks:
    on_demand_vt_scan(indicator, indicator_type)   → VT lookup + cache + SSE
    file_scan(scan_id, sha256)                     → VT hash lookup + persist + SSE

The worker runs in its own container (`strix_arq` in compose.api.yml). It
pulls jobs from the same Redis instance everything else uses (§5.6 — no
new broker).

Each completed job publishes the result to the same SSE channel the route
handlers subscribe to:
    strix:sse:job:{job_id}
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from arq.connections import RedisSettings as ArqRedisSettings

from strix_api.adapters.virustotal_adapter import VirusTotalAdapter, VirusTotalError
from strix_api.observability import (
    configure_logging,
    external_api_errors_total,
    get_logger,
)
from strix_api.repositories.database import init_engine, session_scope
from strix_api.repositories.file_scan_repo import FileScanRepo
from strix_api.repositories.ioc_repo import IocRepo
from strix_api.services.threat_intel_service import (
    detect_indicator_type,
)
from strix_api.settings import Settings, get_settings


def job_channel(job_id: str) -> str:
    return f"strix:sse:job:{job_id}"


def job_result_key(job_id: str) -> str:
    """Persistent record of the last completion payload for this job_id.

    Companion to `job_channel`: the channel is fire-and-forget pubsub, so a
    subscriber that connects after the worker publishes never sees the
    event. We also `SET` the same payload here with a short TTL so the SSE
    endpoint can serve a late-joining client out of this key — the dashboard
    typically opens its EventSource ~50–500 ms after kicking the job, and
    free-tier VT lookups can return faster than that.
    """
    return f"strix:sse:job:{job_id}:result"


_JOB_RESULT_TTL_SECONDS = 300  # 5 min — bounded by max plausible "late client" window


async def _publish_job_event(redis: Any, job_id: str, payload: dict[str, Any]) -> None:
    """Publish to the live channel AND store as a recoverable result key.

    Both writes use the same JSON encoding so the SSE endpoint can yield
    either source through the `job.complete` event with no transformation.
    """
    encoded = json.dumps(payload).encode("utf-8")
    await redis.publish(job_channel(job_id), encoded)
    try:
        await redis.set(job_result_key(job_id), encoded, ex=_JOB_RESULT_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        # Best-effort: pubsub already fired; missing the persisted result
        # only degrades to the original race-condition behaviour.
        pass


# ---- task implementations --------------------------------------------


async def on_demand_vt_scan(
    ctx: dict[str, Any],
    *,
    job_id: str,
    indicator: str,
    indicator_type: str | None = None,
) -> dict[str, Any]:
    """Run a VirusTotal scan + push the result to the per-job SSE channel."""
    log = get_logger("strix_api.workers.arq_tasks.vt_scan", job_id=job_id)
    settings: Settings = ctx["settings"]
    vt: VirusTotalAdapter = ctx["vt"]
    redis = ctx["redis"]

    sniffed = indicator_type or detect_indicator_type(indicator) or "unknown"
    try:
        if sniffed == "ip":
            result = await vt.lookup_ip(indicator)
        elif sniffed == "domain":
            result = await vt.lookup_domain(indicator)
        elif sniffed == "hash":
            result = await vt.lookup_hash(indicator)
        else:
            log.warning("vt_scan_unsupported_type", indicator_type=sniffed)
            payload = {"jobId": job_id, "status": "error", "error": f"unsupported type {sniffed!r}"}
            await _publish_job_event(redis, job_id, payload)
            return payload

        # Cache the result the same way the synchronous path would.
        async with session_scope() as session:
            await IocRepo(session).upsert(
                indicator=result.indicator,
                indicator_type=sniffed,
                source="virustotal",
                reputation=result.reputation,
                payload={
                    "counts": result.counts.__dict__,
                    "engines": result.engines,
                },
                ttl=__import__("datetime").timedelta(hours=24),
            )

        payload = {
            "jobId": job_id,
            "status": "complete",
            "indicator": result.indicator,
            "indicatorType": sniffed,
            "reputation": result.reputation,
            "counts": result.counts.__dict__,
            "engines": result.engines,
        }
        await _publish_job_event(redis, job_id, payload)
        log.info("vt_scan_complete", indicator=indicator, reputation=result.reputation)
        return payload

    except VirusTotalError as exc:
        external_api_errors_total.labels(api="virustotal", error_kind="task_failed").inc()
        payload = {"jobId": job_id, "status": "error", "error": exc.detail or "vt_failed"}
        await _publish_job_event(redis, job_id, payload)
        log.error("vt_scan_failed", indicator=indicator, exc_info=exc)
        return payload


async def generate_sentinel_insight(
    ctx: dict[str, Any],
    *,
    job_id: str,
) -> dict[str, Any]:
    """Refresh the Sentinel Insight cache + push the result to SSE (P7-3)."""
    log = get_logger("strix_api.workers.arq_tasks.sentinel_insight", job_id=job_id)
    redis = ctx["redis"]

    from strix_api.adapters.llm_adapter import LlmAdapter, LlmError
    from strix_api.services.insight_service import InsightService
    from strix_api.settings import get_settings

    llm = LlmAdapter.from_settings(get_settings().llm)
    try:
        async with session_scope() as session:
            service = InsightService(session=session, llm=llm)
            try:
                result = await service.get_or_generate(force_refresh=True)
            except LlmError as exc:
                external_api_errors_total.labels(
                    api="llm",
                    error_kind="insight_failed",
                ).inc()
                payload = {
                    "jobId": job_id,
                    "status": "error",
                    "error": exc.detail or "llm_failed",
                }
                await _publish_job_event(redis, job_id, payload)
                log.error("sentinel_insight_failed", exc_info=exc)
                return payload

        payload = {
            "jobId": job_id,
            "status": "complete",
            "insight": result.insight,
            "recommendedActions": result.recommended_actions,
            "confidence": result.confidence,
            "modelVersion": result.model_version,
            "generatedAt": result.generated_at.isoformat(),
            "stale": result.stale,
        }
        await _publish_job_event(redis, job_id, payload)
        log.info("sentinel_insight_complete", model=result.model_version)
        return payload
    finally:
        # No httpx pool to close — anthropic SDK manages its own.
        pass


async def file_scan(
    ctx: dict[str, Any],
    *,
    job_id: str,
    scan_id: str,
    sha256: str,
) -> dict[str, Any]:
    """Run a VT hash lookup, persist to file_scans, push SSE result."""
    log = get_logger("strix_api.workers.arq_tasks.file_scan", job_id=job_id, scan_id=scan_id)
    vt: VirusTotalAdapter = ctx["vt"]
    redis = ctx["redis"]

    try:
        result = await vt.lookup_hash(sha256)
        async with session_scope() as session:
            from uuid import UUID

            await FileScanRepo(session).mark_complete(
                UUID(scan_id),
                vt_result={
                    "reputation": result.reputation,
                    "counts": result.counts.__dict__,
                    "engines": result.engines,
                },
                status="complete",
            )
            await IocRepo(session).upsert(
                indicator=sha256.lower(),
                indicator_type="hash",
                source="virustotal",
                reputation=result.reputation,
                payload={"counts": result.counts.__dict__, "engines": result.engines},
                ttl=__import__("datetime").timedelta(hours=24),
            )

        payload = {
            "jobId": job_id,
            "scanId": scan_id,
            "status": "complete",
            "sha256": sha256.lower(),
            "reputation": result.reputation,
            "counts": result.counts.__dict__,
        }
        await _publish_job_event(redis, job_id, payload)
        log.info("file_scan_complete", reputation=result.reputation)
        return payload

    except VirusTotalError as exc:
        external_api_errors_total.labels(api="virustotal", error_kind="file_scan_failed").inc()
        async with session_scope() as session:
            from uuid import UUID

            await FileScanRepo(session).mark_complete(
                UUID(scan_id),
                vt_result={"error": str(exc.detail)},
                status="error",
            )
        payload = {
            "jobId": job_id,
            "scanId": scan_id,
            "status": "error",
            "error": exc.detail or "vt_failed",
        }
        await _publish_job_event(redis, job_id, payload)
        log.error("file_scan_failed", exc_info=exc)
        return payload


# ---- worker config --------------------------------------------------


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(
        service_name="strix-arq",
        level=settings.observability.log_level,
        json_output=settings.observability.log_json,
    )
    init_engine(settings)
    httpx_client = httpx.AsyncClient(timeout=10.0)
    ctx["settings"] = settings
    ctx["httpx"] = httpx_client
    ctx["vt"] = VirusTotalAdapter(settings.threat_intel, client=httpx_client)


async def shutdown(ctx: dict[str, Any]) -> None:
    if "httpx" in ctx:
        await ctx["httpx"].aclose()
    if "vt" in ctx:
        await ctx["vt"].aclose()


def _redis_settings_from(settings: Settings) -> ArqRedisSettings:
    return ArqRedisSettings(
        host=settings.redis.host,
        port=settings.redis.port,
        database=settings.redis.db,
        password=(
            settings.redis.password.get_secret_value()
            if settings.redis.password is not None
            else None
        ),
    )


def _arq_worker_settings() -> type:
    """Build the WorkerSettings class lazily so `get_settings()` is only
    called when the worker actually boots (not at import time, which would
    break the unit-test sandbox)."""

    class WorkerSettings:
        functions = [on_demand_vt_scan, file_scan, generate_sentinel_insight]
        on_startup = startup
        on_shutdown = shutdown
        max_jobs = 10
        job_timeout = 60
        redis_settings = _redis_settings_from(get_settings())

    return WorkerSettings


# Importable as `strix_api.workers.arq_tasks.WorkerSettings` once env is ready.
def __getattr__(name: str):  # noqa: D401 — module-level lazy attr
    if name == "WorkerSettings":
        return _arq_worker_settings()
    raise AttributeError(name)


# `WorkerSettings` is defined dynamically via __getattr__ above so ruff's
# static check (F822) doesn't see it — silence per-line.
__all__ = [  # noqa: F822
    "WorkerSettings",
    "file_scan",
    "generate_sentinel_insight",
    "job_channel",
    "on_demand_vt_scan",
]
