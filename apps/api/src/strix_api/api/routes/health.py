"""Health + liveness endpoints.

- `/health` — shallow readiness probe (process is up).
- `/health/deep` — checks Postgres + Redis reachability (added in P0-3).
"""

from __future__ import annotations

from fastapi import APIRouter

from strix_api import __version__

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Liveness probe", response_model=dict[str, str])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
