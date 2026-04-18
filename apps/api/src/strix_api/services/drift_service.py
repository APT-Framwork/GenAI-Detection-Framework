"""Score-distribution drift detection (§12 Q7 + P8-5).

Computes a coarse KL-divergence between the live distribution of each
model's score and a frozen training-time baseline, and updates the
`strix_score_distribution_kl_divergence{model}` Prometheus gauge.

Baseline distributions are stored in `apps/models/drift_baseline.json`
(committed alongside the model checkpoints). When the file is absent we
emit `KL = 0.0` and log a warning — drift is non-fatal.

Per the plan §12 Q7 the actual retraining pipeline is post-1.0; this
service's job is JUST to surface drift via Prometheus so the Phase-8
alert rule can fire.

The KL is computed over fixed-edge histogram bins:
    AE/VAE/GNN scores → 10 bins on [0, 1]
    Transformer confidence → 10 bins on [0, 1]

Sketchy but cheap and stable across orderings of the bin labels.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.observability import (
    get_logger,
    score_distribution_kl_divergence,
)
from strix_api.settings import Settings

log = get_logger("strix_api.services.drift_service")

# Histogram bins on [0, 1] — 10 buckets of width 0.1
_BIN_EDGES: list[float] = [i / 10.0 for i in range(11)]   # 0.0, 0.1, …, 1.0
_BIN_COUNT = len(_BIN_EDGES) - 1
_EPSILON = 1e-9    # smoothing to avoid log(0) / divide-by-0


@dataclass(frozen=True)
class DriftReport:
    model: str
    samples: int
    kl_divergence: float
    above_threshold: bool


def kl_divergence(live: Sequence[float], baseline: Sequence[float]) -> float:
    """Discrete KL(live || baseline) with Laplace smoothing.

    Returns 0.0 when distributions are identical. Always non-negative.
    """
    if len(live) != len(baseline):
        raise ValueError(f"length mismatch: live={len(live)} baseline={len(baseline)}")
    s_live = sum(live) or 1.0
    s_base = sum(baseline) or 1.0
    p = [(v + _EPSILON) / (s_live + _EPSILON * len(live)) for v in live]
    q = [(v + _EPSILON) / (s_base + _EPSILON * len(baseline)) for v in baseline]
    return sum(pi * math.log(pi / qi) for pi, qi in zip(p, q, strict=True))


def histogram(values: Sequence[float]) -> list[int]:
    """Bucket-counts over `_BIN_EDGES`. Out-of-range values get clipped."""
    counts = [0] * _BIN_COUNT
    for v in values:
        if v is None or math.isnan(v):
            continue
        clipped = max(0.0, min(1.0, float(v)))
        idx = min(int(clipped / 0.1), _BIN_COUNT - 1)
        counts[idx] += 1
    return counts


_DRIFT_BASELINE_FILE = "drift_baseline.json"


def load_baseline(models_path: Path) -> dict[str, list[float]]:
    """Load `drift_baseline.json` from the models dir. Empty dict on miss."""
    p = models_path / _DRIFT_BASELINE_FILE
    if not p.exists():
        log.warning("drift_baseline_missing", path=str(p))
        return {}
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        log.warning("drift_baseline_invalid", path=str(p), exc_info=exc)
        return {}
    out: dict[str, list[float]] = {}
    for model, hist in (data.get("models") or {}).items():
        if isinstance(hist, list) and len(hist) == _BIN_COUNT:
            out[model] = [float(x) for x in hist]
        else:
            log.warning("drift_baseline_wrong_shape", model=model, len=len(hist) if hasattr(hist,'__len__') else None)
    return out


class DriftService:
    """Recomputes drift on demand from a window of `detections` rows."""

    def __init__(self, *, session: AsyncSession, settings: Settings) -> None:
        self._s = session
        self._settings = settings
        self._baseline = load_baseline(settings.models.path)
        self._threshold = 0.2   # rough — tune against P8-5 baseline alert

    async def compute_for_window(
        self, *, window_minutes: int = 60,
    ) -> list[DriftReport]:
        """Pull recent score columns, histogram them, compute KL vs baseline,
        update the Prometheus gauge per model. Returns a report per model."""

        result = await self._s.execute(
            text(
                """
                SELECT
                    ae_anomaly_score,
                    vae_malicious_prob,
                    gnn_node_risk,
                    transformer_confidence
                FROM detections
                WHERE occurred_at >= NOW() - (:window || ' minutes')::INTERVAL
                """
            ),
            {"window": str(window_minutes)},
        )
        rows = result.all()

        # Normalise AE score to [0,1] by clipping at 10 (its observation bound).
        ae_norm = [min(1.0, (r.ae_anomaly_score or 0.0) / 10.0) for r in rows]
        vae_p = [r.vae_malicious_prob for r in rows]
        gnn_r = [r.gnn_node_risk for r in rows]
        txf_c = [r.transformer_confidence for r in rows]

        reports: list[DriftReport] = []
        for model, values in (
            ("AE", ae_norm),
            ("VAE", vae_p),
            ("GNN", gnn_r),
            ("TRANSFORMER", txf_c),
        ):
            present = [v for v in values if v is not None]
            kl = 0.0
            if model in self._baseline and present:
                live_hist = histogram(present)
                kl = kl_divergence(live_hist, self._baseline[model])
            score_distribution_kl_divergence.labels(model=model).set(kl)
            reports.append(DriftReport(
                model=model,
                samples=len(present),
                kl_divergence=kl,
                above_threshold=kl > self._threshold,
            ))
        return reports


__all__ = [
    "DriftReport",
    "DriftService",
    "histogram",
    "kl_divergence",
    "load_baseline",
]
