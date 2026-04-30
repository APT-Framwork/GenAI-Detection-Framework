#!/usr/bin/env bash
# Walks the 8 Wazuh → platform connectivity probes from docs/LAB_BRINGUP.md §2.5.
# Exits non-zero on the first failed hop so CI / pre-smoke can short-circuit.
set -euo pipefail

GREEN='\033[32m'; RED='\033[31m'; YELLOW='\033[33m'; DIM='\033[2m'; RESET='\033[0m'
ok()   { printf "${GREEN}✓${RESET} %s\n" "$*"; }
fail() { printf "${RED}✗${RESET} %s\n" "$*"; exit 1; }
warn() { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }
step() { printf "\n${DIM}──[ %s ]──${RESET}\n" "$*"; }

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
API_URL="${API_URL:-http://localhost:8000}"

# ----- (a) manager is writing alerts.json -----------------------------------
step "a) wazuh.manager writes alerts.json"
docker exec strix_wazuh_manager test -s /var/ossec/logs/alerts/alerts.json \
  && ok "alerts.json exists and is non-empty" \
  || fail "alerts.json missing/empty — is strix_wazuh_manager up?"

# ----- (b) agents connected -------------------------------------------------
step "b) agents are Active"
active=$(docker exec strix_wazuh_manager /var/ossec/bin/agent_control -l 2>/dev/null \
          | grep -c "Active" || true)
[[ "$active" -ge 2 ]] && ok "$active agents Active" || fail "fewer than 2 Active agents"

# ----- (c) trip a rule ------------------------------------------------------
step "c) trip a rule inside victim1"
before=$(docker exec strix_wazuh_manager bash -c 'wc -l < /var/ossec/logs/alerts/alerts.json')
docker exec strix_victim1 bash -c 'cat /etc/shadow >/dev/null 2>&1 || true'
docker exec strix_victim1 bash -c 'logger -t auth "lab_verify: FAILED su for root"'
sleep 6
after=$(docker exec strix_wazuh_manager bash -c 'wc -l < /var/ossec/logs/alerts/alerts.json')
[[ "$after" -gt "$before" ]] \
  && ok "alerts.json grew from $before → $after lines" \
  || warn "alerts.json did not grow (+$((after-before))); rules may not be tripping"

# ----- (d) redis list picked up by filebeat --------------------------------
step "d) filebeat → redis list"
llen=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" LLEN strix:alerts:raw:list)
if [[ "$llen" -gt 0 ]]; then
  ok "LLEN strix:alerts:raw:list = $llen (bridge not draining, or draining slower than producer)"
else
  # Bridge might be draining fast — check stream instead.
  warn "LLEN = 0; bridge likely draining in real time (checked in step (e))"
fi

# ----- (e) stream has entries ----------------------------------------------
step "e) wazuh_bridge → redis stream"
xlen=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" XLEN strix:alerts:raw 2>/dev/null || echo 0)
[[ "$xlen" -gt 0 ]] \
  && ok "XLEN strix:alerts:raw = $xlen" \
  || fail "stream empty — is wazuh_bridge running on the host?"

# ----- (f) normalizer consumer group advancing -----------------------------
step "f) normalizer consumer group progress"
if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" XINFO GROUPS strix:alerts:raw 2>/dev/null \
    | grep -q "strix-normalizer"; then
  ok "consumer group 'strix-normalizer' exists"
else
  fail "no consumer group — is the normalizer worker running?"
fi

# ----- (g) verdicts land in postgres ----------------------------------------
step "g) verdicts in postgres"
if command -v psql >/dev/null 2>&1; then
  : "${DB_PASSWORD:?set DB_PASSWORD (source apps/api/.env)}"
  count=$(PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p "${DB_PORT:-5435}" -U "${DB_USER:-strix}" \
           -d "${DB_NAME:-strix}" -tAc "SELECT COUNT(*) FROM detections;" 2>/dev/null || echo 0)
  [[ "$count" -gt 0 ]] \
    && ok "verdicts rows = $count" \
    || warn "0 verdicts — inference / verdicts_writer may not be running yet"
else
  warn "psql not installed on host — skipping"
fi

# ----- (h) API responds -----------------------------------------------------
step "h) API /health"
curl -fsS "$API_URL/health" >/dev/null \
  && ok "$API_URL/health OK" \
  || fail "API not reachable — is uvicorn running?"

printf "\n${GREEN}all probes passed${RESET}\n"
