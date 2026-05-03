# Session Log — Lab Dockerization + Caldera Playbook

**Date:** 2026-04-22
**Topic:** Pivot the STRIX lab from 5-VM to all-Docker simulation with
host-native platform; wire connectivity; document Caldera operations.

---

## Turn 1 — User

> ok so plan changed, we want to setup the simulation environment locally in
> docker images (one docker image for caldera attacker, 2 for victims and
> one for wazuh server) all of them in docker images, except the platform
> which will be in the host … so the VM will be replaced by docker image
> contains ubuntu and all needed apps inside (wazuh agent + sandcat for the
> victim, and caldera red ts for the attacker). for that i want you to
> verify this LAB_BRINGUP.md file, then prepare a docker compose for all
> the docker images needed. (keep in mind that they have to be configured
> in one same network please). and also modify lab_bringup after you
> prepare it.

### Assistant actions

- Read existing [LAB_BRINGUP.md](LAB_BRINGUP.md), [compose.lab.yml](../infra/compose.lab.yml),
  [compose.victim.yml](../infra/compose.victim.yml), [install_victim.sh](../infra/scripts/install_victim.sh),
  [filebeat.yml](../infra/filebeat.yml).
- Confirmed `caldera:latest` (4.46GB) already built locally; `~/Desktop/caldera/` checked out.

### Verification findings on the old doc

- ✅ Sandcat `POST /file/download` endpoint and header trio correct → reused.
- ✅ Wazuh ports 1514/1515/55000 + alerts path `/var/ossec/logs/alerts/alerts.json` correct.
- ✅ Volume name `single-node_wazuh_logs` must match the existing external
  reference in [compose.lab.yml:207](../infra/compose.lab.yml#L207).
- ❌ All VM/SSH/UFW content obsolete → removed.
- ❌ `scp install_victim.sh` pattern → replaced by `docker exec strix_victim1 …`.

### New files created

#### [infra/compose.simulation.yml](../infra/compose.simulation.yml)
4 services on shared bridge `strix_lab_net`:

| Service | Image | Role |
|---|---|---|
| `wazuh.manager` | `wazuh/wazuh-manager:4.9.2` | SIEM core |
| `caldera` | `caldera:latest` | C2 server |
| `victim1`, `victim2` | `strix/victim:lab` (built locally) | targets |

Volume `single-node_wazuh_logs` explicitly named so
[compose.lab.yml](../infra/compose.lab.yml) keeps working as external ref.

#### [infra/simulation/victim/Dockerfile](../infra/simulation/victim/Dockerfile)
Ubuntu 22.04 + `wazuh-agent=4.9.2-1` + tooling.

#### [infra/simulation/victim/entrypoint.sh](../infra/simulation/victim/entrypoint.sh)
- Enrolls via `agent-auth`
- Starts wazuh-agent
- Waits for Caldera to be ready
- Downloads + runs sandcat binary

### LAB_BRINGUP.md rewrite
Dropped VM/SSH/UFW sections; replaced separate `wazuh-docker/single-node`
clone with inline service; updated troubleshooting.

---

## Turn 2 — User

> take this wazuh mapping into consideration

### Assistant actions

- Read [docs/WAZUH_MAPPING.md](WAZUH_MAPPING.md).
- Read [config/wazuh/ossec-agent-localfiles.xml.draft](../config/wazuh/ossec-agent-localfiles.xml.draft)
  + [manager-ossec-conf.xml.draft](../config/wazuh/manager-ossec-conf.xml.draft).

### Key finding
The model was trained on Wazuh fields that require the agent to be
configured for:
- **auditd** → `data.audit.*` (biggest feature family)
- **syscheck / FIM** → `syscheck.*`
- **SCA** → `data.sca.*`
- **PAM/sudo/sshd via `/var/log/auth.log`** → `data.srcip`, `data.command`, etc.
- **dpkg-decoder via `/var/log/dpkg.log`**

Default wazuh-agent install doesn't enable any of that.

### Changes

#### [infra/simulation/victim/Dockerfile](../infra/simulation/victim/Dockerfile)
Added `auditd`, `audispd-plugins`, `rsyslog`, `python3`, `netcat-openbsd`.
Bakes [localfiles.xml](../infra/simulation/victim/localfiles.xml) (copy of
the draft) into `/opt/strix/localfiles.xml`.

#### [infra/simulation/victim/entrypoint.sh](../infra/simulation/victim/entrypoint.sh)
Now a 5-step boot:
1. Inject localfiles fragment into `/var/ossec/etc/ossec.conf` (idempotent,
   marker-guarded via Python one-liner).
2. `rsyslogd` → writes `/var/log/auth.log`, `syslog`, `kern.log`, `dpkg.log`.
3. Best-effort `auditd` + EXECVE rule (flagged limitation: host auditd
   owns kernel netlink).
4. `wazuh-agent` enroll + start.
5. Sandcat fetch + run.

### LAB_BRINGUP.md update
- Training-schema alignment section added to §1.
- auditd-in-container caveat box: two workarounds (stop host auditd, or
  bind-mount `/var/log/audit:/var/log/audit:ro`).

### Coverage table

| Feature family | Status |
|---|---|
| `data.audit.*` | ✅ with host-auditd caveat |
| `syscheck.*` | ✅ |
| `data.sca.*` | ✅ |
| `data.srcip`/`srcuser`/`command` | ✅ |
| `dpkg-decoder` | ✅ |
| `web-accesslog` | ⚠️ file exists, no apache running |

Manager defaults (`log_alert_level: 3`, `jsonout_output: yes`) already match
training — no override needed.

---

## Turn 3 — User

> ok, everything needed to get the needed features for the model at the end

### Assistant response
Confirmed full `_source.*` coverage and flagged two still-open items from
[MEMORY.md](../.claude/projects/-home-yacine-Desktop-GenAI-Detection-Framework/memory/MEMORY.md):

1. SecBERT PCA + StandardScaler artifacts not yet exported (pipeline needs
   them for embeddings to be in-distribution).
2. GNN threshold — still needs per-agent graph state in the stream layer.

---

## Turn 4 — User

> now i will run the platform locally not in docker image, can you ensure
> connectivity and that logs are really going from docker wazuh agents /
> server to the platform: in another words, wazuh communicate with the
> platform?

### Assistant analysis

Three options presented:
- **(A) keep Postgres/Redis/Filebeat in a slim compose** — recommended
- (B) install everything native
- (C) everything native except wazuh/caldera/victims

Went with (A).

### New file — [infra/compose.platform-deps.yml](../infra/compose.platform-deps.yml)

```
services:
  postgres   → 127.0.0.1:5432
  redis      → 127.0.0.1:6379
  filebeat   → mounts single-node_wazuh_logs (external),
               pushes to redis service (same network, "redis:6379" resolves)
```

### Bridge topology

```
docker: wazuh.manager --(volume: single-node_wazuh_logs)--> filebeat --(redis net)--> redis:6379
host:   wazuh_bridge --(127.0.0.1:6379)--> normalizer → inference → verdicts_writer --(127.0.0.1:5432)--> postgres
```

### LAB_BRINGUP.md §2 rewrite

Env overrides for host-run:
```
DB_HOST=localhost
REDIS_HOST=localhost
MODELS_PATH=$(pwd)/apps/models
```

Per-process manual launches:
```bash
uvicorn strix_api.app:app --host 0.0.0.0 --port 8000 --reload
python -m strix_api.workers.wazuh_bridge
python -m strix_api.workers.normalizer
python -m strix_api.workers.inference
python -m strix_api.workers.verdicts_writer
arq strix_api.workers.arq_tasks.WorkerSettings
```

### LAB_BRINGUP.md §2.5 — 8-step connectivity verification

Each step isolates one hop:
- (a) manager writes alerts.json
- (b) agents Active
- (c) rule trips from inside victim
- (d) filebeat → Redis list
- (e) wazuh_bridge → Redis stream
- (f) normalizer consumer group advances
- (g) verdicts land in Postgres
- (h) API responds

Decision tree at the bottom for where breaks are.

---

## Turn 5 — User

> add it
> *(i.e., add the single-command host bring-up)*

### New files

#### [Procfile.host](../Procfile.host)
7 processes in honcho format (api + 5 workers + web).

#### [infra/scripts/lab_verify.sh](../infra/scripts/lab_verify.sh)
The 8 connectivity probes from §2.5 encoded as pass/fail assertions.
Exits non-zero on first failed hop.

### Makefile additions (9 targets under *Host-native lab*)

| Target | Purpose |
|---|---|
| `sim-up` / `sim-down` | simulation compose |
| `deps-up` / `deps-down` | platform-deps compose |
| `host-migrate` | `alembic upgrade head` with `.env` sourced |
| `host-seed` | reuses existing [seed_admin.py](../infra/scripts/seed_admin.py) |
| `host-up` | honcho — all 7 processes, Ctrl-C stops everything |
| `lab-up` | sim-up → deps-up → host-migrate → host-seed |
| `lab-verify` | runs lab_verify.sh |

### Typical flow

```bash
pip install honcho                   # once
make lab-up                           # prep
make host-up                          # foreground
make lab-verify                       # another terminal
```

---

## Turn 6 — User

> check caldera documentation to see how to start the simulation, with
> different techniques of course. write md file for this as well.

### Assistant actions

- WebFetch on readthedocs (returned 403) → fell back to local source.
- Enumerated adversaries from `~/Desktop/caldera/plugins/stockpile/data/adversaries/*.yml` + `packs/`.
- Inspected REST routes at [app/api/v2/handlers/operation_api.py](../../caldera/app/api/v2/handlers/operation_api.py).
- Confirmed operation state enum from [app/objects/c_operation.py](../../caldera/app/objects/c_operation.py)
  `class States(Enum)` → `running | paused | out_of_time | finished | cleanup`.
- Confirmed red API key `ADMIN123` in `conf/default.yml`.
- Counted Linux-compatible abilities by tactic.

### New file — [docs/CALDERA_PLAYBOOK.md](CALDERA_PLAYBOOK.md)

**8 sections, ~280 lines:**

1. **Core concepts** — ability / adversary / planner / operation / group / obfuscator.
2. **Built-in adversaries for Linux** — Check, Discovery, Collection, Thief, Advanced Thief via FTP, Ransack, Super Spy; with avoid-list (Windows-only, external-API-token-needing, WiFi-based).
3. **UI recipe** — 4-step Campaigns → Operations → + → Start.
4. **REST API** — `curl` against `/api/v2/adversaries`, `/operations`, `/planners`; PATCH to stop; report pull.
5. **Technique-targeted recipes** — 6 mini-recipes mapped to MITRE IDs and the specific STRIX engineered features they exercise:
   - T1083 file discovery
   - T1059.004 shell (via `base64jumble` obfuscator)
   - T1005/T1560 collection + archiving
   - T1048.003 FTP exfil (with throwaway `alpine-ftp-server` sidecar)
   - T1046 port scan
   - Full **Thief** chain with timing table
6. **Ad-hoc adversary via API** — 3-call pattern.
7. **Pipeline validation** — before/after `XLEN strix:alerts:raw` + SQL for rule/verdict correlation.
8. **Troubleshooting** — 6 failure modes with fixes.

### Cross-links

- [LAB_BRINGUP.md §3.B](LAB_BRINGUP.md) now has a 3-line summary + pointer to playbook.
- "What to read next" in LAB_BRINGUP.md now lists playbook first.

---

## Summary — final artifact inventory

### New / modified files

| File | Purpose |
|---|---|
| [infra/compose.simulation.yml](../infra/compose.simulation.yml) | Wazuh + Caldera + 2 victims on shared network |
| [infra/compose.platform-deps.yml](../infra/compose.platform-deps.yml) | Postgres + Redis + Filebeat for host-run platform |
| [infra/simulation/victim/Dockerfile](../infra/simulation/victim/Dockerfile) | Victim image — wazuh-agent + auditd + rsyslog |
| [infra/simulation/victim/entrypoint.sh](../infra/simulation/victim/entrypoint.sh) | 5-step boot: inject config, start loggers, enroll, start agent, run sandcat |
| [infra/simulation/victim/localfiles.xml](../infra/simulation/victim/localfiles.xml) | Training-schema agent config fragment |
| [infra/scripts/lab_verify.sh](../infra/scripts/lab_verify.sh) | 8-probe connectivity assertion script |
| [Procfile.host](../Procfile.host) | Honcho-format host processes |
| [Makefile](../Makefile) | Added 9 host-native lab targets |
| [docs/LAB_BRINGUP.md](LAB_BRINGUP.md) | Full rewrite: Docker-only sim + host platform |
| [docs/CALDERA_PLAYBOOK.md](CALDERA_PLAYBOOK.md) | Caldera operation recipes per MITRE technique |

### Open items (not addressed in this session)

- SecBERT PCA / StandardScaler artifacts not yet exported (tracked in
  [MEMORY.md](../.claude/projects/-home-yacine-Desktop-GenAI-Detection-Framework/memory/ml_inference_blockers.md))
- GNN threshold + per-agent graph state in stream layer
- auditd-in-container limitation requires either stopping host auditd or
  bind-mounting host audit logs

### One-liner to run the whole thing

```bash
pip install honcho
make lab-up          # sim + deps + migrate + seed
make host-up         # api + workers + web (Ctrl-C stops all)
make lab-verify      # another terminal — prove Wazuh → platform
```
