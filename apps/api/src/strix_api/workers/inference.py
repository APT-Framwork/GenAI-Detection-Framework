"""Inference worker — Phase 3 (full pipeline).

Per-alert flow (matches §3.1 + §5.4):

   FeatureMessage  ─┐
                    ▼
        ┌─────────────────────┐
        │  AE  (batched 32)   │── latent (64) ── (cache for Transformer)
        │                     │── anomaly_score
        │                     │── recon_error
        └────────┬────────────┘
                 │
        ┌────────▼────────────┐  ┌────────────────────────┐
        │  VAE (batched 32)   │  │  GNN snapshot lookup   │
        │  → malicious_prob   │  │  → node_risk           │
        │  → uncertainty      │  │  → neighbor_risk       │
        └────────┬────────────┘  │  → risk_growth         │
                 │               └────────┬────────────┘
                 │   ┌────────────────────┘
                 ▼   ▼
       ┌─────────────────────────┐
       │  decide_chain_action    │  ─── SKIP_BENIGN ──▶ emit minimal verdict
       │  (§5.4 thresholds)      │
       └────────────┬────────────┘
                    ▼
       ┌─────────────────────────┐
       │  load AE-latent sequence│
       │  from Redis session     │
       └────────────┬────────────┘
                    ▼
       ┌─────────────────────────┐
       │  Transformer (per-seq)  │ → predicted_next_ckc + confidence
       └────────────┬────────────┘
                    ▼
       ┌─────────────────────────┐
       │  build 13-d state       │
       └────────────┬────────────┘
                    ▼
       ┌─────────────────────────┐
       │  DQN (batched 16)       │ → action + Q-values
       └────────────┬────────────┘
                    ▼
       ┌─────────────────────────┐
       │  update Redis session   │   (append latent, ++step,
       │                         │    last_ckc_stage, last_action)
       └────────────┬────────────┘
                    ▼
              VerdictMessage  → strix:verdicts
"""

from __future__ import annotations

import asyncio
import json as _json
import os
import signal
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import numpy as np
import structlog

from strix_api.adapters.model_loaders.autoencoder import AeBatchOutput, AutoencoderLoader
from strix_api.adapters.model_loaders.dqn import DqnDecision, DqnLoader
from strix_api.adapters.model_loaders.gnn import GnnLoader
from strix_api.adapters.model_loaders.transformer import TransformerLoader, TransformerOutput
from strix_api.adapters.model_loaders.vae import VaeBatchOutput, VaeLoader
from strix_api.adapters.preprocessing_pipeline import PreprocessingPipeline, build_pipeline
from strix_api.adapters.redis_adapter import RedisStreamsClient, streams_client, unpack
from strix_api.adapters.session_store import SessionState, SessionStore
from strix_api.api.errors import ValidationFailedError
from strix_api.core.batcher import MicroBatcher
from strix_api.core.constants import (
    CHAIN_OPEN_GNN_THRESHOLD,
    DQN_OOD_AE_RECON_THRESHOLD,
    DQN_Q_MARGIN_MIN,
    DQN_STAGE7_FORCE_ESCALATE_GNN_MIN,
    GNN_SNAPSHOT_INTERVAL_SECONDS,
)
from strix_api.core.enums.dqn import DqnAction
from strix_api.core.gnn_window import (
    GraphSnapshot,
    NodeFact,
    build_snapshot,
    filter_window,
)
from strix_api.core.messages import FeatureMessage
from strix_api.core.sequence import (
    ChainAction,
    decide_chain_action,
    decide_close_reason,
)
from strix_api.core.state_builder import ModelOutputs, build_state
from strix_api.observability import (
    configure_logging,
    get_logger,
    inference_duration_seconds,
    session_active_count,
)
from strix_api.services.live_feed import (
    STREAM_AE_CHANNEL,
    STREAM_GNN_CHANNEL,
    STREAM_RL_CHANNEL,
    STREAM_VAE_CHANNEL,
    publish_live_feed,
)
from strix_api.settings import Settings, get_settings

_VERDICTS_STREAM = "strix:verdicts"
_VERDICTS_STREAM_MAXLEN = 1_000_000

# Phase 2 fan-out — gated. Default OFF to preserve current behavior.
_STREAM_PER_MODEL_ENABLED = os.environ.get("STRIX_STREAM_PER_MODEL", "0") == "1"


async def _publish_stream(redis: Any, channel: str, payload: dict[str, Any], log: Any) -> None:
    """Best-effort per-model pubsub publish. Never raises — Postgres verdict
    write is the source of truth, this is a UI-only superset."""
    if not _STREAM_PER_MODEL_ENABLED:
        return
    try:
        body = _json.dumps(payload).encode("utf-8")
        await redis.publish(channel, body)
    except Exception as exc:  # noqa: BLE001
        log.warning("stream_publish_failed", channel=channel, exc_info=exc)


# ============================================================================
# GNN risk cache — rolling 60-min window per shard
# ============================================================================


class _GnnRiskCache:
    """Per-shard rolling window. The consumer loop appends every alert's
    NodeFact; the background task rebuilds the snapshot every 60 s and
    refreshes per-alert risks. Lookups by alert_id are O(1).
    """

    def __init__(self) -> None:
        self._facts: list[NodeFact] = []
        self._risks: dict[str, float] = {}
        # Per-agent fallback: the latest risk among that agent's scored alerts
        # in the current snapshot. Used when `lookup(alert_id)` misses because
        # the alert hasn't been included in a snapshot yet (snapshots rebuild
        # every GNN_SNAPSHOT_INTERVAL_SECONDS). Without this, fresh alerts
        # *always* score 0.0 → SKIP_BENIGN → chain never opens for new hosts.
        self._risk_by_agent: dict[str, float] = {}
        self._snapshot: GraphSnapshot | None = None
        self._lock = asyncio.Lock()

    async def append(self, fact: NodeFact) -> None:
        async with self._lock:
            self._facts.append(fact)

    async def take_window(self) -> list[NodeFact]:
        async with self._lock:
            window = filter_window(self._facts)
            self._facts = list(window)
            return window

    async def update_risks(self, snapshot: GraphSnapshot, risks: np.ndarray) -> None:
        async with self._lock:
            self._risks = dict(zip(snapshot.alert_ids, risks.tolist(), strict=True))
            self._snapshot = snapshot
            # Index agent → latest risk (snapshot is already sorted ascending
            # by occurred_at — last write wins, so we end with the freshest).
            agent_risks: dict[str, float] = {}
            # filter_window's facts list is sorted; build_snapshot preserves
            # that order, so iterating snapshot.alert_ids in order and
            # cross-referencing the in-window facts gives temporal ordering.
            facts_by_id = {f.alert_id: f for f in self._facts}
            for aid, r in zip(snapshot.alert_ids, risks.tolist(), strict=True):
                fact = facts_by_id.get(aid)
                if fact is None:
                    continue
                agent_risks[fact.agent_id] = float(r)
            self._risk_by_agent = agent_risks

    async def lookup(self, alert_id: str, agent_id: str | None = None) -> float:
        """Return the GNN risk for this alert. Falls back to the latest risk
        scored for the same agent when the alert_id isn't in the current
        snapshot — snapshots are rebuilt periodically, so a fresh alert from
        an already-known host inherits its host's most-recent risk instead of
        the fail-closed 0.0 (which would force every new alert into
        SKIP_BENIGN until the next snapshot tick). Returns 0.0 only when
        neither the alert nor the agent has been scored yet."""
        async with self._lock:
            exact = self._risks.get(alert_id)
            if exact is not None:
                return float(exact)
            if agent_id is not None:
                agent_score = self._risk_by_agent.get(agent_id)
                if agent_score is not None:
                    return float(agent_score)
            return 0.0

    async def local_degree(self, alert_id: str) -> int:
        """Undirected degree of `alert_id` in the latest snapshot, or 0 if absent.

        Used as the `affected_edges` field on the GNN stream frame so the UI
        has a coarse fan-out signal without paying the cost of shipping the
        full edge list per event.
        """
        async with self._lock:
            snap = self._snapshot
            if snap is None:
                return 0
            try:
                i = snap.alert_ids.index(alert_id)
            except ValueError:
                return 0
            edges = snap.edge_index
            return int(((edges[0] == i) | (edges[1] == i)).sum())

    async def neighbor_risk(self, alert_id: str, agent_id: str) -> tuple[float, float]:
        """`(neighbor_risk, risk_growth)` for an alert.

        - neighbor_risk = mean alert_risk on connected EXTERNAL hosts (different agent_id)
        - risk_growth   = current_global_mean - prior_global_mean
                          (computed off the latest snapshot vs the half-window prior)

        Returns (0.0, 0.0) if the alert isn't in the latest snapshot yet.
        """
        async with self._lock:
            snap = self._snapshot
            if snap is None or alert_id not in self._risks:
                return 0.0, 0.0
            risks = self._risks
            facts_by_id = {snap.alert_ids[i]: i for i in range(snap.num_nodes)}
            i = facts_by_id.get(alert_id)
            if i is None:
                return 0.0, 0.0
            # neighbors via edge_index — exclude self + same-agent
            edges = snap.edge_index
            mask = edges[0] == i
            neighbor_idxs = np.unique(edges[1][mask])
            if len(neighbor_idxs) == 0:
                neighbor_risk = 0.0
            else:
                # filter out self + same-agent
                neighbor_ids = [snap.alert_ids[j] for j in neighbor_idxs if j != i]
                neighbor_risks = [risks.get(nid, 0.0) for nid in neighbor_ids]
                neighbor_risk = float(np.mean(neighbor_risks)) if neighbor_risks else 0.0

            # Risk growth: use a coarse half-window split (last 30 min vs prior 30 min).
            # Cheap approximation; full computation lives in `gnn_window.py` later.
            half = len(snap.alert_ids) // 2
            if half == 0:
                growth = 0.0
            else:
                recent = float(np.mean([risks.get(a, 0.0) for a in snap.alert_ids[half:]]))
                prior = float(np.mean([risks.get(a, 0.0) for a in snap.alert_ids[:half]]))
                growth = recent - prior

            return neighbor_risk, growth


# ============================================================================
# Inference worker
# ============================================================================


class InferenceWorker:
    def __init__(
        self,
        *,
        settings: Settings,
        redis: RedisStreamsClient,
        session_store: SessionStore,
        pipeline: PreprocessingPipeline,
        ae: AutoencoderLoader,
        vae: VaeLoader,
        gnn: GnnLoader,
        transformer: TransformerLoader,
        dqn: DqnLoader,
    ) -> None:
        self._settings = settings
        self._redis = redis
        self._sessions = session_store
        self._pipeline = pipeline
        self._ae = ae
        self._vae = vae
        self._gnn = gnn
        self._transformer = transformer
        self._dqn = dqn
        self._stop = asyncio.Event()
        self._log = get_logger("strix_api.workers.inference")
        self._gnn_cache = _GnnRiskCache()

        cfg = settings.inference
        self._ae_batcher: MicroBatcher[np.ndarray, tuple[float, float, np.ndarray]] = MicroBatcher(
            name="ae",
            processor=self._run_ae_batch,
            max_size=cfg.ae_batch_max,
            max_wait_ms=cfg.ae_batch_wait_ms,
        )
        self._vae_batcher: MicroBatcher[np.ndarray, tuple[float, float]] = MicroBatcher(
            name="vae",
            processor=self._run_vae_batch,
            max_size=cfg.vae_batch_max,
            max_wait_ms=cfg.vae_batch_wait_ms,
        )
        self._dqn_batcher: MicroBatcher[np.ndarray, DqnDecision] = MicroBatcher(
            name="dqn",
            processor=self._run_dqn_batch,
            max_size=cfg.dqn_batch_max,
            max_wait_ms=cfg.dqn_batch_wait_ms,
        )

    def request_stop(self) -> None:
        self._stop.set()

    @property
    def shard_id(self) -> int:
        sid = self._settings.inference.shard_id
        return 0 if sid is None else sid

    @property
    def features_stream(self) -> str:
        return f"strix:features:{self.shard_id}"

    @property
    def consumer_group(self) -> str:
        return f"strix-inference-{self.shard_id}"

    async def run(self) -> None:
        await self._redis.ensure_group(self.features_stream, self.consumer_group)
        await self._ae_batcher.start()
        await self._vae_batcher.start()
        await self._dqn_batcher.start()

        gnn_task = asyncio.create_task(
            self._gnn_rebuild_loop(),
            name=f"inference-shard{self.shard_id}-gnn-rebuild",
        )

        self._log.info(
            "inference_started",
            shard=self.shard_id,
            stream=self.features_stream,
            group=self.consumer_group,
            consumer=self._redis.consumer_name,
        )

        try:
            await self._consume_loop()
        finally:
            gnn_task.cancel()
            try:
                await gnn_task
            except asyncio.CancelledError:
                pass
            await self._ae_batcher.aclose()
            await self._vae_batcher.aclose()
            await self._dqn_batcher.aclose()
            self._log.info("inference_stopped", shard=self.shard_id)

    # ---- consumer loop -----------------------------------------------

    async def _consume_loop(self) -> None:
        while not self._stop.is_set():
            try:
                batch = await self._redis.read(
                    self.features_stream,
                    self.consumer_group,
                    count=64,
                    block_ms=5_000,
                )
            except Exception as exc:
                self._log.error("redis_read_failed", exc_info=exc)
                await asyncio.sleep(1)
                continue

            if not batch:
                await self._redis.sample_depth(self.features_stream)
                continue

            tasks: list[asyncio.Task[Any]] = []
            ids: list[bytes] = []
            for _stream, entries in batch:
                for entry_id, fields in entries:
                    ids.append(entry_id)
                    tasks.append(asyncio.create_task(self._handle_one(entry_id, fields)))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for entry_id, result in zip(ids, results, strict=True):
                if isinstance(result, BaseException):
                    self._log.error(
                        "handle_one_failed",
                        entry_id=entry_id.decode(errors="replace"),
                        exc_info=result,
                    )

            try:
                await self._redis.ack(self.features_stream, self.consumer_group, *ids)
            except Exception as exc:
                self._log.error("xack_failed", count=len(ids), exc_info=exc)

    async def _handle_one(self, entry_id: bytes, fields: dict[bytes, bytes]) -> None:
        try:
            payload = unpack(fields)
            msg = FeatureMessage.model_validate(payload)
        except Exception as exc:
            raise ValidationFailedError(f"malformed feature message: {exc}") from exc

        vec = np.asarray(msg.feature_vector, dtype=np.float32)
        occurred_at = _parse_iso(msg.occurred_at)

        # Always run AE + VAE concurrently. Append to GNN window for next snapshot.
        ae_task = asyncio.create_task(self._ae_batcher.submit(vec))
        vae_task = asyncio.create_task(self._vae_batcher.submit(vec))

        gnn_perm_vec = self._pipeline.transform_for_gnn(vec)
        await self._gnn_cache.append(
            NodeFact(
                alert_id=msg.alert_id,
                agent_id=msg.agent_id,
                occurred_at=occurred_at,
                srcuser=msg.srcuser,
                srcip=msg.srcip,
                features_gnn_order=gnn_perm_vec,
            )
        )

        try:
            (anomaly, recon_err, latent), (mal_prob, uncertainty) = await asyncio.gather(
                ae_task,
                vae_task,
            )
        except Exception as exc:
            self._log.error("ae_or_vae_failed", alert_id=msg.alert_id, exc_info=exc)
            return

        # Phase 2 multiplex fan-out (per-event AE + VAE). Strict superset —
        # never blocks on failure (see `_publish_stream`).
        if _STREAM_PER_MODEL_ENABLED:
            await _publish_stream(
                self._redis.client,
                STREAM_AE_CHANNEL,
                {
                    "alert_id": msg.alert_id,
                    "host_id": msg.agent_id,
                    "srcip": msg.srcip,
                    "recon_error": float(recon_err),
                    "anomaly_score": float(anomaly),
                    # Carry MITRE tactics so streams.py derive_label can mark
                    # ground truth even when srcip isn't the attacker IP
                    # (Caldera attacks run locally on the victim).
                    "mitre_tactics": msg.mitre_tactics,
                },
                self._log,
            )
            await _publish_stream(
                self._redis.client,
                STREAM_VAE_CHANNEL,
                {
                    "alert_id": msg.alert_id,
                    "host_id": msg.agent_id,
                    "srcip": msg.srcip,
                    "malicious_prob": float(mal_prob),
                    "uncertainty": float(uncertainty),
                    "mitre_tactics": msg.mitre_tactics,
                },
                self._log,
            )

        # GNN risk drives the chain-open gate (see core.sequence docstring on
        # the AE/VAE inversion finding). Look it up here so the decision can
        # use it; lookup falls back to the agent's most-recent scored risk
        # when this exact alert_id isn't in the current snapshot (snapshots
        # rebuild every 30 s, so without the agent fallback every fresh
        # alert would force SKIP_BENIGN). Returns 0.0 only when neither the
        # alert nor the agent has ever been scored — true cold start.
        gnn_node_risk = await self._gnn_cache.lookup(msg.alert_id, msg.agent_id)

        # MITRE-tagged events bypass the GNN cold-start. If Wazuh has
        # already classified the alert into a CKC stage (>0) via its rule
        # set, that is itself ground truth for "this is an attack tactic"
        # — the GNN was added to catch *unlabelled* anomalies, not to
        # second-guess explicit MITRE attribution. Without this hybrid
        # gate, fresh agents with rule 80789–dominated traffic never open
        # chains in real time (observed: +0 dqn_actions on a 443 s run
        # where 1,990/2,000 events were rule 80789 with no MITRE tag and
        # only ~10 were rule 100xxx STRIX-tagged attack tactics).
        if msg.current_ckc_stage > 0 and gnn_node_risk < CHAIN_OPEN_GNN_THRESHOLD:
            gnn_node_risk = float(CHAIN_OPEN_GNN_THRESHOLD)

        # Pull the current session (or None) and decide what to do.
        session = await self._sessions.get_session(msg.agent_id)
        decision = decide_chain_action(
            session=session,
            ae_anomaly=float(anomaly),
            vae_malicious_prob=float(mal_prob),
            gnn_node_risk=float(gnn_node_risk),
            occurred_at=occurred_at,
        )

        if decision.action is ChainAction.SKIP_BENIGN:
            # Multiplex fan-out for SKIP_BENIGN: still emit GNN + RL frames so
            # the live WS shows fan-out for benign traffic too. We don't run
            # the transformer / DQN here — use cached GNN risk (0 if absent)
            # and a no-op RL action. Cheap and keeps the dashboard live even
            # when the chain decider classifies traffic as benign.
            if _STREAM_PER_MODEL_ENABLED:
                # Reuse `gnn_node_risk` already looked up above (decision input).
                gnn_neighbor_risk_skip, gnn_risk_growth_skip = (
                    await self._gnn_cache.neighbor_risk(msg.alert_id, msg.agent_id)
                )
                affected_edges_skip = await self._gnn_cache.local_degree(msg.alert_id)
                await _publish_stream(
                    self._redis.client,
                    STREAM_GNN_CHANNEL,
                    {
                        "alert_id": msg.alert_id,
                        "host_id": msg.agent_id,
                        "srcip": msg.srcip,
                        "node_risk": float(gnn_node_risk),
                        "neighbor_risk": float(gnn_neighbor_risk_skip),
                        "risk_growth": float(gnn_risk_growth_skip),
                        "affected_edges": affected_edges_skip,
                        "mitre_tactics": msg.mitre_tactics,
                    },
                    self._log,
                )
                # SKIP_BENIGN path — DQN doesn't run, so action=NO_OP, but
                # we still want the dashboard to reflect the MITRE-tagged
                # stage of the event (a benign-classified event from a
                # Persistence rule should still show Installation in the
                # kill-chain heatmap, otherwise stages 4-7 stay empty
                # whenever the chain decider rules SKIP_BENIGN).
                await _publish_stream(
                    self._redis.client,
                    STREAM_RL_CHANNEL,
                    {
                        "alert_id": msg.alert_id,
                        "host_id": msg.agent_id,
                        "srcip": msg.srcip,
                        "action": 0,
                        "action_name": "NO_OP",
                        "q_values": [],
                        "ckc_stage": int(msg.current_ckc_stage),
                        "transformer_pred_ckc": 0,
                        "mitre_ckc_stage": int(msg.current_ckc_stage),
                        "chain_max_ckc_stage": int(msg.current_ckc_stage),
                        "confidence": 0.0,
                        "mitre_tactics": msg.mitre_tactics,
                        "mitre_techniques": msg.mitre_techniques,
                    },
                    self._log,
                )
            await self._emit_skip_verdict(
                msg=msg,
                anomaly=anomaly,
                recon_err=recon_err,
                latent=latent,
                mal_prob=mal_prob,
                uncertainty=uncertainty,
            )
            return

        if decision.action is ChainAction.OPEN_NEW:
            await self._sessions.open_session(
                agent_id=msg.agent_id,
                chain_id=decision.chain_id,  # type: ignore[arg-type]
                opened_at=occurred_at,
                first_malicious_at=occurred_at,
            )
            session = SessionState(
                chain_id=decision.chain_id,  # type: ignore[arg-type]
                episode_start_at=occurred_at,
                opened_at=occurred_at,
                last_seen_at=occurred_at,
                step_count=0,
                last_ckc_stage=None,
                last_action=None,
                max_vae_prob=0.0,
                max_ckc_stage=0,
            )

        assert session is not None
        assert decision.chain_id is not None

        # Build the AE latent sequence for the Transformer: oldest→newest,
        # current latent appended.
        prior_latents = await self._sessions.get_latents(msg.agent_id)  # newest-first
        sequence = list(reversed(prior_latents)) + [latent]
        sequence_arr = np.stack(sequence, axis=0).astype(np.float32)

        transformer_out: TransformerOutput = await asyncio.to_thread(
            self._transformer.predict_sequence,
            sequence_arr,
        )

        # `gnn_node_risk` was looked up before the chain decision (above).
        # Neighbor + risk-growth still need a fresh lookup here.
        gnn_neighbor_risk, gnn_risk_growth = await self._gnn_cache.neighbor_risk(
            msg.alert_id,
            msg.agent_id,
        )

        # Build 13-d state vector + DQN.
        state = build_state(
            outputs=ModelOutputs(
                ae_anomaly_score=float(anomaly),
                ae_recon_error=float(recon_err),
                vae_malicious_prob=float(mal_prob),
                vae_uncertainty=float(uncertainty),
                transformer_pred_ckc=int(transformer_out.pred_ckc),
                transformer_confidence=float(transformer_out.confidence),
                current_ckc_stage=int(msg.current_ckc_stage),
                gnn_node_risk=float(gnn_node_risk),
                gnn_neighbor_risk=float(gnn_neighbor_risk),
                gnn_risk_growth=float(gnn_risk_growth),
            ),
            occurred_at=occurred_at,
            episode_start_at=session.episode_start_at,
            last_event_at=session.last_seen_at if session.step_count > 0 else None,
            sequence_length_so_far=session.step_count,
        )

        dqn_decision: DqnDecision = await self._dqn_batcher.submit(state)

        # ---- Lab-distribution decision gates --------------------------
        # See core/constants.py "DQN decision gates" section for the
        # full diagnosis. These three gates correct two failure modes
        # observed in the wild without retraining the DQN. The Q-values
        # we emit downstream are still the raw model outputs (so the
        # dashboard shows the actual policy); only the chosen `action`
        # is overridden when a gate fires. Each override is logged with
        # `gate_reason` for forensics.
        original_action = dqn_decision.action
        gate_reason: str | None = None
        gated_action = original_action

        # Priority 1 — stage 7 force-escalate. The trained policy
        # reliably picks LOW_ALERT here because Q(ESCALATE | stage=7)
        # is negative; SOC-wise that's wrong.
        if (
            int(msg.current_ckc_stage) >= 7
            and float(gnn_node_risk) >= DQN_STAGE7_FORCE_ESCALATE_GNN_MIN
            and original_action.value < DqnAction.ESCALATE.value
        ):
            gated_action = DqnAction.ESCALATE
            gate_reason = "stage7_force_escalate"

        # Priority 2 — OOD gate. AE recon explosion saturates the VAE
        # calibrator on lab data; the DQN reads "VAE near 1.0" as
        # "attack" and ISOLATEs benign noise. Override on GNN-only.
        elif float(recon_err) > DQN_OOD_AE_RECON_THRESHOLD:
            if float(gnn_node_risk) >= CHAIN_OPEN_GNN_THRESHOLD:
                gated_action = DqnAction.ESCALATE
                gate_reason = "ood_gnn_says_attack"
            else:
                gated_action = DqnAction.MONITOR
                gate_reason = "ood_gnn_says_benign"

        # Priority 3 — Q-margin abstention. If max(Q) − second(Q) is
        # below the configured floor, the choice is essentially noise.
        elif original_action.value >= DqnAction.ESCALATE.value:
            qs = np.asarray(dqn_decision.q_values, dtype=np.float64)
            chosen_q = float(qs[int(original_action.value)])
            qs_no_chosen = np.delete(qs, int(original_action.value))
            second_q = float(qs_no_chosen.max()) if qs_no_chosen.size else chosen_q
            if (chosen_q - second_q) < DQN_Q_MARGIN_MIN:
                gated_action = DqnAction.MONITOR
                gate_reason = "q_margin_abstain"

        if gate_reason is not None:
            self._log.info(
                "dqn_action_gated",
                alert_id=msg.alert_id,
                host_id=msg.agent_id,
                ckc_stage=int(msg.current_ckc_stage),
                ae_recon_error=float(recon_err),
                vae_malicious_prob=float(mal_prob),
                gnn_node_risk=float(gnn_node_risk),
                original_action=original_action.name,
                gated_action=gated_action.name,
                gate_reason=gate_reason,
            )
            # Replace decision in-place. Q-values stay intact for the UI.
            dqn_decision = DqnDecision(action=gated_action, q_values=dqn_decision.q_values)

        # Phase 2 multiplex fan-out (GNN + RL). `affected_edges` is a coarse
        # count (undirected degree of this node in the latest snapshot) — full
        # edge list lives in `gnn_graph_snapshots`.
        if _STREAM_PER_MODEL_ENABLED:
            affected_edges = await self._gnn_cache.local_degree(msg.alert_id)
            await _publish_stream(
                self._redis.client,
                STREAM_GNN_CHANNEL,
                {
                    "alert_id": msg.alert_id,
                    "host_id": msg.agent_id,
                    "srcip": msg.srcip,
                    "node_risk": float(gnn_node_risk),
                    "neighbor_risk": float(gnn_neighbor_risk),
                    "risk_growth": float(gnn_risk_growth),
                    "affected_edges": affected_edges,
                    "mitre_tactics": msg.mitre_tactics,
                },
                self._log,
            )
            # Three stage signals on the RL frame so the dashboard can show
            # the deepest the chain has actually walked, instead of just the
            # Transformer's per-event prediction (which is OOD on lab data
            # and collapses to ~Delivery for most events even when the
            # underlying Wazuh tactic is later in the kill chain):
            #   * `transformer_pred_ckc` — Transformer's classification.
            #   * `mitre_ckc_stage`      — Wazuh-tagged MITRE→CKC mapping
            #     for THIS event (`msg.current_ckc_stage`).
            #   * `chain_max_ckc_stage`  — running max for the chain
            #     (deepest stage *any* prior event in this session reached).
            # `ckc_stage` itself is set to the max of the three so the
            # frontend's existing readers see the sane progression.
            chain_max_ckc = max(
                int(session.max_ckc_stage if session is not None else 0),
                int(msg.current_ckc_stage),
            )
            display_ckc = max(
                int(transformer_out.pred_ckc),
                int(msg.current_ckc_stage),
                chain_max_ckc,
            )
            await _publish_stream(
                self._redis.client,
                STREAM_RL_CHANNEL,
                {
                    "alert_id": msg.alert_id,
                    "host_id": msg.agent_id,
                    "srcip": msg.srcip,
                    "action": int(dqn_decision.action),
                    "action_name": dqn_decision.action.name,
                    "q_values": dqn_decision.q_values.tolist(),
                    "ckc_stage": display_ckc,
                    "transformer_pred_ckc": int(transformer_out.pred_ckc),
                    "mitre_ckc_stage": int(msg.current_ckc_stage),
                    "chain_max_ckc_stage": chain_max_ckc,
                    "confidence": float(transformer_out.confidence),
                    "mitre_tactics": msg.mitre_tactics,
                    "mitre_techniques": msg.mitre_techniques,
                },
                self._log,
            )

        # Persist to Redis BEFORE emitting the verdict so a re-delivered
        # verdict sees the updated session state.
        new_step_count = await self._sessions.append_step(
            agent_id=msg.agent_id,
            latent=latent,
            ckc_stage=int(msg.current_ckc_stage),
            action=int(dqn_decision.action),
            vae_prob=float(mal_prob),
            seen_at=occurred_at,
        )

        # Decide whether THIS step closes the chain (the verdict-writer reads
        # `closeReason` and updates the attack_chain row accordingly).
        close_reason = decide_close_reason(
            session=session,
            new_step_count=new_step_count,
            new_action=dqn_decision.action,
            occurred_at=occurred_at,
        )
        if close_reason is not None:
            # Drop the Redis session immediately so a follow-up alert opens
            # a fresh chain rather than continuing this one.
            await self._sessions.close_session(msg.agent_id)

        verdict = {
            "alertId": msg.alert_id,
            "chainId": str(decision.chain_id),
            "stepInChain": new_step_count - 1,
            "occurredAt": msg.occurred_at,
            "agentId": msg.agent_id,
            "currentCkcStage": int(msg.current_ckc_stage),
            "isFirstInChain": decision.is_first_in_chain,
            "closeReason": close_reason.value if close_reason is not None else None,
            "openedAt": session.opened_at.isoformat(),
            "aeAnomalyScore": float(anomaly),
            "aeReconError": float(recon_err),
            "aeLatent": latent.tolist(),
            "vaeMaliciousProb": float(mal_prob),
            "vaeUncertainty": float(uncertainty),
            "transformerPredCkc": int(transformer_out.pred_ckc),
            "transformerConfidence": float(transformer_out.confidence),
            "gnnNodeRisk": float(gnn_node_risk),
            "gnnNeighborRisk": float(gnn_neighbor_risk),
            "gnnRiskGrowth": float(gnn_risk_growth),
            "stateVector": state.tolist(),
            "dqnAction": int(dqn_decision.action),
            "dqnActionName": dqn_decision.action.name,
            "qValues": dqn_decision.q_values.tolist(),
            "fullLog": msg.full_log,
            "decoderName": msg.decoder_name,
            "location": msg.location,
            "ruleId": msg.rule_id,
            "ruleFiredtimes": msg.rule_firedtimes,
            "mitreTactics": list(msg.mitre_tactics),
            "mitreTechniques": list(msg.mitre_techniques),
            "modelVersions": {
                "ae": self._ae.version,
                "vae": self._vae.version,
                "transformer": self._transformer.version,
                "gnn": self._gnn.version,
                "dqn": self._dqn.version,
            },
        }
        await self._redis.publish(
            _VERDICTS_STREAM,
            verdict,
            maxlen=_VERDICTS_STREAM_MAXLEN,
        )
        # Fan out to SSE subscribers. Never let a pubsub failure block ingestion.
        try:
            verdict["mitreTechniques"] = list(msg.mitre_techniques)
            await publish_live_feed(self._redis.client, verdict)
        except Exception as exc:  # noqa: BLE001
            self._log.warning("sse_publish_failed", alert_id=msg.alert_id, exc_info=exc)

    # ---- minimal verdict for skipped (benign-only) alerts ------------

    async def _emit_skip_verdict(
        self,
        *,
        msg: FeatureMessage,
        anomaly: float,
        recon_err: float,
        latent: np.ndarray,
        mal_prob: float,
        uncertainty: float,
    ) -> None:
        """Write a verdict that records AE+VAE scores but no chain decision.

        These rows feed the Live Feed and Global Risk components but never
        join an attack_chain. The verdicts-writer treats `chainId == None`
        as "no chain row to upsert".
        """
        verdict = {
            "alertId": msg.alert_id,
            "chainId": None,
            "stepInChain": None,
            "occurredAt": msg.occurred_at,
            "agentId": msg.agent_id,
            "currentCkcStage": int(msg.current_ckc_stage),
            "isFirstInChain": False,
            "closeReason": None,
            "openedAt": None,
            "aeAnomalyScore": float(anomaly),
            "aeReconError": float(recon_err),
            "aeLatent": latent.tolist(),
            "vaeMaliciousProb": float(mal_prob),
            "vaeUncertainty": float(uncertainty),
            "transformerPredCkc": None,
            "transformerConfidence": None,
            "gnnNodeRisk": None,
            "gnnNeighborRisk": None,
            "gnnRiskGrowth": None,
            "stateVector": None,
            "dqnAction": None,
            "dqnActionName": None,
            "qValues": None,
            "fullLog": msg.full_log,
            "decoderName": msg.decoder_name,
            "location": msg.location,
            "ruleId": msg.rule_id,
            "ruleFiredtimes": msg.rule_firedtimes,
            "mitreTactics": list(msg.mitre_tactics),
            "mitreTechniques": list(msg.mitre_techniques),
            "modelVersions": {
                "ae": self._ae.version,
                "vae": self._vae.version,
            },
        }
        await self._redis.publish(
            _VERDICTS_STREAM,
            verdict,
            maxlen=_VERDICTS_STREAM_MAXLEN,
        )
        # Skipped (benign-only) alerts still appear in the live feed —
        # they're useful for the SOC to see baseline activity.
        try:
            verdict["mitreTechniques"] = list(msg.mitre_techniques)
            await publish_live_feed(self._redis.client, verdict)
        except Exception as exc:  # noqa: BLE001
            self._log.warning("sse_publish_failed", alert_id=msg.alert_id, exc_info=exc)

    # ---- batched processors ------------------------------------------

    async def _run_ae_batch(self, items: list[np.ndarray]) -> list[tuple[float, float, np.ndarray]]:
        x = np.stack(items, axis=0)
        out: AeBatchOutput = await asyncio.to_thread(self._ae.batch_forward, x)
        return [
            (float(out.anomaly_score[i]), float(out.recon_error[i]), out.latents[i])
            for i in range(out.batch_size)
        ]

    async def _run_vae_batch(self, items: list[np.ndarray]) -> list[tuple[float, float]]:
        x = np.stack(items, axis=0)
        out: VaeBatchOutput = await asyncio.to_thread(self._vae.batch_forward, x)
        return [
            (float(out.malicious_prob[i]), float(out.uncertainty[i])) for i in range(len(items))
        ]

    async def _run_dqn_batch(self, items: list[np.ndarray]) -> list[DqnDecision]:
        x = np.stack(items, axis=0)
        return await asyncio.to_thread(self._dqn.decide_batch, x)

    # ---- GNN background loop -----------------------------------------

    async def _gnn_rebuild_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.sleep(GNN_SNAPSHOT_INTERVAL_SECONDS)
                facts = await self._gnn_cache.take_window()
                session_active_count.set(len(facts))
                if not facts:
                    continue
                snap = build_snapshot(facts)
                t0 = asyncio.get_running_loop().time()
                out = await asyncio.to_thread(
                    self._gnn.score_graph,
                    snap.x,
                    snap.edge_index,
                )
                inference_duration_seconds.labels(model="gnn").observe(
                    asyncio.get_running_loop().time() - t0
                )
                await self._gnn_cache.update_risks(snap, out.risks)
                self._log.info(
                    "gnn_snapshot_refreshed",
                    nodes=snap.num_nodes,
                    edges=snap.num_edges,
                    edge_counts=snap.edge_counts,
                )
                # Persist for the chain Graph-Evolution panel.
                # Keep the payload small: alert_ids + scored risks + edge list,
                # not the full feature matrix.
                try:
                    await self._persist_snapshot(snap, out.risks)
                except Exception as exc:  # noqa: BLE001
                    self._log.warning("gnn_snapshot_persist_failed", exc_info=exc)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._log.error("gnn_snapshot_failed", exc_info=exc)

    async def _persist_snapshot(self, snap: Any, risks: Any) -> None:
        """Insert one row into gnn_graph_snapshots. Best-effort — failures
        are logged but don't stop the inference loop."""
        from datetime import datetime

        from sqlalchemy import text

        from strix_api.repositories.database import session_scope

        # Edges as {"source": s, "target": t} dicts to match the API schema.
        edge_pairs = []
        try:
            ei = snap.edge_index
            for k in range(ei.shape[1]):
                edge_pairs.append(
                    {
                        "source": int(ei[0, k]),
                        "target": int(ei[1, k]),
                    }
                )
        except Exception:
            pass

        nodes_payload = [
            {"alertId": aid, "risk": float(risks[i]) if i < len(risks) else None}
            for i, aid in enumerate(snap.alert_ids)
        ]
        async with session_scope() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO gnn_graph_snapshots
                        (snapshot_id, shard_id, taken_at,
                         node_count, edge_count, nodes, edges)
                    VALUES
                        (:sid, :shard, :ts, :nc, :ec,
                         CAST(:nodes AS JSONB), CAST(:edges AS JSONB))
                    """
                ),
                {
                    "sid": uuid4(),
                    "shard": int(self._settings.inference.shard_id or 0),
                    "ts": datetime.now(UTC),
                    "nc": snap.num_nodes,
                    "ec": snap.num_edges,
                    "nodes": __import__("json").dumps(nodes_payload),
                    "edges": __import__("json").dumps(edge_pairs),
                },
            )


# ============================================================================
# helpers + entry point
# ============================================================================


def _parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


async def _amain() -> None:
    settings = get_settings()
    configure_logging(
        service_name="strix-inference",
        level=settings.observability.log_level,
        json_output=settings.observability.log_json,
    )
    structlog.contextvars.bind_contextvars(
        service="strix-inference",
        shard=str(settings.inference.shard_id or 0),
    )

    # Init the DB pool so _persist_snapshot has session_scope available.
    from strix_api.repositories.database import init_engine

    init_engine(settings)

    pipeline = build_pipeline(settings.models.path, warmup=True)

    from strix_api.adapters.model_registry import load_registry

    state = load_registry(
        settings.models.registry_path,
        settings.models.path,
        verify_checksums=settings.models.verify_checksums,
    )
    ae = AutoencoderLoader.load(state.models["ae"].file, version=state.models["ae"].version)
    vae = VaeLoader.load(
        state.models["vae"].file,
        calibrator=pipeline.calibrators.active,
        version=state.models["vae"].version,
    )
    gnn = GnnLoader.load(
        state.models["gnn"].file,
        metadata=pipeline.gnn,
        version=state.models["gnn"].version,
    )
    transformer = TransformerLoader.load(
        state.models["transformer"].file,
        version=state.models["transformer"].version,
    )
    dqn = DqnLoader.load(
        state.models["dqn"].file,
        version=state.models["dqn"].version,
    )

    async with streams_client(
        settings.redis.url,
        max_connections=settings.redis.max_connections,
    ) as redis:
        sessions = SessionStore(redis.client)
        worker = InferenceWorker(
            settings=settings,
            redis=redis,
            session_store=sessions,
            pipeline=pipeline,
            ae=ae,
            vae=vae,
            gnn=gnn,
            transformer=transformer,
            dqn=dqn,
        )
        loop = asyncio.get_running_loop()
        for sig_name in ("SIGTERM", "SIGINT"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                loop.add_signal_handler(sig, worker.request_stop)
        await worker.run()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()


__all__ = ["InferenceWorker", "main"]
