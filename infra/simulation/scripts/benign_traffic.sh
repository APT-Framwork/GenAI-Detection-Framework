#!/usr/bin/env bash
# =============================================================================
# STRIX — benign-traffic generator.
#
# Loops realistic, harmless activity (SSH login, curl, dig, cron, file reads,
# apt list, dpkg -l) at a configurable rate. Each command is appended to
# {RUN_DIR}/benign_events.jsonl as ground-truth so the labeller can cross-
# reference Wazuh events on (host, ts ± 500 ms).
#
# Filebeat tags these via auid -> user (strixbenign) match (see
# infra/filebeat.yml). The sidecar JSONL is the robust fallback.
#
# Designed to run as the dedicated unprivileged user `strixbenign`.
#
# Usage:
#   benign_traffic.sh --rate 100/min --duration 60s \
#                     --targets 127.0.0.1,wazuh.manager \
#                     --run-dir /path/to/runs/<run_id>
# =============================================================================
set -euo pipefail

RATE="60/min"
DURATION="60s"
TARGETS="127.0.0.1"
RUN_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rate)     RATE="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --targets)  TARGETS="$2"; shift 2 ;;
    --run-dir)  RUN_DIR="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Parse "N/min" or "N/sec" -> events_per_sec
if [[ "$RATE" =~ ^([0-9]+)/min$ ]]; then
  EPS=$(awk -v n="${BASH_REMATCH[1]}" 'BEGIN{printf "%.4f", n/60.0}')
elif [[ "$RATE" =~ ^([0-9]+)/sec$ ]]; then
  EPS="${BASH_REMATCH[1]}"
else
  echo "bad --rate: $RATE (want N/min or N/sec)" >&2
  exit 2
fi

# Parse duration into seconds
case "$DURATION" in
  *s) DUR_S="${DURATION%s}" ;;
  *m) DUR_S=$(( ${DURATION%m} * 60 )) ;;
  *h) DUR_S=$(( ${DURATION%h} * 3600 )) ;;
  *)  DUR_S="$DURATION" ;;
esac

if [[ -z "$RUN_DIR" ]]; then
  echo "--run-dir required" >&2
  exit 2
fi
mkdir -p "$RUN_DIR"
SIDECAR="$RUN_DIR/benign_events.jsonl"
: > "$SIDECAR".lock 2>/dev/null || true
touch "$SIDECAR"

IFS=',' read -r -a TGT_ARR <<< "$TARGETS"
HOST="$(hostname)"

# Mean inter-arrival in ms. Add ±50% jitter to look human.
MEAN_MS=$(awk -v eps="$EPS" 'BEGIN{ if (eps<=0) eps=1; printf "%d", 1000.0/eps }')

emit() {
  # $1 = command label for sidecar
  local cmd="$1"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
  printf '{"ts":"%s","host":"%s","pid":%d,"cmd":%s}\n' \
    "$ts" "$HOST" "$$" "$(printf '%s' "$cmd" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))' 2>/dev/null || printf '"%s"' "$cmd")" \
    >> "$SIDECAR"
}

# ----- benign action implementations (line-buffered, no failures fatal) -----

action_curl() {
  local tgt="${TGT_ARR[RANDOM % ${#TGT_ARR[@]}]}"
  local cmd="curl -fsS --max-time 2 http://${tgt}/"
  ( $cmd >/dev/null 2>&1 || true ) &
  emit "$cmd"
}

action_dig() {
  local hosts=(example.com debian.org github.com kernel.org cloudflare.com)
  local h="${hosts[RANDOM % ${#hosts[@]}]}"
  local cmd="dig +short +time=1 +tries=1 ${h}"
  ( $cmd >/dev/null 2>&1 || true ) &
  emit "$cmd"
}

action_ssh_attempt() {
  local tgt="${TGT_ARR[RANDOM % ${#TGT_ARR[@]}]}"
  # ConnectTimeout=1, BatchMode means it'll fail without prompting — that's
  # the realistic "user typed wrong password" benign signal we want.
  local cmd="ssh -o ConnectTimeout=1 -o BatchMode=yes -o StrictHostKeyChecking=no strixbenign@${tgt} true"
  ( $cmd >/dev/null 2>&1 || true ) &
  emit "$cmd"
}

action_file_read() {
  local files=(/etc/hostname /etc/os-release /proc/uptime /proc/loadavg /proc/cpuinfo)
  local f="${files[RANDOM % ${#files[@]}]}"
  local cmd="cat ${f}"
  ( $cmd >/dev/null 2>&1 || true ) &
  emit "$cmd"
}

action_apt_list() {
  local cmd="apt list --installed"
  ( $cmd >/dev/null 2>&1 || true ) &
  emit "$cmd"
}

action_dpkg_l() {
  local cmd="dpkg -l"
  ( $cmd >/dev/null 2>&1 || true ) &
  emit "$cmd"
}

action_cron_touch() {
  # Append a harmless comment line to the user's own crontab spool — does
  # not require root, exercises the dpkg/PAM/audit watch on cron paths.
  local f="/tmp/strixbenign.cron.$$"
  local cmd="printf '# benign noise %s\n' \"$(date -u +%s)\" > ${f}"
  ( eval "$cmd" >/dev/null 2>&1 || true ) &
  emit "$cmd"
}

ACTIONS=(action_curl action_dig action_ssh_attempt action_file_read action_apt_list action_dpkg_l action_cron_touch)

START="$(date +%s)"
END=$(( START + DUR_S ))

while [[ "$(date +%s)" -lt "$END" ]]; do
  a="${ACTIONS[RANDOM % ${#ACTIONS[@]}]}"
  "$a"
  # jitter ±50% of MEAN_MS
  jitter_ms=$(( (RANDOM % MEAN_MS) + MEAN_MS / 2 ))
  # bash sleep accepts fractional seconds
  sleep "$(awk -v m="$jitter_ms" 'BEGIN{printf "%.3f", m/1000.0}')"
done

# Wait for in-flight background commands so audit events land before exit.
wait || true
