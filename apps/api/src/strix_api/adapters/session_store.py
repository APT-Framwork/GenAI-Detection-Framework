"""Per-host session state in Redis (§5.3 + §6.4).

Schema:
    session:{agent_id}              Hash    chain_id, opened_at, last_seen_at,
                                            step_count, last_ckc_stage, last_action,
                                            episode_start_at, max_vae_prob, max_ckc_stage
    session:{agent_id}:latents      List    AE mu vectors (msgpack-encoded float32[64]),
                                            LPUSH then LTRIM 0 49 to keep last 50

Both keys carry a 2h idle TTL (`CHAIN_IDLE_TIMEOUT_MINUTES`). On every write
we EXPIRE the keys to slide the TTL forward — Redis returns 0 if the key
no longer exists, which we treat as "session expired" and let the caller
open a new chain.

Recovery: on inference-worker restart we don't replay anything; the
session keys are still in Redis (they survived the worker death). The next
alert for an agent finds its chain_id and resumes naturally. If Redis was
also restarted (no AOF, or AOF lost), the next alert opens a new chain —
documented as expected per §5.3.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import msgpack
import numpy as np

from strix_api.core.constants import (
    AE_LATENT_DIM,
    CHAIN_IDLE_TIMEOUT_MINUTES,
    CHAIN_MAX_STEPS,
)
from strix_api.core.session import SessionState

if TYPE_CHECKING:
    from redis.asyncio import Redis

_LATENTS_LIST_LIMIT = CHAIN_MAX_STEPS  # one mu per step; matches Transformer max-seq
_TTL_SECONDS = CHAIN_IDLE_TIMEOUT_MINUTES * 60


def _session_key(agent_id: str) -> str:
    return f"session:{agent_id}"


def _latents_key(agent_id: str) -> str:
    return f"session:{agent_id}:latents"


class SessionStore:
    """Async Redis client for per-host session state.

    Stateless apart from the Redis connection. Workers hold one instance.
    """

    def __init__(self, redis: Redis, *, ttl_seconds: int = _TTL_SECONDS) -> None:
        self._r = redis
        self._ttl = ttl_seconds

    # ---- read ---------------------------------------------------------

    async def get_session(self, agent_id: str) -> SessionState | None:
        raw = await self._r.hgetall(_session_key(agent_id))
        if not raw:
            return None
        return _decode_session(raw)

    async def get_latents(self, agent_id: str, limit: int | None = None) -> list[np.ndarray]:
        """Returns AE mu vectors most-recent-FIRST (LPUSH order).

        Caller reverses if it wants oldest→newest (Transformer wants temporal
        order, so the inference worker calls `list(reversed(...))`).
        """
        end = -1 if limit is None else (limit - 1)
        items = await self._r.lrange(_latents_key(agent_id), 0, end)
        return [_decode_latent(b) for b in items]

    # ---- write --------------------------------------------------------

    async def open_session(
        self,
        *,
        agent_id: str,
        chain_id: UUID,
        opened_at: datetime,
        first_malicious_at: datetime,
    ) -> None:
        """Idempotent. Overwrites any prior session for this agent."""
        key = _session_key(agent_id)
        # Wipe latents from any previous chain for the same agent.
        async with self._r.pipeline(transaction=False) as pipe:
            await pipe.delete(_latents_key(agent_id))
            await pipe.delete(key)
            await pipe.hset(
                key,
                mapping={
                    "chain_id": str(chain_id),
                    "episode_start_at": first_malicious_at.isoformat(),
                    "opened_at": opened_at.isoformat(),
                    "last_seen_at": opened_at.isoformat(),
                    "step_count": "0",
                    "last_ckc_stage": "",
                    "last_action": "",
                    "max_vae_prob": "0",
                    "max_ckc_stage": "0",
                },
            )
            await pipe.expire(key, self._ttl)
            await pipe.execute()

    async def append_step(
        self,
        *,
        agent_id: str,
        latent: np.ndarray,
        ckc_stage: int,
        action: int,
        vae_prob: float,
        seen_at: datetime,
    ) -> int:
        """Append a step's state. Returns the new `step_count`."""
        if latent.shape != (AE_LATENT_DIM,):
            raise ValueError(
                f"latent shape {latent.shape}, expected ({AE_LATENT_DIM},)"
            )
        sess_key = _session_key(agent_id)
        lat_key = _latents_key(agent_id)
        encoded = msgpack.packb(latent.astype(np.float32, copy=False).tolist())

        async with self._r.pipeline(transaction=False) as pipe:
            await pipe.lpush(lat_key, encoded)
            await pipe.ltrim(lat_key, 0, _LATENTS_LIST_LIMIT - 1)
            await pipe.expire(lat_key, self._ttl)
            await pipe.hincrby(sess_key, "step_count", 1)
            await pipe.hset(
                sess_key,
                mapping={
                    "last_seen_at": seen_at.isoformat(),
                    "last_ckc_stage": str(ckc_stage),
                    "last_action": str(action),
                },
            )
            # Monotonic max
            await pipe.eval(_LUA_MAX, 1, sess_key, "max_vae_prob", str(vae_prob))
            await pipe.eval(_LUA_MAX_INT, 1, sess_key, "max_ckc_stage", str(ckc_stage))
            await pipe.expire(sess_key, self._ttl)
            results = await pipe.execute()

        # `hincrby` is the 4th command (after lpush, ltrim, expire) — index 3
        new_step_count = int(results[3])
        return new_step_count

    async def close_session(self, agent_id: str) -> None:
        async with self._r.pipeline(transaction=False) as pipe:
            await pipe.delete(_session_key(agent_id))
            await pipe.delete(_latents_key(agent_id))
            await pipe.execute()

    async def session_exists(self, agent_id: str) -> bool:
        return bool(await self._r.exists(_session_key(agent_id)))


# ---- helpers ---------------------------------------------------------


def _decode_session(raw: dict[bytes, bytes]) -> SessionState:
    def _s(k: str) -> str:
        v = raw.get(k.encode()) or raw.get(k)  # type: ignore[arg-type]
        return v.decode() if isinstance(v, bytes) else (v or "")

    def _i(k: str, default: int) -> int:
        s = _s(k)
        return default if not s else int(s)

    def _f(k: str, default: float) -> float:
        s = _s(k)
        return default if not s else float(s)

    def _opt_i(k: str) -> int | None:
        s = _s(k)
        return None if not s else int(s)

    return SessionState(
        chain_id=UUID(_s("chain_id")),
        episode_start_at=_parse_iso(_s("episode_start_at")),
        opened_at=_parse_iso(_s("opened_at")),
        last_seen_at=_parse_iso(_s("last_seen_at")),
        step_count=_i("step_count", 0),
        last_ckc_stage=_opt_i("last_ckc_stage"),
        last_action=_opt_i("last_action"),
        max_vae_prob=_f("max_vae_prob", 0.0),
        max_ckc_stage=_i("max_ckc_stage", 0),
    )


def _decode_latent(raw: bytes) -> np.ndarray:
    arr = msgpack.unpackb(raw, raw=False)
    if not isinstance(arr, list) or len(arr) != AE_LATENT_DIM:
        raise ValueError(f"corrupt latent in Redis: type={type(arr).__name__}")
    return np.array(arr, dtype=np.float32)


def _parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


# ---- Lua scripts -----------------------------------------------------

# Monotonic max for a float field of a hash. Argv: [field_name, candidate_value].
_LUA_MAX = """
local key = KEYS[1]
local field = ARGV[1]
local candidate = tonumber(ARGV[2])
local current = tonumber(redis.call('HGET', key, field) or "0")
if candidate > current then
  redis.call('HSET', key, field, tostring(candidate))
  return 1
end
return 0
"""

_LUA_MAX_INT = """
local key = KEYS[1]
local field = ARGV[1]
local candidate = tonumber(ARGV[2])
local current = tonumber(redis.call('HGET', key, field) or "0")
if candidate > current then
  redis.call('HSET', key, field, tostring(candidate))
  return 1
end
return 0
"""


__all__ = ["SessionStore"]
