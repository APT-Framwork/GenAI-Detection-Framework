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
from fastapi.middleware.cors import CORSMiddleware

from strix_api import __version__
from strix_api.api.errors import register_exception_handlers
from strix_api.api.middleware import install_middleware
from strix_api.api.routes import (
    actions,
    admin,
    alerts,
    analysis,
    auth,
    cases,
    dashboard,
    health,
    hosts,
    hunt,
    mitre,
    chains as chains_routes,
    intel,
    monitoring,
    playbooks,
    simulation,
    streams,
    threat_intel,
    topology,
    ueba,
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
            "Cyber threat detection platform. See docs/IMPLEMENTATION_PLAN.md for scope & phasing."
        ),
        openapi_url=f"{_API_PREFIX}/openapi.json",
        docs_url=f"{_API_PREFIX}/docs",
        redoc_url=f"{_API_PREFIX}/redoc",
        lifespan=_lifespan,
    )

    register_exception_handlers(app)
    install_middleware(app)

    # CORS — must be added AFTER install_middleware so it wraps OUTERMOST
    # (Starlette: last add_middleware is outermost). Browser preflights and
    # auth-failure responses both need ACAO headers, which only happens if
    # CORSMiddleware sits outside AuthMiddleware. In dev we accept the Expo
    # web origin on :8081 and the Next.js web origin on :3000.
    _settings = get_settings()
    _cors_origins = (
        ["*"]
        if _settings.env == "dev"
        else [
            "http://localhost:3000",
            "http://localhost:8081",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8081",
        ]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=_settings.env != "dev",
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-CSRF-Token"],
    )

    # OpenTelemetry — enabled when OBS_TRACING_ENABLED=true + OTLP endpoint set.
    from strix_api.observability.tracing import configure_tracing, instrument_fastapi

    settings = get_settings()
    configure_tracing(
        settings=settings.observability,
        service_name=settings.service_name,
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
    app.include_router(cases.router, prefix=_API_PREFIX)
    app.include_router(hosts.router, prefix=_API_PREFIX)
    app.include_router(mitre.router, prefix=_API_PREFIX)
    app.include_router(hunt.router, prefix=_API_PREFIX)
    app.include_router(actions.router, prefix=_API_PREFIX)
    app.include_router(ueba.router, prefix=_API_PREFIX)
    app.include_router(playbooks.router, prefix=_API_PREFIX)
    app.include_router(threat_intel.router, prefix=_API_PREFIX)
    app.include_router(intel.router, prefix=_API_PREFIX)
    app.include_router(chains_routes.router, prefix=_API_PREFIX)
    app.include_router(monitoring.router, prefix=_API_PREFIX)
    app.include_router(alerts.router, prefix=_API_PREFIX)
    app.include_router(streams.router, prefix=_API_PREFIX)
    # Phase-2 multiplexed live WebSocket — /api/v1/logs/stream.
    app.include_router(streams.logs_router, prefix=_API_PREFIX)
    app.include_router(topology.router, prefix=_API_PREFIX)
    app.include_router(simulation.router, prefix=_API_PREFIX)
    app.include_router(admin.router, prefix=_API_PREFIX)

    return app


app = create_app()
