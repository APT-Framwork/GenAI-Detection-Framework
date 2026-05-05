#!/usr/bin/env bash
# =============================================================================
# STRIX — non-monotonic-sim + live stage-walk monitor.
#
# Runs the curated --non-monotonic kill-chain demo AND streams the per-event
# `ckc_stage` walk from Postgres in the same terminal, so we can verify that
# the chain matcher is actually seeing the forwards/backwards motion the
# Transformer was trained on (not just a monotonic march to stage 5).
#
# Output legend (one line per poll, every POLL_INTERVAL_S seconds):
#
#   12:34:56  chain ab12cd34  host=victim2   walk: 4 → 4 → 4 → 0 → 4 ↓ → 3 → 4 ↑ → 5
#                                                                  ▲           ▲
#                                                                  └ backward  └ forward
#
#   '↓' marks a per-event stage *drop* (current alert tagged at lower CKC than
#   the previous one) — that's the backward motion we want to see.
#   '↑' marks a forward jump of more than one stage in a single step.
#
# At the end of the run we print a delta summary: total forward steps, backward
# steps, distinct stages observed per chain, and a verdict on whether the run
# actually exhibited non-monotonic motion.
#
# Usage:
#   bash infra/scripts/sim_with_walk_monitor.sh                          # default
#   bash infra/scripts/sim_with_walk_monitor.sh --budget 60 --dwell 30   # extra args
#                                                                         flow through
#                                                                         to lab_simulate.sh
# Stop with Ctrl+C (forwards SIGINT to the simulator so it tears down cleanly).
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PG_CONTAINER="${PG_CONTAINER:-strix_postgres}"
PG_USER="${DB_USER:-strix}"
PG_DB="${DB_NAME:-strix}"
POLL_INTERVAL_S=3
WALK_TAIL=20      # show last N events per chain on each poll
TRACK_CHAINS=4    # how many recently-active chains to show

# Forward whatever the user passed through to lab_simulate.sh — they can
# override --budget/--dwell/--benign-rate but the --non-monotonic mode is
# the whole point of this script so we hard-pin it.
SIM_ARGS=(--non-monotonic "$@")

# ANSI styling (off if not a TTY — keeps logs sane).
if [[ -t 1 ]]; then
  RESET=$'\033[0m'; BOLD=$'\033[1m'; DIM=$'\033[2m'
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; CYAN=$'\033[36m'; MAGENTA=$'\033[35m'
else
  RESET=""; BOLD=""; DIM=""; RED=""; GREEN=""; YELLOW=""; CYAN=""; MAGENTA=""
fi

# Establish the run-window cutoff *before* the sim fires so we never count
# pre-existing chains. Format compatible with PG's `timestamptz` literal.
WINDOW_START_ISO="$(date -u +%Y-%m-%dT%H:%M:%S.%6N+00:00)"

# Kick the sim in the background. Capture its log alongside ours so the
# user has a single artefact to diff later.
SIM_LOG="/tmp/strix-sim-walk-${WINDOW_START_ISO//[:.+-]/_}.log"
echo "${BOLD}[monitor]${RESET}  starting sim — log → ${DIM}${SIM_LOG}${RESET}"
echo "${BOLD}[monitor]${RESET}  args: ${SIM_ARGS[*]}"
echo "${BOLD}[monitor]${RESET}  window cutoff: ${DIM}${WINDOW_START_ISO}${RESET}"
echo

bash "$REPO/infra/scripts/lab_simulate.sh" "${SIM_ARGS[@]}" >"$SIM_LOG" 2>&1 &
SIM_PID=$!

# Cleanly forward Ctrl+C: SIGINT hits the orchestrator so it prints a partial
# report. We don't kill -9; the sim's own KeyboardInterrupt handler does the
# right thing.
trap 'echo; echo "${YELLOW}[monitor]${RESET}  interrupt — propagating to sim (pid=$SIM_PID)"; kill -INT $SIM_PID 2>/dev/null || true' INT TERM

# Per-chain accumulators for the final summary.
declare -A LAST_WALK            # chain_id → last "stage1|stage2|…" string we printed
declare -A FORWARDS BACKWARDS   # chain_id → counters
declare -A STAGES_SEEN          # chain_id → "0,3,4,5" comma-set
declare -A HOST_OF              # chain_id → host name
TOTAL_BACK=0
TOTAL_FWD=0

print_walk_for_chain() {
  local chain_id="$1" host="$2" walk_pipe="$3"
  # Convert pipe-delimited list "4|4|0|4|3|4|5" → "4 → 4 → 4↓ → 0 → 4↑ → 3 → 4↑ → 5"
  IFS='|' read -ra STAGES <<< "$walk_pipe"
  local prev=-1
  local out=""
  local back=0 fwd=0
  for s in "${STAGES[@]}"; do
    [[ -z "$s" ]] && continue
    local seg="$s"
    if [[ $prev -ge 0 ]]; then
      if   (( s < prev )); then seg="${RED}${BOLD}${s}↓${RESET}"; back=$((back+1))
      elif (( s > prev + 1 )); then seg="${GREEN}${BOLD}${s}↑${RESET}"; fwd=$((fwd+1))
      elif (( s > prev )); then seg="${GREEN}${s}${RESET}"; fwd=$((fwd+1))
      fi
      out+=" → ${seg}"
    else
      out+="${seg}"
    fi
    prev="$s"
  done
  # Append per-poll deltas — total seen so far / new since last poll.
  local prev_walk="${LAST_WALK[$chain_id]:-}"
  if [[ "$walk_pipe" != "$prev_walk" ]]; then
    LAST_WALK[$chain_id]="$walk_pipe"
    FORWARDS[$chain_id]=$(( ${FORWARDS[$chain_id]:-0} + fwd ))
    BACKWARDS[$chain_id]=$(( ${BACKWARDS[$chain_id]:-0} + back ))
    HOST_OF[$chain_id]="$host"
    TOTAL_FWD=$(( TOTAL_FWD + fwd ))
    TOTAL_BACK=$(( TOTAL_BACK + back ))
    # uniq stages this poll — append to STAGES_SEEN.
    STAGES_SEEN[$chain_id]="${STAGES_SEEN[$chain_id]:-}${walk_pipe//|/,},"
  fi
  printf "  %schain %s%s  %shost=%s%s   walk: %s\n" \
    "$DIM" "${chain_id:0:8}" "$RESET" \
    "$DIM" "${host:-?}" "$RESET" \
    "$out"
}

poll_once() {
  # PG query: pull the last $WALK_TAIL alerts from each of the most recent
  # $TRACK_CHAINS chains opened *during this run*. We use string_agg with an
  # ORDER BY inside the agg (Postgres) to preserve event time ordering.
  # Output format: chain_id|host_label|stage1|stage2|…  (one line per chain)
  docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAF'|' -c "
    WITH active AS (
      SELECT chain_id, MAX(occurred_at) AS last_seen
        FROM alerts
       WHERE chain_id IS NOT NULL
         AND occurred_at >= '${WINDOW_START_ISO}'::timestamptz
       GROUP BY chain_id
       ORDER BY last_seen DESC
       LIMIT ${TRACK_CHAINS}
    ),
    walk AS (
      SELECT a.chain_id,
             COALESCE(NULLIF(h.agent_name,''), h.ip_address::text, '?') AS host,
             a.ckc_stage,
             a.occurred_at,
             ROW_NUMBER() OVER (PARTITION BY a.chain_id ORDER BY a.occurred_at DESC) AS rn
        FROM alerts a
        JOIN active   ON active.chain_id = a.chain_id
        LEFT JOIN hosts h ON h.host_id = a.host_id
       WHERE a.occurred_at >= '${WINDOW_START_ISO}'::timestamptz
    )
    SELECT chain_id::text,
           MAX(host),
           string_agg(ckc_stage::text, '|' ORDER BY occurred_at)
      FROM walk
     WHERE rn <= ${WALK_TAIL}
     GROUP BY chain_id
     ORDER BY MAX(occurred_at) DESC;
  " 2>/dev/null || true
}

print_final_summary() {
  echo
  echo "${BOLD}${MAGENTA}═════════════════════════════════════════════════════════════════════${RESET}"
  echo "${BOLD}${MAGENTA}  STAGE-WALK SUMMARY${RESET}"
  echo "${BOLD}${MAGENTA}═════════════════════════════════════════════════════════════════════${RESET}"
  echo "  total forward steps  : ${GREEN}${BOLD}${TOTAL_FWD}${RESET}"
  echo "  total backward steps : ${RED}${BOLD}${TOTAL_BACK}${RESET}"
  if (( TOTAL_BACK > 0 )); then
    echo "  ${GREEN}${BOLD}✓ non-monotonic motion observed at the data layer${RESET}"
    echo "  ${DIM}(the dashboard's APT Attack Timeline only renders the running max,${RESET}"
    echo "  ${DIM} so this backward motion is invisible there — the proof is here.)${RESET}"
  else
    echo "  ${YELLOW}⚠ no backward steps observed — chain matcher may have"
    echo "  ${YELLOW}  split each tactic into its own chain. Check that --dwell is"
    echo "  ${YELLOW}  short enough (≤30s) so consecutive tactics share one chain.${RESET}"
  fi
  echo
  echo "  ${BOLD}per-chain detail:${RESET}"
  for cid in "${!FORWARDS[@]}"; do
    local fwd="${FORWARDS[$cid]:-0}"
    local back="${BACKWARDS[$cid]:-0}"
    local host="${HOST_OF[$cid]:-?}"
    # uniq stages — collapse the comma-set, sort numerically, dedupe.
    local uniq_stages
    uniq_stages=$(echo "${STAGES_SEEN[$cid]:-}" | tr ',' '\n' | grep -v '^$' | sort -u | paste -sd' ')
    printf "    %schain %s%s  host=%s   fwd=%s%d%s  back=%s%d%s  stages={%s}\n" \
      "$DIM" "${cid:0:8}" "$RESET" "$host" \
      "$GREEN" "$fwd" "$RESET" \
      "$RED"   "$back" "$RESET" \
      "$uniq_stages"
  done
  echo
  echo "  ${DIM}sim log: $SIM_LOG${RESET}"
  echo "${BOLD}${MAGENTA}═════════════════════════════════════════════════════════════════════${RESET}"
}

# --- main loop ------------------------------------------------------------
echo "${BOLD}${CYAN}poll every ${POLL_INTERVAL_S}s — Ctrl+C to stop${RESET}"
echo "${DIM}(empty polls until the sim's first auditd events propagate — typically 8–15s)${RESET}"
echo

while kill -0 "$SIM_PID" 2>/dev/null; do
  ts="$(date +%H:%M:%S)"
  rows="$(poll_once || true)"
  if [[ -n "$rows" ]]; then
    echo "${DIM}[${ts}]${RESET}"
    while IFS='|' read -r cid host walk; do
      [[ -z "$cid" ]] && continue
      print_walk_for_chain "$cid" "$host" "$walk"
    done <<< "$rows"
    echo
  fi
  sleep "$POLL_INTERVAL_S"
done

# Wait for the sim to actually exit (it may already have).
wait "$SIM_PID" 2>/dev/null || true

print_final_summary
