# Session log — Caldera ATT&CK simulation + audit pipeline fixes

**Date:** 2026-04-29
**Branch:** `Platforme`
**Goal:** Drive Caldera-emulated MITRE techniques against the STRIX victim containers and produce paper-aligned (`_source.data.audit.*`) data flowing all the way to the platform's `detections` table.

**Reference paper:** Karim, S.S. et al. (2024). *Advanced Persistent Threat (APT) and intrusion detection evaluation dataset for Linux systems 2024*. Data in Brief 54, 110290.

**Outcome:** Pipeline fully operational. 31,273 audit alerts produced, 589 alerts persisted to Postgres, 589 detections with full 5-model ML output (AE, VAE, Transformer, GNN, DQN), 451 attack chains, max CKC stage 3 reached.

---

## 0. Pre-session deliverable — Caldera usage guide

User asked for a `.doc` file documenting how to simulate the paper's MITRE tactics & techniques in Caldera. Created:

- [`docs/CALDERA_MITRE_SIMULATION_GUIDE.md`](CALDERA_MITRE_SIMULATION_GUIDE.md) — 33 KB Markdown source
- [`docs/CALDERA_MITRE_SIMULATION_GUIDE.docx`](CALDERA_MITRE_SIMULATION_GUIDE.docx) — Word-compatible export via pandoc

Structure:

1. Background & paper context (Tables 4 & 5 tactic/technique counts)
2. Caldera setup recap (server, sandcat, stockpile, atomic plugins)
3. Core concepts cheat sheet
4. Per-tactic recipes (12 tactics, with stockpile ability mappings)
5. APT-group emulation chains (APT41, APT28, APT29, Turla)
6. Special cases (Apache Struts, keylogger, systemd backdoor)
7. Verification — confirming Wazuh captures the simulation
8. Reproducing the paper's tactic distribution

The guide cross-references the existing [`docs/CALDERA_PLAYBOOK.md`](CALDERA_PLAYBOOK.md) for lab-specific REST API operations rather than duplicating it.

---

## 1. Lab bring-up state

User started with `infra/scripts/lab_up.sh`, which reported:

```
✓ STRIX lab is up
  Caldera      http://localhost:8888
     red    password : strix-red
            api_token: 6_KGdfLFfV0HVBnfqDk8gt1S8yD2ExxW9922FAT8QSw
  XLEN strix:alerts:raw = 128
  verdicts rows = 54
⚠ alerts.json did not grow (+0); rules may not be tripping
```

The `⚠` foreshadowed everything that followed.

---

## 2. Step-by-step Caldera operation

### Step 1 — env vars + verify agents

```bash
export CALDERA=http://localhost:8888
export KEY="KEY: 6_KGdfLFfV0HVBnfqDk8gt1S8yD2ExxW9922FAT8QSw"

curl -s "$CALDERA/api/v2/agents" -H "$KEY" | jq '.[] | {paw, host, platform, group, last_seen}'
```

**Result:** 18 agents listed; only the bottom two (`bslyii` victim2, `byaveh` victim1) had recent `last_seen`. Caldera ignores stale paws automatically.

### Step 2 — run **Check** adversary (sanity op)

```bash
ADV_ID=$(curl -s "$CALDERA/api/v2/adversaries" -H "$KEY" | jq -r '.[] | select(.name=="Check") | .adversary_id')
PLANNER_ID=$(curl -s "$CALDERA/api/v2/planners" -H "$KEY" | jq -r '.[] | select(.name=="batch") | .id')

OP=$(curl -s -X POST "$CALDERA/api/v2/operations" -H "$KEY" \
  -H "Content-Type: application/json" -d "{
    \"name\": \"sim-check-$(date +%s)\",
    \"adversary\": { \"adversary_id\": \"$ADV_ID\" },
    \"group\": \"red\",
    \"planner\": { \"id\": \"$PLANNER_ID\" },
    \"obfuscator\": \"plain-text\",
    \"autonomous\": 1,
    \"state\": \"running\"
  }")
```

**First glitch:** `jq` parse error on the response. Cause: Caldera returns operation creation response with raw control characters in some link's `output` field — sandcat stdout isn't always JSON-escaped. Worked around with `python3 -c "json.loads(..., strict=False)"`.

OP_ID came back: `b77ace3f-7ba9-423e-b187-e8c9e77fea9f`.

### Step 3 — poll the Check op

```bash
sleep 45
curl -s "$CALDERA/api/v2/operations/$OP_ID" -H "$KEY" > /tmp/op.json
python3 - <<'PY'
import json
d = json.load(open('/tmp/op.json'), strict=False)
print(f"state: {d.get('state')}  links: {len(d.get('chain',[]))}")
PY
```

**Result:** `state: finished`, `n_links: 0` — Check has no Linux-applicable abilities in this stockpile build (Windows-focused sanity profile). Infra is fine, just zero output.

### Step 4 — run **Discovery** adversary (real paper techniques)

Same pattern but selecting `name=="Discovery"`. Got `n_links: 6` after waiting 90s:

```
host=victim2  status=  0  T1033       Identify active user
host=victim1  status=  0  T1033       Identify active user
host=victim2  status=  0  T1087.001   Find local users
host=victim1  status=  0  T1087.001   Find local users
host=victim2  status= -3  T1057       Find user processes
host=victim1  status= -3  T1057       Find user processes
```

`status=-3` is "untrusted" — sandcat momentarily out of contact. T1033 + T1087.001 succeeded (paper-aligned techniques: System Owner/User Discovery, Account Discovery).

### Step 5 — long-tail T1057 explosion

Polling 60s later showed **46 links** with T1057 (Process Discovery) repeating per discovered user × 2 agents. The ability is `repeatable: true`; the planner cycles through facts. Stopped the op via PATCH:

```bash
curl -s -X PATCH "$CALDERA/api/v2/operations/$OP_ID" -H "$KEY" \
  -H "Content-Type: application/json" -d '{"state":"finished"}'
```

### Step 6 — inspect link output

Tried to decode `link.output` field but got `N��` — Caldera's link output is **encrypted by default** (sandcat XOR-encrypts result blobs). Decoding requires the report endpoint with `?enable_agent_output=true`, but for paper-equivalence the SIEM-side validation matters more.

### Step 7 — first Wazuh check

```bash
docker exec strix_wazuh_manager tail -300 /var/ossec/logs/alerts/alerts.json | \
  python3 /home/yacine/Desktop/GenAI-Detection-Framework/infra/simulation/scripts/parse_alerts.py
```

**Result:** only rules 533 (netstat port changes) and 510 (rootcheck). **No audit/execve events tagged with MITRE technique IDs.** The paper builds Tables 4 & 5 from `rule.mitre.id` on audit-derived alerts — this was the missing link.

---

## 3. Diagnostic descent — why no audit alerts?

### Step 8 — auditd state inside victim2

```bash
docker exec strix_victim2 sh -c 'auditctl -l; pgrep -a auditd; tail -5 /var/log/audit/audit.log'
```

```
=== auditctl -l (loaded rules) ===
Error sending rule list data request (Operation not permitted)

=== auditd process ===
auditd NOT running

=== /var/log/audit/audit.log ===
-rw-r--r-- 1 root root      0 Apr 28 16:54 audit.log
```

Confirmed: auditd cannot start inside the container. EPERM on netlink.

### Step 9 — diagnose container caps + host auditd

Container had `CapAdd=[AUDIT_READ AUDIT_WRITE AUDIT_CONTROL ...]` — caps are correct. Host `auditd` was `inactive` (only `[kauditd]` kernel thread). Compose excerpt confirmed the caps were intentional.

### Step 10 — test seccomp/apparmor unconfined

Throwaway container with `--security-opt seccomp=unconfined --security-opt apparmor=unconfined` still failed — entrypoint was inherited and DNS-waiting on `wazuh.manager` (different network). Inconclusive.

### Step 11 — clean test bypassing entrypoint + check kernel

```bash
docker run --rm --entrypoint /bin/bash \
  --cap-add AUDIT_CONTROL --cap-add AUDIT_READ --cap-add AUDIT_WRITE \
  --security-opt seccomp=unconfined --security-opt apparmor=unconfined \
  strix/victim:lab \
  -c 'auditctl -l; auditctl -s | head -5; auditctl -a always,exit -F arch=b64 -S execve -k EXEC'
```

Still `Operation not permitted`. Kernel checks:

```
CONFIG_AUDIT=y
CONFIG_AUDITSYSCALL=y
CONFIG_AUDIT_ARCH=y
```

Plus `dmesg` showed audit subsystem actively producing events for AppArmor/snap. **The kernel audit subsystem works on the host. It's purely a per-namespace netlink restriction that Docker bridge networks can't cross.**

### Step 12 — canonical fix from `LAB_BRINGUP.md`

Found in [`docs/LAB_BRINGUP.md:82-87`](LAB_BRINGUP.md):

> ⚠️ auditd caveat. The host kernel's audit netlink is single-owner. […] Either stop the host's auditd or **bind-mount host audit logs (`/var/log/audit:/var/log/audit:ro`) into the victim containers** if you need full auditd coverage.

Plan: install auditd **on the Kali host** (it sees container execve via the shared kernel), bind-mount `/var/log/audit` into both victims, let Wazuh's existing `<localfile><log_format>audit</log_format>` directive read it.

```bash
sudo apt-get install -y auditd audispd-plugins

sudo tee /etc/audit/rules.d/strix.rules > /dev/null <<'RULES'
-D
-b 16384
-a always,exit -F arch=b64 -S execve -k audit-wazuh-x
-a always,exit -F arch=b32 -S execve -k audit-wazuh-x
RULES

sudo augenrules --load
sudo systemctl enable --now auditd
```

(The key was initially `EXEC`; corrected to `audit-wazuh-x` later — see step 17.)

Patched [`infra/compose.simulation.yml`](../infra/compose.simulation.yml) to add `volumes: - /var/log/audit:/var/log/audit:ro` to victim1 and victim2.

### Step 13 — restart victims → restart loop

`docker compose up -d --force-recreate victim1 victim2` and victims went into a CrashLoop:

```
[victim] manager=wazuh.manager caldera=caldera:8888 name=victim2
touch: cannot touch '/var/log/audit/audit.log': Read-only file system
```

Cause: entrypoint had `set -e` and unconditional `touch /var/log/audit/audit.log`. The bind-mount is read-only — touch fails — `set -e` exits — restart.

### Step 14 — fix entrypoint + rebuild

Patched [`infra/simulation/victim/entrypoint.sh`](../infra/simulation/victim/entrypoint.sh):

```bash
mkdir -p /var/log /var/log/apache2
[ -d /var/log/audit ] || mkdir -p /var/log/audit
touch /var/log/auth.log /var/log/syslog /var/log/kern.log /var/log/dpkg.log \
      /var/log/apache2/access.log
[ -w /var/log/audit ] && touch /var/log/audit/audit.log || \
  echo "[victim] /var/log/audit is read-only (host bind-mount) — skipping touch"
```

Rebuilt + restarted. Both victims `Up`. Audit log now visible inside container at 7.2 MB. **But still only rules 533/510 in alerts.json.**

### Step 15 — agent reads + manager decodes diagnostic

```
=== AGENT (victim1) side ===
✅ ossec.conf has audit localfile
✅ logcollector: "Analyzing file: '/var/log/audit/audit.log'"
✅ recent EXECVE lines visible

=== MANAGER side ===
❌ no non-533/510 rules
❌ no decoder errors in ossec.log
```

Agent is reading & sending. Manager sees nothing matching audit rules.

### Step 16 — `wazuh-logtest` to confirm decoder + rule

```bash
docker exec -i strix_wazuh_manager /var/ossec/bin/wazuh-logtest <<'EOF'
type=SYSCALL msg=audit(...): ... comm="whoami" exe="/usr/bin/whoami" key="EXEC"
EOF
```

→ Phase 2: decoder=auditd ✅. Phase 3: **rule 80700 level 0** — "Audit: Messages grouped" — does NOT alert (alert level filter is ≥3).

Same line with `key="audit-wazuh-x"` → **rule 80789 level 3** — "Audit: Watch - Execute access" — **Alert to be generated.**

The audit key was the issue. Wazuh's default audit ruleset uses a CDB lookup against `etc/lists/audit-keys` which expects keys like `audit-wazuh-x` (execute), `audit-wazuh-w` (write), etc.

### Step 17 — switch host audit key to `audit-wazuh-x`

Updated `/etc/audit/rules.d/strix.rules` and `augenrules --load`. CDB list verified:

```
audit-wazuh-w:write
audit-wazuh-r:read
audit-wazuh-a:attribute
audit-wazuh-x:execute
audit-wazuh-c:command
```

### Step 17b — second blocker: agent enrollment failures

Even with the right key, alerts.json showed 0 rule-80789. Tracing the agent log:

```
wazuh-agentd: ERROR: Duplicate agent name: victim1 (from manager)
wazuh-agentd: ERROR: Unable to add agent (from manager)
```

Cause: `force-recreate` wipes the container's `client.keys` (no named volume for `/var/ossec/etc`), but the manager retains the prior registration. New agent can't claim a name that already exists.

Fix: removed duplicates, restarted victims:

```bash
docker exec strix_wazuh_manager bash -c '
  /var/ossec/bin/manage_agents -r 003 << "EOF"
y
EOF
  /var/ossec/bin/manage_agents -r 004 << "EOF"
y
EOF
'
docker compose -f infra/compose.simulation.yml restart victim1 victim2
```

Agents enrolled fresh as 005/006. **Rule 80789 alerts: 0 → 1,273.** Sample alert:

```json
{
  "rule.id": "80789",
  "rule.description": "Audit: Watch - Execute access: /usr/bin/ps.",
  "agent.name": "victim2",
  "data.audit.command": "ps",
  "data.audit.exe": "/usr/bin/ps",
  "data.audit.key": "audit-wazuh-x"
}
```

Paper-aligned shape ([WAZUH_MAPPING.md §4](WAZUH_MAPPING.md)).

---

## 4. STRIX platform side — final blocker

After verifying alerts flow into Wazuh, checked the platform's Postgres:

```
=== STRIX platform side ===
Redis stream length: 1,514
alerts table:        54  (unchanged)
detections table:    54  (unchanged)
```

Stream is filling but tables aren't growing. Normalizer log was screaming:

```json
{"reason": "VALIDATION_FAILED", "detail": "alert is missing agent.id", "event": "alert_dropped"}
```

Hundreds per second. **Every alert dropped at the normalizer.**

### Root cause — Filebeat config

Checked the redis stream entry shape vs the Wazuh alert: alert has `agent.id`, `agent.name`, `agent.ip`. Stream entry had **no `agent` block at all**.

[`infra/filebeat.yml:36`](../infra/filebeat.yml):

```yaml
processors:
  - drop_fields:
      fields: ["agent", "ecs", "host", "input", "log", "@metadata", "@version"]
```

Intent was to strip Filebeat's *own* envelope (`agent.type=filebeat`, `agent.version=8.x`). With `parsers.ndjson.target=""` + `overwrite_keys=true`, Wazuh's `agent.*` rode in the same block — and got dropped.

### Fix

```diff
 processors:
   - drop_fields:
-      fields: ["agent", "ecs", "host", "input", "log", "@metadata", "@version"]
+      fields: ["ecs", "host", "input", "log", "@metadata", "@version"]
       ignore_missing: true
```

Restarted filebeat (with `--env-file apps/api/.env`) — DB_PASSWORD interpolation requires it.

**Result:** redis entries now contain the merged agent block:

```json
{
  "agent": {
    "type": "filebeat",
    "version": "8.15.3",
    "ephemeral_id": "...",
    "id": "005",
    "name": "victim1",
    "ip": "172.21.0.2"
  }
}
```

`alerts` table 54 → 489 → 589 → growing. `detections` matching 1:1.

---

## 5. Final state

```
[1] Caldera ops fired:                 5+ (sim-discovery-*, all state=finished)
[2] Wazuh rule-80789 audit alerts:     31,273
[3] Redis stream strix:alerts:raw:     31,999 entries (consumer lag = 0)
[4] Postgres alerts (skeleton FK rows): 589
[5] Postgres detections (full ML out):  589
[6] Postgres attack_chains:             451 (max CKC stage 3)
[7] Postgres dqn_actions:               589
                                          312 NO_OP                 (no approval)
                                          189 BLOCK_USER_IP         (approval req)
                                           55 NOTIFY                (no approval)
                                           33 ISOLATE_HOST          (approval req)
[8] Hosts:                               7 (active: 005=victim1, 006=victim2)
```

Sample detection row showing all 5 ML models running:

```
ae_anomaly_score: 44.36
vae_malicious_prob: 1.000
transformer_pred_ckc: 0
transformer_confidence: 0.51
gnn_node_risk: 0
state_vector: {10,10,1,0,0,0.5,0,0,0,0,0,0,0}
model_versions: {"ae":"v1", "dqn":"v1", "gnn":"v1", "vae":"v1", "transformer":"v1"}
```

### Why the alerts table looks "empty"

`alerts.raw_jsonb = {}`, `decoder_name = NULL`, `rule_id = NULL` for the new rows. **By design**, per [`apps/api/src/strix_api/workers/verdicts_writer.py:8-10`](../apps/api/src/strix_api/workers/verdicts_writer.py):

> "INSERTs a skeleton alert row (FK target — Phase 5+ will fill MITRE fields once we wire the full RawAlert through the queue)."

The verdicts_writer only persists what's needed for FK relations from `detections`/`attack_chains`/`dqn_actions`. The real ML output is in `detections`.

---

## 6. Files modified this session

| Path | Change |
|---|---|
| [`docs/CALDERA_MITRE_SIMULATION_GUIDE.md`](CALDERA_MITRE_SIMULATION_GUIDE.md) | New — usage guide for all 12 paper tactics in Caldera |
| [`docs/CALDERA_MITRE_SIMULATION_GUIDE.docx`](CALDERA_MITRE_SIMULATION_GUIDE.docx) | New — pandoc-converted Word doc |
| [`infra/compose.simulation.yml`](../infra/compose.simulation.yml) | Added `volumes: - /var/log/audit:/var/log/audit:ro` to victim1/victim2 |
| [`infra/simulation/victim/entrypoint.sh`](../infra/simulation/victim/entrypoint.sh) | Conditional `touch` on read-only audit mount |
| [`infra/filebeat.yml`](../infra/filebeat.yml) | Removed `agent` from `drop_fields` |
| `/etc/audit/rules.d/strix.rules` (host) | New — `audit-wazuh-x` execve rules |

Plus a helper saved to [`infra/simulation/scripts/parse_alerts.py`](../infra/simulation/scripts/parse_alerts.py) for grouping alerts.json entries by `(rule_id, agent, mitre)`.

---

## 7. What to run next (paper coverage)

The pipeline now ingests every Caldera-emitted shell command. To populate the paper's other tactics, fire the corresponding stockpile adversaries against `group=red`:

| Paper tactic | Stockpile adversary | Paper techniques covered |
|---|---|---|
| Discovery (TA0007) | `Discovery` ✅ done | T1083, T1057, T1033, T1087.001, T1069.001 |
| Defense Evasion (TA0005) | `Avoid logs` (custom chain) | T1070.003, T1070.004 |
| Persistence (TA0003) | `Hunter` (or custom T1136 chain) | T1136, T1098, T1037 |
| Privilege Escalation (TA0004) | `Privileged Operations` | T1548.003, T1068 |
| Credential Access (TA0006) | custom (Hydra ability) | T1110.001, T1003.008 |
| Lateral Movement (TA0008) | `Lateral Movement (SSH)` | T1021.004 |
| Collection (TA0009) | `Collection` | T1005, T1560.001 |
| Exfiltration (TA0010) | `Advanced Thief via FTP` | T1048 |
| Impact (TA0040) | `Ransack` (destructive — careful) | T1485, T1565.001 |

For initial-access (T1190 Apache Struts) the lab needs a vulhub container — see [`docs/CALDERA_MITRE_SIMULATION_GUIDE.md` §5.2](CALDERA_MITRE_SIMULATION_GUIDE.md).

---

## 8. Take-aways for future sessions

1. **Audit netlink in Docker is per-namespace and init-netns-only.** Don't try to run auditd inside containers — even with `CAP_AUDIT_*` and seccomp/apparmor unconfined. Run it on the host and bind-mount the log.

2. **Wazuh's audit ruleset only fires on `audit-wazuh-{w,r,a,x,c}` keys** (mapped via CDB list `etc/lists/audit-keys`). Any other key gets rule 80700 level 0 — silent drop.

3. **`docker compose up -d --force-recreate` of victims breaks agent enrollment** because there's no named volume for `/var/ossec/etc`. Always `manage_agents -r <id>` before re-enrolling, or add `-r` flag to `agent-auth` in entrypoint.

4. **Filebeat `drop_fields: ["agent"]` will break the normalizer.** Wazuh's agent block must survive — Filebeat's own `agent.type/version` merge harmlessly into the same object.

5. **`alerts.raw_jsonb = {}` is by design.** The verdicts_writer creates a skeleton FK row only — full RawAlert wiring is Phase 5+ work. Real ML state lives in `detections`.

Memory saved at [`memory/project_lab_audit_pipeline_fixes.md`](/home/yacine/.claude/projects/-home-yacine-Desktop-GenAI-Detection-Framework/memory/project_lab_audit_pipeline_fixes.md) so future agents pick up this context without re-discovering.
