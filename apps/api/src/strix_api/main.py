"""FastAPI application factory.

Phase-0 shape:
- configures structlog + Prometheus
- mounts /metrics (separate sub-app per Prometheus asgi convention)
- registers Problem+JSON error handlers
- includes stub routers under /api/v1 so the frontend can wire hooks
- `/health` liveness for docker-compose healthchecks

Workers are separate entry points (see `strix_api.workers.*`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from strix_api import __version__
from strix_api.api.errors import register_exception_handlers
from strix_api.api.middleware import install_middleware
from strix_api.api.routes import (
    admin,
    alerts,
    analysis,
    auth,
    dashboard,
    health,
    monitoring,
    streams,
    threat_intel,
    topology,
)
from strix_api.observability import configure_logging, get_logger, metrics_app
from strix_api.settings import get_settings

_API_PREFIX = "/api/v1"


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(
        service_name=settings.service_name,
        level=settings.observability.log_level,
        json_output=settings.observability.log_json,
    )
    log = get_logger("strix_api.main")
    log.info("startup", env=settings.env, version=__version__)

    from strix_api.repositories.database import dispose_engine, init_engine
    init_engine(settings)
    try:
        yield
    finally:
        await dispose_engine()
        log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="STRIX API",
        version=__version__,
        description=(
            "Cyber threat detection platform. "
            "See docs/IMPLEMENTATION_PLAN.md for scope & phasing."
        ),
        openapi_url=f"{_API_PREFIX}/openapi.json",
        docs_url=f"{_API_PREFIX}/docs",
        redoc_url=f"{_API_PREFIX}/redoc",
        lifespan=_lifespan,
    )

    register_exception_handlers(app)
    install_middleware(app)

    # OpenTelemetry — enabled when OBS_TRACING_ENABLED=true + OTLP endpoint set.
    from strix_api.observability.tracing import configure_tracing, instrument_fastapi
    settings = get_settings()
    configure_tracing(
        settings=settings.observability, service_name=settings.service_name,
    )
    instrument_fastapi(app)

    # Liveness — NOT prefixed with /api/v1 so k8s/compose healthchecks
    # hit a stable path across API versions.
    app.include_router(health.router)

    # Prometheus scrape target.
    app.mount("/metrics", metrics_app)

    # Versioned API surface.
    app.include_router(auth.router, prefix=_API_PREFIX)
    app.include_router(dashboard.router, prefix=_API_PREFIX)
    app.include_router(analysis.router, prefix=_API_PREFIX)
    app.include_router(threat_intel.router, prefix=_API_PREFIX)
    app.include_router(monitoring.router, prefix=_API_PREFIX)
    app.include_router(alerts.router, prefix=_API_PREFIX)
    app.include_router(streams.router, prefix=_API_PREFIX)
    app.include_router(topology.router, prefix=_API_PREFIX)
    app.include_router(admin.router, prefix=_API_PREFIX)

    return app


app = create_app()
