"""List → Stream bridge for Wazuh alerts from Filebeat.

Filebeat's native Redis output only supports `list` / `channel` — it cannot
write to Redis Streams directly. This worker BLPOPs from the list Filebeat
writes to (`strix:alerts:raw:list`) and XADDs each entry onto the Streams
key the normalizer reads (`strix:alerts:raw`), wrapping the raw Wazuh doc
in the `RawAlertMessage` envelope.

Separate from the normalizer so each side can scale independently and a
failure in feature engineering never blocks ingestion.
"""

from __future__ import annotations

import asyncio
import json
import signal
import uuid
from typing import Any

import structlog

from strix_api.adapters.redis_adapter import streams_client
from strix_api.core.messages import RawAlertMessage
from strix_api.observability import (
    alerts_ingested_total,
    configure_logging,
    get_logger,
)
from strix_api.settings import get_settings

_LIST_KEY = "strix:alerts:raw:list"  # must match infra/filebeat.yml `output.redis.key`


class _Stop:
    """Simple shared stop flag so signals drop us out of BLPOP gracefully."""

    def __init__(self) -> None:
        self._flag = asyncio.Event()

    def set(self) -> None:
        self._flag.set()

    @property
    def is_set(self) -> bool:
        return self._flag.is_set()


async def _run() -> None:
    settings = get_settings()
    configure_logging(
        service_name="strix-wazuh-bridge",
        level=settings.observability.log_level,
        json_output=settings.observability.log_json,
    )
    structlog.contextvars.bind_contextvars(service="strix-wazuh-bridge")
    log = get_logger("strix_api.workers.wazuh_bridge")

    stop = _Stop()
    loop = asyncio.get_running_loop()
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            loop.add_signal_handler(sig, stop.set)

    async with streams_client(
        settings.redis.url, max_connections=settings.redis.max_connections
    ) as rs:
        redis = rs.client
        log.info(
            "wazuh_bridge_started",
            list_key=_LIST_KEY,
            stream_key=settings.wazuh.raw_stream,
        )
        while not stop.is_set:
            try:
                # BLPOP returns (key, value) or None on timeout.
                item = await redis.blpop([_LIST_KEY], timeout=5)
            except Exception as exc:
                log.error("blpop_failed", exc_info=exc)
                await asyncio.sleep(1)
                continue
            if item is None:
                continue

            _key, raw = item
            try:
                doc: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError as exc:
                log.warning(
                    "skipping_malformed_json",
                    error=str(exc),
                    preview=raw[:120] if isinstance(raw, bytes) else str(raw)[:120],
                )
                continue

            # Some Filebeat configurations wrap the document under `_source`;
            # the Wazuh Filebeat module publishes at the root. Accept either.
            msg = RawAlertMessage(
                alert_id=_derive_alert_id(doc),
                raw_json=doc,
            )
            try:
                await rs.publish(
                    settings.wazuh.raw_stream,
                    msg.model_dump(mode="json", by_alias=True),
                    maxlen=settings.wazuh.raw_stream_maxlen,
                )
                alerts_ingested_total.labels(source="filebeat").inc()
            except Exception as exc:
                log.error("xadd_failed", exc_info=exc)
                # We've already popped from the list. Put it back at the head
                # so we don't lose it.
                try:
                    await redis.lpush(_LIST_KEY, raw)
                except Exception:  # noqa: BLE001
                    log.error("lpush_restore_failed", lost=True)

        log.info("wazuh_bridge_stopped")


def _derive_alert_id(doc: dict[str, Any]) -> str:
    """Best-effort stable ID from the Wazuh doc.

    Wazuh's `_id` is a string that's guaranteed unique per alert per manager.
    Some pipelines drop it; in that case we fall back to a rule-id + timestamp
    combo, and ultimately a random UUID.
    """
    raw_id = doc.get("_id") or doc.get("id")
    if raw_id:
        return str(raw_id)

    src = doc.get("_source") if isinstance(doc.get("_source"), dict) else doc
    rule_id = ((src.get("rule") or {}) if isinstance(src, dict) else {}).get("id")
    ts = (src.get("@timestamp") if isinstance(src, dict) else None) or ""
    if rule_id and ts:
        return f"{rule_id}-{ts}"
    return f"synthetic-{uuid.uuid4()}"


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()


__all__ = ["main"]
