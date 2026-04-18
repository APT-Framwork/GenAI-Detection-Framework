"""Alert list + acknowledge schemas.

Severity is derived from the joined detection row at query time (§6.3 /
§4.3 mapping). Alerts with no detection yet (ingested but not inferred)
get `"info"`.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from strix_api.api.schemas.common import (
    PaginatedResponse,
    Severity,
    StrixBase,
)

AlertSeverityFilter = Literal["all", "critical", "high", "medium", "low", "info"]


class AlertItem(StrixBase):
    alert_id: str
    occurred_at: str
    host_id: UUID | None
    chain_id: UUID | None
    rule_id: str | None
    decoder_name: str | None
    full_log: str | None
    mitre_tactics: list[str]
    mitre_techniques: list[str]
    ckc_stage: int | None
    severity: Severity
    vae_malicious_prob: float | None
    ae_anomaly_score: float | None
    acknowledged_at: str | None
    acknowledged_by: UUID | None


AlertListResponse = PaginatedResponse[AlertItem]


class AlertAcknowledgeRequest(StrixBase):
    """Body is optional — the path param carries alert_id; occurred_at is
    required because (alert_id, occurred_at) is the primary key of the
    hypertable and a single alert_id may exist at multiple timestamps on
    re-delivery edge cases.
    """

    occurred_at: str


class AlertAcknowledgeResponse(StrixBase):
    alert_id: str
    occurred_at: str
    acknowledged_at: str
    acknowledged_by: UUID
    already_acknowledged: bool
