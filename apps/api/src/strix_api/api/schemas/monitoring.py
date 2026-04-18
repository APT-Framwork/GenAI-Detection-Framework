"""Model-monitoring response schemas (§4.4 + P8-5)."""

from __future__ import annotations

from strix_api.api.schemas.common import StrixBase


class ModelHealth(StrixBase):
    name: str                     # 'AE' | 'VAE' | 'TRANSFORMER' | 'GNN' | 'DQN'
    version: str
    weights_sha256: str
    status: str                   # 'active' | 'degraded'
    accuracy: float | None = None
    f1: float | None = None
    p50_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    drift_kl: float | None = None
    last_health_check: str


class ModelsResponse(StrixBase):
    models: list[ModelHealth]


class CompositeAccuracyResponse(StrixBase):
    value: float
    computed_at: str


class TrendPoint(StrixBase):
    ts: str
    ae_anomaly: float
    vae_prob: float
    transformer_confidence: float
    gnn_risk: float


class ConfidenceTrendResponse(StrixBase):
    window: str
    points: list[TrendPoint]


class DriftReportItem(StrixBase):
    model: str
    samples: int
    kl_divergence: float
    above_threshold: bool


class DriftResponse(StrixBase):
    window_minutes: int
    items: list[DriftReportItem]


class RetrainResponse(StrixBase):
    accepted: bool
    message: str


__all__ = [
    "CompositeAccuracyResponse",
    "ConfidenceTrendResponse",
    "DriftReportItem",
    "DriftResponse",
    "ModelHealth",
    "ModelsResponse",
    "RetrainResponse",
    "TrendPoint",
]
