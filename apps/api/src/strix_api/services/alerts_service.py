"""Alert list + acknowledge service.

Thin orchestrator over `AlertRepo` that (a) maps internal DB rows to the
wire schema and (b) derives the string severity from the joined VAE
probability using the §6.3 thresholds — the DB doesn't persist severity
because it's a pure function of `vae_malicious_prob` and can change if
thresholds are recalibrated (P2-9).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from strix_api.api.schemas.alerts import (
    AlertAcknowledgeResponse,
    AlertItem,
    AlertListResponse,
)
from strix_api.api.schemas.common import Page
from strix_api.repositories.repos import AlertRepo


SeverityStr = Literal["critical", "high", "medium", "low", "info"]


def severity_from_vae_prob(prob: float | None) -> SeverityStr:
    """Map VAE malicious probability to the 5-level severity bucket.

    Thresholds mirror §6.3 + the infection rule constant 0.7. Alerts
    without a detection row yet (pre-inference, or ingestion-only path)
    get `"info"` rather than silently dropping.
    """
    if prob is None:
        return "info"
    if prob >= 0.9:
        return "critical"
    if prob >= 0.7:
        return "high"
    if prob >= 0.5:
        return "medium"
    if prob >= 0.3:
        return "low"
    return "info"


def _row_to_item(row: dict[str, Any]) -> AlertItem:
    occurred_at: datetime = row["occurred_at"]
    ack_at: datetime | None = row.get("acknowledged_at")
    return AlertItem(
        alert_id=row["alert_id"],
        occurred_at=occurred_at.isoformat(),
        host_id=row.get("host_id"),
        chain_id=row.get("chain_id"),
        rule_id=row.get("rule_id"),
        decoder_name=row.get("decoder_name"),
        full_log=row.get("full_log"),
        mitre_tactics=list(row.get("mitre_tactics") or []),
        mitre_techniques=list(row.get("mitre_techniques") or []),
        ckc_stage=row.get("ckc_stage"),
        severity=severity_from_vae_prob(row.get("vae_malicious_prob")),
        vae_malicious_prob=row.get("vae_malicious_prob"),
        ae_anomaly_score=row.get("ae_anomaly_score"),
        acknowledged_at=ack_at.isoformat() if ack_at else None,
        acknowledged_by=row.get("acknowledged_by"),
    )


def _min_prob_for_severity(
    sev: Literal["all", "critical", "high", "medium", "low", "info"],
) -> float | None:
    """Translate a severity filter to the minimum VAE probability that
    qualifies. Returns None for "all"/"info" (no floor applied).
    """
    if sev == "critical":
        return 0.9
    if sev == "high":
        return 0.7
    if sev == "medium":
        return 0.5
    if sev == "low":
        return 0.3
    return None


class AlertsService:
    def __init__(self, repo: AlertRepo) -> None:
        self._repo = repo

    async def list_alerts(
        self,
        *,
        cursor: str | None = None,
        limit: int = 50,
        severity: Literal[
            "all", "critical", "high", "medium", "low", "info"
        ] = "all",
        only_unacknowledged: bool = False,
    ) -> AlertListResponse:
        before: datetime | None = None
        if cursor:
            try:
                before = datetime.fromisoformat(cursor)
            except ValueError:
                before = None

        # Ask for 1 more than `limit` so we can set has_more without a
        # second roundtrip.
        rows = await self._repo.list_page(
            limit=limit + 1,
            before=before,
            min_vae_prob=_min_prob_for_severity(severity),
            only_unacknowledged=only_unacknowledged,
        )
        has_more = len(rows) > limit
        rows = rows[:limit]

        items = [_row_to_item(r) for r in rows]
        next_cursor = (
            rows[-1]["occurred_at"].isoformat() if rows and has_more else None
        )
        return AlertListResponse(
            items=items,
            page=Page(cursor=next_cursor, has_more=has_more),
        )

    async def acknowledge(
        self, *, alert_id: str, occurred_at: str, user_id: UUID,
    ) -> AlertAcknowledgeResponse | None:
        try:
            ts = datetime.fromisoformat(occurred_at)
        except ValueError:
            return None

        now = datetime.now(timezone.utc)
        applied = await self._repo.acknowledge(
            alert_id=alert_id,
            occurred_at=ts,
            user_id=user_id,
            now=now,
        )

        # Fetch current state to return the authoritative ack timestamp
        # (the row may have been previously ack'd — we still want to
        # return 200 with already_acknowledged=True rather than 404).
        row = await self._repo.get(alert_id=alert_id, occurred_at=ts)
        if row is None:
            return None

        actual_ack_at = row.acknowledged_at or now
        actual_ack_by = row.acknowledged_by or user_id
        return AlertAcknowledgeResponse(
            alert_id=row.alert_id,
            occurred_at=row.occurred_at.isoformat(),
            acknowledged_at=actual_ack_at.isoformat(),
            acknowledged_by=actual_ack_by,
            already_acknowledged=not applied,
        )
