#!/usr/bin/env bash
# =============================================================================
# STRIX — full real-time MITRE ATT&CK simulation.
#
# Drives Caldera through every paper-aligned tactic against group=red,
# captures Wazuh alerts, watches them flow through Redis -> Postgres
# (alerts -> detections -> attack_chains -> dqn_actions), and prints a
# per-tactic + final report card.
#
# This wrapper:
#   - allocates a per-run directory under infra/simulation/runs/{run_id}
#   - emits topology.json ground-truth manifest at startup
#   - kicks the benign-traffic generator inside each victim container
#     (in parallel, non-blocking) when --benign-rate is set
#   - exec's the python orchestrator under stdbuf -oL -eL so every event
#     line flushes immediately (auditd->filebeat tail picks up <2 s)
#
# Usage:
#   bash infra/scripts/lab_simulate.sh                    # full run
#   bash infra/scripts/lab_simulate.sh --dry-run          # plan only
#   bash infra/scripts/lab_simulate.sh --report-only      # current state
#   bash infra/scripts/lab_simulate.sh --list             # show stockpile
#   bash infra/scripts/lab_simulate.sh --only Discovery,Collection
#   bash infra/scripts/lab_simulate.sh --budget 120 --dwell 45
#   bash infra/scripts/lab_simulate.sh \
#         --benign-rate 100/min --duration 60s --apt APT29
#
# Pre-reqs:
#   1. lab is up:                bash infra/scripts/lab_up.sh
#   2. host auditd has rules:    sudo auditctl -l | grep audit-wazuh-x
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$REPO/apps/api/.env"
PY="$REPO/apps/api/.venv/bin/python"
SCRIPT="$REPO/infra/simulation/scripts/run_full_simulation.py"
BENIGN_SH="$REPO/infra/simulation/scripts/benign_traffic.sh"
RUNS_DIR="$REPO/infra/simulation/runs"

# ---- arg pre-parse: extract our orchestration-only flags before exec'ing
# the python script. Anything we don't recognise is forwarded verbatim.
BENIGN_RATE=""
DURATION=""
APT=""
DRY_RUN=0
PASS_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --benign-rate) BENIGN_RATE="$2"; shift 2 ;;
    --duration)    DURATION="$2"; shift 2 ;;
    --apt)         APT="$2"; PASS_ARGS+=("--apt" "$2"); shift 2 ;;
    --dry-run)     DRY_RUN=1; PASS_ARGS+=("--dry-run"); shift ;;
    *)             PASS_ARGS+=("$1"); shift ;;
  esac
done

# Load env vars (DB_USER, DB_NAME, REDIS_HOST etc.) so the python script picks them up.
if [[ -f "$ENV_FILE" ]]; then
  set -a; . <(grep -v '^#' "$ENV_FILE" | grep -v '^$' | sed 's/ #.*//'); set +a
fi

# Fall back to system python3 if venv missing.
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

# ---- run dir + topology.json ------------------------------------------------
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
RUN_DIR="$RUNS_DIR/$RUN_ID"
mkdir -p "$RUN_DIR"
echo "[lab_simulate] run_id=$RUN_ID"
echo "[lab_simulate] run_dir=$RUN_DIR"

export STRIX_RUN_ID="$RUN_ID"
export STRIX_RUN_DIR="$RUN_DIR"
export STRIX_APT="${APT:-}"

# Compose-network introspection — best-effort. Fall back to docker DNS names.
attacker_ip="$(docker inspect strix_caldera \
  --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{"\n"}}{{end}}' \
  2>/dev/null | head -1 || true)"
victim1_ip="$(docker inspect strix_victim1 \
  --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{"\n"}}{{end}}' \
  2>/dev/null | head -1 || true)"
victim2_ip="$(docker inspect strix_victim2 \
  --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{"\n"}}{{end}}' \
  2>/dev/null | head -1 || true)"
export STRIX_ATTACKER_IP="${attacker_ip:-}"
export STRIX_VICTIM1_IP="${victim1_ip:-}"
export STRIX_VICTIM2_IP="${victim2_ip:-}"

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > "$RUN_DIR/topology.json" <<JSON
{
  "run_id": "$RUN_ID",
  "started_at": "$started_at",
  "attacker_ip": "${attacker_ip:-caldera}",
  "victims": [
    {"ip": "${victim1_ip:-victim1}", "hostname": "victim1", "agents": ["wazuh", "sandcat", "auditd"]},
    {"ip": "${victim2_ip:-victim2}", "hostname": "victim2", "agents": ["wazuh", "sandcat", "auditd"]}
  ],
  "apt_group": "${APT:-}",
  "tactics_planned": [
    "Discovery", "Defense Evasion", "Persistence", "Privilege Escalation",
    "Credential Access", "Lateral Movement", "Collection",
    "Exfiltration", "Impact"
  ]
}
JSON
echo "[lab_simulate] wrote $RUN_DIR/topology.json"

# ---- benign generator (parallel, non-blocking) ------------------------------
BENIGN_PIDS=()
cleanup_benign() {
  for pid in "${BENIGN_PIDS[@]:-}"; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done
}
trap cleanup_benign EXIT

if [[ -n "$BENIGN_RATE" && "$DRY_RUN" -eq 0 ]]; then
  dur="${DURATION:-300s}"
  echo "[lab_simulate] starting benign traffic generators rate=$BENIGN_RATE duration=$dur"
  for victim in strix_victim1 strix_victim2; do
    if docker ps --format '{{.Names}}' | grep -qx "$victim"; then
      docker cp "$BENIGN_SH" "$victim:/tmp/benign_traffic.sh" >/dev/null 2>&1 || true
      docker exec "$victim" chmod +x /tmp/benign_traffic.sh >/dev/null 2>&1 || true
      docker exec "$victim" mkdir -p "/tmp/strix_run/$RUN_ID" >/dev/null 2>&1 || true
      # Run as strixbenign so auid carries the synthetic_benign signal.
      stdbuf -oL -eL docker exec "$victim" \
        runuser -u strixbenign -- \
        /tmp/benign_traffic.sh \
          --rate "$BENIGN_RATE" \
          --duration "$dur" \
          --targets "127.0.0.1,wazuh.manager,caldera" \
          --run-dir "/tmp/strix_run/$RUN_ID" \
        > "$RUN_DIR/benign_${victim}.log" 2>&1 &
      BENIGN_PIDS+=("$!")
      echo "[lab_simulate]   spawned benign on $victim (pid=$!)"
    fi
  done
fi

# ---- main orchestrator ------------------------------------------------------
# stdbuf -oL -eL forces the python child to flush stdout/stderr at line
# granularity even when piped through tee/tail. Combined with PYTHONUNBUFFERED
# this guarantees per-event visibility within the auditd->filebeat tail latency.
export PYTHONUNBUFFERED=1

stdbuf -oL -eL "$PY" -u "$SCRIPT" "${PASS_ARGS[@]:-}"
rc=$?

# Drain benign generators (they will self-exit when --duration elapses).
for pid in "${BENIGN_PIDS[@]:-}"; do
  wait "$pid" 2>/dev/null || true
done

# Pull benign sidecars off the victims into the run dir for offline labelling.
for victim in strix_victim1 strix_victim2; do
  if docker ps --format '{{.Names}}' | grep -qx "$victim"; then
    docker cp "$victim:/tmp/strix_run/$RUN_ID/benign_events.jsonl" \
      "$RUN_DIR/benign_events_${victim}.jsonl" >/dev/null 2>&1 || true
  fi
done

echo "[lab_simulate] run complete rc=$rc artifacts=$RUN_DIR"
exit "$rc"
