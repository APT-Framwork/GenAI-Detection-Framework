"""Auto-response kill switch (P8-8 / §12 Q3).

When the kill switch is ENGAGED, no DQN action of severity ≥ ESCALATE
will ever be auto-applied — even when `AUTH_AUTO_RESPONSE_ENABLED=true`.
The flag is held in Redis so an operator can flip it from any pod
(curl, ops dashboard, etc.) without restarting workers.

Defaults to ENGAGED (`true`) on a fresh deploy, matching §12 Q3's
"flag stays OFF in 1.0" intent — explicit operator action is required to
disengage it.

Key:    `strix:auto_response:kill_switch`   string ("on" | "off")
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from typing import Any

_KEY = "strix:auto_response:kill_switch"


@dataclass(frozen=True)
class KillSwitchState:
    engaged: bool         # True → block all auto-applies
    set_by: str | None
    set_at: str | None


class KillSwitchService:
    """Stateless apart from the Redis client. Uses STRING semantics so any
    Redis client (compose, hand-curl) can read/write without msgpack."""

    def __init__(self, redis: Any) -> None:
        self._r = redis

    async def is_engaged(self) -> bool:
        """Default to ENGAGED when key is absent (safest)."""
        v = await self._r.get(_KEY)
        if v is None:
            return True
        if isinstance(v, bytes):
            v = v.decode("utf-8", "replace")
        return v.strip().lower() not in ("off", "0", "false")

    async def state(self) -> KillSwitchState:
        engaged = await self.is_engaged()
        meta_set_by = await self._r.get(_KEY + ":set_by")
        meta_set_at = await self._r.get(_KEY + ":set_at")
        return KillSwitchState(
            engaged=engaged,
            set_by=(meta_set_by.decode() if isinstance(meta_set_by, bytes) else meta_set_by),
            set_at=(meta_set_at.decode() if isinstance(meta_set_at, bytes) else meta_set_at),
        )

    async def engage(self, *, by: str) -> None:
        from datetime import datetime
        async with self._r.pipeline(transaction=False) as pipe:
            await pipe.set(_KEY, "on")
            await pipe.set(_KEY + ":set_by", by)
            await pipe.set(_KEY + ":set_at", datetime.now(UTC).isoformat())
            await pipe.execute()

    async def disengage(self, *, by: str) -> None:
        from datetime import datetime
        async with self._r.pipeline(transaction=False) as pipe:
            await pipe.set(_KEY, "off")
            await pipe.set(_KEY + ":set_by", by)
            await pipe.set(_KEY + ":set_at", datetime.now(UTC).isoformat())
            await pipe.execute()


__all__ = ["KillSwitchService", "KillSwitchState"]
