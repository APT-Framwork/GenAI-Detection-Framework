#!/usr/bin/env bash
# =============================================================================
# STRIX — one-shot lab bring-up.
#
# Starts the full stack end-to-end:
#   1. simulation:  wazuh.manager + caldera + victim1 + victim2   (Docker)
#   2. deps:        postgres (5435) + redis (6380) + filebeat     (Docker)
#   3. migrations + admin seed
#   4. host processes (honcho): api + web + 5 workers
#   5. lab-verify connectivity probes
#
# Usage:  bash infra/scripts/lab_up.sh
#         bash infra/scripts/lab_up.sh --no-verify   # skip final probes
#         bash infra/scripts/lab_up.sh stop          # tear everything down
# =============================================================================
set -euo pipefail

GREEN='\033[32m'; RED='\033[31m'; YELLOW='\033[33m'; DIM='\033[2m'; RESET='\033[0m'
ok()   { printf "${GREEN}✓${RESET} %s\n" "$*"; }
fail() { printf "${RED}✗${RESET} %s\n" "$*"; exit 1; }
warn() { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }
step() { printf "\n${DIM}──[ %s ]──${RESET}\n" "$*"; }

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

VENV="$REPO/apps/api/.venv"
ENV_FILE="$REPO/apps/api/.env"
HONCHO_LOG="/tmp/strix_honcho.log"
HONCHO_PID_FILE="/tmp/strix_honcho.pid"

# --------------------------------------------------------------------- stop
if [[ "${1:-}" == "stop" ]]; then
  step "stopping host processes"
  if [[ -f "$HONCHO_PID_FILE" ]]; then
    pid=$(cat "$HONCHO_PID_FILE")
    kill -TERM "$pid" 2>/dev/null && ok "sent SIGTERM to honcho (pid=$pid)" || warn "honcho (pid=$pid) not running"
    rm -f "$HONCHO_PID_FILE"
  else
    pkill -f "honcho -f Procfile.host" 2>/dev/null && ok "killed honcho" || warn "no honcho process found"
  fi
  step "stopping deps"
  docker compose --env-file "$ENV_FILE" -f infra/compose.platform-deps.yml down
  step "stopping simulation"
  docker compose -f infra/compose.simulation.yml down
  ok "stack stopped (volumes kept)"
  exit 0
fi

SKIP_VERIFY=0
[[ "${1:-}" == "--no-verify" ]] && SKIP_VERIFY=1

# --------------------------------------------------------------------- prereqs
step "checking prerequisites"
command -v docker >/dev/null || fail "docker not installed"
docker compose version >/dev/null 2>&1 || fail "docker compose v2 not installed"
command -v honcho >/dev/null || fail "honcho not installed — run: pipx install honcho"
command -v pnpm >/dev/null   || fail "pnpm not installed"
[[ -f "$ENV_FILE" ]]         || fail "$ENV_FILE missing"
[[ -d "$VENV" ]]              || fail "$VENV missing — run: python3.12 -m venv $VENV && $VENV/bin/pip install -e $REPO/apps/api"
"$VENV/bin/python" -c "import strix_api" 2>/dev/null || fail "strix_api not installed in venv — run: $VENV/bin/pip install -e $REPO/apps/api"
docker image inspect caldera:latest >/dev/null 2>&1 || fail "caldera:latest image missing — build from https://github.com/mitre/caldera"
ok "all prereqs present"

# --------------------------------------------------------------------- env
# Strip comments so `export $(xargs)` doesn't choke on "KEY=val # comment".
STRIX_ENV_EXPORT="/tmp/strix_env.txt"
grep -v '^#' "$ENV_FILE" | grep -v '^$' | sed 's/ #.*//' > "$STRIX_ENV_EXPORT"
set -a; . "$STRIX_ENV_EXPORT"; set +a

# --------------------------------------------------------------------- 1. sim
step "1/5  simulation stack (wazuh + caldera + victims)"
docker compose -f infra/compose.simulation.yml up -d --build
ok "simulation containers launched"

step "waiting for wazuh.manager + caldera healthy"
until docker inspect --format '{{.State.Health.Status}}' strix_wazuh_manager 2>/dev/null | grep -q healthy \
  && docker inspect --format '{{.State.Health.Status}}' strix_caldera       2>/dev/null | grep -q healthy; do
  sleep 3
done
ok "wazuh.manager + caldera healthy"

# --- pin Caldera credentials (so they don't drift across container rebuilds)
# Caldera v5 generates random red/blue passwords on first boot. We overwrite
# them with deterministic plaintext in conf/local.yml while caldera is STOPPED
# (Caldera re-writes local.yml from in-memory state on shutdown — patching a
# running container would be clobbered by that shutdown-write-back). On the
# next boot Caldera hashes the plaintext and form-login accepts our values.
# Idempotent: re-running this script reapplies the same plaintext.
CALDERA_RED_PASSWORD="${CALDERA_RED_PASSWORD:-strix-red}"
CALDERA_BLUE_PASSWORD="${CALDERA_BLUE_PASSWORD:-strix-blue}"
step "pinning Caldera credentials (red:${CALDERA_RED_PASSWORD}  blue:${CALDERA_BLUE_PASSWORD})"
# Make sure local.yml exists first (caldera generates it on first boot).
for _ in $(seq 1 30); do
  docker exec strix_caldera test -s /usr/src/app/conf/local.yml 2>/dev/null && break
  sleep 1
done
docker stop strix_caldera >/dev/null
CAL_TMP=$(mktemp)
docker cp strix_caldera:/usr/src/app/conf/local.yml "$CAL_TMP"
RED_PW="$CALDERA_RED_PASSWORD" BLUE_PW="$CALDERA_BLUE_PASSWORD" CAL_TMP="$CAL_TMP" \
  python3 - <<'PY'
import os, yaml
p = os.environ['CAL_TMP']
with open(p) as f:
    cfg = yaml.safe_load(f) or {}
cfg.setdefault('users', {}).setdefault('red',  {})['red']  = os.environ['RED_PW']
cfg.setdefault('users', {}).setdefault('blue', {})['blue'] = os.environ['BLUE_PW']
with open(p, 'w') as f:
    yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)
PY
docker cp "$CAL_TMP" strix_caldera:/usr/src/app/conf/local.yml
rm -f "$CAL_TMP"
docker start strix_caldera >/dev/null
until docker inspect --format '{{.State.Health.Status}}' strix_caldera 2>/dev/null | grep -q healthy; do
  sleep 2
done
ok "caldera credentials pinned"

# --------------------------------------------------------------------- 2. deps
step "2/5  platform deps (postgres + redis + filebeat)"
docker compose --env-file "$ENV_FILE" -f infra/compose.platform-deps.yml up -d
until docker inspect --format '{{.State.Health.Status}}' strix_postgres 2>/dev/null | grep -q healthy \
   && docker inspect --format '{{.State.Health.Status}}' strix_redis    2>/dev/null | grep -q healthy; do
  sleep 2
done
ok "postgres + redis healthy"

# --------------------------------------------------------------------- 3. db
step "3/5  migrations + admin seed"
( cd "$REPO/apps/api" && "$VENV/bin/alembic" upgrade head )
ok "alembic at head"
"$VENV/bin/python" "$REPO/infra/scripts/seed_admin.py" \
  --email "${ADMIN_EMAIL:-admin@strix.local}" \
  --password "${ADMIN_PASSWORD:-changeme}" \
  --role admin
ok "admin user seeded"

# --------------------------------------------------------------------- 4. host
step "4/5  host processes (honcho)"
# Kill any previous honcho owned by this script (idempotent re-runs).
if [[ -f "$HONCHO_PID_FILE" ]]; then
  old=$(cat "$HONCHO_PID_FILE")
  kill -TERM "$old" 2>/dev/null && warn "killed previous honcho (pid=$old)"
  sleep 2
fi
pkill -f "honcho -f Procfile.host" 2>/dev/null || true
sleep 1

nohup honcho -f "$REPO/Procfile.host" start > "$HONCHO_LOG" 2>&1 &
echo $! > "$HONCHO_PID_FILE"
ok "honcho launched (pid=$(cat "$HONCHO_PID_FILE")) — log: $HONCHO_LOG"

step "waiting for API /health"
for i in $(seq 1 60); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    ok "API /health OK after ${i}s"
    break
  fi
  sleep 1
  [[ "$i" == 60 ]] && fail "API did not come up in 60s — check $HONCHO_LOG"
done

step "waiting for web (Next.js on :5600)"
for i in $(seq 1 60); do
  if curl -fsS http://localhost:5600 >/dev/null 2>&1; then
    ok "web UI up after ${i}s"
    break
  fi
  sleep 1
  [[ "$i" == 60 ]] && warn "web did not respond in 60s — check $HONCHO_LOG"
done

# --------------------------------------------------------------------- 5. verify
if [[ "$SKIP_VERIFY" == 0 ]]; then
  step "5/5  connectivity probes"
  REDIS_PORT="${REDIS_PORT:-6380}" DB_PORT="${DB_PORT:-5435}" \
    bash "$REPO/infra/scripts/lab_verify.sh" || warn "some probes warned — see above"
fi

# --------------------------------------------------------------------- done
# Caldera v5 generates random passwords + API tokens on first boot and prints
# them once in the container log (rich-logger wraps them across multiple lines).
# Reassemble them so the user has something to paste into the login form.
read_caldera_creds() {
  # Heredoc + pipe collide on stdin, so feed logs via a tempfile passed as argv.
  local logf; logf=$(mktemp)
  docker logs strix_caldera >"$logf" 2>&1 || { rm -f "$logf"; return 1; }
  python3 - "$logf" <<'PY'
import re, sys
with open(sys.argv[1]) as f:
    text = re.sub(r'\x1b\[[0-9;]*m', '', f.read())
role = None; field = None; buf = ""
data = {"red": {}, "blue": {}}
def flush():
    global buf, role, field
    if role and field and buf:
        data[role][field] = buf
    buf = ""
for s in (l.strip() for l in text.splitlines()):
    if s.startswith("Red:"):       flush(); role, field = "red",  None; continue
    if s.startswith("Blue:"):      flush(); role, field = "blue", None; continue
    if s.startswith("USERNAME:"):  flush(); field = None; continue
    if s.startswith("PASSWORD:"):  flush(); field = "password";  buf = s[9:].strip();  continue
    if s.startswith("API_TOKEN:"): flush(); field = "api_token"; buf = s[10:].strip(); continue
    if field and re.fullmatch(r"[A-Za-z0-9_\-]+", s):
        buf += s; continue
    if field:
        flush(); field = None
flush()
for role in ("red", "blue"):
    print(f"{role}_pw={data[role].get('password','')}")
    print(f"{role}_tok={data[role].get('api_token','')}")
PY
  rm -f "$logf"
}
CAL_CREDS=$(read_caldera_creds 2>/dev/null || true)
CAL_RED_TOK=$(printf '%s\n' "$CAL_CREDS" | sed -n 's/^red_tok=//p')
CAL_BLUE_TOK=$(printf '%s\n' "$CAL_CREDS"| sed -n 's/^blue_tok=//p')

cat <<EOF

${GREEN}✓ STRIX lab is up${RESET}

  API          http://localhost:8000
  API docs     http://localhost:8000/docs
  Web UI       http://localhost:5600
  Caldera      http://localhost:8888
     red    password : ${CALDERA_RED_PASSWORD}
            api_token: ${CAL_RED_TOK:-<run again — token only logged on first boot>}
     blue   password : ${CALDERA_BLUE_PASSWORD}
            api_token: ${CAL_BLUE_TOK:-<run again — token only logged on first boot>}
  Postgres     127.0.0.1:5435  user=strix  db=strix
  Redis        127.0.0.1:6380

  Admin login  ${ADMIN_EMAIL:-admin@strix.local} / ${ADMIN_PASSWORD:-changeme}
  Honcho log   tail -f $HONCHO_LOG
  Tear down    bash infra/scripts/lab_up.sh stop
EOF
