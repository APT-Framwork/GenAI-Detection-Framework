# STRIX Lab Bring-up — 5 VM Walkthrough

A single, copy-pasteable runbook for the 5-VM PoC: Wazuh manager + STRIX
app, Caldera attacker, three victim hosts. Top-to-bottom, ~25 minutes
end-to-end on a warm network.

```
            VM 1 — Manager + App                       VM 2 — Attacker
   ┌─────────────────────────────────┐         ┌──────────────────────┐
   │  wazuh.manager   wazuh.indexer  │         │  caldera (red TS)    │
   │  wazuh.dashboard                │◀────────│  http://VM2:8888     │
   │                                 │         └──────────┬───────────┘
   │  ┌──────── STRIX app ────────┐  │                    │
   │  │ postgres  redis  filebeat │  │             sandcat │ ops
   │  │ api  workers×4  arq  web  │  │                    ▼
   │  └───────────────────────────┘  │         ┌──────────┴───────────┐
   │  http://VM1:3000   :8000  :443  │         │ VMs 3/4/5 — Victims  │
   └────────────────▲────────────────┘         │  wazuh-agent +       │
                    │                          │  sandcat (systemd)   │
                    └──────── alerts (1514) ───┤                      │
                                               └──────────────────────┘
```

---

## 0. Prerequisites (every VM)

```bash
# All 5 VMs — Ubuntu 22.04+, run once each
sudo apt-get update && sudo apt-get install -y curl ca-certificates gnupg
sudo timedatectl set-ntp true             # ⚠ Wazuh enrollment fails on time skew

# VMs 1, 2 only — install Docker
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker $USER && newgrp docker
```

**Network requirements** (open these on the indicated VM's firewall):

| From → To | Port | Why |
|---|---|---|
| 3/4/5 → 1 | 1514, 1515 | Wazuh agent → manager (alerts + enrollment) |
| browser → 1 | 443 | Wazuh dashboard |
| browser → 1 | 3000, 8000 | STRIX web + API |
| 3/4/5 → 2 | 8888 | sandcat → Caldera (C2) |
| browser → 2 | 8888 | Caldera UI |

UFW one-liners:
```bash
# VM 1
sudo ufw allow 1514,1515,443,3000,8000/tcp
# VM 2
sudo ufw allow 8888/tcp
# VMs 3/4/5 — outbound only, no rules needed
```

Record the IPs once — every command below references them:
```bash
export VM1_IP=10.0.0.10   # manager + app
export VM2_IP=10.0.0.11   # caldera
```

---

## 1. VM 1 — Wazuh stack (do this FIRST)

```bash
git clone https://github.com/wazuh/wazuh-docker.git -b v4.9.2 ~/wazuh-docker
cd ~/wazuh-docker/single-node
docker compose -f generate-indexer-certs.yml run --rm generator
docker compose up -d
```

Wait ~60s for the indexer cluster to settle, then:

```bash
# ✅ Verify
curl -fsSk https://localhost:443 -o /dev/null -w "dashboard: %{http_code}\n"
docker exec wazuh.manager /var/ossec/bin/cluster_control -l
# Expected: dashboard: 302 (redirect to login), single node listed
```

Open **https://VM1_IP:443** → login `admin` / `SecretPassword`. Confirm the agents tab is empty (good — we haven't deployed any yet).

---

## 2. VM 1 — STRIX app stack

```bash
cd ~/GenAI-Detection-Framework
cp apps/api/.env.example apps/api/.env

# Set the two required secrets
sed -i "s|^DB_PASSWORD=.*|DB_PASSWORD=$(openssl rand -base64 24)|" apps/api/.env
sed -i "s|^# AUTH_JWT_SECRET=.*|AUTH_JWT_SECRET=$(openssl rand -base64 48)|" apps/api/.env
sed -i "s|^AUTH_DEV_SKIP_AUTH=.*|AUTH_DEV_SKIP_AUTH=false|" apps/api/.env
sed -i "s|^INFERENCE_NUM_SHARDS=.*|INFERENCE_NUM_SHARDS=1|" apps/api/.env

# Bring up the full stack (api + 4 workers + web + filebeat + db + redis)
docker compose -f infra/compose.lab.yml up -d --build
```

First build pulls torch+transformers and SecBERT — **5 to 10 minutes** depending on your network. Subsequent builds are seconds.

Seed the bootstrap admin:

```bash
docker exec strix_api python -c "
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

```bash
# ✅ Verify
curl -fsS http://localhost:8000/health           # {"status":"ok",...}
curl -fsS http://localhost:3000 -o /dev/null -w "web: %{http_code}\n"   # 200
docker compose -f infra/compose.lab.yml ps      # all services healthy/up
```

Open **http://VM1_IP:3000** → login `admin@strix.io` / `changeme123!`. The dashboard loads with all-zero counters. Good — no alerts yet.

---

## 3. VM 2 — Caldera

```bash
cd ~/Desktop/caldera
docker compose up -d   # or whatever the image expects
# (you said it's pre-pulled — adjust if your run command differs)
```

```bash
# ✅ Verify
curl -fsS http://localhost:8888 -o /dev/null -w "caldera: %{http_code}\n"   # 200/302
```

Open **http://VM2_IP:8888** → login `red` / `admin`. Confirm "Agents" tab is empty.

---

## 4. VMs 3, 4, 5 — Victim agents (Wazuh + sandcat)

From your laptop or any host with SSH access to the victims:

```bash
for vm in vm3 vm4 vm5; do
  scp infra/scripts/install_victim.sh "$vm:/tmp/"
  ssh "$vm" "sudo MANAGER_IP=$VM1_IP CALDERA_IP=$VM2_IP bash /tmp/install_victim.sh"
done
```

Each VM takes ~30s. The script is idempotent — safe to re-run if anything hiccups.

```bash
# ✅ Verify from VM 1
ssh vm1 'docker exec wazuh.manager /var/ossec/bin/agent_control -l'
# Expected:
#   ID: 001, Name: vm3, IP: ..., Status: Active
#   ID: 002, Name: vm4, ...
#   ID: 003, Name: vm5, ...

# ✅ Verify from VM 2
ssh vm2 'curl -s http://localhost:8888/api/v2/agents -H "KEY: ADMIN123" | jq ".[].host"'
# Expected: "vm3", "vm4", "vm5"
```

If an agent is "Disconnected" or missing: jump to **Troubleshooting** below.

---

## 5. End-to-end smoke

The whole point of the lab — fire a real attack from VM 2 against the victims, watch alerts flow through Wazuh → STRIX.

### A. Manual probe (60s)

On any victim, generate an alert that should trip Wazuh's default rules:

```bash
ssh vm3 'sudo cat /etc/shadow >/dev/null'   # rule 5402 fires (sudo to root)
ssh vm3 'echo "fake auth failure" | sudo tee -a /var/log/auth.log'   # rule 5503
```

Within 5–15s:
- **Wazuh dashboard** (https://VM1:443) → Discover → events appear
- **STRIX dashboard** (http://VM1:3000) → Vigilance Feed → live SSE event
- **STRIX dashboard** → Attack Vector counter ticks up

### B. Caldera-driven attack chain (proper test)

In the Caldera UI (http://VM2:8888):
1. **Adversaries** → "Hunter" or "Discovery" (built-in)
2. **Operations** → New → name "lab-test", adversary "Hunter", group "red"
3. Click **▶ Start**

Within 30–60s, in the STRIX dashboard:
- **Attack Analysis** → a new chain appears
- Click into it → kill-chain progression should advance through stages
- **Topology** page → at least one host status flips to *warning* or *compromised*

---

## 6. Troubleshooting (in priority order)

| Symptom | Likely cause | Fix |
|---|---|---|
| `external volume "single-node_wazuh_logs" not found` when starting `compose.lab.yml` | Wazuh stack wasn't started, or used different compose project name | `docker volume ls \| grep wazuh` then update `name:` in [compose.lab.yml](../infra/compose.lab.yml) |
| Wazuh agent stuck "Pending" / never reaches "Active" | Time skew, or 1514/1515 blocked | `sudo timedatectl set-ntp true` on victim; check UFW on VM 1 allows 1514/1515 |
| Sandcat install fails: `connection refused` | Caldera not up yet on VM 2 | Bring Caldera up first, re-run `install_victim.sh` (idempotent) |
| STRIX `/auth/me` returns 401 after successful login | `AUTH_DEV_SKIP_AUTH=true` substitutes a fake user not in the DB | `sed -i 's|^AUTH_DEV_SKIP_AUTH=.*|AUTH_DEV_SKIP_AUTH=false|' apps/api/.env && docker compose -f infra/compose.lab.yml restart api` |
| Web dashboard loads but every API call 500s | API container can't reach Postgres | `docker logs strix_api \| tail -30` — usually `DB_PASSWORD` mismatch or migrate didn't run |
| Inference worker crashloops on `OSError: PermissionError at /home/strix` | HuggingFace cache permission | Already fixed in the Dockerfile (`HF_HOME=/app/.cache/huggingface`); rebuild with `--no-cache` if you have an old image |
| Vigilance Feed never receives SSE events | Filebeat can't read Wazuh's log file | `docker logs strix_filebeat \| tail` — usually means the wazuh_alerts volume isn't mounted; verify section 1 succeeded |
| Caldera dashboard sees 0 agents but `systemctl status sandcat` is green on victims | Wrong CALDERA_IP at install time | `ssh vm3 'sudo systemctl edit sandcat'` → fix `-server` URL → `sudo systemctl restart sandcat` |
| Notifications page is empty even after attacks | DQN model picks LOW_ALERT for the synthetic patterns; not a bug | Run a longer Caldera operation (Hunter → Discovery → Collection) so chains progress to CKC ≥ EXPLOITATION; the query surfaces those even at LOW_ALERT |

---

## 7. Tear-down / reset

```bash
# Wipe STRIX state but keep Wazuh + agents
docker compose -f infra/compose.lab.yml down -v

# Wipe everything on VM 1
docker compose -f infra/compose.lab.yml down -v
cd ~/wazuh-docker/single-node && docker compose down -v

# Wipe a victim
ssh vm3 'sudo apt-get purge -y wazuh-agent && sudo systemctl disable --now sandcat && sudo rm -f /etc/systemd/system/sandcat.service /usr/local/bin/sandcat'
```

---

## What to read next

- **Architecture details** — [docs/IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
- **Wazuh field → STRIX feature mapping** — [docs/WAZUH_MAPPING.md](WAZUH_MAPPING.md)
- **Model versions, registry, drift** — [docs/MODELS_REFERENCE.md](MODELS_REFERENCE.md)
- **Frontend dev** — [docs/WEB_RUN.md](WEB_RUN.md)
