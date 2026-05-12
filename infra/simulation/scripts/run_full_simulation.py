#!/usr/bin/env python3
"""
STRIX — full real-time MITRE ATT&CK simulation runner.

Drives Caldera through every paper-aligned tactic against the lab's
sandcat agents, monitors the platform end-to-end (Wazuh alerts -> Redis
stream -> Postgres detections + attack_chains + dqn_actions), and prints
a per-tactic + final report card.

Usage:
    python3 run_full_simulation.py                   # full run, default pacing
    python3 run_full_simulation.py --dry-run         # plan only, no firing
    python3 run_full_simulation.py --report-only     # current platform state
    python3 run_full_simulation.py --list            # show stockpile adversaries
    python3 run_full_simulation.py --only Discovery,Collection
    python3 run_full_simulation.py --budget 120 --dwell 45 --obfuscator base64

Pre-reqs: lab is up (bash infra/scripts/lab_up.sh) AND
          host /etc/audit/rules.d/strix.rules has audit-wazuh-x rules loaded
          AND filebeat is forwarding (xlen growing).
"""
from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------- config

CALDERA_URL = os.environ.get("CALDERA_URL", "http://localhost:8888")
CALDERA_API_KEY = os.environ.get("CALDERA_API_KEY", "")
CALDERA_GROUP = os.environ.get("CALDERA_GROUP", "red")
CALDERA_CONTAINER = os.environ.get("CALDERA_CONTAINER", "strix_caldera")
ATTACKER_CONTAINER = os.environ.get("ATTACKER_CONTAINER", "strix_attacker")
RECON_BURST_PATH = os.environ.get("RECON_BURST_PATH", "/opt/recon_burst.sh")
# Victim hosts the recon burst targets. The default matches the lab compose
# (victim1, victim2). Override via env when running against a custom topology.
RECON_TARGETS = os.environ.get("RECON_TARGETS", "victim1,victim2").split(",")

PG_CONTAINER = os.environ.get("PG_CONTAINER", "strix_postgres")
PG_USER = os.environ.get("DB_USER", "strix")
PG_DB = os.environ.get("DB_NAME", "strix")

REDIS_CONTAINER = os.environ.get("REDIS_CONTAINER", "strix_redis")
REDIS_STREAM = os.environ.get("REDIS_STREAM", "strix:alerts:raw")

WAZUH_CONTAINER = os.environ.get("WAZUH_CONTAINER", "strix_wazuh_manager")
ALERTS_PATH = "/var/ossec/logs/alerts/alerts.json"

# --------------------------------------------------------------------- ANSI

class C:
    G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; B = "\033[34m"
    M = "\033[35m"; CY = "\033[36m"; D = "\033[2m"; BLD = "\033[1m"; X = "\033[0m"

# Force line-buffered stdout/stderr so each event is visible to the parent
# tail (filebeat / docker logs / tee) within ~auditd flush latency, not at
# script exit. flush=True on every print is the belt; reconfigure() is the
# braces — handles cases where stdout is a pipe (default block-buffering).
try:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    sys.stderr.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

def step(msg: str) -> None:    print(f"\n{C.D}── [ {msg} ] ──{C.X}", flush=True)
def ok(msg: str) -> None:      print(f"{C.G}✓{C.X} {msg}", flush=True)
def warn(msg: str) -> None:    print(f"{C.Y}⚠{C.X} {msg}", flush=True)
def fail(msg: str) -> None:    print(f"{C.R}✗{C.X} {msg}", flush=True); sys.exit(1)
def info(msg: str) -> None:    print(f"{C.D}·{C.X} {msg}", flush=True)
def section(msg: str) -> None: print(f"\n{C.BLD}{C.B}{'═'*70}\n{msg}\n{'═'*70}{C.X}", flush=True)

# --------------------------------------------------------------------- shell

def sh(cmd: list[str], check: bool = True, timeout: int = 30) -> str:
    """Run a shell command, return stdout. Raise on non-zero unless check=False.

    Decodes bytes with errors='replace' — some tools (redis-cli XREVRANGE, docker
    logs) emit raw bytes from upstream streams that aren't valid UTF-8."""
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        if check: fail(f"timeout running: {' '.join(cmd[:6])}")
        return ""
    if check and r.returncode != 0:
        err = r.stderr.decode("utf-8", errors="replace").strip()
        fail(f"command failed (rc={r.returncode}): {' '.join(cmd[:6])}\n{err}")
    return r.stdout.decode("utf-8", errors="replace")

def docker_exec(container: str, *args: str, check: bool = True, timeout: int = 30) -> str:
    return sh(["docker", "exec", container, *args], check=check, timeout=timeout)

# --------------------------------------------------------------------- caldera client

class Caldera:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key

    def _req(self, method: str, path: str, body: dict | None = None, timeout: int = 30) -> Any:
        url = f"{self.url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "KEY": self.key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode("utf-8", errors="replace")[:300] if hasattr(e, "read") else ""
            raise RuntimeError(f"HTTP {e.code} on {method} {path}: {body_txt}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"Caldera unreachable at {url}: {e.reason}") from None
        if not raw.strip():
            return None
        try:
            return json.loads(raw, strict=False)
        except json.JSONDecodeError:
            # Caldera's link.output sometimes contains raw control chars — strict=False
            # is already permissive; if we still fail, salvage with replacement.
            cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
            return json.loads(cleaned, strict=False)

    # --- discovery
    def list_adversaries(self) -> list[dict]:  return self._req("GET", "/api/v2/adversaries") or []
    def list_planners(self)    -> list[dict]:  return self._req("GET", "/api/v2/planners") or []
    def list_abilities(self)   -> list[dict]:  return self._req("GET", "/api/v2/abilities") or []
    def list_agents(self)      -> list[dict]:  return self._req("GET", "/api/v2/agents") or []

    # --- ops
    def create_adhoc_adversary(self, name: str, ability_ids: list[str]) -> str:
        adv = self._req("POST", "/api/v2/adversaries", {
            "name": name, "atomic_ordering": ability_ids,
        })
        return adv["adversary_id"]

    def launch_op(self, name: str, adv_id: str, planner_id: str,
                  group: str, obfuscator: str = "plain-text") -> str:
        op = self._req("POST", "/api/v2/operations", {
            "name": name,
            "adversary": {"adversary_id": adv_id},
            "group": group,
            "planner": {"id": planner_id},
            "obfuscator": obfuscator,
            "autonomous": 1,
            "state": "running",
        })
        return op["id"]

    def get_op(self, op_id: str) -> dict:        return self._req("GET", f"/api/v2/operations/{op_id}") or {}
    def stop_op(self, op_id: str) -> None:       self._req("PATCH", f"/api/v2/operations/{op_id}", {"state": "finished"})

# --------------------------------------------------------------------- token resolution

_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]+")

def resolve_caldera_token(container: str) -> str:
    """Token discovery: env var -> docker logs scrape -> fail."""
    if CALDERA_API_KEY:
        return CALDERA_API_KEY
    info(f"CALDERA_API_KEY not set — extracting from `docker logs {container}`")
    raw = sh(["docker", "logs", container], check=False, timeout=10)
    raw = re.sub(r"\x1b\[[0-9;]*m", "", raw)  # strip ANSI
    role = field_ = None; buf = ""
    out: dict[str, dict[str, str]] = {"red": {}, "blue": {}}
    def flush() -> None:
        nonlocal buf, role, field_
        if role and field_ and buf: out[role][field_] = buf
        buf = ""
    for s in (l.strip() for l in raw.splitlines()):
        if s.startswith("Red:"):       flush(); role, field_ = "red", None;  continue
        if s.startswith("Blue:"):      flush(); role, field_ = "blue", None; continue
        if s.startswith("USERNAME:"):  flush(); field_ = None;                continue
        if s.startswith("PASSWORD:"):  flush(); field_ = "password";  buf = s[9:].strip();  continue
        if s.startswith("API_TOKEN:"): flush(); field_ = "api_token"; buf = s[10:].strip(); continue
        if field_ and _TOKEN_RE.fullmatch(s): buf += s; continue
        if field_: flush(); field_ = None
    flush()
    tok = out.get("red", {}).get("api_token", "")
    if not tok:
        fail("could not extract Caldera red api_token. "
             "Set CALDERA_API_KEY=... or re-run `bash infra/scripts/lab_up.sh`.")
    return tok

# --------------------------------------------------------------------- platform metrics

@dataclass
class Snapshot:
    wall_ts: float
    redis_xlen: int
    pg_alerts: int
    pg_detections: int
    pg_chains: int
    pg_chains_open: int
    pg_max_ckc: int
    pg_dqn: int
    wazuh_alert_lines: int
    pg_now: str = ""  # ISO timestamp from PG, used to scope FINAL REPORT to this run

def _psql_int(sql: str) -> int:
    out = docker_exec(PG_CONTAINER, "psql", "-U", PG_USER, "-d", PG_DB, "-Atc", sql, check=False)
    try:
        return int((out.strip().splitlines() or ["0"])[0] or 0)
    except (ValueError, IndexError):
        return 0

def _psql_rows(sql: str) -> list[list[str]]:
    out = docker_exec(PG_CONTAINER, "psql", "-U", PG_USER, "-d", PG_DB, "-Atc", sql, check=False)
    rows = []
    for line in out.strip().splitlines():
        if line:
            rows.append(line.split("|"))
    return rows

# --------------------------------------------------------------------- RL ESCALATE watch
#
# When the DQN fires ESCALATE on a host, the simulator should stop the
# Caldera op currently attacking that host and skip remaining tactics
# targeting it. We detect ESCALATE by polling `dqn_actions` joined with
# `hosts` for hostnames decided since RUN_START_TS, which is captured
# once at the top of the for-tactics loop in main().

RUN_START_TS: str = ""

def contained_hosts() -> set[str]:
    """Hostnames the DQN has ESCALATE'd on since RUN_START_TS.

    Empty when no run cutoff is set yet (preflight, --report-only, etc).
    Resilient to PG hiccups: any error returns an empty set so the sim
    keeps running.
    """
    if not RUN_START_TS:
        return set()
    try:
        rows = _psql_rows(
            "SELECT DISTINCT h.agent_name FROM dqn_actions d "
            "JOIN hosts h ON h.host_id = d.host_id "
            f"WHERE d.action_name = 'ESCALATE' AND d.decided_at > '{RUN_START_TS}';"
        )
    except Exception:  # noqa: BLE001
        return set()
    return {r[0] for r in rows if r and r[0]}

_GROUP_HOSTS_CACHE: dict[str, set[str]] = {}

def mark_interventions_applied(hostnames: set[str]) -> int:
    """Flip pending ESCALATE/ISOLATE/BLOCK rows to applied for the given hosts.

    Called once stop_op() succeeds — the action *was* applied (Caldera
    op killed) so the /actions queue should reflect that.

    Returns rows affected. Best-effort; PG hiccups don't fail the sim.
    """
    if not hostnames or not RUN_START_TS:
        return 0
    names_sql = ",".join("'" + n.replace("'", "''") + "'" for n in hostnames)
    sql = (
        "WITH targets AS ("
        "  SELECT d.action_id FROM dqn_actions d "
        "  JOIN hosts h ON h.host_id = d.host_id "
        f" WHERE h.agent_name IN ({names_sql}) "
        f"   AND d.decided_at > '{RUN_START_TS}' "
        "   AND d.applied = false "
        "   AND d.action_name IN ('ESCALATE','ISOLATE_HOST','BLOCK_USER_IP')"
        ") "
        "UPDATE dqn_actions SET applied = true, applied_at = NOW() "
        "WHERE action_id IN (SELECT action_id FROM targets) "
        "RETURNING action_id;"
    )
    try:
        rows = _psql_rows(sql)
    except Exception:  # noqa: BLE001
        return 0
    return len(rows)

def group_hostnames(cal: Caldera, group: str) -> set[str]:
    """Caldera sandcat agents in `group`, by host. Cached per group."""
    if group in _GROUP_HOSTS_CACHE:
        return _GROUP_HOSTS_CACHE[group]
    try:
        agents = cal.list_agents()
    except RuntimeError:
        return set()
    hosts = {
        (a.get("host") or "").strip()
        for a in agents
        if (a.get("group") or "") == group
    }
    hosts.discard("")
    _GROUP_HOSTS_CACHE[group] = hosts
    return hosts

def take_snapshot() -> Snapshot:
    xlen_out = docker_exec(REDIS_CONTAINER, "redis-cli", "XLEN", REDIS_STREAM, check=False)
    xlen = int(xlen_out.strip() or 0) if xlen_out.strip().isdigit() else 0
    wazuh_lines_out = docker_exec(WAZUH_CONTAINER, "bash", "-c",
                                  f"wc -l < {ALERTS_PATH} 2>/dev/null || echo 0", check=False)
    try: wazuh_lines = int(wazuh_lines_out.strip() or 0)
    except ValueError: wazuh_lines = 0
    pg_now_out = docker_exec(PG_CONTAINER, "psql", "-U", PG_USER, "-d", PG_DB,
                             "-Atc", "SELECT NOW();", check=False)
    pg_now = (pg_now_out.strip().splitlines() or [""])[0]
    return Snapshot(
        wall_ts=time.time(),
        redis_xlen=xlen,
        wazuh_alert_lines=wazuh_lines,
        pg_alerts=_psql_int("SELECT COUNT(*) FROM alerts;"),
        pg_detections=_psql_int("SELECT COUNT(*) FROM detections;"),
        pg_chains=_psql_int("SELECT COUNT(*) FROM attack_chains;"),
        pg_chains_open=_psql_int("SELECT COUNT(*) FROM attack_chains WHERE status='open';"),
        pg_max_ckc=_psql_int("SELECT COALESCE(MAX(max_ckc_stage), 0) FROM attack_chains;"),
        pg_dqn=_psql_int("SELECT COUNT(*) FROM dqn_actions;"),
        pg_now=pg_now,
    )

def diff_table(before: Snapshot, after: Snapshot) -> str:
    def row(label: str, b: int, a: int) -> str:
        d = a - b
        col = C.G if d > 0 else (C.D if d == 0 else C.R)
        return f"  {label:<22s} {b:>8d} -> {a:>8d}   {col}{d:+d}{C.X}"
    return "\n".join([
        row("wazuh alerts.json",   before.wazuh_alert_lines, after.wazuh_alert_lines),
        row("redis xlen",          before.redis_xlen,        after.redis_xlen),
        row("pg alerts",           before.pg_alerts,         after.pg_alerts),
        row("pg detections",       before.pg_detections,     after.pg_detections),
        row("pg attack_chains",    before.pg_chains,         after.pg_chains),
        row("pg open chains",      before.pg_chains_open,    after.pg_chains_open),
        row("pg max_ckc_stage",    before.pg_max_ckc,        after.pg_max_ckc),
        row("pg dqn_actions",      before.pg_dqn,            after.pg_dqn),
    ])

# --------------------------------------------------------------------- pre-flight

def preflight(cal: Caldera, group: str) -> None:
    section("PRE-FLIGHT")

    step("docker containers up")
    names = sh(["docker", "ps", "--format", "{{.Names}}"], check=False).split()
    for c in (CALDERA_CONTAINER, PG_CONTAINER, REDIS_CONTAINER, WAZUH_CONTAINER, "strix_filebeat"):
        if c in names: ok(f"{c} running")
        else: fail(f"{c} not running — run `bash infra/scripts/lab_up.sh`")

    step("Caldera reachable + agents in group")
    agents = cal.list_agents()
    active = [a for a in agents if a.get("group") == group]
    if not active:
        fail(f"no agents in group '{group}' — check victim sandcat enrollment")
    # last_seen freshness — Caldera ISO format is UTC ("2026-04-29T13:42:11Z").
    # Use calendar.timegm so we don't apply the local-tz offset.
    fresh = []
    for a in active:
        last = a.get("last_seen", "")
        if last:
            try:
                t = time.strptime(last.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
                last_ts = calendar.timegm(t)
                if time.time() - last_ts < 600: fresh.append(a)
            except ValueError:
                pass
    if not fresh:
        warn(f"{len(active)} agents in group '{group}' but none seen in last 10 min — "
             f"sandcat may have lost contact")
    else:
        ok(f"{len(fresh)}/{len(active)} agents in group '{group}' fresh "
           f"(paws: {', '.join(a['paw'] for a in fresh)})")

    step("host auditd is producing audit-wazuh-x events")
    # /etc/audit/rules.d is root-only and `auditctl -l` needs sudo. The cleanest
    # check is: do recent execve events in the (bind-mounted) audit.log carry
    # key=audit-wazuh-x? If yes, the host rules are live.
    found = docker_exec("strix_victim1", "bash", "-c",
                        "tail -2000 /var/log/audit/audit.log 2>/dev/null | grep -c 'audit-wazuh-x' || true",
                        check=False)
    n = 0
    try: n = int(found.strip().splitlines()[-1] if found.strip() else 0)
    except (ValueError, IndexError): n = 0
    if n > 0:
        ok(f"audit-wazuh-x events present in /var/log/audit/audit.log (last 2k lines: {n} hits)")
    else:
        warn("no audit-wazuh-x markers in recent audit.log. "
             "Verify host: `sudo auditctl -l | grep audit-wazuh-x`. "
             "If missing, see SESSION_LOG step 17.")

    step("Wazuh agents Active")
    out = docker_exec(WAZUH_CONTAINER, "/var/ossec/bin/agent_control", "-l", check=False)
    n_active = sum(1 for line in out.splitlines() if "Active" in line)
    if n_active >= 2: ok(f"{n_active} Wazuh agents Active")
    else: warn(f"only {n_active} agents Active — see SESSION_LOG step 17b (re-enrollment)")

    step("Redis stream + Postgres reachable")
    s = take_snapshot()
    ok(f"redis xlen={s.redis_xlen}  alerts={s.pg_alerts}  detections={s.pg_detections}  chains={s.pg_chains}")

    step("Filebeat agent block survives (normalizer not dropping)")
    # Stream entries are msgpack-encoded; substring matching on JSON won't work.
    # Reliable signal: a victim agent name appears in the bytes (only Wazuh's
    # agent.name produces those — Filebeat's own agent block has type=filebeat).
    sample = docker_exec(REDIS_CONTAINER, "redis-cli", "XREVRANGE", REDIS_STREAM, "+", "-", "COUNT", "1",
                         check=False)
    if not sample.strip():
        warn("no entries yet in redis stream — preflight inconclusive")
    elif "victim1" in sample or "victim2" in sample or "agent.name" in sample:
        ok("redis entries carry Wazuh agent.name — filebeat config is correct")
    else:
        warn("redis entries lack a victim agent name — normalizer will drop on missing agent.id. "
             "Check infra/filebeat.yml: `agent` must NOT be in drop_fields. See SESSION_LOG §4.")

# --------------------------------------------------------------------- tactic plan

@dataclass
class Tactic:
    label: str                   # paper-friendly name
    paper_tactic_id: str         # MITRE TA####
    technique_ids: list[str]     # MITRE T####.### family
    stockpile_names: list[str]   # accepted stockpile adversary names (case-insensitive, ordered preference)
    obfuscator: str = "plain-text"
    notes: str = ""
    # When set, this tactic does NOT route through Caldera. The runner
    # dispatches to the named handler (see run_tactic) and the resulting
    # activity is attributed to a non-Caldera source — used for the
    # pre-implant Reconnaissance phase, which needs a separate attacker
    # IP and toolset (nmap / ssh) that Caldera/Sandcat can't provide.
    custom_executor: str | None = None

PLAN: list[Tactic] = [
    # ── Pre-implant reconnaissance (CKC stage 1) ─────────────────────────
    # Fired from strix_attacker via /opt/recon_burst.sh — NOT through
    # Caldera. The recon burst makes the victims' sshd log invalid-user
    # bursts that Wazuh's stock rules 5710/5712 match; STRIX rules
    # 100050/100051 chain off those to attach T1595 (Active Scanning),
    # which `mitre_to_ckc.json` maps to CKC stage 1.
    Tactic("Reconnaissance",     "TA0043",
           ["T1595", "T1595.002"],
           [],  # no Caldera stockpile — uses custom executor
           obfuscator="plain-text",
           custom_executor="recon_burst",
           notes="external SSH probe burst from strix_attacker → tagged T1595"),
    Tactic("Discovery",          "TA0007",
           ["T1033", "T1057", "T1083", "T1087.001", "T1069.001"],
           ["Discovery", "Enumerator", "Terminal"],
           notes="paper Tables 4 & 5 baseline — System/User/Process/File discovery"),
    Tactic("Defense Evasion",    "TA0005",
           ["T1070.003", "T1070.004", "T1027", "T1562.001"],
           ["Defense Evasion", "Undercover"],
           notes="log clearing — exercises FIM + audit DEL syscalls"),
    Tactic("Persistence",        "TA0003",
           ["T1136.001", "T1098", "T1037", "T1543.002", "T1053.003"],
           ["Stowaway", "Persistence"],
           notes="account creation + cron/systemd backdoors (likely ad-hoc)"),
    Tactic("Privilege Escalation","TA0004",
           ["T1548.003", "T1068", "T1548.001"],
           ["Privileged Operations", "Privileged"],
           notes="sudo abuse / SUID hunt (likely ad-hoc)"),
    Tactic("Credential Access",  "TA0006",
           ["T1110.001", "T1003.008", "T1552.001", "T1003"],
           ["Credential Access", "Brute Force"],
           obfuscator="plain-text",
           notes="brute force + /etc/shadow read (likely ad-hoc)"),
    Tactic("Lateral Movement",   "TA0008",
           ["T1021.004", "T1021"],
           ["Lateral Movement (SSH)", "Lateral Movement"],
           notes="SSH pivot — needs reachable target on lab net (likely ad-hoc)"),
    Tactic("Collection",         "TA0009",
           ["T1005", "T1560.001", "T1119"],
           ["Collection", "Thief"],
           notes="stages files under /tmp/staged → FIM signal"),
    Tactic("Exfiltration",       "TA0010",
           ["T1048", "T1048.003", "T1041"],
           ["Advanced Thief via FTP", "Advanced Thief", "Thief"],
           notes="ftp exfil; if no FTP receiver on lab net the link will fail rc≠0 (still produces audit signal)"),
    Tactic("Impact",             "TA0040",
           ["T1485", "T1565.001", "T1486"],
           ["Ransack"],
           notes="DESTRUCTIVE-flavoured — keep budget short. Hits /tmp only in stockpile."),
    # T1059.004 (Unix Shell execution) is exercised across all of the above when
    # obfuscator != plain-text. Run with --obfuscator base64jumble for SecBERT coverage.
]

# --------------------------------------------------------------------- APT groups

@dataclass
class APTGroup:
    """Ordered tactic chain emulating a known APT group's TTPs.

    Steps that need manual setup (Initial Access, C2 contact-switching,
    Reconnaissance) are dropped from the chain; the rest reuses the
    auto-runnable tactic pipeline so the platform sees a coherent
    APT-shaped progression in attack_chains.

    Mappings derived from docs/CALDERA_MITRE_SIMULATION_GUIDE.md §6.
    """
    name: str
    paper_note: str
    tactic_chain: list[str]   # ordered tactic labels (must exist in PLAN)
    obfuscator: str = "plain-text"
    notes: str = ""

APT_GROUPS: dict[str, APTGroup] = {
    "APT41": APTGroup(
        name="APT41",
        paper_note="commonly used as backdoor/rootkit; signature exfil over rsync",
        tactic_chain=["Persistence", "Privilege Escalation", "Defense Evasion",
                      "Discovery", "Collection", "Exfiltration"],
        notes="dropped: Initial Access (Apache Struts) + C2 (T1105 wget) — manual setup"),
    "APT28": APTGroup(
        name="APT28",
        paper_note="Sofacy — exploits known CVEs, establishes remote access, "
                   "exfils via curl POST",
        tactic_chain=["Discovery", "Privilege Escalation", "Defense Evasion",
                      "Collection", "Exfiltration"],
        notes="dropped: Reconnaissance (T1595.002) + Initial Access (manual CVE)"),
    "APT29": APTGroup(
        name="APT29",
        paper_note="Cozy Bear — stealthy, custom malware, lateral movement focus",
        tactic_chain=["Persistence", "Defense Evasion", "Lateral Movement",
                      "Privilege Escalation", "Discovery"],
        obfuscator="base64jumble",
        notes="obfuscator=base64jumble for stealth; dropped: phishing initial access + DNS C2"),
    "Turla": APTGroup(
        name="Turla",
        paper_note="Snake/Uroburos — persistence-heavy, credential-focused",
        tactic_chain=["Persistence", "Privilege Escalation", "Credential Access",
                      "Discovery", "Collection", "Defense Evasion"],
        notes="dropped: T1078 valid-accounts initial access (would need pre-seeded SSH creds)"),
}

# --------------------------------------------------------------------- CKC-stage → tactic mapping
#
# The Transformer + DQN were trained on sequences where the CKC stage
# moves *non-monotonically* — e.g. an adversary cycling Recon → Delivery
# → Exploit → Recon → Delivery → Exploit → Recon → Exploit. To exercise
# that behaviour from the lab we need to express stage sequences that
# repeat. Caldera operates at the tactic level (not stage), so each stage
# maps to a representative auto-runnable tactic.
#
# The mapping is intentionally a *lab convention*, not a 1:1 ATT&CK
# definition: stages 2 (Weaponisation) and 6 (C2) have no auto-runnable
# Caldera analogue (the Sandcat agent IS C2; weaponisation is pre-implant),
# so they're approximated by the closest tactic that produces telemetry of
# similar shape on the host.
#
# Use --sequence with explicit tactic labels for full control. Use
# --ckc-stages when you want to think in stage numbers directly.
STAGE_TO_TACTIC: dict[int, str] = {
    1: "Reconnaissance",       # real T1595 alerts via strix_attacker recon_burst
    2: "Defense Evasion",      # weaponisation has no analogue; closest is early-stage hiding
    3: "Defense Evasion",      # delivery — also no analogue post-implant; reuse the early-stage proxy
    4: "Privilege Escalation",
    5: "Persistence",
    6: "Persistence",          # C2 is implicit in Caldera; Persistence keeps the channel warm
    7: "Impact",
}


# Default non-monotonic demo sequence. Picked to:
#   * exercise the forward/backward stage walk the Transformer was trained on
#   * hit ckc=5 (Persistence) twice so the DQN actually crosses its ESCALATE
#     threshold and the dashboard shows real predetections
#   * end on ckc=7 (Impact) so the kill-chain visualisation lights up the
#     "stages 5–7 prevented" badge on the predetection receipt card
# Use --ckc-stages to override.
DEFAULT_NONMONO_STAGES: list[int] = [1, 3, 4, 5, 1, 3, 4, 5, 7]


def stages_to_labels(stages: list[int]) -> list[str]:
    """Translate a CKC stage sequence to tactic labels via STAGE_TO_TACTIC.

    Unknown stages are dropped with a warning (the caller decides how to
    surface that). Repeats are preserved — that's the whole point.
    """
    out: list[str] = []
    for s in stages:
        label = STAGE_TO_TACTIC.get(s)
        if label is None:
            warn(f"--ckc-stages: stage {s} has no auto-runnable tactic — skipped")
            continue
        out.append(label)
    return out


# --------------------------------------------------------------------- not auto-runnable

# Tactics not auto-runnable (need extra setup). Reconnaissance used to live
# here — it now fires from strix_attacker via the recon_burst executor and
# is auto-runnable (see the "Reconnaissance" entry in PLAN above).
NOT_AUTOMATED = [
    ("Initial Access (TA0001 / T1190 Apache Struts)",
     "Requires a vulnerable target container (vulhub) — see "
     "docs/CALDERA_MITRE_SIMULATION_GUIDE.md §5.2"),
    ("Command & Control (TA0011)",
     "Sandcat IS the C2 channel — every op exercises it implicitly."),
]

# --------------------------------------------------------------------- adversary resolution

def find_adversary(cal: Caldera, names: list[str]) -> dict | None:
    """Exact-name match only. Substring matching pulled wrong-platform adversaries
    (e.g. 'Lateral Movement' grabs 'Lateral Movement - Certutil', a Windows pack).
    If exact match fails, callers fall through to platform-aware ad-hoc construction."""
    advs = cal.list_adversaries()
    by_name = {a["name"].lower(): a for a in advs if a.get("name")}
    for n in names:
        a = by_name.get(n.lower())
        if a:
            return a
    return None

def build_adhoc_adversary(cal: Caldera, label: str, technique_ids: list[str]) -> tuple[str | None, list[str]]:
    """
    Build an ad-hoc adversary from abilities matching the given technique IDs,
    filtered to linux executors. Returns (adversary_id, list_of_picked_ability_names).
    """
    abilities = cal.list_abilities()
    picked: list[dict] = []
    picked_names: list[str] = []
    for tid in technique_ids:
        # match T1033 against both "T1033" and "T1033.001" prefixes
        tid_norm = tid.upper()
        for ab in abilities:
            ab_tid = (ab.get("technique_id") or "").upper()
            if ab_tid != tid_norm and not ab_tid.startswith(tid_norm + "."):
                continue
            execs = ab.get("executors", []) or []
            if not any(e.get("platform") in ("linux", "darwin") for e in execs):
                continue
            picked.append(ab); picked_names.append(f"{ab_tid}:{ab.get('name','?')}")
            break  # one ability per technique_id is enough
    if not picked:
        return None, []
    name = f"adhoc-{label.lower().replace(' ','-')}-{int(time.time())}"
    adv_id = cal.create_adhoc_adversary(name, [a["ability_id"] for a in picked])
    return adv_id, picked_names

def resolve_planner(cal: Caldera, name: str = "batch") -> str:
    plans = cal.list_planners()
    for p in plans:
        if p.get("name", "").lower() == name.lower():
            return p["id"]
    if plans:
        warn(f"planner '{name}' not found, falling back to '{plans[0].get('name')}'")
        return plans[0]["id"]
    fail("no planners available — Caldera not initialised correctly")
    return ""  # unreachable

# --------------------------------------------------------------------- per-tactic runner

@dataclass
class TacticResult:
    tactic: Tactic
    adv_resolution: str           # "stockpile:<name>" | "adhoc:<n>abilities" | "skipped:<reason>"
    op_id: str | None
    op_links: int
    op_status_summary: dict[int, int]
    snapshot_before: Snapshot | None
    snapshot_after: Snapshot | None
    duration_s: float
    error: str | None = None

def _write_current_tactic(label: str | None) -> None:
    """Stamp the active tactic into topology.json for downstream watchers
    (monitor_demo.py + playwright_check.py per-tactic screenshot triggers)."""
    run_dir = os.environ.get("STRIX_RUN_DIR", "")
    if not run_dir:
        return
    try:
        topo_path = os.path.join(run_dir, "topology.json")
        if not os.path.exists(topo_path):
            return
        with open(topo_path) as fh:
            existing = json.load(fh)
        if label is None:
            existing.pop("current_tactic", None)
        else:
            existing["current_tactic"] = label
        existing["current_tactic_updated_at"] = datetime.utcnow().isoformat() + "Z"
        with open(topo_path, "w") as fh:
            json.dump(existing, fh, indent=2)
    except Exception:  # noqa: BLE001
        pass  # never let topology IO break the sim


def _run_recon_burst(t: Tactic, dwell_s: int, dry_run: bool) -> TacticResult:
    """Pre-implant Reconnaissance executor — bypasses Caldera.

    Shells into strix_attacker and runs /opt/recon_burst.sh against the
    configured victim list. The resulting nmap + sshd-invalid-user activity
    is what STRIX rules 100050/100051 chain off to attribute T1595.

    Mirrors the bookkeeping `run_tactic`'s Caldera path does — same
    Snapshot before/after, same dwell wait — so the final report's
    per-tactic delta is meaningful.
    """
    targets = [v.strip() for v in RECON_TARGETS if v.strip()]
    if not targets:
        warn(f"{t.label}: RECON_TARGETS is empty — nothing to scan")
        return TacticResult(t, "skipped:no-recon-targets", None, 0, {}, None, None, 0.0)

    if dry_run:
        info(f"DRY-RUN — would exec {RECON_BURST_PATH} {' '.join(targets)}")
        return TacticResult(t, "recon:would-fire", None, 0, {}, None, None, 0.0)

    # Verify the attacker container is reachable. If not, fail soft —
    # better to skip the recon phase than to abort the whole sim.
    chk = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=10,
    )
    if ATTACKER_CONTAINER not in (chk.stdout or "").splitlines():
        warn(f"{t.label}: container '{ATTACKER_CONTAINER}' not running — skipping. "
             f"Bring up the lab via `docker compose -f infra/compose.simulation.yml up -d`.")
        return TacticResult(t, f"skipped:no-{ATTACKER_CONTAINER}", None, 0, {}, None, None, 0.0)

    before = take_snapshot()
    info(f"baseline:  alerts={before.pg_alerts}  detections={before.pg_detections}  "
         f"chains={before.pg_chains}  max_ckc={before.pg_max_ckc}  xlen={before.redis_xlen}")

    op_name = f"recon-burst-{int(time.time())}"
    t0 = time.time()
    info(f"firing recon burst from {ATTACKER_CONTAINER} → {', '.join(targets)}")
    try:
        # Stream stdout so the burst's progress lines interleave with the
        # main runner's logs — same UX as Caldera's poll loop.
        proc = subprocess.Popen(
            ["docker", "exec", ATTACKER_CONTAINER, "bash", RECON_BURST_PATH, *targets],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        if proc.stdout is not None:
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    info(line)
        rc = proc.wait()
        if rc != 0:
            warn(f"recon burst exited rc={rc}")
    except Exception as exc:  # noqa: BLE001
        warn(f"recon burst failed: {exc}")
        return TacticResult(t, "recon:failed", None, 0, {}, before, take_snapshot(),
                            time.time() - t0, error=str(exc))

    info(f"dwell {dwell_s}s for pipeline drain")
    time.sleep(dwell_s)

    after = take_snapshot()
    duration = time.time() - t0
    print(f"\n  {C.BLD}delta over {duration:.0f}s:{C.X}")
    print(diff_table(before, after))
    return TacticResult(
        t, f"recon:burst({op_name})", None,
        # `links` field reused as "probe count fired" — the burst doesn't
        # have Caldera links, but the metric slot is still useful.
        len(targets),
        {},
        before, after, duration,
    )


def run_tactic(cal: Caldera, t: Tactic, planner_id: str, group: str,
               budget_s: int, dwell_s: int, obfuscator_override: str | None,
               dry_run: bool) -> TacticResult:
    section(f"TACTIC: {t.label}  ({t.paper_tactic_id})")
    print(f"  techniques: {', '.join(t.technique_ids)}")
    if t.notes: print(f"  notes:      {t.notes}")
    _write_current_tactic(t.label)

    # Custom executor: bypass Caldera entirely. Used for Reconnaissance
    # which fires from strix_attacker rather than from a Sandcat agent.
    if t.custom_executor == "recon_burst":
        return _run_recon_burst(t, dwell_s, dry_run)

    obfuscator = obfuscator_override or t.obfuscator

    # 1. resolve adversary
    adv = find_adversary(cal, t.stockpile_names)
    if adv:
        adv_id = adv["adversary_id"]
        resolution = f"stockpile:{adv['name']}"
        ok(f"using stockpile adversary: {adv['name']}  ({adv_id})")
    else:
        info(f"stockpile {t.stockpile_names} not found — building ad-hoc from technique IDs")
        if dry_run:
            return TacticResult(t, "adhoc:would-build", None, 0, {}, None, None, 0.0)
        adv_id, picked = build_adhoc_adversary(cal, t.label, t.technique_ids)
        if not adv_id:
            warn(f"no linux abilities for {t.technique_ids} — skipping")
            return TacticResult(t, f"skipped:no-linux-abilities-for-{','.join(t.technique_ids)}",
                                None, 0, {}, None, None, 0.0)
        resolution = f"adhoc:{len(picked)}abilities"
        ok(f"built ad-hoc adversary  ({adv_id})  with: {', '.join(picked[:6])}"
           + (f", +{len(picked)-6} more" if len(picked) > 6 else ""))

    if dry_run:
        info(f"DRY-RUN — would launch {t.label} with obfuscator={obfuscator}")
        return TacticResult(t, resolution, None, 0, {}, None, None, 0.0)

    # 2. baseline snapshot
    before = take_snapshot()
    info(f"baseline:  alerts={before.pg_alerts}  detections={before.pg_detections}  "
         f"chains={before.pg_chains}  max_ckc={before.pg_max_ckc}  xlen={before.redis_xlen}")

    # 3. launch op
    op_name = f"sim-{t.label.lower().replace(' ', '-')}-{int(time.time())}"
    t0 = time.time()
    try:
        op_id = cal.launch_op(op_name, adv_id, planner_id, group, obfuscator=obfuscator)
        ok(f"launched op  name={op_name}  id={op_id}  obfuscator={obfuscator}")
    except RuntimeError as e:
        warn(f"launch failed: {e}")
        return TacticResult(t, resolution, None, 0, {}, before, take_snapshot(),
                            time.time() - t0, error=str(e))

    # 4. poll until budget exhausted OR state==finished OR RL ESCALATE
    poll_every = 6
    last_links = 0
    intervened_on: set[str] = set()
    while time.time() - t0 < budget_s:
        op = cal.get_op(op_id)
        chain = op.get("chain", []) or []
        n = len(chain)
        state = op.get("state", "?")
        if n != last_links:
            last_link = chain[-1] if chain else {}
            ab = last_link.get("ability", {}) or {}
            tid = ab.get("technique_id", "")
            nm = ab.get("name", "")[:40]
            host = (last_link.get("host") or "?")[:14]
            stat = last_link.get("status", "?")
            info(f"links={n:<3d} state={state:<10s} latest: [{host}] {tid:<10s} {nm}  rc={stat}")
            last_links = n
        if state in ("finished", "out_of_time", "cleanup"):
            break
        # RL containment: if the DQN has ESCALATE'd on any host this op
        # has touched (or is targeting), stop the op early — the agent's
        # decision is the whole point, honour it at the attack source.
        contained = contained_hosts()
        if contained:
            op_hosts = {(l.get("host") or "") for l in chain}
            op_hosts.discard("")
            hit = contained & op_hosts
            if hit:
                intervened_on = hit
                warn(f"RL ESCALATE on {sorted(hit)} — stopping op {op_id} early")
                # Stop the op first so the kill is real, then mark the
                # pending intervention rows applied — order matters for
                # honesty: applied=true should imply Caldera was killed.
                try:
                    cal.stop_op(op_id)
                except RuntimeError as e:  # noqa: BLE001
                    info(f"stop op rc: {e}")
                applied_n = mark_interventions_applied(hit)
                if applied_n:
                    info(f"marked {applied_n} pending action(s) applied for {sorted(hit)}")
                break
        time.sleep(poll_every)

    # 5. stop op (idempotent)
    try:
        cal.stop_op(op_id)
        info("op stopped")
    except RuntimeError as e:
        info(f"stop op rc: {e}")

    # 6. dwell — let pipeline drain
    info(f"dwell {dwell_s}s for pipeline drain")
    time.sleep(dwell_s)

    # 7. final op state
    op = cal.get_op(op_id)
    chain = op.get("chain", []) or []
    by_status: dict[int, int] = {}
    for link in chain:
        s = link.get("status", -99)
        try: s = int(s)
        except (TypeError, ValueError): s = -99
        by_status[s] = by_status.get(s, 0) + 1

    after = take_snapshot()
    duration = time.time() - t0

    # 8. report tactic delta
    print(f"\n  {C.BLD}delta over {duration:.0f}s:{C.X}")
    print(diff_table(before, after))
    print(f"\n  {C.BLD}link statuses:{C.X}  " +
          "  ".join(f"rc={s}:{n}" for s, n in sorted(by_status.items())))

    if intervened_on:
        resolution = f"{resolution}|rl-contained:{','.join(sorted(intervened_on))}"
    return TacticResult(t, resolution, op_id, len(chain), by_status, before, after, duration)

# --------------------------------------------------------------------- final report

def final_report(results: list[TacticResult], grand_before: Snapshot, grand_after: Snapshot) -> None:
    section("FINAL REPORT")

    # grand totals
    print(f"{C.BLD}Total platform delta:{C.X}")
    print(diff_table(grand_before, grand_after))
    print(f"\n  wallclock:  {(grand_after.wall_ts - grand_before.wall_ts):.0f}s")

    # per-tactic table
    print(f"\n{C.BLD}Per-tactic results:{C.X}")
    print(f"  {'tactic':<22s} {'resolution':<28s} {'links':>6s} {'detns Δ':>8s} {'ckc Δ':>6s} {'dur':>5s}")
    for r in results:
        if not r.snapshot_before or not r.snapshot_after:
            line = (f"  {r.tactic.label:<22s} {r.adv_resolution:<28s} "
                    f"{'-':>6s} {'-':>8s} {'-':>6s} {'-':>5s}")
        else:
            d_det = r.snapshot_after.pg_detections - r.snapshot_before.pg_detections
            d_ckc = r.snapshot_after.pg_max_ckc    - r.snapshot_before.pg_max_ckc
            line = (f"  {r.tactic.label:<22s} {r.adv_resolution[:28]:<28s} "
                    f"{r.op_links:>6d} {d_det:>+8d} {d_ckc:>+6d} {r.duration_s:>4.0f}s")
        print(line)

    # Baseline for run-scoped queries — falls back to "all time" if the
    # snapshot didn't capture a PG timestamp (e.g. PG was unreachable).
    since = grand_before.pg_now or ""
    since_clause = f"WHERE decided_at > '{since}'" if since else ""
    chain_since   = f"WHERE created_at > '{since}'" if since else ""

    # DQN action distribution — scoped to THIS run.
    print(f"\n{C.BLD}DQN action mix (this run):{C.X}")
    rows = _psql_rows(f"SELECT action_name, COUNT(*) FROM dqn_actions {since_clause} "
                      "GROUP BY action_name ORDER BY COUNT(*) DESC;")
    if rows:
        for name, cnt in rows:
            print(f"  {name:<22s} {int(cnt):>6d}")
    else:
        warn("no dqn_actions rows in this run window")

    # CKC stage histogram — only chains opened during this run.
    print(f"\n{C.BLD}Attack-chain CKC stage histogram (this run):{C.X}")
    rows = _psql_rows(f"SELECT max_ckc_stage, COUNT(*) FROM attack_chains {chain_since} "
                      "GROUP BY max_ckc_stage ORDER BY max_ckc_stage;")
    if rows:
        for stage, cnt in rows:
            print(f"  stage {int(stage)}: {int(cnt):>5d} chains")
    else:
        warn("no attack_chains rows in this run window")

    # top rule.id producers (last 10 min)
    print(f"\n{C.BLD}Top Wazuh rule_id (last 10 min):{C.X}")
    out = docker_exec(WAZUH_CONTAINER, "bash", "-c",
                      "tail -2000 /var/ossec/logs/alerts/alerts.json 2>/dev/null", check=False)
    by_rule: dict[str, int] = {}
    for line in out.splitlines()[-2000:]:
        try:
            j = json.loads(line)
        except Exception:
            continue
        rid = (j.get("rule") or {}).get("id", "?")
        by_rule[rid] = by_rule.get(rid, 0) + 1
    for rid, n in sorted(by_rule.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  rule {rid:>6s}: {n:>5d}")

    print()
    section("DONE")
    print(f"{C.D}Tip: tail Wazuh alerts:{C.X}  "
          f"docker exec -it {WAZUH_CONTAINER} tail -f {ALERTS_PATH}")
    print(f"{C.D}Tip: query detections:{C.X}  "
          f"docker exec -it {PG_CONTAINER} psql -U {PG_USER} {PG_DB} "
          f"-c 'SELECT alert_id, ae_anomaly_score, vae_malicious_prob FROM detections ORDER BY occurred_at DESC LIMIT 20;'")
    print()

# --------------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list",        action="store_true", help="list stockpile adversaries + planners + agents and exit")
    p.add_argument("--list-apts",   action="store_true", help="list APT-group chains and exit")
    p.add_argument("--report-only", action="store_true", help="print current platform metrics and exit")
    p.add_argument("--dry-run",     action="store_true", help="resolve plan, don't fire any ops")
    p.add_argument("--no-preflight",action="store_true", help="skip preflight checks (use after manual verify)")
    p.add_argument("--apt",         type=str, default="",
                   help=f"emulate one APT group's tactic chain "
                        f"(choices: {','.join(APT_GROUPS)},all). Overrides --only/--skip ordering.")
    p.add_argument("--sequence",    type=str, default="",
                   help="Custom non-monotonic tactic sequence — comma-separated tactic "
                        "labels in any order, repeats allowed. Example: "
                        "'Discovery,Persistence,Discovery,Defense Evasion,Persistence,"
                        "Lateral Movement'. Each entry fires a fresh Caldera op; the "
                        "chain matcher appends to the same attack_chain so the "
                        "Transformer sees the full non-monotonic stage walk. "
                        "Mutually exclusive with --apt.")
    p.add_argument("--ckc-stages",  type=str, default="",
                   help="Custom CKC stage sequence — comma-separated stage integers "
                        "(1..7), repeats allowed. Example: '1,3,4,1,3,4,1,4'. Each "
                        "stage maps to a representative auto-runnable tactic via "
                        "STAGE_TO_TACTIC; see the module docstring for the mapping. "
                        "Mutually exclusive with --apt, --sequence, and --non-monotonic.")
    p.add_argument("--non-monotonic", action="store_true",
                   help=f"Curated forward/backward kill-chain demo. Equivalent to "
                        f"--ckc-stages '{','.join(str(s) for s in DEFAULT_NONMONO_STAGES)}' — "
                        f"exercises the non-monotonic stage walk the Transformer was "
                        f"trained on AND crosses the DQN's ESCALATE threshold so the "
                        f"dashboard's RL Intervention Timeline lights up.")
    p.add_argument("--only",        type=str, default="", help="comma-sep tactic labels to include")
    p.add_argument("--skip",        type=str, default="", help="comma-sep tactic labels to skip")
    p.add_argument("--budget",      type=int, default=90,  help="per-tactic op budget in seconds (default 90)")
    p.add_argument("--dwell",       type=int, default=30,  help="drain wait between tactics in seconds (default 30)")
    p.add_argument("--obfuscator",  type=str, default="",  help="global obfuscator override: plain-text|base64|base64jumble|caesar cipher")
    p.add_argument("--planner",     type=str, default="batch", help="planner name (default batch)")
    p.add_argument("--group",       type=str, default=CALDERA_GROUP, help=f"caldera agent group (default {CALDERA_GROUP})")
    args = p.parse_args()

    section("STRIX FULL SIMULATION")
    print(f"  caldera:    {CALDERA_URL}")
    print(f"  group:      {args.group}")
    print(f"  budget:     {args.budget}s/tactic   dwell: {args.dwell}s")
    print(f"  planner:    {args.planner}")
    if args.obfuscator: print(f"  obfuscator: {args.obfuscator} (override)")

    token = resolve_caldera_token(CALDERA_CONTAINER)
    cal = Caldera(CALDERA_URL, token)

    # --list
    if args.list:
        section("CALDERA INVENTORY")
        print(f"{C.BLD}Adversaries:{C.X}")
        for a in cal.list_adversaries():
            print(f"  {a.get('adversary_id','?')}  {a.get('name','?')}")
        print(f"\n{C.BLD}Planners:{C.X}")
        for pl in cal.list_planners():
            print(f"  {pl.get('id','?')}  {pl.get('name','?')}")
        print(f"\n{C.BLD}Agents:{C.X}")
        for ag in cal.list_agents():
            print(f"  paw={ag.get('paw','?'):<10s} group={ag.get('group','?'):<8s} "
                  f"host={ag.get('host','?'):<14s} platform={ag.get('platform','?'):<8s} "
                  f"last_seen={ag.get('last_seen','?')}")
        return 0

    # --list-apts
    if args.list_apts:
        section("APT GROUP CHAINS")
        for g in APT_GROUPS.values():
            print(f"\n{C.BLD}{g.name}{C.X}  — {g.paper_note}")
            print(f"  obfuscator: {g.obfuscator}")
            print(f"  chain: {' → '.join(g.tactic_chain)}")
            if g.notes: print(f"  {C.D}{g.notes}{C.X}")
        return 0

    # --report-only
    if args.report_only:
        section("CURRENT PLATFORM STATE")
        s = take_snapshot()
        print(f"  redis xlen ({REDIS_STREAM}):  {s.redis_xlen}")
        print(f"  wazuh alerts.json lines:        {s.wazuh_alert_lines}")
        print(f"  pg alerts:                      {s.pg_alerts}")
        print(f"  pg detections:                  {s.pg_detections}")
        print(f"  pg attack_chains:               {s.pg_chains}  (open: {s.pg_chains_open})")
        print(f"  pg max ckc stage reached:       {s.pg_max_ckc}")
        print(f"  pg dqn_actions:                 {s.pg_dqn}")
        return 0

    # preflight
    if not args.no_preflight:
        preflight(cal, args.group)

    # planner
    planner_id = resolve_planner(cal, args.planner)
    info(f"planner: {args.planner}  id={planner_id}")

    # tactic filtering — APT mode reorders the plan; --only/--skip subsets it.
    # Mutual exclusion: --apt | --sequence | --ckc-stages | --non-monotonic
    # are four different ways to drive the plan; pick at most one.
    mode_count = sum(
        bool(x)
        for x in (args.apt, args.sequence, args.ckc_stages, args.non_monotonic)
    )
    if mode_count > 1:
        fail("--apt, --sequence, --ckc-stages, and --non-monotonic are mutually "
             "exclusive — pick one.")

    # `--non-monotonic` is just a curated default for `--ckc-stages`; promote
    # it before the dispatcher so downstream code only sees one path.
    if args.non_monotonic:
        args.ckc_stages = ",".join(str(s) for s in DEFAULT_NONMONO_STAGES)

    by_label = {t.label.lower(): t for t in PLAN}
    apt_runs: list[APTGroup]
    plan: list[Tactic]

    if args.sequence or args.ckc_stages:
        # Custom non-monotonic sequence. Repetition is the whole point —
        # bypass the dedup that the named-APT path applies. Each entry in
        # the sequence becomes a separate Caldera op; the chain matcher
        # appends them all to one attack_chain (within idle timeout) so
        # the Transformer sees a non-monotonic per-event ckc_stage walk.
        if args.ckc_stages:
            try:
                stages = [int(s.strip()) for s in args.ckc_stages.split(",") if s.strip()]
            except ValueError:
                fail(f"--ckc-stages: expected comma-separated integers, got {args.ckc_stages!r}")
            labels = stages_to_labels(stages)
            sequence_source = f"ckc-stages={','.join(str(s) for s in stages)}"
        else:
            labels = [s.strip() for s in args.sequence.split(",") if s.strip()]
            sequence_source = f"sequence={','.join(labels)}"

        if not labels:
            fail("custom sequence resolved to zero runnable tactics — nothing to do.")

        plan = []
        for label in labels:
            t = by_label.get(label.lower())
            if not t:
                warn(f"sequence: tactic '{label}' not in PLAN — skipped "
                     f"(available: {[x.label for x in PLAN]})")
                continue
            plan.append(t)
        if not plan:
            fail("none of the requested tactics matched PLAN.")

        apt_runs = [APTGroup(
            name="custom",
            paper_note=f"non-monotonic sequence ({sequence_source})",
            tactic_chain=[t.label for t in plan],
            obfuscator=args.obfuscator or "plain-text",
            notes="custom sequence — repeats preserved; chain matcher will append "
                  "all firings to the same attack_chain within idle timeout.",
        )]

    elif args.apt:
        if args.apt.lower() == "all":
            apt_runs = list(APT_GROUPS.values())
        else:
            grp = APT_GROUPS.get(args.apt) or APT_GROUPS.get(args.apt.upper())
            if not grp:
                fail(f"--apt: unknown group '{args.apt}'. "
                     f"Choices: {','.join(APT_GROUPS)},all")
            apt_runs = [grp]
        # build the plan as the union of the chains, in order, deduped
        plan = []
        seen: set[str] = set()
        for g in apt_runs:
            for label in g.tactic_chain:
                t = by_label.get(label.lower())
                if not t:
                    warn(f"APT {g.name}: tactic '{label}' not in PLAN — skipped")
                    continue
                # don't dedupe across APT groups — we WANT to re-fire if multiple
                # APTs were requested, since each replay extends attack_chains.
                key = f"{g.name}:{label}"
                if key in seen: continue
                seen.add(key)
                plan.append(t)
        if not args.obfuscator and len(apt_runs) == 1:
            args.obfuscator = apt_runs[0].obfuscator
    else:
        apt_runs = []
        plan = list(PLAN)

    if args.only:
        wanted = {x.strip().lower() for x in args.only.split(",") if x.strip()}
        plan = [t for t in plan if t.label.lower() in wanted]
        if not plan: fail(f"--only matched no tactics. Available: {[t.label for t in PLAN]}")
    if args.skip:
        skip = {x.strip().lower() for x in args.skip.split(",") if x.strip()}
        plan = [t for t in plan if t.label.lower() not in skip]

    section("EXECUTION PLAN")
    if apt_runs:
        for g in apt_runs:
            print(f"  {C.BLD}APT chain — {g.name}:{C.X}  {' → '.join(g.tactic_chain)}")
            print(f"    {C.D}{g.paper_note}{C.X}")
        print()
    for t in plan:
        print(f"  • {t.label:<22s}  techniques={','.join(t.technique_ids)}")
    if NOT_AUTOMATED and not apt_runs:
        print(f"\n{C.D}Not auto-runnable (manual setup required):{C.X}")
        for label, why in NOT_AUTOMATED:
            print(f"  - {label}\n    {C.D}{why}{C.X}")

    # Refine topology.json with the actual filtered plan (the wrapper writes
    # an initial copy with the full PLAN list — overwrite with the real one
    # so consumers see ground truth, not the catalog).
    run_dir = os.environ.get("STRIX_RUN_DIR", "")
    if run_dir:
        try:
            topo_path = os.path.join(run_dir, "topology.json")
            existing = {}
            if os.path.exists(topo_path):
                with open(topo_path) as fh:
                    existing = json.load(fh)
            existing["tactics_planned"] = [t.label for t in plan]
            # Per-tactic technique catalogue so monitor_demo.py can
            # cross-check observed alerts against the planned techniques
            # and report match-rate per tactic.
            existing["tactic_techniques"] = {
                t.label: list(t.technique_ids) for t in plan
            }
            if args.apt:
                existing["apt_group"] = args.apt
            with open(topo_path, "w") as fh:
                json.dump(existing, fh, indent=2)
            info(f"topology.json updated with {len(plan)} planned tactics")
        except Exception as e:  # noqa: BLE001
            warn(f"could not refine topology.json: {e}")

    grand_before = take_snapshot()
    # Mark the run cutoff so contained_hosts() ignores ESCALATEs from
    # prior runs that are still in dqn_actions.
    global RUN_START_TS
    RUN_START_TS = grand_before.pg_now or ""

    results: list[TacticResult] = []
    try:
        for t in plan:
            # Honour earlier RL ESCALATE: skip a tactic when every host it
            # would target is already contained.
            contained = contained_hosts() if not args.dry_run else set()
            if contained:
                if t.custom_executor == "recon_burst":
                    targets = {v.strip() for v in RECON_TARGETS if v.strip()}
                else:
                    targets = group_hostnames(cal, args.group)
                if targets and targets.issubset(contained):
                    section(f"TACTIC: {t.label}  ({t.paper_tactic_id})")
                    warn(f"all targets {sorted(targets)} contained by RL — "
                         f"skipping {t.label}")
                    results.append(TacticResult(
                        t, f"skipped:rl-contained({','.join(sorted(contained & targets))})",
                        None, 0, {}, None, None, 0.0,
                    ))
                    continue
            r = run_tactic(cal, t, planner_id, args.group,
                           args.budget, args.dwell,
                           args.obfuscator or None, args.dry_run)
            results.append(r)
    except KeyboardInterrupt:
        warn("interrupted — generating report with what we have")

    grand_after = take_snapshot()
    if not args.dry_run:
        final_report(results, grand_before, grand_after)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        fail(str(e))
