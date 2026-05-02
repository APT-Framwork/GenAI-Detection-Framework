"""Simulation runs — read-only ground-truth manifest endpoint.

Exposes the per-run `topology.json` written by `infra/scripts/lab_simulate.sh`.
Filesystem-backed (no DB): walks `infra/simulation/runs/`, picks the newest
directory by mtime, returns its parsed topology + path. 404 if no runs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/simulation", tags=["simulation"])


def _runs_dir() -> Path:
    """Resolve the runs directory.

    Order of resolution:
      1. STRIX_SIMULATION_RUNS_DIR env var (deploys / tests can override).
      2. <repo>/infra/simulation/runs (the lab_simulate.sh default).
    """
    override = os.environ.get("STRIX_SIMULATION_RUNS_DIR")
    if override:
        return Path(override)
    # this file: apps/api/src/strix_api/api/routes/simulation.py
    # parents[0]=routes, [1]=api, [2]=strix_api, [3]=src, [4]=api, [5]=apps,
    # [6]=repo root.  (streams.py uses the same parents[6] resolution.)
    return Path(__file__).resolve().parents[6] / "infra" / "simulation" / "runs"


@router.get("/runs/latest", response_model=dict)
async def get_latest_run() -> dict[str, Any]:
    runs = _runs_dir()
    if not runs.exists() or not runs.is_dir():
        raise HTTPException(status_code=404, detail="no simulation runs directory")
    candidates = [p for p in runs.iterdir() if p.is_dir()]
    if not candidates:
        raise HTTPException(status_code=404, detail="no simulation runs found")
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    topo_path = latest / "topology.json"
    if not topo_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"latest run {latest.name} has no topology.json",
        )
    try:
        topology = json.loads(topo_path.read_text())
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"topology.json malformed: {e}",
        ) from None
    return {
        "run_id": latest.name,
        "path": str(topo_path),
        "topology": topology,
    }
