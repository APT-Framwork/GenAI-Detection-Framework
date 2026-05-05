#!/usr/bin/env bash
# =============================================================================
# jury_demo_single.sh — single-victim variant of jury_demo.sh.
#
# Same end-to-end flow as jury_demo.sh (real Caldera-driven MITRE tactics →
# Wazuh → normalizer → inference → live dashboard at http://localhost:5600),
# but the simulated APT only has ONE victim host. The other victim container
# is stopped before Caldera kicks off, so:
#
#   * Caldera's `red` group sees a single sandcat agent → every ability fires
#     against just that host.
#   * The dashboard's APT Attack Timeline shows ONE chain, not two.
#   * The RL Intervention Timeline shows ONE verdict per tactic (predetected
#     or post-detected) — easier to narrate to a jury that hasn't seen the
#     two-host case before.
#
# Pre-requisites: same as jury_demo.sh.
#
# Usage:
#   bash jury_demo_single.sh                         # victim1 (default)
#   bash jury_demo_single.sh --victim victim2        # use victim2 instead
#   bash jury_demo_single.sh --apt APT41             # alt APT profile
#   bash jury_demo_single.sh --duration 240
#   bash jury_demo_single.sh stop                    # tear everything down
#
# What gets stopped:
#   default --victim victim1 → strix_victim2 is stopped (kept paused, not removed)
#                              compose down brings it back next run.
# =============================================================================
set -euo pipefail

# ---- styling ---------------------------------------------------------------
# ANSI-C $'…' quoting so each var holds the real ESC byte, not literal "\033".
# Otherwise embedding ${BOLD} inside a printf %s argument prints "\033[1m" verbatim.
GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; CYAN=$'\033[36m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
ok()    { printf "${GREEN}✓${RESET} %s\n" "$*"; }
fail()  { printf "${RED}✗${RESET} %s\n" "$*"; exit 1; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }
step()  { printf "\n${DIM}──[ ${BOLD}%s${RESET}${DIM} ]──${RESET}\n" "$*"; }

# ---- paths -----------------------------------------------------------------
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

ENV_FILE="$REPO/apps/api/.env"
VENV="$REPO/apps/api/.venv"
HONCHO_LOG="/tmp/strix_honcho.log"
HONCHO_PID_FILE="/tmp/strix_honcho.pid"

DASHBOARD_URL="http://localhost:5600"
API_URL="http://localhost:8000"

# ---- args ------------------------------------------------------------------
APT="APT29"
DURATION="180s"
BENIGN_RATE="100/min"
NON_MONOTONIC=0  # see --non-monotonic flag below
STOP=0
SKIP_SIM=0
CLEAN_STATE=1
VICTIM="victim1"   # which victim survives — the other one gets stopped

print_help() {
  cat <<'EOF'
NAME
    jury_demo_single.sh — single-victim variant of jury_demo.sh.

SYNOPSIS
    bash jury_demo_single.sh [--victim victim1|victim2]
                             [--apt APT29|APT41|...]
                             [--duration 180s] [--benign-rate 100/min]
                             [--keep-state] [--skip-sim]
    bash jury_demo_single.sh stop
    bash jury_demo_single.sh -h | --help

DESCRIPTION
    Same end-to-end flow as jury_demo.sh — Caldera → Wazuh → normalizer →
    inference (AE/VAE/Transformer/GNN/DQN) → live dashboard at
    http://localhost:5600 — but the simulated APT only targets ONE
    victim host. The other victim's container is stopped before Caldera
    fires, so:

      * Caldera's `red` group sees a single sandcat agent → every
        ability fires against just that host.
      * The dashboard's APT Attack Timeline shows ONE chain.
      * The RL Intervention Timeline shows ONE verdict per tactic
        (predetected or post-detected) — easier to narrate to a jury
        that hasn't seen the two-host case before.

    Use jury_demo.sh for the full two-victim version.

PREREQUISITES
    Identical to jury_demo.sh (Docker, honcho, pnpm, .venv, .env).

OPTIONS
    --victim NAME         Which victim STAYS up — `victim1` (default) or
                          `victim2`. The other container is stopped after
                          the sim lab is healthy and before lab_simulate
                          starts. The stopped container is preserved
                          (`docker stop`, not `docker rm`); restart it
                          with `docker start strix_victim2` once you're
                          done.

    --apt NAME            APT profile to emulate. Default: APT29.

    --non-monotonic       Curated forward/backward kill-chain demo built to
                          trip the DQN's ESCALATE threshold. Mutually
                          exclusive with --apt; when set, --apt is ignored.

    --duration TIME       Total simulation runtime (e.g. 60s, 4m, 240s).
                          Default: 180s.

    --benign-rate RATE    Background benign-traffic rate per victim, e.g.
                          50/min, 200/min. Default: 100/min.

    --keep-state          Skip the clean-state step (debug only).

    --skip-sim            Bring stack up but do NOT run lab_simulate.

    stop | --stop         Tear everything down — same as jury_demo.sh.

    -h, --help            Show this help and exit.

ENV VARS APPLIED IDEMPOTENTLY TO apps/api/.env
    Same set as jury_demo.sh:
      STRIX_STREAM_PER_MODEL=1
      STRIX_CHAIN_MAX_STEPS=15
      STRIX_CHAIN_IDLE_TIMEOUT_MIN=10

EXECUTION FLOW
    Identical to jury_demo.sh, with two extra single-victim steps:

      0)   Restore production GNN threshold + apply chain env vars
      1)   Stop any prior host stack
      2)   docker compose up sim lab (wazuh + caldera + both victims)
           — wait for wazuh healthy + reload rules
      2.5) **docker stop the OTHER victim** (the one not selected by
           --victim). Caldera's `red` group then has a single agent.
      2.6) **Refresh the KEPT victim**: docker restart so sandcat is
           freshly launched (after a previous run with
           STRIX_DEMO_AUTO_ISOLATE=1, sandcat was pkilled and never
           respawned — without this restart the next run produces
           0 Caldera links). Also kills any orphaned benign-traffic
           generators from a Ctrl-C'd prior run, then waits for
           sandcat to enroll into Caldera.
      3)   docker compose up platform deps
      4)   alembic upgrade head
      4.5) Clean state (unless --keep-state) — TRUNCATE PG +
           wipe Redis streams/sessions/queues
      5)   honcho start — api + web + 6 workers
      6)   Wait for /health + dashboard, prompt the operator
      7)   bash infra/scripts/lab_simulate.sh

TOPOLOGY
    infra/scripts/lab_simulate.sh now builds topology.json dynamically
    from running `strix_victim*` containers, so the dashboard's topology
    widget shows ONE node when this script is used (the other victim is
    stopped, so it's not enumerated). The widget polls topology.json
    every 5 s and updates the SVG when the run_id or victim count changes.

EXAMPLES
    bash jury_demo_single.sh
    bash jury_demo_single.sh --victim victim2
    bash jury_demo_single.sh --apt APT41 --duration 240
    bash jury_demo_single.sh stop
    docker start strix_victim2     # bring the stopped victim back

SEE ALSO
    jury_demo.sh                                two-victim variant
    infra/scripts/lab_simulate.sh               the underlying sim runner
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    stop|--stop)     STOP=1; shift ;;
    --apt)           APT="$2"; shift 2 ;;
    --duration)      DURATION="$2"; shift 2 ;;
    --benign-rate)   BENIGN_RATE="$2"; shift 2 ;;
    --keep-state)    CLEAN_STATE=0; shift ;;
    --skip-sim)      SKIP_SIM=1; shift ;;
    --non-monotonic) NON_MONOTONIC=1; APT=""; shift ;;
    --victim)        VICTIM="$2"; shift 2 ;;
    -h|--help)       print_help; exit 0 ;;
    *) fail "unknown arg: $1   (try: bash $0 --help)" ;;
  esac
done

# Validate --victim and derive the OTHER container that we'll stop.
case "$VICTIM" in
  victim1) OTHER_VICTIM="strix_victim2" ;;
  victim2) OTHER_VICTIM="strix_victim1" ;;
  *) fail "--victim must be 'victim1' or 'victim2' (got: $VICTIM)" ;;
esac
KEEP_VICTIM="strix_${VICTIM}"

# ---- stop path -------------------------------------------------------------
if [[ "$STOP" -eq 1 ]]; then
  step "stopping host processes (honcho)"
  if [[ -f "$HONCHO_PID_FILE" ]]; then
    pid="$(cat "$HONCHO_PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null && ok "sent SIGTERM to honcho (pid=$pid)"
      sleep 3
      kill -KILL "$pid" 2>/dev/null || true
    fi
    rm -f "$HONCHO_PID_FILE"
  fi
  pkill -f "honcho -f Procfile.host" 2>/dev/null || true
  pkill -f "uvicorn strix_api.main" 2>/dev/null || true
  pkill -f "strix_api.workers" 2>/dev/null || true
  ok "host processes down"

  step "stopping platform deps (postgres + redis + filebeat)"
  docker compose -f infra/compose.platform-deps.yml --env-file "$ENV_FILE" down || true
  step "stopping simulation lab (wazuh + caldera + victims)"
  docker compose -f infra/compose.simulation.yml down || true
  ok "stack stopped (volumes preserved)"
  exit 0
fi

# ---- prereq checks ---------------------------------------------------------
step "checking prerequisites"
command -v docker >/dev/null            || fail "docker not installed"
docker compose version >/dev/null 2>&1  || fail "docker compose v2 required"
command -v honcho >/dev/null            || fail "honcho not installed (pipx install honcho)"
[[ -f "$ENV_FILE" ]]                    || fail "$ENV_FILE missing"
[[ -x "$VENV/bin/python" ]]             || fail "$VENV missing — see docs/LAB_BRINGUP.md"
[[ -x "$VENV/bin/alembic" ]]            || fail "$VENV/bin/alembic missing"
ok "prereqs OK  (single-victim mode: keeping ${BOLD}$VICTIM${RESET}, will stop ${BOLD}$OTHER_VICTIM${RESET})"

# ---- 0) restore production GNN threshold ----------------------------------
step "restoring production GNN open threshold (removing synthetic test override)"
if grep -q "^STRIX_GNN_OPEN_THRESHOLD=" "$ENV_FILE"; then
  sed -i '/^# Lowered for synthetic-traffic testing/d' "$ENV_FILE"
  sed -i '/^STRIX_GNN_OPEN_THRESHOLD=/d' "$ENV_FILE"
  ok "removed STRIX_GNN_OPEN_THRESHOLD override (default 0.7743 will apply)"
else
  ok "no override present"
fi

if ! grep -q "^STRIX_STREAM_PER_MODEL=1" "$ENV_FILE"; then
  printf '\nSTRIX_STREAM_PER_MODEL=1\n' >> "$ENV_FILE"
  ok "set STRIX_STREAM_PER_MODEL=1 (per-model ws fan-out)"
else
  ok "STRIX_STREAM_PER_MODEL=1 already set"
fi

# Tighter chain binding — same demo defaults as jury_demo.sh.
if ! grep -q "^STRIX_CHAIN_MAX_STEPS=" "$ENV_FILE"; then
  printf 'STRIX_CHAIN_MAX_STEPS=15\n' >> "$ENV_FILE"
  ok "set STRIX_CHAIN_MAX_STEPS=15 (was 50)"
else
  ok "STRIX_CHAIN_MAX_STEPS already set"
fi
if ! grep -q "^STRIX_CHAIN_IDLE_TIMEOUT_MIN=" "$ENV_FILE"; then
  printf 'STRIX_CHAIN_IDLE_TIMEOUT_MIN=10\n' >> "$ENV_FILE"
  ok "set STRIX_CHAIN_IDLE_TIMEOUT_MIN=10 (was 120)"
else
  ok "STRIX_CHAIN_IDLE_TIMEOUT_MIN already set"
fi

# Demo-only auto-isolation: kill sandcat on the predetected victim so the
# jury sees the attack visibly stop. Hard-off in production.
if ! grep -q "^STRIX_DEMO_AUTO_ISOLATE=" "$ENV_FILE"; then
  printf 'STRIX_DEMO_AUTO_ISOLATE=1\n' >> "$ENV_FILE"
  ok "set STRIX_DEMO_AUTO_ISOLATE=1 (severs sandcat on first ESCALATE+)"
else
  ok "STRIX_DEMO_AUTO_ISOLATE already set"
fi

# ---- 1) tear down any prior host processes -------------------------------
step "stopping any prior host processes"
if [[ -f "$HONCHO_PID_FILE" ]]; then
  pid="$(cat "$HONCHO_PID_FILE" 2>/dev/null || true)"
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null || true
    sleep 2
    kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$HONCHO_PID_FILE"
fi
pkill -f "honcho -f Procfile.host" 2>/dev/null || true
pkill -f "uvicorn strix_api.main" 2>/dev/null || true
pkill -f "strix_api.workers" 2>/dev/null || true
ok "host slot clear"

# ---- 2) bring up the simulation lab --------------------------------------
step "bringing up simulation lab (wazuh manager + caldera + ${KEEP_VICTIM} only)"
docker compose -f infra/compose.simulation.yml up -d --build
ok "sim containers requested"

printf "${DIM}waiting for wazuh.manager healthy ${RESET}"
for _ in $(seq 1 60); do
  status="$(docker inspect -f '{{.State.Health.Status}}' strix_wazuh_manager 2>/dev/null || echo missing)"
  if [[ "$status" == "healthy" ]]; then printf "\n"; ok "wazuh.manager healthy"; break; fi
  printf "."; sleep 3
done
if [[ "${status:-missing}" != "healthy" ]]; then
  warn "wazuh.manager did not report healthy — proceeding anyway (sandcat agents may still enroll)"
fi

if docker exec strix_wazuh_manager /var/ossec/bin/wazuh-control reload >/dev/null 2>&1; then
  ok "wazuh: ruleset reloaded (custom local_rules.xml applied)"
else
  warn "wazuh-control reload failed — restarting container"
  docker compose -f infra/compose.simulation.yml restart strix_wazuh_manager >/dev/null
fi

# ---- 2.5) single-victim mode: stop the OTHER victim ----------------------
step "single-victim mode: stopping $OTHER_VICTIM"
if docker ps --format '{{.Names}}' | grep -qx "$OTHER_VICTIM"; then
  docker stop "$OTHER_VICTIM" >/dev/null
  ok "$OTHER_VICTIM stopped — Caldera 'red' group will only see $VICTIM"
else
  ok "$OTHER_VICTIM not running — nothing to stop"
fi

# Sanity check: the kept victim must be running so sandcat can enroll.
if ! docker ps --format '{{.Names}}' | grep -qx "$KEEP_VICTIM"; then
  fail "$KEEP_VICTIM is not running — bring up the lab manually then retry"
fi
ok "$KEEP_VICTIM running"

# ---- 2.6) refresh the kept victim so sandcat is alive ---------------------
# After a previous run with STRIX_DEMO_AUTO_ISOLATE=1, sandcat was pkilled
# on this host and never respawned (entrypoint launches it once, then
# `exec tail -F`s the wazuh log). Without this restart, Caldera's `red`
# group has zero agents and lab_simulate would silently produce 0 links.
# Also kills any orphaned benign-traffic generators from a prior run that
# was Ctrl-C'd before the EXIT trap could clean them up.
step "refreshing $KEEP_VICTIM (ensures sandcat is alive + flushes stale state)"
docker exec "$KEEP_VICTIM" pkill -f benign_traffic.sh >/dev/null 2>&1 || true
docker restart "$KEEP_VICTIM" >/dev/null
printf "${DIM}waiting for $KEEP_VICTIM sandcat to enroll ${RESET}"
sandcat_alive=0
for _ in $(seq 1 60); do
  if docker exec "$KEEP_VICTIM" pgrep -f sandcat >/dev/null 2>&1; then
    printf "\n"; sandcat_alive=1; break
  fi
  printf "."; sleep 2
done
if [[ "$sandcat_alive" -eq 1 ]]; then
  ok "sandcat running on $KEEP_VICTIM — Caldera 'red' group has 1 agent"
else
  warn "sandcat did not start on $KEEP_VICTIM within 120s — Caldera ops may produce 0 links"
fi

# ---- 3) bring up platform deps -------------------------------------------
step "bringing up platform deps (postgres + redis + filebeat)"
docker compose -f infra/compose.platform-deps.yml --env-file "$ENV_FILE" up -d
printf "${DIM}waiting for postgres + redis healthy ${RESET}"
for _ in $(seq 1 30); do
  pg="$(docker inspect -f '{{.State.Health.Status}}' strix_postgres 2>/dev/null || echo missing)"
  rd="$(docker inspect -f '{{.State.Health.Status}}' strix_redis 2>/dev/null || echo missing)"
  if [[ "$pg" == "healthy" && "$rd" == "healthy" ]]; then printf "\n"; ok "deps healthy"; break; fi
  printf "."; sleep 1
done

# ---- 4) migrations -------------------------------------------------------
step "running alembic upgrade head (via project venv)"
( cd apps/api && set -a && source ./.env && set +a && "$VENV/bin/alembic" upgrade head ) >/dev/null
ok "schema at head"

# ---- 4.5) clean prior state ----------------------------------------------
if [[ "$CLEAN_STATE" -eq 1 ]]; then
  step "clean state — wiping chains/detections/alerts + redis streams"
  ( cd apps/api && set -a && source ./.env && set +a && \
    PGPASSWORD="${DB_PASSWORD:?DB_PASSWORD missing in .env}" \
    psql -h "${DB_HOST:-127.0.0.1}" -p "${DB_PORT:-5432}" \
         -U "${DB_USER:-strix}"     -d "${DB_NAME:-strix}" -v ON_ERROR_STOP=1 <<'SQL' >/dev/null
TRUNCATE TABLE
  attack_chains,
  detections,
  alerts,
  dqn_actions
RESTART IDENTITY CASCADE;
SQL
  ) || fail "psql truncate failed — check apps/api/.env DB_* vars"
  ok "postgres: chains/detections/alerts/dqn_actions truncated"

  docker exec strix_redis sh -lc '
    for pat in "strix:stream:*" "strix:sse:*" "strix:features:*" "session:*"; do
      redis-cli --scan --pattern "$pat" | xargs -r redis-cli DEL >/dev/null
    done
    redis-cli DEL strix:alerts:raw strix:alerts:raw:list strix:verdicts >/dev/null
  ' >/dev/null && ok "redis: streams + sessions + queues cleared" \
                 || warn "redis clean partial — inspect with: docker exec strix_redis redis-cli keys 'strix:*'"
else
  warn "clean-state SKIPPED (--keep-state) — FINAL REPORT deltas will include prior-run history"
fi

# ---- 5) start the host stack via honcho ----------------------------------
step "starting host stack via honcho (logs → $HONCHO_LOG)"
: > "$HONCHO_LOG"
nohup honcho -f Procfile.host -e "$ENV_FILE" start >>"$HONCHO_LOG" 2>&1 &
echo $! > "$HONCHO_PID_FILE"
ok "honcho started (pid=$(cat "$HONCHO_PID_FILE"))"

printf "${DIM}waiting for api /health and web :5600 ${RESET}"
ready_api=0; ready_web=0
for _ in $(seq 1 90); do
  [[ "$ready_api" -eq 0 ]] && curl -fsS "$API_URL/health" >/dev/null 2>&1 && ready_api=1
  [[ "$ready_web" -eq 0 ]] && curl -fsS "$DASHBOARD_URL" >/dev/null 2>&1 && ready_web=1
  if [[ "$ready_api" -eq 1 && "$ready_web" -eq 1 ]]; then printf "\n"; break; fi
  printf "."; sleep 2
done
[[ "$ready_api" -eq 1 ]] && ok "api up at $API_URL" || warn "api /health did not respond — check $HONCHO_LOG"
[[ "$ready_web" -eq 1 ]] && ok "web up at $DASHBOARD_URL" || warn "web did not respond — check $HONCHO_LOG"

# ---- 6) demo banner ------------------------------------------------------
echo
echo -e "${BOLD}${CYAN}┌─────────────────────────────────────────────────────────────────┐${RESET}"
echo -e "${BOLD}${CYAN}│${RESET}  Dashboard ready: ${BOLD}$DASHBOARD_URL${RESET}"
echo -e "${BOLD}${CYAN}│${RESET}  Single-victim mode — ${BOLD}$VICTIM${RESET} only (${OTHER_VICTIM} stopped)."
echo -e "${BOLD}${CYAN}│${RESET}  About to drive Caldera through APT=$APT for $DURATION."
echo -e "${BOLD}${CYAN}│${RESET}  Watch:"
echo -e "${BOLD}${CYAN}│${RESET}    • Topology — attacker → 1 victim, red pulses on each tactic"
echo -e "${BOLD}${CYAN}│${RESET}    • RL Kill-Chain — single chain progressing 1→…→7"
echo -e "${BOLD}${CYAN}│${RESET}    • Detection Quality — TP/FP/TN/FN per stage"
echo -e "${BOLD}${CYAN}│${RESET}    • Forensic Logs — auditd lines from $VICTIM"
echo -e "${BOLD}${CYAN}└─────────────────────────────────────────────────────────────────┘${RESET}"
read -r -p "Press ENTER once the dashboard is open and LIVE…"

if [[ "$SKIP_SIM" -eq 1 ]]; then
  ok "stack up; --skip-sim set, not running lab_simulate.sh"
  if [[ "$NON_MONOTONIC" -eq 1 ]]; then
    echo "Run the sim manually:  bash infra/scripts/lab_simulate.sh --non-monotonic --benign-rate $BENIGN_RATE --duration $DURATION"
  else
    echo "Run the sim manually:  bash infra/scripts/lab_simulate.sh --apt $APT --benign-rate $BENIGN_RATE --duration $DURATION"
  fi
  exit 0
fi

# ---- 7) drive the simulation ---------------------------------------------
# lab_simulate.sh already gracefully skips victims that aren't running
# (it does a `docker ps` check before spawning the benign generator) so no
# changes needed there — the sim just operates on the one live victim.
if [[ "$NON_MONOTONIC" -eq 1 ]]; then
  step "running lab_simulate.sh (non-monotonic kill-chain demo  benign=$BENIGN_RATE  duration=$DURATION)"
  bash infra/scripts/lab_simulate.sh \
    --non-monotonic \
    --benign-rate "$BENIGN_RATE" \
    --duration "$DURATION"
else
  step "running lab_simulate.sh (apt=$APT  benign=$BENIGN_RATE  duration=$DURATION)"
  bash infra/scripts/lab_simulate.sh \
    --apt "$APT" \
    --benign-rate "$BENIGN_RATE" \
    --duration "$DURATION"
fi

ok "simulation complete — leave the dashboard up for review"
echo
echo "  ${BOLD}Tear down later:${RESET}  bash $0 stop"
echo "  ${BOLD}Honcho logs:${RESET}      tail -f $HONCHO_LOG"
echo "  ${BOLD}Restart $OTHER_VICTIM later:${RESET}  docker start $OTHER_VICTIM"
