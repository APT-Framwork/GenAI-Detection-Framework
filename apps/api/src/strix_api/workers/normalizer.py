"""Normalizer worker — Phase 1 critical path.

Consumes raw Wazuh alerts from `strix:alerts:raw` (§6.4), parses them
through `WazuhAlertAdapter`, runs the `PreprocessingPipeline` to produce
a 55-dim feature vector, and publishes a `FeatureMessage` to the sharded
`strix:features:{shard}` stream so downstream inference workers see every
alert from one host on the same shard (§5.2 sharding strategy).

Design points honored from the plan:
- Sharding by `agent_id` via consistent hash → `int(shard_id) % num_shards`.
- MessagePack on the wire (§6.5).
- Per-alert span metrics (§8.2 `strix_normalizer_duration_seconds`).
- Torch inference runs in a thread via `asyncio.to_thread()` (§7.5) so the
  event loop stays free for Redis I/O.
- Graceful shutdown on SIGTERM/SIGINT.

Run:
    python -m strix_api.workers.normalizer
    # or inside compose:
    # command: ["python", "-m", "strix_api.workers.normalizer"]
"""

from __future__ import annotations

import asyncio
import hashlib
import signal
from uuid import UUID, uuid5

import structlog

from strix_api.adapters.preprocessing_pipeline import (
    PreprocessingPipeline,
    build_pipeline,
)
from strix_api.adapters.redis_adapter import RedisStreamsClient, unpack
from strix_api.adapters.wazuh_adapter import WazuhAlertAdapter
from strix_api.api.errors import StrixError, ValidationFailedError
from strix_api.core.messages import FeatureMessage, RawAlertMessage
from strix_api.observability import (
    alerts_ingested_total,
    configure_logging,
    get_logger,
)
from strix_api.settings import Settings, get_settings

_FEATURES_STREAM_MAXLEN = 50_000  # §6.4


# Namespace for deriving a deterministic host_id from agent_id. Kept here
# rather than in settings because it's part of the wire contract with
# other workers — changing it would break every in-flight chain.
_HOST_ID_NAMESPACE = UUID("6d42aafe-0000-4000-8000-000000000000")


def _shard_for(agent_id: str, num_shards: int) -> int:
    """Consistent shard selection.

    Uses SHA-1 so the number is stable across worker restarts, process
    boundaries, and Python releases — unlike `hash()` which is salted.
    """
    digest = hashlib.sha1(agent_id.encode("utf-8"), usedforsecurity=False).digest()
    return int.from_bytes(digest[:4], "big") % max(num_shards, 1)


def _host_id_for(agent_id: str) -> UUID:
    """UUID v5 in a private namespace — stable across Wazuh re-registrations."""
    return uuid5(_HOST_ID_NAMESPACE, agent_id)


class NormalizerWorker:
    """Single-instance worker. Multiple replicas read from the same consumer group."""

    def __init__(
        self,
        *,
        settings: Settings,
        redis: RedisStreamsClient,
        pipeline: PreprocessingPipeline,
        wazuh: WazuhAlertAdapter,
    ) -> None:
        self._settings = settings
        self._redis = redis
        self._pipeline = pipeline
        self._wazuh = wazuh
        self._stop = asyncio.Event()
        self._log = get_logger("strix_api.workers.normalizer")

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        stream_in = self._settings.wazuh.raw_stream
        group = self._settings.wazuh.consumer_group
        await self._redis.ensure_group(stream_in, group)

        self._log.info(
            "normalizer_started",
            stream_in=stream_in,
            group=group,
            consumer=self._redis.consumer_name,
            num_shards=self._settings.inference.num_shards,
        )

        while not self._stop.is_set():
            try:
                batch = await self._redis.read(
                    stream_in, group, count=32, block_ms=5_000
                )
            except Exception as exc:  # redis connection blip etc.
                self._log.error("redis_read_failed", exc_info=exc)
                await asyncio.sleep(1)
                continue

            if not batch:
                # Keep the depth gauge fresh during idle.
                await self._redis.sample_depth(stream_in)
                continue

            # `batch` is [(stream_name, [(entry_id, field_map), ...])]
            ids_to_ack: list[bytes] = []
            for _stream_name, entries in batch:
                for entry_id, fields in entries:
                    try:
                        await self._handle_one(entry_id, fields)
                    except StrixError as exc:
                        # Typed domain errors → drop message + log.
                        self._log.warning(
                            "alert_dropped",
                            reason=exc.code,
                            detail=exc.detail,
                            entry_id=entry_id.decode(errors="replace"),
                        )
                    except Exception as exc:  # never crash the consumer loop
                        self._log.error(
                            "alert_handler_crashed",
                            entry_id=entry_id.decode(errors="replace"),
                            exc_info=exc,
                        )
                    finally:
                        # Always ACK — bad messages don't return to the stream
                        # (they'd just keep crashing us). Phase 8 can add a
                        # dead-letter queue if we want replay.
                        ids_to_ack.append(entry_id)

            if ids_to_ack:
                try:
                    await self._redis.ack(stream_in, group, *ids_to_ack)
                except Exception as exc:
                    self._log.error("xack_failed", count=len(ids_to_ack), exc_info=exc)

        self._log.info("normalizer_stopped")

    async def _handle_one(self, entry_id: bytes, fields: dict[bytes, bytes]) -> None:
        # Unpack envelope → RawAlertMessage
        try:
            envelope = unpack(fields)
            raw_msg = RawAlertMessage.model_validate(envelope)
        except Exception as exc:
            raise ValidationFailedError(f"malformed raw-alert envelope: {exc}") from exc

        alerts_ingested_total.labels(source="wazuh").inc()

        # Parse Wazuh JSON → RawAlert (leaky-col drop happens here)
        alert = self._wazuh.parse(raw_msg.raw_json)

        # Feature engineer + SecBERT + PCA + scaler → 55-dim vector.
        # CPU-bound, runs in default thread pool to keep the event loop free.
        scaled = await asyncio.to_thread(self._pipeline.transform, alert)

        # Emit FeatureMessage on the sharded output stream.
        agent_id = alert.agent.agent_id
        shard = _shard_for(agent_id, self._settings.inference.num_shards)
        out_stream = f"strix:features:{shard}"

        host_id = _host_id_for(agent_id)

        # Resolve current CKC stage from MITRE annotations on the alert.
        # Lazy-import to keep core ↔ adapters decoupled at import time.
        from strix_api.core.mitre import get_mitre_mapper
        mitre = get_mitre_mapper()
        current_ckc = int(mitre.resolve(
            tactics=alert.rule.mitre_tactics,
            techniques=alert.rule.mitre_techniques,
        ))

        msg = FeatureMessage(
            alert_id=alert.alert_id,
            agent_id=agent_id,
            host_id=host_id,
            occurred_at=alert.occurred_at.isoformat(),
            feature_vector=scaled.tolist(),
            current_ckc_stage=current_ckc,
            mitre_tactics=list(alert.rule.mitre_tactics),
            mitre_techniques=list(alert.rule.mitre_techniques),
            srcuser=alert.data.srcuser,
            srcip=alert.data.srcip,
        )

        await self._redis.publish(
            out_stream,
            msg.model_dump(mode="json", by_alias=True),
            maxlen=_FEATURES_STREAM_MAXLEN,
        )


# ---------------------------------------------------------------- entry point


async def _amain() -> None:
    settings = get_settings()
    configure_logging(
        service_name="strix-normalizer",
        level=settings.observability.log_level,
        json_output=settings.observability.log_json,
    )
    structlog.contextvars.bind_contextvars(service="strix-normalizer")

    from strix_api.adapters.redis_adapter import streams_client

    pipeline = build_pipeline(settings.models.path, warmup=True)
    wazuh = WazuhAlertAdapter()
    async with streams_client(
        settings.redis.url, max_connections=settings.redis.max_connections
    ) as redis_client:
        worker = NormalizerWorker(
            settings=settings,
            redis=redis_client,
            pipeline=pipeline,
            wazuh=wazuh,
        )
        loop = asyncio.get_running_loop()
        for sig_name in ("SIGTERM", "SIGINT"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                loop.add_signal_handler(sig, worker.request_stop)
        await worker.run()


def main() -> None:  # module entry (`python -m strix_api.workers.normalizer`)
    asyncio.run(_amain())


if __name__ == "__main__":
    main()


__all__ = ["NormalizerWorker", "_host_id_for", "_shard_for", "main"]
