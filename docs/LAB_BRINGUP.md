# STRIX Lab Bring-up — All-Docker Walkthrough

A single, copy-pasteable runbook for the full PoC on **one host**: Wazuh
manager + Caldera attacker + 2 victims, all as containers on a shared Docker
network. The STRIX platform (API + web + workers) runs on the same host via
its own compose and reads Wazuh alerts through a shared named volume.

```
          host (your laptop)
 ┌─────────────────────────────────────────────────────────────────┐
 │   host:  uvicorn · workers · pnpm dev (apps/web)                │
 │   docker (infra/compose.platform-deps.yml): postgres · redis · filebeat │
 │                         ▲                                       │
 │            reads alerts │ volume: single-node_wazuh_logs        │
 │                         │                                       │
 │   ── simulation net (strix_lab_net, infra/compose.simulation.yml) ──
 │                         │                                       │
 │    wazuh.manager ◀── 1514/1515 ─── victim1 ─ sandcat ──▶ caldera│
 │        :55000                      victim2 ─ sandcat ──▶ :8888  │
 └─────────────────────────────────────────────────────────────────┘
```

No VMs, no SSH, no UFW. Only prerequisite is Docker + Compose v2.

---

## 0. Prerequisites

```bash
# Ubuntu / Debian host
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker $USER && newgrp docker

# Sanity
docker version
docker compose version
```

Clone the repo:

```bash
git clone <this-repo> ~/GenAI-Detection-Framework
cd ~/GenAI-Detection-Framework
```

Required local image: **`caldera:latest`**. If you don't already have it:

```bash
git clone https://github.com/mitre/caldera.git --recursive ~/caldera
cd ~/caldera && docker build -t caldera:latest .
cd -
```

---

## 1. Simulation stack — Wazuh + Caldera + victims

```bash
docker compose -f infra/compose.simulation.yml up -d --build
```

This spins up four containers on the `strix_lab_net` bridge network:

| Container | Image | Role | Exposed |
|---|---|---|---|
| `strix_wazuh_manager` | `wazuh/wazuh-manager:4.9.2` | SIEM core, writes `alerts.json` | 1514, 1515, 55000 |
| `strix_caldera` | `caldera:latest` | Red-team C2 server | 8888 |
| `strix_victim1` | `strix/victim:lab` (built locally) | Ubuntu + wazuh-agent + auditd + rsyslog + sandcat | — |
| `strix_victim2` | `strix/victim:lab` | same | — |

First build of the victim image pulls Ubuntu + wazuh-agent — ~2 minutes on a
warm cache.

**Training-schema alignment:** the victim image injects the
[config/wazuh/ossec-agent-localfiles.xml.draft](../config/wazuh/ossec-agent-localfiles.xml.draft)
fragment into `ossec.conf` on first boot — enables auditd, syscheck, SCA, and
the PAM/sudo/sshd/dpkg/apache log sources the ML models were trained on
(see [WAZUH_MAPPING.md](WAZUH_MAPPING.md)). The manager runs with stock
defaults (`log_alert_level: 3`, `jsonout_output: yes`) which already match the
training dump.

> ⚠️  **auditd caveat.** The host kernel's audit netlink is single-owner. If
> the Docker host itself runs `auditd`, the container's `auditctl` calls fail
> and `data.audit.*` features will be sparse (entrypoint logs this). Either
> stop the host's auditd (`sudo systemctl stop auditd`) or bind-mount host
> audit logs (`/var/log/audit:/var/log/audit:ro`) into the victim containers
> if you need full auditd coverage.

```bash
# ✅ Verify
docker compose -f infra/compose.simulation.yml ps
docker exec strix_wazuh_manager /var/ossec/bin/agent_control -l
# Expected after ~30s:
#   ID: 001, Name: victim1, Status: Active
#   ID: 002, Name: victim2, Status: Active
```

Caldera UI: **http://localhost:8888** → login `red` / `admin`. The Agents tab
should list `victim1` and `victim2` (paw IDs differ each run).

---

## 2. Platform — run natively on the host

> **TL;DR** — `pip install honcho` (once), then:
> ```
> make lab-up        # sim + deps + migrate + seed
> make host-up       # one command for api + all workers + web (honcho)
> make lab-verify    # in another terminal — 8 connectivity probes
> ```
> The sections below explain what each step does.


Only **Postgres + Redis + Filebeat** stay in Docker (via
`compose.platform-deps.yml`); the API, workers, and web UI run directly on
the host. Filebeat bridges the two worlds: it tails the Wazuh alerts volume
(shared with the simulation stack) and pushes lines to the Redis list the
host-run `wazuh_bridge` worker drains.

### 2.1 Env

```bash
cp apps/api/.env.example apps/api/.env

sed -i "s|^DB_HOST=.*|DB_HOST=localhost|"    apps/api/.env
sed -i "s|^REDIS_HOST=.*|REDIS_HOST=localhost|" apps/api/.env
sed -i "s|^DB_PASSWORD=.*|DB_PASSWORD=$(openssl rand -base64 24)|" apps/api/.env
sed -i "s|^# AUTH_JWT_SECRET=.*|AUTH_JWT_SECRET=$(openssl rand -base64 48)|" apps/api/.env
sed -i "s|^AUTH_DEV_SKIP_AUTH=.*|AUTH_DEV_SKIP_AUTH=false|" apps/api/.env
sed -i "s|^INFERENCE_NUM_SHARDS=.*|INFERENCE_NUM_SHARDS=1|" apps/api/.env
sed -i "s|^MODELS_PATH=.*|MODELS_PATH=$(pwd)/apps/models|" apps/api/.env
```

### 2.2 Postgres + Redis + Filebeat

```bash
# Compose inherits DB_PASSWORD from apps/api/.env — pass via --env-file
docker compose --env-file apps/api/.env \
  -f infra/compose.platform-deps.yml up -d
```

That publishes Postgres on `127.0.0.1:5432` and Redis on `127.0.0.1:6379`.

### 2.3 API + workers (host)

```bash
cd apps/api
pip install -e ".[dev]"          # one-time
export $(grep -v '^#' .env | xargs)

alembic upgrade head             # migrations

# Launch each in its own terminal (or tmux / overmind / honcho):
uvicorn strix_api.app:app --host 0.0.0.0 --port 8000 --reload
python -m strix_api.workers.wazuh_bridge
python -m strix_api.workers.normalizer
python -m strix_api.workers.inference       # set INFERENCE_SHARD_ID=0
python -m strix_api.workers.verdicts_writer
arq strix_api.workers.arq_tasks.WorkerSettings
```

Seed the bootstrap admin (once):

```bash
cd apps/api && python -c "
import asyncio
from strix_api.repositories.database import init_engine, session_scope
from strix_api.repositories.user_repo import UserRepo
from strix_api.services.auth import hash_password
from strix_api.settings import get_settings
async def run():
    init_engine(get_settings())
    async with session_scope() as s:
        await UserRepo(s).create(email='admin@strix.io',
            password_hash=hash_password('changeme123!'), role='admin')
asyncio.run(run())"
```

### 2.4 Web

```bash
cd apps/web
pnpm install                     # one-time
STRIX_API_URL=http://localhost:8000 pnpm dev
```

Open **http://localhost:3000** → login `admin@strix.io` / `changeme123!`.

---

## 2.5 Prove Wazuh → platform connectivity (step-by-step)

Run these in order after bringing everything up. Each step isolates one hop
so you know where a break is if the chain fails.

```bash
# ---- (a) Is the manager writing alerts.json? -----------------------------
docker exec strix_wazuh_manager \
  ls -la /var/ossec/logs/alerts/alerts.json
docker exec strix_wazuh_manager \
  tail -1 /var/ossec/logs/alerts/alerts.json | head -c 200
# Expected: file exists, last line is a JSON doc with "rule", "agent", etc.
```

```bash
# ---- (b) Are agents actually connected? ----------------------------------
docker exec strix_wazuh_manager /var/ossec/bin/agent_control -l
# Expected: victim1 and victim2 both "Active"
```

```bash
# ---- (c) Trip a rule from inside a victim --------------------------------
docker exec strix_victim1 bash -c 'cat /etc/shadow >/dev/null 2>&1 || true'
docker exec strix_victim1 bash -c 'logger -t auth "fake: FAILED su for root"'
# Wait ~5s for the manager to process it
sleep 5
docker exec strix_wazuh_manager \
  tail -5 /var/ossec/logs/alerts/alerts.json | grep -c '"agent":{"id":"00'
# Expected: > 0 — an alert mentioning a non-zero agent id just arrived.
```

```bash
# ---- (d) Did Filebeat pick it up and push to Redis? ---------------------
# While the wazuh_bridge worker is NOT running, items pile up on the list.
# (If it IS running, LLEN will be 0 because the bridge drains it immediately —
#  that's also a green result; skip to step (e) in that case.)
redis-cli -h 127.0.0.1 -p 6379 LLEN strix:alerts:raw:list
# Expected: N > 0 if bridge is stopped; 0 if it's running + draining fine.

# Peek at the most recent entry without consuming it:
redis-cli -h 127.0.0.1 -p 6379 LRANGE strix:alerts:raw:list -1 -1 | head -c 200
```

```bash
# ---- (e) Did the bridge forward into the Redis stream? ------------------
redis-cli -h 127.0.0.1 -p 6379 XLEN strix:alerts:raw
redis-cli -h 127.0.0.1 -p 6379 XREVRANGE strix:alerts:raw + - COUNT 1
# Expected: XLEN grows; last entry contains the alert JSON.
```

```bash
# ---- (f) Did the normalizer + inference consume it? ---------------------
# The normalizer uses a consumer group — pending-list shows work in flight.
redis-cli -h 127.0.0.1 -p 6379 XINFO GROUPS strix:alerts:raw
# Expected: group "strix-normalizer" with last-delivered-id moving forward.
```

```bash
# ---- (g) Did a verdict land in Postgres? --------------------------------
PGPASSWORD=$(grep ^DB_PASSWORD apps/api/.env | cut -d= -f2) \
  psql -h 127.0.0.1 -U strix -d strix \
       -c "SELECT COUNT(*), MAX(created_at) FROM verdicts;"
# Expected: count grows over time; MAX(created_at) is within the last minute.
```

```bash
# ---- (h) End-to-end via the API -----------------------------------------
curl -fsS http://localhost:8000/health
curl -fsS "http://localhost:8000/api/v1/alerts?limit=1" \
  -H "Cookie: $(cat ~/.strix_cookie 2>/dev/null)" | jq '.items[0] | {id, rule_id, created_at}'
# Or just watch the Vigilance Feed SSE stream in the browser.
```

If (a)–(c) pass but (d) shows LLEN=0 *and* the bridge is stopped → Filebeat
isn't connected. Check `docker logs strix_filebeat | tail -50`. Most common
cause: the `single-node_wazuh_logs` volume wasn't created because the
simulation compose wasn't brought up first.

If (d) passes but (e) shows XLEN=0 → the `wazuh_bridge` worker isn't running
or can't reach Redis on `localhost:6379`. Check the worker's stdout.

If (e) passes but (g) shows no rows → normalizer or inference is down, or a
model artifact is missing (check `MODELS_PATH` and that the `.pth` files exist).

---

## 3. End-to-end smoke

### A. Manual probe (60s)

Trip a Wazuh rule from inside a victim container:

```bash
docker exec strix_victim1 bash -c 'sudo cat /etc/shadow >/dev/null'
docker exec strix_victim1 bash -c 'echo "fake auth failure" >> /var/log/auth.log'
```

Within 5–15s:
- **STRIX dashboard** (http://localhost:3000) → Vigilance Feed → live SSE event
- **Attack Vector** counter ticks up

### B. Caldera-driven attack chain

Fast path (full recipes, REST API, technique-targeted ops):
→ **[CALDERA_PLAYBOOK.md](CALDERA_PLAYBOOK.md)**.

30-second version:
1. http://localhost:8888 → `red` / `admin`
2. Campaigns → Operations → `+` → Adversary: **Thief**, Group: `red`,
   Planner: `batch`, Obfuscator: `plain-text`, Autonomous: ✅
3. ▶ Start

Within 30–60s:
- **Attack Analysis** page → new chain appears
- Kill-chain advances through DISCOVERY → COLLECTION stages
- **Topology** → at least one host flips to *warning* / *compromised*

---

## 4. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `external volume "single-node_wazuh_logs" not found` starting `compose.platform-deps.yml` | Simulation stack not up yet | `docker compose -f infra/compose.simulation.yml up -d` first |
| `victim` health flaps, agent "Never connected" in `agent_control -l` | Caldera not healthy yet on first boot — victim's entrypoint blocks on it | `docker logs strix_victim1 -f` — wait for `sandcat launched`, then check agent |
| Caldera UI shows 0 agents but victims are running | sandcat fetched before Caldera finished warming up | `docker compose -f infra/compose.simulation.yml restart victim1 victim2` |
| STRIX `/auth/me` returns 401 after login | `AUTH_DEV_SKIP_AUTH=true` substitutes a fake user | `sed -i 's/^AUTH_DEV_SKIP_AUTH=.*/AUTH_DEV_SKIP_AUTH=false/' apps/api/.env` and restart the host-run `uvicorn` |
| API 500s: `connection to server on "postgres"` | `.env` still points at docker hostname | `sed -i 's/^DB_HOST=.*/DB_HOST=localhost/' apps/api/.env` + restart uvicorn |
| Workers 500: `Connection refused to redis:6379` | Same pattern | `sed -i 's/^REDIS_HOST=.*/REDIS_HOST=localhost/' apps/api/.env` + restart workers |
| Vigilance Feed never receives events | Filebeat can't read alerts.json | `docker logs strix_filebeat \| tail` — confirm `single-node_wazuh_logs` volume is mounted |
| Caldera build fails with Go / mingw errors | Upstream quirk | Build from a tagged release: `git -C ~/caldera checkout 5.1.0 && docker build -t caldera:latest ~/caldera` |
| Victim image build fails on `apt install wazuh-agent` | Wazuh APT repo transient outage | Retry the build; optionally pin a mirror in the Dockerfile |
| `docker compose up` on victim fails with `cap_add: AUDIT_READ` on older Docker | Docker < 20.10 | Upgrade Docker, or drop the audit caps from compose.simulation.yml |

---

## 5. Tear-down / reset

```bash
# Reset STRIX platform but keep simulation + agent registrations
docker compose -f infra/compose.platform-deps.yml down -v

# Reset the simulation lab (wipes Wazuh agents + Caldera state)
docker compose -f infra/compose.simulation.yml down -v

# Full nuke
docker compose -f infra/compose.platform-deps.yml down -v
docker compose -f infra/compose.simulation.yml down -v
docker volume rm single-node_wazuh_logs 2>/dev/null || true
```

---

## What to read next

- **Caldera attack recipes** — [docs/CALDERA_PLAYBOOK.md](CALDERA_PLAYBOOK.md)
- **Architecture** — [docs/IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
- **Wazuh field → STRIX feature mapping** — [docs/WAZUH_MAPPING.md](WAZUH_MAPPING.md)
- **Model versions, registry, drift** — [docs/MODELS_REFERENCE.md](MODELS_REFERENCE.md)
- **Frontend dev** — [docs/WEB_RUN.md](WEB_RUN.md)
