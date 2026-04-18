"""Expo Push Notification adapter (M0-B6).

Thin async wrapper around Expo's public push API. The API is a simple
JSON POST — no SDK required. A single request can carry up to 100
messages in a batch; we enforce that client-side.

Reference: https://docs.expo.dev/push-notifications/sending-notifications/

Circuit-breaker pattern mirrors the HIBP / VirusTotal adapters: 5
failures in 60 s trip open; 30 s half-open probe. When open, the
dispatcher silently drops the notification (delivery is best-effort).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import pybreaker
import structlog

_log = structlog.get_logger(__name__)

_EXPO_URL = "https://exp.host/--/api/v2/push/send"
_MAX_BATCH = 100


expo_push_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=30,
    name="expo_push",
)


@dataclass(slots=True, frozen=True)
class PushMessage:
    to: str                    # Expo push token
    title: str
    body: str
    data: dict[str, Any] | None = None
    sound: str | None = "default"
    priority: str = "high"     # 'default' | 'normal' | 'high'


@dataclass(slots=True, frozen=True)
class PushResult:
    ok: int
    failed: int
    invalid_tokens: list[str]


class ExpoPushAdapter:
    """Async Expo push sender. Construct once per worker — thread-safe."""

    def __init__(
        self,
        *,
        access_token: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/json",
        }
        if access_token:
            # Enhanced security — only required if the project opts in.
            headers["Authorization"] = f"Bearer {access_token}"
        self._client = httpx.AsyncClient(
            headers=headers, timeout=timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def send(self, messages: list[PushMessage]) -> PushResult:
        """Send up to N messages. Returns aggregated (ok, failed, invalid).

        "Invalid" tokens are those Expo explicitly rejects as
        `DeviceNotRegistered` — the dispatcher should delete these from
        the ``push_devices`` table so it doesn't keep retrying.
        """
        if not messages:
            return PushResult(ok=0, failed=0, invalid_tokens=[])

        ok = 0
        failed = 0
        invalid: list[str] = []

        for i in range(0, len(messages), _MAX_BATCH):
            batch = messages[i : i + _MAX_BATCH]
            payload = [
                {
                    "to": m.to,
                    "title": m.title,
                    "body": m.body,
                    "data": m.data or {},
                    "sound": m.sound,
                    "priority": m.priority,
                }
                for m in batch
            ]
            try:
                resp = await expo_push_breaker.call_async(
                    self._post_batch, payload,
                )
            except pybreaker.CircuitBreakerError:
                _log.warning("expo_push_breaker_open", batch_size=len(batch))
                failed += len(batch)
                continue
            except httpx.HTTPError as exc:
                _log.warning("expo_push_http_error", error=str(exc))
                failed += len(batch)
                continue

            data = resp.get("data", [])
            for msg, item in zip(batch, data, strict=False):
                status = item.get("status")
                if status == "ok":
                    ok += 1
                    continue
                failed += 1
                details = item.get("details") or {}
                if details.get("error") == "DeviceNotRegistered":
                    invalid.append(msg.to)

        return PushResult(ok=ok, failed=failed, invalid_tokens=invalid)

    async def _post_batch(self, payload: list[dict[str, Any]]) -> dict[str, Any]:
        resp = await self._client.post(_EXPO_URL, json=payload)
        resp.raise_for_status()
        return resp.json()
