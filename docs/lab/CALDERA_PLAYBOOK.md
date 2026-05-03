# Caldera Playbook — running attack simulations against the STRIX lab

Copy-pasteable operations for driving the Docker victims through MITRE
ATT&CK techniques so Wazuh produces realistic alerts for the ML pipeline.

Assumes [LAB_BRINGUP.md](LAB_BRINGUP.md) is green (victims `Active`,
sandcat agents visible in Caldera).

- UI: **http://localhost:8888** — user `red` / `admin`
- REST API key (red team): `ADMIN123` — pass as `KEY: ADMIN123` header
- OpenAPI spec: **http://localhost:8888/api/docs**

---

## 1. Core concepts (30-second version)

| Term | What it is |
|---|---|
| **Ability** | Single MITRE ATT&CK technique implementation (bash/PowerShell/Python snippet). Tagged with `technique_id` (e.g. `T1083`) and `tactic` (e.g. `discovery`). |
| **Adversary** | Ordered list of abilities = a profile. Can be ad-hoc or from the stockpile. |
| **Planner** | Scheduler that decides which ability to run next. `batch` (sequential), `buckets` (by tactic), `atomic` (one-at-a-time), `look ahead`, `bayes`. |
| **Operation** | An execution: adversary + planner + group (targets) + obfuscator. |
| **Group** | A tag on agents. Victims in this lab enroll as `red` (set in `compose.simulation.yml`). |
| **Obfuscator** | Command-line munger (`plain-text`, `base64`, `base64jumble`, `caesar cipher`). Determines how noisy the command field looks to Wazuh. |

Source of truth for stockpile abilities in this repo's Caldera checkout:

```
plugins/stockpile/data/
  abilities/<tactic>/<uuid>.yml
  adversaries/<uuid>.yml
  adversaries/packs/<uuid>.yml
  planners/<uuid>.yml
```

---

## 2. Built-in adversaries that work on the Linux victims

Stockpile ships ~30 adversary profiles; most target Windows. The subset that
exercises the Linux victims in this lab (Ubuntu + sandcat + wazuh-agent):

| Adversary | What it runs | Noise it creates (for Wazuh) |
|---|---|---|
| **Discovery** *(pack)* | `whoami`, `hostname`, network neighbor scan, process list, user enumeration | `data.command` via PAM/sudo, `data.audit.*` via auditd exec |
| **Collection** *(pack)* | Finds + stages sensitive files under `/tmp/staged` | FIM `syscheck.*` on `/tmp`, `path_is_temp=1` feature |
| **Thief** *(pack)* | Discovery → Collection → compress staged dir | Combined: auditd exec chain + FIM activity |
| **Advanced Thief via FTP** | Thief chain + `curl` exfil to an FTP endpoint | Plus outbound `data.srcip` noise |
| **Ransack** | Host profile + sensitive-file hunt | Heavy discovery signal |
| **Super Spy** | Clipboard + browser history + user navigation | Broad `data.command` coverage |
| **Check** | Sanity profile — verifies platform config | Low-noise — use this first to confirm chain works |

Avoid on this lab:
- `Advanced Thief via DropBox` / `via GitHub Gist` / `via GitHub Repo` — need
  external API tokens.
- `Nosy Neighbor` — WiFi discovery, doesn't work inside containers.
- Windows-only (`You Shall (Not) Bypass`, `Lateral Movement - Esentutl`,
  `Service Creation Lateral Movement`, `Signed Binary Proxy Execution`).
- `Worm` — lateral movement across hosts; works but produces network
  scanning noise that tends to trip generic Wazuh rules rather than the
  training-schema ones.

---

## 3. UI recipe — start an operation in 30 seconds

1. Open **http://localhost:8888** → `red` / `admin`.
2. **Navigate →** `Campaigns` → `Operations` → `+`.
3. Fill:
   - **Name**: `lab-<technique>-<n>` (used in verdict correlation).
   - **Group**: `red` (the group sandcat is enrolled into).
   - **Adversary**: pick from §2 — start with **Check**, then **Discovery**.
   - **Planner**: `batch` for a single pass, `atomic` if you want to
     step through one ability at a time, `buckets` to cycle tactics.
   - **Obfuscator**: `plain-text` while you're learning — switch to
     `base64` later to see how SecBERT handles encoded commands.
   - **Autonomous**: ✅ (otherwise you have to click each link).
4. **Start** (▶).

Kill-chain progression in the UI's *Debrief* tab maps to what the STRIX
*Attack Analysis* view aggregates via the GNN model.

---

## 4. REST API — scripted operations

### 4.1 Auth

Every request needs `KEY: ADMIN123` (red-team API key from
`conf/default.yml`). Can be overridden via `CALDERA_API_KEY` env var at
server start.

### 4.2 List adversaries + pick one

```bash
CALDERA=http://localhost:8888
KEY="KEY: ADMIN123"

# UUIDs of all adversaries (grep by name)
curl -s "$CALDERA/api/v2/adversaries" -H "$KEY" | \
  jq -r '.[] | "\(.adversary_id)  \(.name)"'

DISCOVERY_ID=$(curl -s "$CALDERA/api/v2/adversaries" -H "$KEY" | \
  jq -r '.[] | select(.name=="Discovery") | .adversary_id')
echo "Discovery adversary: $DISCOVERY_ID"
```

### 4.3 Start an operation

```bash
curl -s -X POST "$CALDERA/api/v2/operations" \
  -H "$KEY" -H "Content-Type: application/json" \
  -d @- <<JSON | jq '.id, .state'
{
  "name": "lab-discovery-1",
  "adversary": { "adversary_id": "$DISCOVERY_ID" },
  "group": "red",
  "planner": { "id": "aba5f073-4dbc-4fc4-b2d0-3c97a13ea94b" },
  "obfuscator": "plain-text",
  "autonomous": 1,
  "state": "running"
}
JSON
```

> ⚠️  `planner.id` values differ per Caldera version. Fetch live:
> ```bash
> curl -s "$CALDERA/api/v2/planners" -H "$KEY" | \
>   jq -r '.[] | "\(.name)  \(.id)"'
> ```
> `batch` is the safest default. `atomic` requires manual `run_one_link`
> state transitions — skip unless you know why you want it.

### 4.4 Watch it, then stop

```bash
OP_ID=<id from step 4.3>

# Polling loop — shows chain length + state
while :; do
  curl -s "$CALDERA/api/v2/operations/$OP_ID" -H "$KEY" | \
    jq '{state, links:(.chain|length), last:(.chain[-1].ability.name // null)}'
  sleep 3
done

# Stop
curl -s -X PATCH "$CALDERA/api/v2/operations/$OP_ID" \
  -H "$KEY" -H "Content-Type: application/json" \
  -d '{"state":"finished"}'

# Pull the final report (all links, results, facts learned)
curl -s -X POST "$CALDERA/api/v2/operations/$OP_ID/report" -H "$KEY" > \
  /tmp/caldera_report_$OP_ID.json
```

Operation states you'll see: `running` → `paused` → `out_of_time` →
`finished` → `cleanup` (from [app/objects/c_operation.py](../../caldera/app/objects/c_operation.py)).

---

## 5. Technique-targeted recipes

Each recipe names the MITRE technique family you're exercising and the
STRIX features it's expected to light up. Run these individually to get
labeled flows for debugging the ML pipeline.

### 5.1 T1083 — File and Directory Discovery

**Purpose:** heavy auditd `execve` signal; populates `data.audit.command`,
`cmd_grep_find`, `cmd_cat_less` engineered features.

```bash
# Custom one-ability adversary: "Find files" from stockpile/collection.
ABILITY=<lookup: see below>
# Or simplest — just run the built-in Discovery pack (above).
```

Lookup abilities by technique:
```bash
curl -s "$CALDERA/api/v2/abilities" -H "$KEY" | \
  jq -r '.[] | select(.technique_id=="T1083") | "\(.ability_id)  \(.name)"'
```

### 5.2 T1059.004 — Unix Shell execution

**Purpose:** `data.command` + SecBERT embedding coverage. Raw shell like
`bash -c`, pipe chains, `eval`.

Run **Discovery** adversary with `obfuscator=base64jumble` → drives
`cmd_base64` / `cmd_eval_exec` feature flags.

### 5.3 T1005 + T1560 — Local data collection & archiving

**Purpose:** FIM signal (`syscheck_added`, `path_is_temp`) + exfil
precursor.

Adversary: **Collection** (or **Thief** for a chained version). Expect
syscheck events for files appearing under `/tmp/staged`.

### 5.4 T1048.003 — Exfil over unencrypted protocol

**Purpose:** outbound `data.srcip` with non-RFC1918 target, populates
`srcip_is_private=0` feature.

Adversary: **Advanced Thief via FTP**. You'll need an FTP receiver — an
easy lab one:

```bash
docker run -d --name strix_ftp_sink --network strix_lab_net \
  -p 2121:21 -e FTP_USER=red -e FTP_PASS=red \
  delfer/alpine-ftp-server
# Then in the adversary facts, set server.ftp.* to the above container.
```

### 5.5 T1046 — Network service scanning

**Purpose:** lateral-movement precursor noise; trips Wazuh network rules.

Ability: `Scan IP for ports` (under `discovery/`). Wrap in a tiny ad-hoc
adversary or add to an existing pack.

### 5.6 A realistic full chain (the smoke test)

Use the **Thief** pack (Discovery → Collection → compress) against group
`red`. Expected end-to-end on a warm pipeline:

| Stage | Seconds | STRIX signal |
|---|---|---|
| sandcat link check-in | 0 | nothing yet |
| Discovery abilities fire | 3–10 | Vigilance Feed SSE events appear |
| Collection creates `/tmp/staged/` | 10–20 | `syscheck_added=1`, FIM alerts |
| Compress staged dir | 20–30 | `cmd_tar_zip=1` feature |
| Kill-chain stages advance | continuous | Attack Analysis chain grows; CKC reaches COLLECTION or ACTIONS_ON_OBJECTIVES |

---

## 6. Running an ad-hoc adversary (one-off technique, no stockpile)

Sometimes you want a single command against the victim without authoring a
YAML. Caldera exposes a generic "run" path via the UI (**Campaigns →
Abilities** → pick ability → *run against group*), but the API version is
cleaner for automation:

```bash
# 1. Get an ability_id you want to exercise
ABILITY=$(curl -s "$CALDERA/api/v2/abilities" -H "$KEY" | \
  jq -r '.[] | select(.name=="View Processes") | .ability_id')

# 2. Wrap it as a transient adversary
ADV_ID=$(curl -s -X POST "$CALDERA/api/v2/adversaries" -H "$KEY" \
  -H "Content-Type: application/json" -d "{
    \"name\": \"oneoff-$(date +%s)\",
    \"atomic_ordering\": [\"$ABILITY\"]
  }" | jq -r '.adversary_id')

# 3. Launch op against the one-off
curl -s -X POST "$CALDERA/api/v2/operations" -H "$KEY" \
  -H "Content-Type: application/json" -d "{
    \"name\": \"adhoc-$(date +%s)\",
    \"adversary\": { \"adversary_id\": \"$ADV_ID\" },
    \"group\": \"red\",
    \"planner\": { \"id\": \"aba5f073-4dbc-4fc4-b2d0-3c97a13ea94b\" },
    \"obfuscator\": \"plain-text\",
    \"autonomous\": 1,
    \"state\": \"running\"
  }"
```

---

## 7. Validating each op reached the STRIX pipeline

After each operation ends (§4.4), the lab_verify script's stream check
should show growth:

```bash
# Before op
XLEN_BEFORE=$(redis-cli XLEN strix:alerts:raw)

# ... run op ...

# After
XLEN_AFTER=$(redis-cli XLEN strix:alerts:raw)
echo "alerts produced: $((XLEN_AFTER - XLEN_BEFORE))"
```

Correlate in Postgres:

```sql
SELECT rule_id, COUNT(*) AS n
FROM alerts
WHERE created_at >= NOW() - INTERVAL '5 min'
GROUP BY rule_id
ORDER BY n DESC
LIMIT 10;
```

And cross-check the verdict distribution the ML models emit:

```sql
SELECT verdict, COUNT(*)
FROM verdicts
WHERE created_at >= NOW() - INTERVAL '5 min'
GROUP BY verdict;
```

If a Caldera operation completes but produces zero Wazuh alerts:
- Check auditd in the victim: `docker exec strix_victim1 auditctl -l` —
  should list the `execve` rule. If empty, the host audit netlink is
  already in use (see [LAB_BRINGUP.md §1](LAB_BRINGUP.md) auditd caveat).
- Check the ability actually ran: `curl .../operations/$OP_ID | jq '.chain[] | {ability:.ability.name, status}'` — status 0 = success, non-zero = failed-to-execute.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `400 planner not found` when POSTing an operation | Fetch `planner.id` live — value changes between Caldera versions. See §4.3. |
| Abilities show status `-3` (untrusted) on victims | Sandcat lost contact; restart the victim container or check `docker logs strix_victim1` |
| Operation stuck in `running` with empty chain | No agents in group `red`. Check Caldera Agents tab + victim `CALDERA_GROUP` env var |
| Abilities with platform `windows` silently skipped | Expected — stockpile mixes platforms; planner filters to Linux at runtime |
| `base64jumble` obfuscator breaks the ability | Some abilities are shell-fragment sensitive. Fall back to `plain-text` or `base64` |
| Kill-chain in STRIX never advances past RECONNAISSANCE | The GNN needs multiple tactics in one operation — use **Thief** or a `buckets` planner, not single-tactic adversaries |

---

## What to read next

- **Full lab bring-up** — [LAB_BRINGUP.md](LAB_BRINGUP.md)
- **What features each Wazuh field feeds** — [WAZUH_MAPPING.md](WAZUH_MAPPING.md)
- **Adversary YAML format** — Caldera repo: `plugins/stockpile/data/adversaries/*.yml`
- **Ability YAML format** — Caldera repo: `plugins/stockpile/data/abilities/<tactic>/*.yml`
- **Official Caldera docs** — https://caldera.readthedocs.io
