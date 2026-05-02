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
GREEN='\033[32m'; RED='\033[31m'; YELLOW='\033[33m'; CYAN='\033[36m'; DIM='\033[2m'; BOLD='\033[1m'; RESET='\033[0m'
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
STOP=0
SKIP_SIM=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    stop|--stop)     STOP=1; shift ;;
    --apt)           APT="$2"; shift 2 ;;
    --duration)      DURATION="$2"; shift 2 ;;
    --benign-rate)   BENIGN_RATE="$2"; shift 2 ;;
    --skip-sim)      SKIP_SIM=1; shift ;;  # bring stack up but don't run lab_simulate
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    *) fail "unknown arg: $1" ;;
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
  echo "Run the sim manually:  bash infra/scripts/lab_simulate.sh --apt $APT --benign-rate $BENIGN_RATE --duration $DURATION"
  exit 0
fi

# ---- 7) drive the simulation ----------------------------------------------
step "running lab_simulate.sh (apt=$APT  benign=$BENIGN_RATE  duration=$DURATION)"
bash infra/scripts/lab_simulate.sh \
  --apt "$APT" \
  --benign-rate "$BENIGN_RATE" \
  --duration "$DURATION"

ok "simulation complete — leave the dashboard up for review"
echo
echo "  ${BOLD}Tear down later:${RESET}  bash $0 stop"
echo "  ${BOLD}Honcho logs:${RESET}      tail -f $HONCHO_LOG"
