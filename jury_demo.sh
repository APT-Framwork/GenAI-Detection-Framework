#!/usr/bin/env bash
# =============================================================================
# jury_demo.sh — one-shot end-to-end demo for the STRIX dashboard.
#
# Runs the full proof: real Caldera-driven MITRE tactics → Wazuh →
# normalizer → inference (AE / VAE / Transformer / GNN / DQN) → live
# dashboard at http://localhost:5600. Designed so the RL agent visibly
# intervenes (ESCALATE / ISOLATE_HOST) before the chain reaches stage 7
# (ACTIONS_ON_OBJECTIVES) — the "pre-detection" the jury should see.
#
# Pre-requisites:
#   * Docker + docker compose v2
#   * pipx-installed honcho (`pipx install honcho`)
#   * apps/api/.venv exists with the project installed
#   * apps/api/.env present (DB_PASSWORD, AUTH_JWT_SECRET, etc.)
#
# Usage:
#   bash jury_demo.sh             # full bring-up + run + (leaves stack up)
#   bash jury_demo.sh --apt APT41 # alternative APT profile
#   bash jury_demo.sh --duration 240
#   bash jury_demo.sh stop        # tear everything down
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
# Non-monotonic mode: the curated forward/backward kill-chain demo built to
# trip the DQN's ESCALATE threshold so the RL Intervention Timeline lights up
# during the jury demo. See run_full_simulation.py:DEFAULT_NONMONO_STAGES.
NON_MONOTONIC=0
STOP=0
SKIP_SIM=0
CLEAN_STATE=1   # default ON: wipe prior chains/detections/alerts so the run is observable

print_help() {
  cat <<'EOF'
NAME
    jury_demo.sh — one-shot end-to-end STRIX dashboard demo against TWO victims.

SYNOPSIS
    bash jury_demo.sh [--apt APT29|APT41|...]
                      [--duration 180s] [--benign-rate 100/min]
                      [--keep-state] [--skip-sim]
    bash jury_demo.sh stop
    bash jury_demo.sh -h | --help

DESCRIPTION
    Brings the full STRIX stack up locally and drives Caldera through a
    real APT tactic chain against TWO sandcat-enrolled victims:

        wazuh.manager ◀── 1514/1515 ── victim1 ── sandcat ──▶ caldera
              │                       victim2 ── sandcat ──▶
              ▼
          filebeat ──▶ redis ──▶ normalizer ──▶ inference (AE/VAE/TXR/GNN/DQN)
                                       │
                                       ▼
                                 postgres + ws/sse
                                       │
                                       ▼
                       dashboard at http://localhost:5600

    Designed so the RL agent visibly intervenes (ESCALATE / ISOLATE_HOST)
    BEFORE chains reach stage 7 (Actions on Objectives) — the
    "predetection" the jury should see on the dashboard.

    For a one-victim variant (cleaner narrative for first-time juries),
    use jury_demo_single.sh.

PREREQUISITES
    * Docker + docker compose v2
    * pipx-installed honcho        (pipx install honcho)
    * Node + pnpm on PATH          (broken /usr/bin/pnpm symlink? see notes)
    * apps/api/.venv with project + alembic installed
    * apps/api/.env present        (DB_PASSWORD, AUTH_JWT_SECRET, …)

OPTIONS
    --apt NAME            APT profile to emulate. Default: APT29.
                          Implemented chains live in
                          infra/simulation/scripts/run_full_simulation.py
                          (--list-apts to enumerate).

    --non-monotonic       Curated forward/backward kill-chain demo built to
                          trip the DQN's ESCALATE threshold so the dashboard's
                          RL Intervention Timeline lights up during the demo.
                          Sequence: Discovery → Defense Evasion → PrivEsc →
                          Persistence → (repeat) → Impact. Mutually exclusive
                          with --apt; when set, --apt is ignored.

    --duration TIME       Total simulation runtime (e.g. 60s, 4m, 240s).
                          Default: 180s.

    --benign-rate RATE    Background benign-traffic rate per victim, e.g.
                          50/min, 200/min. Default: 100/min.

    --keep-state          Skip the clean-state step. PG (attack_chains,
                          detections, alerts, dqn_actions) and Redis
                          streams keep their prior contents. Useful when
                          comparing runs; off by default because stale
                          chains pollute the live "rl" stream and the
                          FINAL REPORT deltas.

    --skip-sim            Bring the stack up but do NOT run lab_simulate.
                          Run it manually with the printed command.

    stop | --stop         Tear everything down: kills honcho + workers,
                          docker compose down for both compose files.
                          Volumes are preserved so PG keeps its data.

    -h, --help            Show this help and exit.

ENV VARS APPLIED IDEMPOTENTLY TO apps/api/.env
    STRIX_STREAM_PER_MODEL=1            per-model WS fan-out for the dashboard
    STRIX_CHAIN_MAX_STEPS=15            chain rollover after 15 steps (was 50)
    STRIX_CHAIN_IDLE_TIMEOUT_MIN=10     close idle chains after 10 min (was 120)

    Removed if present:
    STRIX_GNN_OPEN_THRESHOLD            synthetic-test override; production
                                        uses the trained 0.7743 default

EXECUTION FLOW
    0)   Restore production GNN threshold + apply chain-binding env vars
    1)   Stop any prior host stack (honcho/uvicorn/workers)
    2)   docker compose up the simulation lab (wazuh + caldera + 2 victims),
         wait for wazuh healthy, run wazuh-control reload to apply
         infra/lab-provisioning/wazuh/local_rules.xml (mutes parent
         rules 80789/80784/80785 so children 100100+ can shine through)
    3)   docker compose up platform deps (postgres + redis + filebeat)
    4)   alembic upgrade head (via apps/api/.venv)
    4.5) Clean state (unless --keep-state) — TRUNCATE chains/detections/
         alerts/dqn_actions + wipe Redis streams/sessions/queues
    5)   honcho start — api + web + 5 workers, log → /tmp/strix_honcho.log
    6)   Wait for /health and dashboard, then prompt the operator
    7)   bash infra/scripts/lab_simulate.sh — drives Caldera through the
         chosen APT chain with paced benign traffic in parallel

WHAT TO WATCH ON THE DASHBOARD
    * Topology              attacker → 2 victims, red pulses on each tactic
    * APT Attack Timeline   live chain progression — paced 6 s/stage
    * RL Intervention       cards land here once the agent intervenes or
      Timeline              the chain hits stage 7
    * Detection Quality     TP/FP/TN/FN populating once labels resolve
    * Forensic Logs         real Wazuh/auditd lines flowing

OUTPUTS
    /tmp/strix_honcho.log                     stdout/stderr of the host stack
    /tmp/strix_honcho.pid                     honcho pid for the stop path
    infra/simulation/runs/<RUN_ID>/           topology.json + per-tactic logs
    Postgres tables                           alerts, detections,
                                              attack_chains, dqn_actions
    FINAL REPORT (run-scoped)                 printed by lab_simulate at end

TROUBLESHOOTING
    pnpm: command not found
        Broken corepack symlink. Fix:
            sudo rm -f /usr/bin/pnpm /usr/bin/pnpx
            sudo npm install -g pnpm

    honcho stops immediately, web.1 rc=127
        Same root cause as above (pnpm missing).

    api /health does not respond
        tail -f /tmp/strix_honcho.log — usually a missing env var, a port
        already in use (8000), or alembic migration fail.

    "0 PREDETECTED / 0 POST-DETECTED" in RL Intervention Timeline
        Backfill from PG should hydrate this. If it stays empty, the API
        may be running stale code — restart with:
            bash jury_demo.sh stop && bash jury_demo.sh

    FINAL REPORT shows ckc Δ +0 for every tactic
        Fixed in May 2026. If still seen, ensure the script being run is
        the latest (run_full_simulation.py uses pg_now baseline).

EXAMPLES
    bash jury_demo.sh
    bash jury_demo.sh --apt APT41 --duration 240
    bash jury_demo.sh --benign-rate 50/min
    bash jury_demo.sh --keep-state              # debug, no clean state
    bash jury_demo.sh --skip-sim                # bring stack up only
    bash jury_demo.sh stop                      # tear down

SEE ALSO
    jury_demo_single.sh                         single-victim variant
    infra/scripts/lab_simulate.sh               the underlying sim runner
    docs/LAB_BRINGUP.md                         one-time setup
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    stop|--stop)     STOP=1; shift ;;
    --apt)           APT="$2"; shift 2 ;;
    --duration)      DURATION="$2"; shift 2 ;;
    --benign-rate)   BENIGN_RATE="$2"; shift 2 ;;
    --keep-state)    CLEAN_STATE=0; shift ;;  # preserve PG/redis history (debug only)
    --skip-sim)      SKIP_SIM=1; shift ;;  # bring stack up but don't run lab_simulate
    --non-monotonic) NON_MONOTONIC=1; APT=""; shift ;;  # forward/backward kill-chain demo
    -h|--help)       print_help; exit 0 ;;
    *) fail "unknown arg: $1   (try: bash $0 --help)" ;;
  esac
done

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
ok "prereqs OK"

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

# Tighter chain binding for demo runs. Default constants (50 steps / 120 min)
# coalesce a whole simulation into one chain per host; demo values produce a
# new chain per tactic so the dashboard + histogram reflect actual phases.
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
# jury sees the attack visibly stop. Hard-off in production (1.0 SOC-policy
# is advisory-only). Worker module: apps/api/.../workers/demo_isolation.py.
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

# ---- 2) bring up the simulation lab (wazuh + caldera + victims) -----------
step "bringing up simulation lab (wazuh manager + caldera + victim1/2)"
docker compose -f infra/compose.simulation.yml up -d --build
ok "sim containers requested"

# Wait for wazuh manager to be healthy (≤180 s — first start is slow).
printf "${DIM}waiting for wazuh.manager healthy ${RESET}"
for _ in $(seq 1 60); do
  status="$(docker inspect -f '{{.State.Health.Status}}' strix_wazuh_manager 2>/dev/null || echo missing)"
  if [[ "$status" == "healthy" ]]; then printf "\n"; ok "wazuh.manager healthy"; break; fi
  printf "."; sleep 3
done
if [[ "${status:-missing}" != "healthy" ]]; then
  warn "wazuh.manager did not report healthy — proceeding anyway (sandcat agents may still enroll)"
fi

# Reload Wazuh rules so edits to local_rules.xml (e.g. 80789 mute) take
# effect even when the container was already running from a previous run.
# The file is bind-mounted ro from infra/lab-provisioning/wazuh/.
if docker exec strix_wazuh_manager /var/ossec/bin/wazuh-control reload >/dev/null 2>&1; then
  ok "wazuh: ruleset reloaded (custom local_rules.xml applied)"
else
  warn "wazuh-control reload failed — restarting container"
  docker compose -f infra/compose.simulation.yml restart strix_wazuh_manager >/dev/null
fi

# ---- 3) bring up platform deps (postgres + redis + filebeat) --------------
step "bringing up platform deps (postgres + redis + filebeat)"
docker compose -f infra/compose.platform-deps.yml --env-file "$ENV_FILE" up -d
printf "${DIM}waiting for postgres + redis healthy ${RESET}"
for _ in $(seq 1 30); do
  pg="$(docker inspect -f '{{.State.Health.Status}}' strix_postgres 2>/dev/null || echo missing)"
  rd="$(docker inspect -f '{{.State.Health.Status}}' strix_redis 2>/dev/null || echo missing)"
  if [[ "$pg" == "healthy" && "$rd" == "healthy" ]]; then printf "\n"; ok "deps healthy"; break; fi
  printf "."; sleep 1
done

# ---- 4) migrations (venv alembic — system pipx alembic lacks pydantic) ----
step "running alembic upgrade head (via project venv)"
( cd apps/api && set -a && source ./.env && set +a && "$VENV/bin/alembic" upgrade head ) >/dev/null
ok "schema at head"

# ---- 4.5) clean prior state so the demo run is observable -----------------
# Pass --keep-state to skip (debug only). The platform accumulates ~100k open
# chains across runs; without this step the live "rl" stream surfaces stale
# chains from old runs and the FINAL REPORT deltas are dominated by history.
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

  # Wipe live streams, alert queue, verdicts, SSE channels, per-agent sessions,
  # and feature shards. Preserves arq:* (worker queue) and strix:auto_response:*
  # (kill-switch). Key prefixes verified against:
  #   apps/api/src/strix_api/api/routes/streams.py    (strix:stream:*, strix:sse:*)
  #   apps/api/src/strix_api/adapters/session_store.py (session:*)
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

# ---- 5) start the host stack (api + web + 5 workers) via honcho -----------
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

# ---- 6) the demo moment ----------------------------------------------------
echo
echo -e "${BOLD}${CYAN}┌─────────────────────────────────────────────────────────────────┐${RESET}"
echo -e "${BOLD}${CYAN}│${RESET}  Dashboard ready: ${BOLD}$DASHBOARD_URL${RESET}"
echo -e "${BOLD}${CYAN}│${RESET}  Open it in your browser ${BOLD}NOW${RESET}, confirm the LIVE pill is green."
echo -e "${BOLD}${CYAN}│${RESET}  About to drive Caldera through APT=$APT for $DURATION."
echo -e "${BOLD}${CYAN}│${RESET}  Watch:"
echo -e "${BOLD}${CYAN}│${RESET}    • Topology — attacker → 2 victims, red pulses on each tactic"
echo -e "${BOLD}${CYAN}│${RESET}    • RL Kill-Chain — rows progressing 1→…→7, DQN intervenes mid-chain"
echo -e "${BOLD}${CYAN}│${RESET}    • Detection Quality — TP/FP/TN/FN populating once labels resolve"
echo -e "${BOLD}${CYAN}│${RESET}    • Forensic Logs — real Wazuh/auditd lines flowing"
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

# ---- 7) drive the simulation ----------------------------------------------
# Pick the right driver flag — APT chain (default) vs the curated
# non-monotonic kill-chain demo. Both go through lab_simulate.sh which
# forwards everything verbatim to run_full_simulation.py.
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
