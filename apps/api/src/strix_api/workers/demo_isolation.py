"""Demo-only auto-isolation worker.

When ``STRIX_DEMO_AUTO_ISOLATE=1`` is set, this worker subscribes to
``strix:stream:rl`` and on the first ESCALATE-or-stronger frame per host,
runs::

    docker exec strix_<victim> pkill -f sandcat

Severing sandcat severs the victim's C2 link to Caldera so subsequent
abilities fail with ``rc=-3`` (agent unreachable). Wazuh + auditd remain
running, so the dashboard's other panels keep flowing — only the attack
itself stops. The dashboard's topology widget visually drops the
attacker→victim edge to "BLOCKED" via the predetection store, in lock
step with this worker.

This is **demo-only**. Hard-off without the env flag (`STRIX_DEMO_AUTO_ISOLATE`).
Production runs of STRIX 1.0 are advisory-only per §12 Q3.

Container name mapping
----------------------
The RL frame's ``host_id`` is the wazuh numeric agent id (e.g. ``"008"``)
on this lab, but the container is named ``strix_victim1``. We bootstrap
a numeric→container map at startup from ``client.keys`` inside each
running ``strix_victim*`` container, then refresh on miss.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
from typing import Any

import structlog
from redis.asyncio import Redis

from strix_api.observability import configure_logging
from strix_api.services.live_feed import STREAM_RL_CHANNEL
from strix_api.settings import get_settings

_INTERVENING_ACTIONS = {"ESCALATE", "ISOLATE_HOST", "BLOCK_USER_IP"}
_DOCKER_TIMEOUT_SECONDS = 5.0
_VICTIM_CONTAINER_PREFIX = "strix_victim"


class DemoIsolationWorker:
    def __init__(self, redis: Redis, log: structlog.BoundLogger) -> None:
        self._r = redis
        self._log = log
        self._isolated_hosts: set[str] = set()
        self._stop = asyncio.Event()
        self._dry_run = os.environ.get("STRIX_DEMO_ISOLATE_DRY_RUN", "0") == "1"
        # numeric_id ("008") OR agent_name ("victim1") -> container ("strix_victim1")
        self._id_map: dict[str, str] = {}

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        await self._refresh_id_map()
        pubsub = self._r.pubsub()
        await pubsub.subscribe(STREAM_RL_CHANNEL)
        self._log.info(
            "demo_isolation_started",
            channel=STREAM_RL_CHANNEL,
            dry_run=self._dry_run,
            id_map=self._id_map,
        )
        try:
            while not self._stop.is_set():
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if msg is None:
                    continue
                if msg.get("type") != "message":
                    continue
                payload = msg.get("data") or b"{}"
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8", errors="replace")
                try:
                    frame = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                await self._handle_frame(frame)
        finally:
            try:
                await pubsub.unsubscribe(STREAM_RL_CHANNEL)
            except Exception:  # noqa: BLE001 — best-effort teardown
                pass
            try:
                await pubsub.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._log.info("demo_isolation_stopped")

    async def _handle_frame(self, frame: dict[str, Any]) -> None:
        action_name = frame.get("action_name") or ""
        if action_name not in _INTERVENING_ACTIONS:
            return
        host_id = str(frame.get("host_id") or "")
        if not host_id:
            return
        if host_id in self._isolated_hosts:
            return  # already severed; pkill again is harmless but noisy.
        container = self._resolve_container(host_id)
        if container is None:
            # Map miss — refresh once in case a victim came up after startup.
            await self._refresh_id_map()
            container = self._resolve_container(host_id)
        if container is None:
            self._log.warning(
                "demo_isolation_no_container",
                host_id=host_id,
                action_name=action_name,
                known_ids=list(self._id_map.keys()),
            )
            return
        self._isolated_hosts.add(host_id)
        rc, stderr = await self._docker_exec(container, "pkill", "-f", "sandcat")
        # pkill exits 0 if it killed >=1 process, 1 if no match. Either is fine
        # — 0 is the success path; 1 means sandcat already dead (still OK).
        ok = rc in (0, 1)
        log = self._log.info if ok else self._log.warning
        log(
            "demo_isolation_applied" if ok else "demo_isolation_failed",
            container=container,
            host_id=host_id,
            action_name=action_name,
            stage=frame.get("ckc_stage"),
            chain_max_ckc=frame.get("chain_max_ckc_stage"),
            pkill_rc=rc,
            stderr=stderr,
            dry_run=self._dry_run,
        )

    def _resolve_container(self, host_id: str) -> str | None:
        # Direct map hit (numeric id or agent_name).
        c = self._id_map.get(host_id)
        if c is not None:
            return c
        # Fallback: host_id might already be a hostname like "victim1".
        candidate = f"strix_{host_id}"
        if candidate in self._id_map.values():
            return candidate
        return None

    async def _refresh_id_map(self) -> None:
        rc, out = await self._run_subprocess("docker", "ps", "--format", "{{.Names}}")
        if rc != 0:
            self._log.warning("demo_isolation_docker_ps_failed", rc=rc, stderr=out)
            return
        containers = [
            n for n in out.splitlines()
            if n.startswith(_VICTIM_CONTAINER_PREFIX)
        ]
        new_map: dict[str, str] = {}
        for c in containers:
            # Container's hostname (suffix after strix_) is also a valid alias.
            new_map[c.removeprefix("strix_")] = c
            rc, content = await self._run_subprocess(
                "docker", "exec", c, "cat", "/var/ossec/etc/client.keys"
            )
            if rc != 0:
                continue
            for line in content.splitlines():
                parts = line.split()
                # Wazuh client.keys format: "<id> <name> <ip> <key>"
                if len(parts) >= 2:
                    new_map[parts[0]] = c
                    new_map[parts[1]] = c
        if new_map != self._id_map:
            self._log.info("demo_isolation_id_map_refreshed", id_map=new_map)
        self._id_map = new_map

    async def _docker_exec(
        self, container: str, *cmd: str
    ) -> tuple[int, str]:
        if self._dry_run:
            self._log.info("demo_isolation_dry_run", container=container, cmd=cmd)
            return 0, ""
        return await self._run_subprocess("docker", "exec", container, *cmd)

    @staticmethod
    async def _run_subprocess(*cmd: str) -> tuple[int, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, FileNotFoundError) as exc:
            return -1, str(exc)
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_DOCKER_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            proc.kill()
            return -1, f"timeout after {_DOCKER_TIMEOUT_SECONDS}s"
        text = (stdout or b"").decode("utf-8", errors="replace")
        if proc.returncode != 0:
            text = (stderr or b"").decode("utf-8", errors="replace") or text
        return int(proc.returncode or 0), text


async def _amain() -> None:
    # Check the flag BEFORE loading settings — the idle path must not
    # require DB / Redis env vars (it does nothing). Only the active
    # path needs the full settings object.
    enabled = os.environ.get("STRIX_DEMO_AUTO_ISOLATE", "0") == "1"
    if not enabled:
        configure_logging(service_name="strix-demo-isolation", level="INFO", json_output=True)
        log = structlog.get_logger().bind(service="strix-demo-isolation")
        log.info(
            "demo_isolation_disabled",
            hint="set STRIX_DEMO_AUTO_ISOLATE=1 to enable",
        )
        # Stay alive so honcho doesn't restart-loop us. Sleep until SIGTERM.
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig_name in ("SIGTERM", "SIGINT"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                loop.add_signal_handler(sig, stop.set)
        await stop.wait()
        return

    settings = get_settings()
    configure_logging(
        service_name="strix-demo-isolation",
        level=settings.observability.log_level,
        json_output=settings.observability.log_json,
    )
    log = structlog.get_logger().bind(service="strix-demo-isolation")

    redis = Redis.from_url(
        settings.redis.url,
        max_connections=settings.redis.max_connections,
        decode_responses=False,
    )
    worker = DemoIsolationWorker(redis, log)
    loop = asyncio.get_running_loop()
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            loop.add_signal_handler(sig, worker.request_stop)
    try:
        await worker.run()
    finally:
        try:
            await redis.aclose()
        except Exception:  # noqa: BLE001
            pass


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
