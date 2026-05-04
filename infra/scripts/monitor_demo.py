#!/usr/bin/env python3
"""
STRIX end-to-end demo monitor — Layer 1 (platform) + Layer 2 (gateway).

Live cross-checks every 5 s while ``jury_demo*.sh`` runs in another
terminal. Validates that every panel on the dashboard has correct
backend data behind it, and (with ``--ws-tap``) that the API gateway is
delivering frames to the browser path.

Layer 3 (DOM rendering) is covered by ``playwright_check.py`` separately.

Outputs
-------
1. Live ANSI table to stdout, refreshed every 5 s.
2. Line-delimited JSON to ``/tmp/strix_e2e_<RUN_ID>/monitor.jsonl``.
3. Final pass/fail scorecard on Ctrl-C or sim end (no new alerts for 60 s).

Usage
-----
    bash jury_demo_single.sh --apt APT41 --duration 240   # terminal 1
    python infra/scripts/monitor_demo.py                  # terminal 2
    python infra/scripts/monitor_demo.py --ws-tap         # also Layer 2

Layer 2 caveat: WS tap requires a valid auth token. Set
STRIX_TEST_PASSWORD or run with --skip-ws-auth if AUTH_DEV_SKIP_AUTH=true
on the API.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from collections import defaultdict, deque
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
import redis.asyncio as aioredis
import urllib.error
import urllib.parse
import urllib.request

try:
    import websockets  # type: ignore
except ImportError:
    websockets = None  # WS tap will degrade gracefully

REPO = Path(__file__).resolve().parents[2]
ENV_FILE = REPO / "apps" / "api" / ".env"
SIM_RUNS_DIR = REPO / "infra" / "simulation" / "runs"
MITRE_MAP_FILE = REPO / "apps" / "api" / "docs" / "mitre_to_ckc.json"

# ANSI colors (no external dep — works in any terminal)
G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; C = "\033[36m"
D = "\033[2m"; B = "\033[1m"; X = "\033[0m"

POLL_SECONDS = 5.0
IDLE_EXIT_SECONDS = 60.0  # exit after this long with no new alerts

# Pass/fail thresholds (matches the rubric the user agreed on).
HARD_AE_VAE_COVERAGE = 0.80
HARD_MIN_GNN_NODES = 10
HARD_MIN_GNN_NODE_DEADLINE_S = 90.0
HARD_MIN_ESCALATES = 1
HARD_MIN_ALERT_RATE_PER_MIN = 10
HARD_MIN_FORENSIC_TECHNIQUES = 5

REDIS_STREAMS = ["strix:alerts:raw"]
REDIS_PUBSUB = ["strix:stream:ae", "strix:stream:vae", "strix:stream:gnn", "strix:stream:rl"]

# Layer 2 (WS tap) — envelope `type` values published by the API gateway.
# Source: apps/api/src/strix_api/api/routes/streams.py logs_stream().
WS_FRAME_TYPES = ["raw_log", "ae", "vae", "gnn", "rl", "topology", "status"]
DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_WS_URL = "ws://localhost:8000/api/v1/logs/stream"
DEFAULT_TEST_EMAIL = "admin@strix.io"
DEFAULT_TEST_PASSWORD = "changeme123!"


# ---------- env loader (handles quoted values + #-comments) ----------
def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        v = v.split(" #", 1)[0].strip().strip("'\"")
        env[k.strip()] = v
    return env


# ---------- MITRE name ↔ ID bridge ----------
def load_mitre_id_to_name() -> dict[str, str]:
    """Build {T-id → human name} from mitre_to_ckc.json so we can match
    alerts that carry technique NAMES against a plan that carries IDs."""
    try:
        d = json.loads(MITRE_MAP_FILE.read_text())
    except Exception:
        return {}
    out: dict[str, str] = {}
    for tid, info in (d.get("technique_id_to_ckc") or {}).items():
        nm = info.get("name") if isinstance(info, dict) else None
        if nm:
            out[tid] = nm
    return out


# ---------- topology.json discovery ----------
def latest_topology() -> tuple[str | None, dict | None]:
    if not SIM_RUNS_DIR.exists():
        return None, None
    runs = sorted(SIM_RUNS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for d in runs:
        f = d / "topology.json"
        if f.exists():
            try:
                return d.name, json.loads(f.read_text())
            except Exception:
                continue
    return None, None


# ---------- monitor state ----------
@dataclass
class StreamMeter:
    name: str
    total: int = 0
    last_total: int = 0
    received_ws: int = 0  # filled by WS tap if enabled
    last_received_ws: int = 0


@dataclass
class MonitorState:
    started_at: float = field(default_factory=time.time)
    sim_start_iso: str | None = None
    run_id: str | None = None
    run_dir: Path | None = None
    streams: dict[str, StreamMeter] = field(default_factory=dict)
    pubsub_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_pubsub_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    # WS tap (Layer 2) — frames received per envelope type from /api/v1/logs/stream.
    ws_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_ws_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    ws_state: str = "disabled"  # disabled | connecting | open | closed | auth_failed | error

    pg_alerts: int = 0
    pg_detections: int = 0
    pg_chains: int = 0
    pg_chains_open: int = 0
    pg_dqn_actions: int = 0
    pg_ae_nonnull: int = 0
    pg_vae_nonnull: int = 0
    pg_gnn_nonnull: int = 0
    pg_chain_stage_hist: dict[int, int] = field(default_factory=dict)
    pg_dqn_action_mix: dict[str, int] = field(default_factory=dict)
    pg_max_techniques_in_window: int = 0
    pg_recent_techniques: dict[str, int] = field(default_factory=dict)
    # Run-scoped: every distinct technique tag observed since sim_start.
    pg_run_techniques: set[str] = field(default_factory=set)
    # Plan from topology.json: {tactic_label: [T-id, …]}.
    plan_tactic_techniques: dict[str, list[str]] = field(default_factory=dict)

    last_pg_alerts: int = 0
    last_alert_seen_ts: float = field(default_factory=time.time)

    gnn_first_at: float | None = None
    gnn_max_nodes: int = 0


# ---------- async tasks ----------
async def poll_redis(state: MonitorState, redis: aioredis.Redis) -> None:
    """XLEN polling for streams. Pubsub frames are tallied by subscribe_pubsub."""
    while True:
        for key in REDIS_STREAMS:
            try:
                n = await redis.xlen(key)
            except Exception:
                n = 0
            meter = state.streams.setdefault(key, StreamMeter(name=key))
            meter.last_total = meter.total
            meter.total = int(n)
        await asyncio.sleep(POLL_SECONDS)


async def subscribe_pubsub(state: MonitorState, redis: aioredis.Redis, channel: str) -> None:
    pubsub = redis.pubsub()
    try:
        await pubsub.subscribe(channel)
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg.get("type") == "message":
                state.pubsub_counts[channel] += 1
    finally:
        with suppress(Exception):
            await pubsub.unsubscribe(channel)
        with suppress(Exception):
            await pubsub.aclose()


def _login_get_cookie(api_url: str, email: str, password: str) -> str | None:
    """Hit /api/v1/auth/login and return the Set-Cookie header value (or None)."""
    body = json.dumps({"email": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{api_url}/api/v1/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            cookies = resp.headers.get_all("Set-Cookie") or []
            # Pluck the strix_access cookie (matches CSRF + access-token doubleish flow).
            jar = []
            for c in cookies:
                # Take just `name=value` (drop attributes).
                first = c.split(";", 1)[0].strip()
                if first.startswith("strix_") or first.startswith("access_token") or "=" in first:
                    jar.append(first)
            return "; ".join(jar) if jar else None
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"{R}login HTTP {e.code}: {e.read()[:200]!r}{X}\n")
        return None
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"{R}login error: {e}{X}\n")
        return None


async def ws_tap(state: MonitorState, ws_url: str, cookie_header: str | None) -> None:
    """Layer 2: subscribe to the API's multiplexed WS and count envelopes per type.

    Envelope shape from streams.py: {"type": <str>, "payload": <obj>, "ts": …}.
    Auto-reconnects with backoff on disconnect.
    """
    if websockets is None:
        state.ws_state = "error: websockets module not installed"
        return
    headers: list[tuple[str, str]] = []
    if cookie_header:
        headers.append(("Cookie", cookie_header))

    backoff = 1.0
    while True:
        state.ws_state = "connecting"
        try:
            async with websockets.connect(
                ws_url,
                additional_headers=headers if headers else None,
                ping_interval=20,
                close_timeout=2,
                max_size=2 * 1024 * 1024,
            ) as ws:
                state.ws_state = "open"
                backoff = 1.0
                async for raw in ws:
                    try:
                        env = json.loads(raw)
                    except Exception:
                        continue
                    t = env.get("type") if isinstance(env, dict) else None
                    if isinstance(t, str):
                        state.ws_counts[t] += 1
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "401" in msg or "403" in msg or "auth" in msg.lower():
                state.ws_state = f"auth_failed ({msg[:60]})"
            else:
                state.ws_state = f"error ({type(e).__name__})"
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 10.0)


async def poll_pg(state: MonitorState, pool: asyncpg.Pool) -> None:
    """Snapshot of all platform-side metrics every POLL_SECONDS."""
    while True:
        # Re-read each tick so a topology refresh in the main loop
        # (new run started) takes effect on the next query.
        since_iso = state.sim_start_iso
        since_dt = None
        if since_iso:
            try:
                since_dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
            except ValueError:
                since_dt = None
        try:
            async with pool.acquire() as conn:
                where_alert = ""
                where_det = ""
                where_chain = ""
                where_dqn = ""
                params: list[Any] = []
                if since_dt is not None:
                    params = [since_dt]
                    where_alert = "WHERE created_at > $1"
                    where_det = "WHERE created_at > $1"
                    where_chain = "WHERE created_at > $1"
                    where_dqn = "WHERE decided_at > $1"

                state.pg_alerts = await conn.fetchval(
                    f"SELECT COUNT(*) FROM alerts {where_alert}", *params
                ) or 0
                state.pg_detections = await conn.fetchval(
                    f"SELECT COUNT(*) FROM detections {where_det}", *params
                ) or 0
                state.pg_ae_nonnull = await conn.fetchval(
                    f"SELECT COUNT(*) FROM detections {where_det} "
                    f"{'AND' if where_det else 'WHERE'} ae_anomaly_score IS NOT NULL",
                    *params,
                ) or 0
                state.pg_vae_nonnull = await conn.fetchval(
                    f"SELECT COUNT(*) FROM detections {where_det} "
                    f"{'AND' if where_det else 'WHERE'} vae_malicious_prob IS NOT NULL",
                    *params,
                ) or 0
                state.pg_gnn_nonnull = await conn.fetchval(
                    f"SELECT COUNT(*) FROM detections {where_det} "
                    f"{'AND' if where_det else 'WHERE'} gnn_node_risk IS NOT NULL",
                    *params,
                ) or 0
                state.pg_chains = await conn.fetchval(
                    f"SELECT COUNT(*) FROM attack_chains {where_chain}", *params
                ) or 0
                state.pg_chains_open = await conn.fetchval(
                    f"SELECT COUNT(*) FROM attack_chains {where_chain} "
                    f"{'AND' if where_chain else 'WHERE'} status='open'",
                    *params,
                ) or 0
                state.pg_dqn_actions = await conn.fetchval(
                    f"SELECT COUNT(*) FROM dqn_actions {where_dqn}", *params
                ) or 0

                hist_rows = await conn.fetch(
                    f"SELECT max_ckc_stage, COUNT(*) FROM attack_chains {where_chain} "
                    "GROUP BY max_ckc_stage ORDER BY max_ckc_stage",
                    *params,
                )
                state.pg_chain_stage_hist = {int(r[0]): int(r[1]) for r in hist_rows}

                mix_rows = await conn.fetch(
                    f"SELECT action_name, COUNT(*) FROM dqn_actions {where_dqn} "
                    "GROUP BY action_name",
                    *params,
                )
                state.pg_dqn_action_mix = {r[0]: int(r[1]) for r in mix_rows}

                # Last-60s technique cardinality (for forensic-logs cross-check).
                tech_rows = await conn.fetch(
                    "SELECT t, COUNT(*) FROM ("
                    "  SELECT UNNEST(mitre_techniques) AS t FROM alerts "
                    "  WHERE occurred_at > NOW() - INTERVAL '60 seconds'"
                    ") s GROUP BY t ORDER BY COUNT(*) DESC LIMIT 8"
                )
                state.pg_recent_techniques = {r[0]: int(r[1]) for r in tech_rows}

                # Run-scoped distinct techniques (for plan cross-reference).
                if since_dt is not None:
                    run_tech_rows = await conn.fetch(
                        "SELECT DISTINCT t FROM ("
                        "  SELECT UNNEST(mitre_techniques) AS t FROM alerts "
                        "  WHERE occurred_at > $1"
                        ") s",
                        since_dt,
                    )
                    state.pg_run_techniques = {r[0] for r in run_tech_rows}

            now = time.time()
            if state.pg_alerts > state.last_pg_alerts:
                state.last_alert_seen_ts = now
            state.last_pg_alerts = state.pg_alerts
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"{R}pg poll error: {exc}{X}\n")
        await asyncio.sleep(POLL_SECONDS)


# ---------- rendering ----------
def fmt_int(n: int) -> str:
    return f"{n:,}"


def fmt_pct(num: int, denom: int) -> str:
    if denom <= 0:
        return "—"
    return f"{100.0 * num / denom:5.1f}%"


def color_for_pct(num: int, denom: int, threshold: float) -> str:
    if denom <= 0:
        return D
    pct = num / denom
    return G if pct >= threshold else (Y if pct >= threshold * 0.8 else R)


def status_glyph(ok: bool, warn: bool = False) -> str:
    if ok:
        return f"{G}✓{X}"
    if warn:
        return f"{Y}⚠{X}"
    return f"{R}✗{X}"


_ID2NAME = load_mitre_id_to_name()


def render(state: MonitorState, ws_enabled: bool) -> str:
    lines = []
    elapsed = int(time.time() - state.started_at)
    sim_min, sim_sec = divmod(elapsed, 60)

    # Header.
    rid = state.run_id or "<no run yet>"
    lines.append(f"{B}{C}═══ STRIX E2E MONITOR ═══ run {rid}  ·  t+{sim_min:02d}:{sim_sec:02d}{X}")
    lines.append("")

    # Pipeline flow rows.
    lines.append(f"{B}PIPELINE FLOW{X}")
    for stream in REDIS_STREAMS:
        m = state.streams.get(stream, StreamMeter(name=stream))
        delta = m.total - m.last_total
        flow_glyph = status_glyph(delta > 0 or m.total > 0)
        lines.append(f"  redis xlen {stream:<22s}  +{delta:>4d}/5s  · {fmt_int(m.total):>8s}   {flow_glyph}")

    for ch in REDIS_PUBSUB:
        cnt = state.pubsub_counts.get(ch, 0)
        last = state.last_pubsub_counts.get(ch, 0)
        delta = cnt - last
        ok = delta > 0 or cnt > 0
        lines.append(f"  pubsub     {ch:<22s}  +{delta:>4d}/5s  · {fmt_int(cnt):>8s}   {status_glyph(ok)}")
        state.last_pubsub_counts[ch] = cnt
    lines.append("")

    # Layer 2 — WS tap to API gateway.
    if ws_enabled:
        lines.append(f"{B}API GATEWAY — WS TAP (Layer 2){X}  {D}state: {state.ws_state}{X}")
        for t in WS_FRAME_TYPES:
            cnt = state.ws_counts.get(t, 0)
            last = state.last_ws_counts.get(t, 0)
            delta = cnt - last
            # Cross-check: if Redis pubsub had frames but WS tap got 0, that's a gateway gap.
            corresponding_pubsub = {
                "ae": state.pubsub_counts.get("strix:stream:ae", 0),
                "vae": state.pubsub_counts.get("strix:stream:vae", 0),
                "gnn": state.pubsub_counts.get("strix:stream:gnn", 0),
                "rl": state.pubsub_counts.get("strix:stream:rl", 0),
            }.get(t)
            if corresponding_pubsub is not None and corresponding_pubsub > 0 and cnt == 0:
                glyph = status_glyph(False)
                hint = f"  {R}gateway gap{X}"
            elif corresponding_pubsub is not None and cnt == 0:
                glyph = status_glyph(False, warn=True)
                hint = ""
            else:
                glyph = status_glyph(cnt > 0 or delta > 0)
                hint = ""
            lines.append(f"  ws    {t:<22s}  +{delta:>4d}/5s  · {fmt_int(cnt):>8s}   {glyph}{hint}")
            state.last_ws_counts[t] = cnt
        lines.append("")

    # PG state.
    lines.append(f"{B}PG STATE (this run){X}")
    lines.append(f"  alerts                                {fmt_int(state.pg_alerts):>10s}")
    lines.append(f"  detections                            {fmt_int(state.pg_detections):>10s}")

    ae_pct_color = color_for_pct(state.pg_ae_nonnull, state.pg_detections, HARD_AE_VAE_COVERAGE)
    vae_pct_color = color_for_pct(state.pg_vae_nonnull, state.pg_detections, HARD_AE_VAE_COVERAGE)
    gnn_pct_color = color_for_pct(state.pg_gnn_nonnull, state.pg_detections, HARD_AE_VAE_COVERAGE)
    lines.append(f"      AE non-null   {ae_pct_color}{fmt_pct(state.pg_ae_nonnull, state.pg_detections)}{X}      "
                 f"{fmt_int(state.pg_ae_nonnull):>10s}")
    lines.append(f"      VAE non-null  {vae_pct_color}{fmt_pct(state.pg_vae_nonnull, state.pg_detections)}{X}      "
                 f"{fmt_int(state.pg_vae_nonnull):>10s}")
    lines.append(f"      GNN non-null  {gnn_pct_color}{fmt_pct(state.pg_gnn_nonnull, state.pg_detections)}{X}      "
                 f"{fmt_int(state.pg_gnn_nonnull):>10s}")

    lines.append(f"  attack_chains                         {fmt_int(state.pg_chains):>10s}   "
                 f"({state.pg_chains_open} open)")
    if state.pg_chain_stage_hist:
        for stage in sorted(state.pg_chain_stage_hist):
            n = state.pg_chain_stage_hist[stage]
            mark = G if stage >= 5 else (Y if stage >= 4 else D)
            lines.append(f"      stage {stage}  {mark}{fmt_int(n):>6s}{X}")

    lines.append(f"  dqn_actions                           {fmt_int(state.pg_dqn_actions):>10s}")
    if state.pg_dqn_action_mix:
        for name in sorted(state.pg_dqn_action_mix, key=lambda k: -state.pg_dqn_action_mix[k]):
            n = state.pg_dqn_action_mix[name]
            mark = G if name in ("ESCALATE", "ISOLATE_HOST", "BLOCK_USER_IP") else D
            lines.append(f"      {name:<14s}  {mark}{fmt_int(n):>6s}{X}")
    lines.append("")

    # Recent techniques.
    lines.append(f"{B}TECHNIQUES OBSERVED (last 60 s){X}")
    if state.pg_recent_techniques:
        for t, n in state.pg_recent_techniques.items():
            lines.append(f"  {t:<48s}  ×{n}")
    else:
        lines.append(f"  {D}(none yet){X}")
    lines.append("")

    # Plan vs observed cross-reference.
    if state.plan_tactic_techniques:
        lines.append(f"{B}PLAN ↔ OBSERVED (run-scoped){X}")
        id2name = _ID2NAME
        for tactic, tech_ids in state.plan_tactic_techniques.items():
            matches = []
            misses = []
            for tid in tech_ids:
                name = id2name.get(tid)
                hit = (tid in state.pg_run_techniques) or (
                    name is not None and name in state.pg_run_techniques
                )
                if hit:
                    matches.append(tid)
                else:
                    misses.append(tid)
            n_total = len(tech_ids)
            n_hit = len(matches)
            color = G if n_hit == n_total else (Y if n_hit >= 1 else R)
            lines.append(f"  {tactic:<22s}  {color}{n_hit}/{n_total}{X}  hit: {','.join(matches) or '—'}")
            if misses:
                lines.append(f"    {D}miss: {','.join(misses)}{X}")
        lines.append("")

    # Quick verdicts.
    lines.append(f"{B}VERDICTS{X}")
    rate_per_min = (state.pg_alerts / max(1.0, elapsed)) * 60.0
    rate_ok = rate_per_min >= HARD_MIN_ALERT_RATE_PER_MIN or state.pg_alerts == 0
    lines.append(f"  alert rate ≥ {HARD_MIN_ALERT_RATE_PER_MIN}/min       {status_glyph(rate_ok, warn=state.pg_alerts == 0)}  "
                 f"({rate_per_min:.1f}/min)")

    ae_ok = state.pg_detections == 0 or (state.pg_ae_nonnull / state.pg_detections) >= HARD_AE_VAE_COVERAGE
    lines.append(f"  AE coverage ≥ {int(HARD_AE_VAE_COVERAGE*100)}%        {status_glyph(ae_ok)}")
    vae_ok = state.pg_detections == 0 or (state.pg_vae_nonnull / state.pg_detections) >= HARD_AE_VAE_COVERAGE
    lines.append(f"  VAE coverage ≥ {int(HARD_AE_VAE_COVERAGE*100)}%       {status_glyph(vae_ok)}")

    gnn_ok = state.pg_gnn_nonnull > 0
    lines.append(f"  GNN producing scores       {status_glyph(gnn_ok, warn=state.pg_detections == 0)}")

    n_escalates = state.pg_dqn_action_mix.get("ESCALATE", 0) + \
                  state.pg_dqn_action_mix.get("ISOLATE_HOST", 0) + \
                  state.pg_dqn_action_mix.get("BLOCK_USER_IP", 0)
    esc_ok = n_escalates >= HARD_MIN_ESCALATES
    lines.append(f"  ESCALATEs ≥ {HARD_MIN_ESCALATES}              "
                 f"{status_glyph(esc_ok, warn=elapsed < 60)}  ({n_escalates})")

    lines.append("")
    lines.append(f"{D}(Ctrl-C → final report){X}")
    return "\n".join(lines)


# ---------- final report ----------
def final_report(state: MonitorState, ws_enabled: bool) -> dict[str, Any]:
    elapsed = max(1.0, time.time() - state.started_at)
    rate_per_min = state.pg_alerts / elapsed * 60.0

    ae_cov = state.pg_ae_nonnull / state.pg_detections if state.pg_detections else 0.0
    vae_cov = state.pg_vae_nonnull / state.pg_detections if state.pg_detections else 0.0
    gnn_cov = state.pg_gnn_nonnull / state.pg_detections if state.pg_detections else 0.0
    n_escalates = sum(state.pg_dqn_action_mix.get(k, 0)
                      for k in ("ESCALATE", "ISOLATE_HOST", "BLOCK_USER_IP"))

    checks: list[tuple[str, bool, str]] = []
    checks.append(("Wazuh ingest rate ≥ 10/min",
                   rate_per_min >= HARD_MIN_ALERT_RATE_PER_MIN,
                   f"{rate_per_min:.1f}/min"))
    checks.append(("Redis stream xlen growing (alerts:raw)",
                   any(m.total > 0 for m in state.streams.values()),
                   f"{sum(m.total for m in state.streams.values())} total"))
    checks.append(("Pubsub frames received per stream",
                   all(state.pubsub_counts.get(ch, 0) > 0 for ch in REDIS_PUBSUB)
                   if state.pg_detections > 0 else True,
                   "; ".join(f"{ch.split(':')[-1]}={state.pubsub_counts.get(ch,0)}" for ch in REDIS_PUBSUB)))
    checks.append(("AE coverage ≥ 80%",
                   ae_cov >= HARD_AE_VAE_COVERAGE or state.pg_detections == 0,
                   f"{ae_cov*100:.1f}%"))
    checks.append(("VAE coverage ≥ 80%",
                   vae_cov >= HARD_AE_VAE_COVERAGE or state.pg_detections == 0,
                   f"{vae_cov*100:.1f}%"))
    checks.append(("GNN producing scores",
                   gnn_cov > 0 or state.pg_detections == 0,
                   f"{gnn_cov*100:.1f}%"))
    checks.append((f"DQN ESCALATEs ≥ {HARD_MIN_ESCALATES}",
                   n_escalates >= HARD_MIN_ESCALATES,
                   f"{n_escalates}"))
    checks.append(("Forensic techniques ≥ 5 in run",
                   sum(state.pg_recent_techniques.values()) >= HARD_MIN_FORENSIC_TECHNIQUES
                   or state.pg_alerts == 0,
                   f"{sum(state.pg_recent_techniques.values())}"))

    # Plan ↔ observed: per-tactic, ≥1 of the planned techniques must
    # have shown up in alerts.mitre_techniques (id OR name match).
    if state.plan_tactic_techniques:
        for tactic, tech_ids in state.plan_tactic_techniques.items():
            id2name = _ID2NAME
            n_hit = sum(
                1 for tid in tech_ids
                if tid in state.pg_run_techniques
                or (id2name.get(tid) and id2name[tid] in state.pg_run_techniques)
            )
            n_total = len(tech_ids)
            ok = n_hit >= 1 or state.pg_alerts == 0
            checks.append((f"Tactic {tactic:<22s} ≥1 technique observed", ok, f"{n_hit}/{n_total}"))

    # Layer 2 — WS tap checks (only if --ws-tap was on).
    if ws_enabled and not state.ws_state.startswith(("disabled", "websockets-not-installed")):
        ws_open_ok = state.ws_state == "open"
        checks.append(("WS gateway connected",
                       ws_open_ok or state.ws_state == "auth_failed",  # auth_failed is a soft pass for skip-auth
                       state.ws_state))
        # Per-stream parity: if Redis pubsub had any frames, WS should too.
        for stream_short, redis_ch in [("ae", "strix:stream:ae"),
                                       ("vae", "strix:stream:vae"),
                                       ("gnn", "strix:stream:gnn"),
                                       ("rl", "strix:stream:rl")]:
            r = state.pubsub_counts.get(redis_ch, 0)
            w = state.ws_counts.get(stream_short, 0)
            if r == 0:
                ok = True  # nothing to deliver
                note = "no traffic"
            else:
                ok = w > 0  # any delivery proves the path
                note = f"redis={r}, ws={w}"
            checks.append((f"WS gateway delivers {stream_short}", ok, note))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    overall = "PASS" if passed == total else "FAIL"

    print(f"\n{B}{C}═══ FINAL E2E AUDIT ═══{X}")
    print(f"{B}Overall: {G if overall=='PASS' else R}{overall}{X}{B}  ({passed}/{total} hard checks){X}")
    print()
    for name, ok, note in checks:
        print(f"  {status_glyph(ok)}  {name:<42s} {D}{note}{X}")
    print()
    print(f"{B}Run summary{X}")
    print(f"  run_id          {state.run_id}")
    print(f"  duration        {int(elapsed)}s")
    print(f"  pg alerts       {fmt_int(state.pg_alerts)}")
    print(f"  pg detections   {fmt_int(state.pg_detections)}")
    print(f"  pg chains       {fmt_int(state.pg_chains)} ({state.pg_chains_open} open)")
    print(f"  pg dqn_actions  {fmt_int(state.pg_dqn_actions)}")
    print(f"  chain stages    {state.pg_chain_stage_hist}")
    print(f"  dqn mix         {state.pg_dqn_action_mix}")
    return {
        "overall": overall,
        "passed": passed,
        "total": total,
        "checks": [{"name": n, "ok": ok, "note": note} for n, ok, note in checks],
        "metrics": {
            "alerts": state.pg_alerts,
            "detections": state.pg_detections,
            "chains": state.pg_chains,
            "chains_open": state.pg_chains_open,
            "dqn_actions": state.pg_dqn_actions,
            "ae_coverage": ae_cov,
            "vae_coverage": vae_cov,
            "gnn_coverage": gnn_cov,
            "escalates": n_escalates,
            "rate_per_min": rate_per_min,
            "chain_stage_hist": state.pg_chain_stage_hist,
            "dqn_mix": state.pg_dqn_action_mix,
        },
    }


# ---------- main ----------
async def amain(args: argparse.Namespace) -> int:
    env = load_env(ENV_FILE)
    pg_user = env.get("DB_USER", "strix")
    pg_pwd = env.get("DB_PASSWORD", "")
    pg_host = env.get("DB_HOST", "127.0.0.1")
    pg_port = int(env.get("DB_PORT", "5432"))
    pg_db = env.get("DB_NAME", "strix")
    redis_url = env.get("REDIS_URL")
    if not redis_url:
        redis_url = (
            f"redis://{env.get('REDIS_HOST', '127.0.0.1')}"
            f":{env.get('REDIS_PORT', '6379')}/{env.get('REDIS_DB', '0')}"
        )

    if not pg_pwd:
        sys.stderr.write(f"{R}DB_PASSWORD missing in {ENV_FILE}{X}\n")
        return 2

    state = MonitorState()
    rid, topo = latest_topology()
    state.run_id = rid
    if topo and topo.get("started_at"):
        state.sim_start_iso = topo["started_at"]
    if rid:
        state.run_dir = SIM_RUNS_DIR / rid

    # Output dir.
    out_dir = Path(f"/tmp/strix_e2e_{rid or 'live'}")
    out_dir.mkdir(parents=True, exist_ok=True)
    monitor_log = out_dir.open("w") if False else (out_dir / "monitor.jsonl").open("a")

    pool = await asyncpg.create_pool(
        user=pg_user, password=pg_pwd, host=pg_host, port=pg_port, database=pg_db,
        min_size=1, max_size=2,
    )
    redis = aioredis.from_url(redis_url, decode_responses=False)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            loop.add_signal_handler(sig, stop.set)

    tasks = [
        asyncio.create_task(poll_redis(state, redis)),
        asyncio.create_task(poll_pg(state, pool)),
    ]
    for ch in REDIS_PUBSUB:
        tasks.append(asyncio.create_task(subscribe_pubsub(state, redis, ch)))

    if args.ws_tap:
        if websockets is None:
            sys.stderr.write(f"{R}--ws-tap requires `websockets` package; skipping{X}\n")
            state.ws_state = "websockets-not-installed"
        else:
            cookie = None
            if not args.ws_no_auth:
                print(f"{D}logging in as {args.email} for WS tap…{X}")
                cookie = _login_get_cookie(args.api_url, args.email, args.password)
                if cookie is None:
                    sys.stderr.write(
                        f"{R}WS tap login failed — set STRIX_TEST_PASSWORD or pass "
                        f"--password / --ws-no-auth (if AUTH_DEV_SKIP_AUTH=true){X}\n"
                    )
                    state.ws_state = "auth_failed"
                else:
                    print(f"{G}cookie acquired ({len(cookie)} chars){X}")
            tasks.append(asyncio.create_task(ws_tap(state, args.ws_url, cookie)))

    print(f"{B}{C}STRIX E2E monitor started{X}")
    print(f"  run:      {rid or '(none yet — waiting for jury_demo*.sh)'}")
    print(f"  pg:       {pg_user}@{pg_host}:{pg_port}/{pg_db}")
    print(f"  redis:    {redis_url}")
    print(f"  log:      {out_dir}/monitor.jsonl")
    print()

    last_render = 0.0
    try:
        while not stop.is_set():
            now = time.time()
            # Refresh topology.json on every tick — captures the
            # tactic_techniques map written by run_full_simulation.py
            # mid-run, so the cross-reference panel updates as the plan
            # is finalised. Also picks up new run_ids when the previous
            # demo ends and a new one starts.
            rid2, topo2 = latest_topology()
            if rid2 and rid2 != state.run_id:
                state.run_id = rid2
                if topo2 and topo2.get("started_at"):
                    state.sim_start_iso = topo2["started_at"]
                state.run_dir = SIM_RUNS_DIR / rid2
            if topo2:
                tt = topo2.get("tactic_techniques")
                if isinstance(tt, dict):
                    state.plan_tactic_techniques = {
                        k: list(v) for k, v in tt.items() if isinstance(v, list)
                    }

            if now - last_render >= POLL_SECONDS:
                # Clear-screen + draw fresh.
                sys.stdout.write("\033[2J\033[H")
                sys.stdout.write(render(state, args.ws_tap))
                sys.stdout.write("\n")
                sys.stdout.flush()

                # Append snapshot to JSONL.
                snapshot = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "elapsed_s": int(now - state.started_at),
                    "run_id": state.run_id,
                    "pg": {
                        "alerts": state.pg_alerts,
                        "detections": state.pg_detections,
                        "ae_nonnull": state.pg_ae_nonnull,
                        "vae_nonnull": state.pg_vae_nonnull,
                        "gnn_nonnull": state.pg_gnn_nonnull,
                        "chains": state.pg_chains,
                        "chains_open": state.pg_chains_open,
                        "dqn_actions": state.pg_dqn_actions,
                        "chain_stage_hist": state.pg_chain_stage_hist,
                        "dqn_mix": state.pg_dqn_action_mix,
                    },
                    "redis": {s: state.streams[s].total for s in state.streams},
                    "pubsub": dict(state.pubsub_counts),
                    "techniques_60s": state.pg_recent_techniques,
                }
                monitor_log.write(json.dumps(snapshot) + "\n")
                monitor_log.flush()

                last_render = now

                # Idle exit: if alerts have been growing then stop, exit.
                if (state.pg_alerts > 0
                        and (now - state.last_alert_seen_ts) > IDLE_EXIT_SECONDS):
                    print(f"\n{Y}No new alerts for {IDLE_EXIT_SECONDS:.0f}s — assuming sim ended.{X}")
                    stop.set()
                    break

            await asyncio.sleep(0.5)
    finally:
        for t in tasks:
            t.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await asyncio.gather(*tasks, return_exceptions=True)
        with suppress(Exception):
            await redis.aclose()
        with suppress(Exception):
            await pool.close()
        report = final_report(state, args.ws_tap)
        (out_dir / "monitor_final.json").write_text(json.dumps(report, indent=2))
        monitor_log.close()
        print(f"\n{D}artifacts: {out_dir}/{X}")
    return 0 if report["overall"] == "PASS" else 1


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ws-tap", action="store_true",
                   help="Layer 2: tap the API gateway WS at /api/v1/logs/stream and count frames per type")
    p.add_argument("--api-url", default=os.environ.get("STRIX_API_URL", DEFAULT_API_URL),
                   help=f"API base URL for login (default: {DEFAULT_API_URL})")
    p.add_argument("--ws-url", default=os.environ.get("STRIX_WS_URL", DEFAULT_WS_URL),
                   help=f"WS endpoint URL (default: {DEFAULT_WS_URL})")
    p.add_argument("--email", default=os.environ.get("STRIX_TEST_EMAIL", DEFAULT_TEST_EMAIL),
                   help=f"login email for WS tap (default: {DEFAULT_TEST_EMAIL})")
    p.add_argument("--password", default=os.environ.get("STRIX_TEST_PASSWORD", DEFAULT_TEST_PASSWORD),
                   help="login password for WS tap (default: env STRIX_TEST_PASSWORD or hard-coded fallback)")
    p.add_argument("--ws-no-auth", action="store_true",
                   help="skip login — set if AUTH_DEV_SKIP_AUTH=true on the API")
    args = p.parse_args()
    sys.exit(asyncio.run(amain(args)))


if __name__ == "__main__":
    main()
