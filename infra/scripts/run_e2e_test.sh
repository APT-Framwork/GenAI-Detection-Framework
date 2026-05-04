#!/usr/bin/env bash
# =============================================================================
# run_e2e_test.sh — one-command end-to-end verification of the STRIX demo.
#
# Sequence (single foreground orchestrator):
#   1. Launch jury_demo_single.sh in foreground (it brings the lab + honcho
#      up and waits for "Press ENTER…").
#   2. Once /health + dashboard are up, fork:
#        - monitor_demo.py --ws-tap        (Layers 1+2: backend + gateway)
#        - playwright_check.py             (Layer 3: dashboard render)
#   3. Send ENTER to jury_demo so lab_simulate begins.
#   4. Wait for lab_simulate to finish.
#   5. SIGTERM both monitors (each writes a PASS/FAIL JSON on exit).
#   6. Aggregate the three artifact dirs into FINAL_REPORT.md.
#
# Outputs land in /tmp/strix_e2e_<RUN_ID>/.
#
# Usage:
#   bash infra/scripts/run_e2e_test.sh                           # APT41 default
#   bash infra/scripts/run_e2e_test.sh --apt APT29 --duration 240
#   bash infra/scripts/run_e2e_test.sh --skip-monitor            # demo only
#   bash infra/scripts/run_e2e_test.sh --skip-playwright         # no browser
#   bash infra/scripts/run_e2e_test.sh -h | --help
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

VENV="$REPO/apps/api/.venv"
DEMO_LOG="/tmp/strix_e2e_demo.log"
MONITOR_LOG="/tmp/strix_e2e_monitor.log"
PLAYWRIGHT_LOG="/tmp/strix_e2e_playwright.log"

# Colors: ANSI-C $'…' so they survive printf %s.
G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; D=$'\033[2m'; B=$'\033[1m'; X=$'\033[0m'
ok()   { printf "%s✓%s %s\n" "$G" "$X" "$*"; }
warn() { printf "%s⚠%s %s\n" "$Y" "$X" "$*"; }
fail() { printf "%s✗%s %s\n" "$R" "$X" "$*"; exit 1; }
step() { printf "\n%s──[ %s%s%s%s ]──%s\n" "$D" "$B" "$*" "$X" "$D" "$X"; }

APT="APT41"
DURATION="240s"
SKIP_MONITOR=0
SKIP_PLAYWRIGHT=0
HEADLESS_FLAG="--headless"
EMAIL_FLAG=""
PASSWORD_FLAG=""

print_help() {
  sed -n '4,23p' "$0" | sed 's/^# \?//'
  cat <<EOF

OPTIONS
    --apt NAME            APT profile (default: APT41)
    --duration TIME       sim duration (default: 240s)
    --skip-monitor        don't run monitor_demo.py
    --skip-playwright     don't run playwright_check.py
    --no-headless         show browser (default: headless)
    --email EMAIL         dashboard login email
    --password PASSWORD   dashboard login password
    -h, --help            show this help

NOTES
    The orchestrator does NOT modify your demo flow — jury_demo_single.sh
    runs unchanged in the foreground. The monitors attach in parallel.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apt)            APT="$2"; shift 2 ;;
    --duration)       DURATION="$2"; shift 2 ;;
    --skip-monitor)   SKIP_MONITOR=1; shift ;;
    --skip-playwright)SKIP_PLAYWRIGHT=1; shift ;;
    --no-headless)    HEADLESS_FLAG="--no-headless --system-chrome"; shift ;;
    --email)          EMAIL_FLAG="--email $2"; shift 2 ;;
    --password)       PASSWORD_FLAG="--password $2"; shift 2 ;;
    -h|--help)        print_help; exit 0 ;;
    *) fail "unknown arg: $1   (try: bash $0 --help)" ;;
  esac
done

# ---- prereqs --------------------------------------------------------------
step "checking prereqs"
[[ -x "$VENV/bin/python" ]] || fail "$VENV missing — run from a fresh project setup"
"$VENV/bin/python" -c "import asyncpg, redis.asyncio, websockets" 2>/dev/null \
  || fail "venv missing asyncpg/redis/websockets — run: $VENV/bin/pip install asyncpg redis websockets"
if [[ "$SKIP_PLAYWRIGHT" -eq 0 ]]; then
  "$VENV/bin/python" -c "import playwright" 2>/dev/null \
    || fail "playwright missing — run: $VENV/bin/pip install playwright && $VENV/bin/playwright install chromium"
fi
ok "prereqs OK"

# ---- launch jury_demo, capture its output ---------------------------------
step "launching jury_demo_single.sh --apt $APT --duration $DURATION"
: > "$DEMO_LOG"
# Run jury_demo with stdin tied to a FIFO so we can auto-press ENTER once
# the dashboard is up.
DEMO_FIFO="$(mktemp -u)"
mkfifo "$DEMO_FIFO"
exec 9<>"$DEMO_FIFO"

(
  bash jury_demo_single.sh --apt "$APT" --duration "$DURATION" <"$DEMO_FIFO" \
    > >(tee -a "$DEMO_LOG") 2>&1
) &
DEMO_PID=$!

# ---- wait for dashboard ready prompt --------------------------------------
step "waiting for jury_demo to reach the operator prompt"
DEADLINE=$(( $(date +%s) + 300 ))   # 5 min boot budget
while [[ $(date +%s) -lt $DEADLINE ]]; do
  if grep -q "Press ENTER once the dashboard is open" "$DEMO_LOG" 2>/dev/null; then
    ok "demo reached operator prompt"
    break
  fi
  sleep 2
done

if ! grep -q "Press ENTER" "$DEMO_LOG"; then
  warn "demo didn't reach the prompt within 5 min — check $DEMO_LOG"
fi

# ---- press ENTER → sim begins (BEFORE monitors so topology.json is fresh) -
step "pressing ENTER to start the simulation"
sleep 2
echo "" >&9
exec 9>&-
ok "ENTER sent"

# ---- wait for the new run_id to appear in the demo log --------------------
# lab_simulate.sh prints `[lab_simulate] run_id=<NEW>` once it has written
# the fresh topology.json. We wait for that so monitor + playwright pick
# up the new run from the start, and their artifact dirs use the right
# run_id (not whatever stale topology was around at orchestrator start).
step "waiting for fresh run_id + topology.json from lab_simulate"
# IMPORTANT: lab_simulate prints `run_id=...` BEFORE writing topology.json.
# Monitor + playwright resolve their out_dir via latest_topology(), which
# reads infra/simulation/runs/*/topology.json by mtime — so we have to wait
# for the FILE, not just the log line. Otherwise they pick up the previous
# run's topology and write artifacts to the wrong dir.
#
# `set -e` + `pipefail` means a failed grep on the first poll (before the
# log line exists) would silently kill the orchestrator. `|| true` on each
# substitution keeps us in the loop while the line is missing.
NEW_RUN_ID=""
WAIT_DEADLINE=$(( $(date +%s) + 90 ))
while [[ $(date +%s) -lt $WAIT_DEADLINE ]]; do
  NEW_RUN_ID="$(grep -oE '\[lab_simulate\] run_id=[^[:space:]]+' "$DEMO_LOG" 2>/dev/null \
                  | tail -1 | sed 's/.*run_id=//' || true)"
  if [[ -n "$NEW_RUN_ID" ]] \
     && [[ -f "$REPO/infra/simulation/runs/$NEW_RUN_ID/topology.json" ]]; then
    break
  fi
  sleep 1
done
if [[ -z "$NEW_RUN_ID" ]]; then
  warn "no run_id yet — monitors may attach to an older topology"
elif [[ ! -f "$REPO/infra/simulation/runs/$NEW_RUN_ID/topology.json" ]]; then
  warn "run_id=$NEW_RUN_ID found but topology.json never appeared"
else
  ok "fresh run_id=$NEW_RUN_ID  (topology.json present)"
fi

# ---- start monitors -------------------------------------------------------
MONITOR_PID=""
PLAYWRIGHT_PID=""
if [[ "$SKIP_MONITOR" -eq 0 ]]; then
  step "starting monitor_demo.py (Layers 1+2)"
  : > "$MONITOR_LOG"
  ( "$VENV/bin/python" "$REPO/infra/scripts/monitor_demo.py" --ws-tap \
       $EMAIL_FLAG $PASSWORD_FLAG \
       > "$MONITOR_LOG" 2>&1 ) &
  MONITOR_PID=$!
  ok "monitor pid=$MONITOR_PID  log=$MONITOR_LOG"
fi

if [[ "$SKIP_PLAYWRIGHT" -eq 0 ]]; then
  step "starting playwright_check.py (Layer 3)"
  : > "$PLAYWRIGHT_LOG"
  ( "$VENV/bin/python" "$REPO/infra/scripts/playwright_check.py" \
       $HEADLESS_FLAG $EMAIL_FLAG $PASSWORD_FLAG \
       --watch-seconds 600 \
       > "$PLAYWRIGHT_LOG" 2>&1 ) &
  PLAYWRIGHT_PID=$!
  ok "playwright pid=$PLAYWRIGHT_PID  log=$PLAYWRIGHT_LOG"
fi

# ---- wait for sim to finish ----------------------------------------------
step "waiting for simulation to complete (up to ${DURATION%s} + 120s buffer)"
wait "$DEMO_PID" || true
ok "demo finished"

# ---- shut down monitors ---------------------------------------------------
# SIGTERM the monitors so they break out of their watch loops, run their
# post-sim wrap-up (playwright's UI tour + drill-down, monitor's final
# JSON), and exit cleanly. We give them up to 90 s — playwright's UI tour
# visits ~7 pages and clicks into attack-analysis, which takes a while —
# only SIGKILL if they're still running after that.
step "shutting down monitors (SIGTERM → final reports, up to 90s)"
[[ -n "$MONITOR_PID" ]]    && kill -TERM "$MONITOR_PID"    2>/dev/null || true
[[ -n "$PLAYWRIGHT_PID" ]] && kill -TERM "$PLAYWRIGHT_PID" 2>/dev/null || true
WAIT_DEADLINE=$(( $(date +%s) + 90 ))
while [[ $(date +%s) -lt $WAIT_DEADLINE ]]; do
  alive=0
  [[ -n "$MONITOR_PID" ]]    && kill -0 "$MONITOR_PID"    2>/dev/null && alive=1
  [[ -n "$PLAYWRIGHT_PID" ]] && kill -0 "$PLAYWRIGHT_PID" 2>/dev/null && alive=1
  [[ "$alive" -eq 0 ]] && break
  sleep 2
done
[[ -n "$MONITOR_PID" ]]    && kill -KILL "$MONITOR_PID"    2>/dev/null || true
[[ -n "$PLAYWRIGHT_PID" ]] && kill -KILL "$PLAYWRIGHT_PID" 2>/dev/null || true

# ---- find the run_id, aggregate -------------------------------------------
step "aggregating into FINAL_REPORT.md"
RUN_DIR="$(find /tmp -maxdepth 1 -type d -name 'strix_e2e_*' -printf '%T@ %p\n' 2>/dev/null | sort -nr | awk 'NR==1{print $2}')"
if [[ -z "$RUN_DIR" || ! -d "$RUN_DIR" ]]; then
  warn "no /tmp/strix_e2e_* dir found — monitors may not have started"
  exit 2
fi

REPORT="$RUN_DIR/FINAL_REPORT.md"
{
  echo "# STRIX E2E Test Report"
  echo
  echo "Run dir: \`$RUN_DIR\`"
  echo "Date:    $(date -Iseconds)"
  echo "APT:     $APT"
  echo "Duration:$DURATION"
  echo

  if [[ -f "$RUN_DIR/monitor_final.json" ]]; then
    echo "## Layer 1+2 — Backend + Gateway (monitor_demo.py)"
    "$VENV/bin/python" -c "
import json, sys
d = json.load(open('$RUN_DIR/monitor_final.json'))
print(f\"**Verdict:** {d['overall']}  ({d['passed']}/{d['total']} hard checks)\")
print()
print('| Check | Result | Note |')
print('|---|---|---|')
for c in d['checks']:
    glyph = '✅' if c['ok'] else '❌'
    note = c.get('note','').replace('|','\\\\|')
    print(f\"| {c['name']} | {glyph} | {note} |\")
print()
print('## Run metrics')
m = d.get('metrics', {})
for k, v in m.items():
    print(f'- **{k}**: {v}')
print()
"
  else
    echo "## Layer 1+2 — Backend + Gateway"
    echo
    echo "_(monitor_demo.py did not produce monitor_final.json — see \`$MONITOR_LOG\`)_"
    echo
  fi

  if [[ -f "$RUN_DIR/playwright_final.json" ]]; then
    echo "## Layer 3 — Dashboard Render (playwright_check.py)"
    "$VENV/bin/python" -c "
import json
d = json.load(open('$RUN_DIR/playwright_final.json'))
print(f\"**Verdict:** {d['overall']}  ({d['passed']}/{d['total']} assertions)\")
print()
print('| Assertion | Result | Note |')
print('|---|---|---|')
for a in d['assertions']:
    glyph = '✅' if a['ok'] else '❌'
    note = a.get('note','').replace('|','\\\\|')[:80]
    print(f\"| {a['name']} | {glyph} | {note} |\")
print()
"
  else
    echo "## Layer 3 — Dashboard Render"
    echo
    echo "_(playwright_check.py did not produce playwright_final.json — see \`$PLAYWRIGHT_LOG\`)_"
    echo
  fi

  echo "## Artifacts"
  echo
  echo '```'
  ls -1 "$RUN_DIR" 2>/dev/null
  echo '```'
  if [[ -d "$RUN_DIR/screenshots" ]]; then
    echo
    echo "### Screenshots"
    echo
    for f in "$RUN_DIR"/screenshots/*.png; do
      [[ -f "$f" ]] && echo "- \`$f\`"
    done
  fi
  echo
  echo "## Logs"
  echo
  echo "- demo:        \`$DEMO_LOG\`"
  echo "- monitor:     \`$MONITOR_LOG\`"
  echo "- playwright:  \`$PLAYWRIGHT_LOG\`"
} > "$REPORT"

# ---- decide overall exit code --------------------------------------------
OVERALL_PASS=1
if [[ -f "$RUN_DIR/monitor_final.json" ]]; then
  grep -q '"overall": "FAIL"' "$RUN_DIR/monitor_final.json" && OVERALL_PASS=0
fi
if [[ -f "$RUN_DIR/playwright_final.json" ]]; then
  grep -q '"overall": "FAIL"' "$RUN_DIR/playwright_final.json" && OVERALL_PASS=0
fi

step "final"
echo "Report: $REPORT"
if [[ "$OVERALL_PASS" -eq 1 ]]; then
  ok "OVERALL: PASS"
  exit 0
else
  fail "OVERALL: FAIL — see $REPORT"
fi
