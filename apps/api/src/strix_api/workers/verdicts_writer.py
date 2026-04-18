"""Verdicts writer (Phase 3 — full).

Consumes `VerdictMessage`s on `strix:verdicts`. Per verdict the writer:

  1. UPSERTs the host row (last_seen_at, agent_name, ip).
  2. INSERTs a skeleton alert row (FK target — Phase 5+ will fill MITRE
     fields once we wire the full RawAlert through the queue).
  3. INSERTs the detection row (one per alert, hypertable).
  4. If `chainId` is present (i.e. the alert wasn't SKIP_BENIGN):
       - opens the attack_chain row when `isFirstInChain` is true,
       - bumps `max_ckc_stage` / `max_vae_prob` / `step_count` otherwise,
       - INSERTs the dqn_action row (with `requires_approval` per
         `ISOLATE_HOST` / `BLOCK_USER_IP` semantics — §6.2).
  5. If `closeReason` is set, closes the chain in the same transaction.

All writes for a single batch go through one `session_scope()` transaction
so partial-state Postgres rows can never persist.
"""

from __future__ import annotations

import asyncio
import signal
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import structlog

from strix_api.adapters.redis_adapter import streams_client, unpack
from strix_api.api.errors import ValidationFailedError
from strix_api.core.constants import CHAIN_MAX_STEPS
from strix_api.core.enums import DqnAction
from strix_api.observability import (
    attack_chain_closed_total,
    attack_chain_opened_total,
    configure_logging,
    dqn_action_total,
    get_logger,
)
from strix_api.repositories.database import init_engine, session_scope
from strix_api.repositories.models import AttackChain
from strix_api.repositories.repos import (
    AlertRepo,
    AttackChainRepo,
    DetectionRepo,
    DqnActionRepo,
    HostRepo,
)
from strix_api.services.push_dispatcher import (
    InterventionEvent,
    PushDispatcher,
)
from strix_api.settings import Settings, get_settings
from strix_api.workers.normalizer import _host_id_for

_VERDICTS_STREAM = "strix:verdicts"
_GROUP = "strix-writer"
_FLUSH_EVERY_MS = 50
_FLUSH_MAX_ROWS = 500


class VerdictsWriter:
    def __init__(self, *, settings: Settings, redis: Any) -> None:
        self._settings = settings
        self._redis = redis
        self._stop = asyncio.Event()
        self._log = get_logger("strix_api.workers.verdicts_writer")
        self._auto_response = settings.auth.auto_response_enabled
        push_access_token = (
            settings.push.access_token.get_secret_value()
            if settings.push.access_token is not None
            else None
        )
        self._push = PushDispatcher(
            enabled=settings.push.enabled,
            expo_access_token=push_access_token,
        )

    def request_stop(self) -> None:
        self._stop.set()

    async def aclose(self) -> None:
        await self._push.close()

    async def run(self) -> None:
        await self._redis.ensure_group(_VERDICTS_STREAM, _GROUP)
        self._log.info(
            "verdicts_writer_started",
            stream=_VERDICTS_STREAM,
            group=_GROUP,
            consumer=self._redis.consumer_name,
            auto_response_enabled=self._auto_response,
        )

        pending: list[tuple[bytes, dict[str, Any]]] = []
        last_flush = asyncio.get_event_loop().time()
        flush_window = _FLUSH_EVERY_MS / 1000.0

        while not self._stop.is_set():
            time_to_flush = max(flush_window - (asyncio.get_event_loop().time() - last_flush), 0)
            block_ms = int(time_to_flush * 1000) if pending else 1000

            try:
                batch = await self._redis.read(
                    _VERDICTS_STREAM, _GROUP, count=64, block_ms=block_ms,
                )
            except Exception as exc:
                self._log.error("redis_read_failed", exc_info=exc)
                await asyncio.sleep(1)
                continue

            for _stream, entries in batch:
                for entry_id, fields in entries:
                    try:
                        payload = unpack(fields)
                    except Exception as exc:
                        self._log.warning(
                            "drop_unparseable_verdict",
                            entry_id=entry_id.decode(errors="replace"),
                            exc_info=exc,
                        )
                        await self._redis.ack(_VERDICTS_STREAM, _GROUP, entry_id)
                        continue
                    pending.append((entry_id, payload))

            now = asyncio.get_event_loop().time()
            if pending and (
                len(pending) >= _FLUSH_MAX_ROWS or (now - last_flush) >= flush_window
            ):
                await self._flush(pending)
                pending = []
                last_flush = now

        if pending:
            await self._flush(pending)
        self._log.info("verdicts_writer_stopped")

    async def _flush(self, batch: list[tuple[bytes, dict[str, Any]]]) -> None:
        ids = [eid for eid, _ in batch]
        payloads = [p for _, p in batch]

        try:
            async with session_scope() as session:
                host_repo = HostRepo(session)
                alert_repo = AlertRepo(session)
                detection_repo = DetectionRepo(session)
                chain_repo = AttackChainRepo(session)
                action_repo = DqnActionRepo(session)

                # Host upserts (deduped by agent_id)
                host_upserts: dict[str, dict[str, Any]] = {}
                for p in payloads:
                    agent_id = p.get("agentId")
                    if not agent_id:
                        continue
                    occ = _parse_iso(p["occurredAt"])
                    cur = host_upserts.get(agent_id)
                    if cur is None:
                        host_upserts[agent_id] = {
                            "host_id": _host_id_for(agent_id),
                            "agent_id": agent_id,
                            "agent_name": agent_id,
                            "ip_address": None,
                            "first_seen_at": occ,
                            "last_seen_at": occ,
                        }
                    else:
                        cur["last_seen_at"] = max(cur["last_seen_at"], occ)
                for h in host_upserts.values():
                    await host_repo.upsert_host(**h)

                # Skeleton alert rows + detection rows
                alert_rows: list[dict[str, Any]] = []
                detection_rows: list[dict[str, Any]] = []
                action_rows: list[dict[str, Any]] = []

                for p in payloads:
                    try:
                        alert_id: str = p["alertId"]
                        occurred_at = _parse_iso(p["occurredAt"])
                        agent_id = p["agentId"]
                    except KeyError as exc:
                        raise ValidationFailedError(f"verdict missing field: {exc}") from exc

                    host_id = _host_id_for(agent_id)
                    chain_id_str = p.get("chainId")
                    chain_id: UUID | None = UUID(chain_id_str) if chain_id_str else None

                    # Open new chain row if applicable.
                    if chain_id is not None and p.get("isFirstInChain"):
                        opened_at = _parse_iso(p.get("openedAt") or p["occurredAt"])
                        await chain_repo.insert(AttackChain(
                            chain_id=chain_id,
                            host_id=host_id,
                            opened_at=opened_at,
                            closed_at=None,
                            close_reason=None,
                            first_malicious_at=opened_at,
                            max_ckc_stage=int(p.get("currentCkcStage", 0)),
                            max_vae_prob=float(p.get("vaeMaliciousProb") or 0.0),
                            intervention_action_id=None,
                            step_count=0,
                            status="open",
                        ))
                        attack_chain_opened_total.inc()

                    alert_rows.append({
                        "alert_id": alert_id,
                        "host_id": host_id,
                        "chain_id": chain_id,
                        "occurred_at": occurred_at,
                        "decoder_name": None,
                        "location": None,
                        "full_log": None,
                        "rule_id": None,
                        "rule_firedtimes": None,
                        "mitre_tactics": [],
                        "mitre_techniques": [],
                        "ckc_stage": _i(p.get("currentCkcStage")),
                        "raw_jsonb": {},
                    })

                    # Detection rows always get inserted; chain_id is required by
                    # the schema, so SKIP_BENIGN verdicts use host_id as a
                    # placeholder (no FK on chain_id to attack_chains for
                    # detections — see migration 0001).
                    detection_rows.append({
                        "alert_id": alert_id,
                        "occurred_at": occurred_at,
                        "host_id": host_id,
                        "chain_id": chain_id if chain_id is not None else host_id,
                        "step_in_chain": _i(p.get("stepInChain")) or 0,
                        "ae_anomaly_score": _f(p.get("aeAnomalyScore")),
                        "ae_recon_error": _f(p.get("aeReconError")),
                        "vae_malicious_prob": _f(p.get("vaeMaliciousProb")),
                        "vae_uncertainty": _f(p.get("vaeUncertainty")),
                        "transformer_pred_ckc": _i(p.get("transformerPredCkc")),
                        "transformer_confidence": _f(p.get("transformerConfidence")),
                        "gnn_node_risk": _f(p.get("gnnNodeRisk")),
                        "gnn_neighbor_risk": _f(p.get("gnnNeighborRisk")),
                        "gnn_risk_growth": _f(p.get("gnnRiskGrowth")),
                        "state_vector": p.get("stateVector"),
                        "model_versions": p.get("modelVersions") or {},
                    })

                    # DQN action rows only for non-skipped verdicts that ran the DQN.
                    if chain_id is not None and p.get("dqnAction") is not None:
                        action_int = int(p["dqnAction"])
                        action = DqnAction(action_int)
                        requires_approval = (
                            action.requires_approval and not self._auto_response
                        )
                        applied = not requires_approval
                        action_rows.append({
                            "action_id": uuid4(),
                            "alert_id": alert_id,
                            "chain_id": chain_id,
                            "host_id": host_id,
                            "decided_at": occurred_at,
                            "action": action_int,
                            "action_name": action.name,
                            "q_values": list(p.get("qValues") or []),
                            "ckc_stage_at_decision": int(p.get("currentCkcStage", 0)),
                            "requires_approval": requires_approval,
                            "applied": applied,
                            "applied_at": occurred_at if applied else None,
                            "applied_by": None,    # auto-applied; analyst overrides come later
                            "rejected_at": None,
                            "rejected_by": None,
                        })
                        dqn_action_total.labels(action_name=action.name).inc()

                # Bulk inserts
                inserted_alerts = await alert_repo.bulk_insert(alert_rows)
                inserted_detections = await detection_repo.bulk_insert(detection_rows)
                inserted_actions = await action_repo.bulk_insert(action_rows)

                # Update / close chains. Doing this AFTER actions so we have the
                # action_id to record as `intervention_action_id` if needed.
                action_id_by_alert = {
                    row["alert_id"]: row["action_id"] for row in action_rows
                }
                for p in payloads:
                    chain_id_str = p.get("chainId")
                    if not chain_id_str:
                        continue
                    chain_id = UUID(chain_id_str)
                    occurred_at = _parse_iso(p["occurredAt"])
                    step_in_chain = _i(p.get("stepInChain")) or 0
                    await chain_repo.update_max_stage_and_prob(
                        chain_id=chain_id,
                        ckc_stage=int(p.get("currentCkcStage", 0)),
                        vae_prob=float(p.get("vaeMaliciousProb") or 0.0),
                        last_step=step_in_chain,
                    )
                    close_reason = p.get("closeReason")
                    if close_reason:
                        intervention_id = (
                            action_id_by_alert.get(p["alertId"])
                            if close_reason == "INTERVENTION"
                            else None
                        )
                        await chain_repo.close(
                            chain_id=chain_id,
                            closed_at=occurred_at,
                            close_reason=close_reason,
                            intervention_action_id=intervention_id,
                        )
                        attack_chain_closed_total.labels(close_reason=close_reason).inc()
        except Exception as exc:
            self._log.error(
                "db_flush_failed",
                count=len(batch),
                exc_info=exc,
            )
            return  # don't ack — Redis will re-deliver after PEL idle timeout

        await self._redis.ack(_VERDICTS_STREAM, _GROUP, *ids)

        # Best-effort push dispatch (M0-B6). Runs after the DB commit so
        # we never notify an operator about a row we later rolled back.
        # The dispatcher is a no-op when settings.push.enabled is False.
        interventions: list[InterventionEvent] = []
        for row in action_rows:
            if row["action"] >= DqnAction.ESCALATE.value:
                interventions.append(
                    InterventionEvent(
                        chain_id=row["chain_id"],
                        alert_id=row["alert_id"],
                        host_id=row["host_id"],
                        action_name=row["action_name"],
                        ckc_stage=row.get("ckc_stage_at_decision") or 0,
                        vae_prob=None,
                    )
                )
        if interventions:
            asyncio.create_task(
                self._push.dispatch_interventions(interventions)
            )

        self._log.info(
            "verdicts_flushed",
            count=len(batch),
            alerts_inserted=inserted_alerts,
            detections_inserted=inserted_detections,
            actions_inserted=inserted_actions,
        )


# ---- helpers --------------------------------------------------------


def _parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _f(v: Any) -> float | None:
    return None if v is None else float(v)


def _i(v: Any) -> int | None:
    return None if v is None else int(v)


# ---- entry point ---------------------------------------------------


async def _amain() -> None:
    settings = get_settings()
    configure_logging(
        service_name="strix-verdicts-writer",
        level=settings.observability.log_level,
        json_output=settings.observability.log_json,
    )
    structlog.contextvars.bind_contextvars(service="strix-verdicts-writer")

    init_engine(settings)

    async with streams_client(
        settings.redis.url, max_connections=settings.redis.max_connections,
    ) as redis:
        worker = VerdictsWriter(settings=settings, redis=redis)
        loop = asyncio.get_running_loop()
        for sig_name in ("SIGTERM", "SIGINT"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                loop.add_signal_handler(sig, worker.request_stop)
        try:
            await worker.run()
        finally:
            await worker.aclose()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()


__all__ = ["VerdictsWriter", "main"]
