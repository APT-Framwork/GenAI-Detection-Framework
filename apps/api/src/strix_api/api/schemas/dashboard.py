"""Dashboard-tab response schemas (§4.1).

Phase 2 endpoints return empty-but-valid aggregates so the frontend can
wire its hooks; Phase 4 fills with real continuous-aggregate queries.
"""

from __future__ import annotations

from pydantic import Field

from strix_api.api.schemas.common import StrixBase, WindowLiteral


class StageBucket(StrixBase):
    ckc_stage: int
    ckc_name: str
    count: int
    percent: float


class AttackVectorResponse(StrixBase):
    window: WindowLiteral
    total_alerts: int
    stages: list[StageBucket]


class GlobalRiskComponents(StrixBase):
    vae_mean_prob: float
    gnn_max_node_risk: float
    anomaly_rate: float
    risk_growth: float


class GlobalRiskTrendPoint(StrixBase):
    ts: str
    value: float


class GlobalRiskResponse(StrixBase):
    window: WindowLiteral
    global_risk: float
    components: GlobalRiskComponents
    delta_1h: float
    trend: list[GlobalRiskTrendPoint]


class VictimNode(StrixBase):
    host_id: str
    host_name: str
    severity: str  # uses the Severity literal — but kept str for OpenAPI compactness
    infected: bool
    risk_score: float


class VictimEdge(StrixBase):
    # `from` is reserved in Python; alias makes it `from` on the wire.
    from_: str = Field(alias="from")
    to: str
    edge_type: str
    shared_indicator: str | None = None


class VictimGraphResponse(StrixBase):
    window: WindowLiteral
    nodes: list[VictimNode]
    edges: list[VictimEdge]


class SentinelInsightAction(StrixBase):
    label: str
    rationale: str


class SentinelInsightResponse(StrixBase):
    generated_at: str
    model_version: str
    insight: str
    recommended_actions: list[SentinelInsightAction]
    confidence: float
    stale: bool = False


__all__ = [
    "AttackVectorResponse",
    "GlobalRiskComponents",
    "GlobalRiskResponse",
    "GlobalRiskTrendPoint",
    "SentinelInsightAction",
    "SentinelInsightResponse",
    "StageBucket",
    "VictimEdge",
    "VictimGraphResponse",
    "VictimNode",
]
