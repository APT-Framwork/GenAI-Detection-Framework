# Conversation log — building the platform real-time simulation runner

**Date:** 2026-04-29
**Branch:** `Platforme`
**Outcome:** A self-contained Python orchestrator + bash wrapper that drives Caldera through 9 paper-aligned MITRE ATT&CK tactics (and 4 APT-group emulation chains) against the lab's sandcat agents, monitors the platform end-to-end (Wazuh → Redis → Postgres detections / attack_chains / dqn_actions), and prints a per-tactic + final report card.

---

## 1. User: "summary of the last conversation — can we say the platform is working perfectly?"

The user asked me to read [`docs/SESSION_LOG_CALDERA_AUDIT_PIPELINE.md`](SESSION_LOG_CALDERA_AUDIT_PIPELINE.md) (the previous session's record of fixing auditd, filebeat, and agent enrollment to get Caldera→detections flowing), then assess whether the platform was "working perfectly in this simulation."

### Assistant response

Pipeline works end-to-end, but **"perfectly" overstates it**. Honest read:

**What the run proved:**
- ✅ Ingest path Caldera → host auditd → Wazuh agent → manager → Filebeat → Redis → normalizer → Postgres is unbroken
- ✅ All 5 ML models execute on real data (AE / VAE / Transformer / GNN / DQN), not placeholders
- ✅ Attack-chain stitching works (451 chains, CKC stages observed)
- ✅ DQN policy outputs realistic action mixes including approval-gated ones

**Caveats not to gloss over:**
1. **Only 1 of the paper's 12 tactics was exercised** (Discovery — T1033, T1087.001, T1057). Defense Evasion, Persistence, Priv-Esc, Cred Access, Lateral Movement, Collection, Exfil, Impact, Initial Access — all still untested.
2. **31,273 Wazuh alerts → 31,999 stream entries → 589 DB alerts.** ~1.8% landing in Postgres. Some intended dedup/batching, but the ratio deserves a deliberate check.
3. **`alerts.raw_jsonb = {}`, `rule_id = NULL`, `decoder_name = NULL`** by design per `verdicts_writer.py:8-10` — skeleton FK target until Phase 5+. The `alerts` table being "empty" is intentional; the real ML output is in `detections`.
4. **Max CKC stage = 3.** Expected with only Discovery firing — but the chain model hasn't been stressed past mid-kill-chain.
5. **2 of 7 hosts active.** Fine for a smoke run, not representative load.

**Fair claim:** "Pipeline is operational and produces paper-aligned detections under a Discovery-only Caldera workload." That's defensible. "Perfect" requires firing the remaining adversaries, confirming detections stay 1:1, hitting higher CKC stages, and explaining the 31k→589 ratio.

---

## 2. User: "i want a full complete script which executes all needed tactics, techniques, adversaries… we want to do a real-time simulation, logs capturing and send them to the platform to test the models capabilities in real time"

### Assistant: design + build

Plan before coding:
- **One Python script** — `infra/simulation/scripts/run_full_simulation.py`, stdlib only (`urllib`, `subprocess`, `json`, `argparse`) so it runs without venv activation
- **Thin bash wrapper** — `infra/scripts/lab_simulate.sh`, mirrors `lab_up.sh` style
- **Coverage** — 9 paper tactics with stockpile→ad-hoc fallback (auto-builds adversary from abilities matching paper technique IDs when the named profile isn't installed)
- **Real-time monitoring** — per-tactic before/after deltas (Wazuh alerts, Redis xlen, Postgres alerts/detections/chains/DQN), final report card
- **Pre-flight gates** — catches the exact failure modes from the prior session (host auditd missing rules, agents not Active, normalizer dropping for missing `agent.id`, Filebeat down)

### Files created

| Path | Role |
|---|---|
| [`infra/simulation/scripts/run_full_simulation.py`](../infra/simulation/scripts/run_full_simulation.py) | Python orchestrator |
| [`infra/scripts/lab_simulate.sh`](../infra/scripts/lab_simulate.sh) | Bash wrapper (loads `apps/api/.env`, picks venv) |

### Bugs caught during smoke testing (and fixed)

1. **Fuzzy substring match on adversary names** pulled `Lateral Movement - Certutil` (Windows-only) for the Linux Lateral Movement tactic. Removed substring matching entirely — exact-name only, then fall through to platform-aware ad-hoc construction.
2. **Stale-agent calculation wrong** — `time.mktime()` treats Caldera's UTC `last_seen` as local time, so all agents looked stale. Switched to `calendar.timegm()`.
3. **`/etc/audit/rules.d/strix.rules` is root-only** — preflight couldn't read it. Replaced with a check for `audit-wazuh-x` markers in `/var/log/audit/audit.log` (readable inside the bind-mounted victim).
4. **`subprocess.run(text=True)`** crashed on `UnicodeDecodeError` because redis-cli's XREVRANGE output is msgpack-binary. Switched to bytes + `errors="replace"` decode.
5. **`XRANGE strix:alerts:raw + - COUNT 1`** returns nothing (start > end). Switched to `XREVRANGE` for "latest entry first".
6. **Filebeat agent-block sanity check** was substring-searching for `"agent":{` in msgpack-encoded bytes — never matched. Switched to looking for a victim agent name (`victim1`/`victim2`) which only Wazuh's `agent.name` would carry.

### What `--list` revealed about the live stockpile

```
Discovery, Defense Evasion, Stowaway, Collection, Advanced Thief via FTP, Ransack
   → resolve via stockpile (exact name)

Privileged Operations, Credential Access, Lateral Movement (SSH)
   → not in stockpile, fall back to platform-aware ad-hoc construction
```

The plan's `stockpile_names` list was updated to use names that actually exist (`Defense Evasion`, `Stowaway`) rather than guessed ones (`Avoid logs`, `Hunter`).

### Final preflight output (all green)

```
✓ strix_caldera / strix_postgres / strix_redis / strix_wazuh_manager / strix_filebeat running
✓ 2/22 agents in group 'red' fresh (paws: jrnqcx, bpwkvu)
✓ audit-wazuh-x events present in /var/log/audit/audit.log (last 2k lines: 385 hits)
✓ 3 Wazuh agents Active
✓ redis xlen=75965  alerts=589  detections=589  chains=451
✓ redis entries carry Wazuh agent.name — filebeat config is correct
```

### Memory saved

[`memory/reference_lab_simulate_runner.md`](/home/yacine/.claude/projects/-home-yacine-Desktop-GenAI-Detection-Framework/memory/reference_lab_simulate_runner.md) so future agents pick up the runner without re-discovering it.

---

## 3. User: "i want a .md file in `infra/simulation/scripts` which lists all tactics that are going to be simulated through the script, with their techniques as well — the textual and numerical names"

### Assistant: write `simulate.md`

Created [`infra/simulation/scripts/simulate.md`](../infra/simulation/scripts/simulate.md) with:

- **Per-tactic section** for each of the 9 auto-runnable tactics:
  - `TA####` paper code
  - Brief paper context + which platform features the tactic exercises
  - Table of `T####` IDs and full MITRE ATT&CK Enterprise textual names
  - Adversary resolution chain (stockpile preferred → ad-hoc fallback)
- **Cross-cutting section** — `T1059.004 Unix Shell` (implicit on every op; obfuscator notes)
- **Not auto-runnable section** — TA0001 Initial Access (T1190 Apache Struts needs vulhub), TA0043 Reconnaissance (pre-implant; out of scope), TA0011 C2 (sandcat *is* the C2 channel)
- **Adversary resolution algorithm** — exact-name lookup → linux-only ad-hoc construction → skip with warning
- **Postgres write contract** — what each fired tactic deposits in `alerts` / `detections` / `attack_chains` / `dqn_actions`
- **Quick command reference** at the bottom

Total: ~30 distinct techniques across the 9 tactics, plus T1059.004 cross-cutting.

---

## 4. User: "add also the apt groups that will be simulated"

### Assistant: extend script + doc

Read [`docs/CALDERA_MITRE_SIMULATION_GUIDE.md` §6](CALDERA_MITRE_SIMULATION_GUIDE.md) for the four APT chains (APT41, APT28, APT29, Turla) the paper authors emulated, then **wired them into actual execution** so "will be simulated" is true.

### Script changes

Added `APTGroup` dataclass + `APT_GROUPS` dict at module level:

| Group | Default obfuscator | Tactic chain |
|---|---|---|
| **APT41** | plain-text | Persistence → Privilege Escalation → Defense Evasion → Discovery → Collection → Exfiltration |
| **APT28** | plain-text | Discovery → Privilege Escalation → Defense Evasion → Collection → Exfiltration |
| **APT29** | **base64jumble** | Persistence → Defense Evasion → Lateral Movement → Privilege Escalation → Discovery |
| **Turla** | plain-text | Persistence → Privilege Escalation → Credential Access → Discovery → Collection → Defense Evasion |

Each chain reuses the existing per-tactic firing logic — just reordered to match how the group operates in the wild. Steps that need manual setup (Initial Access, Reconnaissance, C2 contact-switching) are dropped from each chain and noted in the `notes` field.

New flags:
- `--list-apts` — print all APT chains
- `--apt <APT41|APT28|APT29|Turla|all>` — emulate one group (or all four back-to-back)

When `--apt APT29` is passed, the script auto-applies the `base64jumble` obfuscator (Cozy Bear's stealth signature).

### Doc changes — `simulate.md`

Added **"APT-group emulation (4)"** section between cross-cutting tactics and not-auto-runnable. Each group has:
- Paper quote + attribution
- Step-by-step tactic→technique table (numerical + textual MITRE names)
- Default obfuscator
- Explicit list of what was dropped from the paper's full chain (and why)

Closing subsection — **why ordering matters for the platform:**
- `attack_chains.max_ckc_stage` rewards Discovery → … → Exfiltration progression. Random order tops out earlier.
- The GNN sees a coherent host-graph evolution (one APT chain == one logical campaign per victim).
- The Transformer kill-chain predictor has a real labelled trajectory instead of an unordered bag.

So `--apt APT41` and the same set of tactics fired alphabetically produce **different** ML outputs even with identical Caldera abilities — order is part of the signal.

### Verified via `--dry-run`

```
APT chain — APT41:  Persistence → Privilege Escalation → Defense Evasion → Discovery → Collection → Exfiltration
APT chain — APT28:  Discovery → Privilege Escalation → Defense Evasion → Collection → Exfiltration
APT chain — APT29:  Persistence → Defense Evasion → Lateral Movement → Privilege Escalation → Discovery
APT chain — Turla:  Persistence → Privilege Escalation → Credential Access → Discovery → Collection → Defense Evasion
```

`--apt all` chains all four sequentially (~45 min wallclock at default budget/dwell).

---

## 5. User: "ok so now i can start the script and open the platform to see the results right?"

### Assistant: cleanest first-run recipe

**Step 1 — open the platform UI:** http://localhost:5600 (admin login `admin@strix.local` / `changeme`).

Two views to keep open:
- **Attack Analysis** — live attack chains; CKC stages advance as tactics fire
- **Vigilance Feed** (SSE) — every detection appears as it lands

**Step 2 — run a single APT first, not `--apt all`:**

```bash
bash infra/scripts/lab_simulate.sh --apt APT41
```

Why APT41 first: 6 tactics in a coherent chain (~12 min wallclock), produces a real campaign-shaped trace in `attack_chains` rather than 9 unrelated ops. `--apt all` commits to ~45 min before the final report.

**Expected timeline:**

| Time | Where | What |
|---|---|---|
| 0–10 s | terminal | preflight → green → `EXECUTION PLAN` → `TACTIC: Persistence` |
| 10–90 s | terminal | `links=N state=running latest: …` lines as Caldera fires |
| 30–60 s | UI Vigilance Feed | first new detections appear (AE/VAE scores, DQN action) |
| 60 s+ | UI Attack Analysis | a chain on victim1 / victim2 starts climbing CKC stages |
| ~12 min | terminal | `FINAL REPORT` with per-tactic delta + DQN mix + CKC histogram |

**Optional second-terminal live tail** (filtered to rule id + MITRE technique):

```bash
docker exec -it strix_wazuh_manager tail -f /var/ossec/logs/alerts/alerts.json | \
  grep --line-buffered -oE '"rule":\{"id":"[^"]+","level":[0-9]+|technique[":]+T[0-9]+[.0-9]*'
```

---

## 6. Key takeaways

1. **The runner is now the canonical real-time simulation entry point.** `bash infra/scripts/lab_simulate.sh [...]` covers single tactic, multiple tactics, and APT-group chains.
2. **Ordering is part of the signal.** Tactic order matters for CKC progression, GNN host-graph coherence, and the Transformer's kill-chain predictor. APT mode exists because of this.
3. **Stockpile names ≠ paper tactics.** Six of nine tactics resolve to a stockpile adversary; three fall back to platform-aware ad-hoc construction from technique IDs.
4. **Three tactics genuinely can't be auto-run** — TA0001 (vulhub container needed), TA0043 (pre-implant, Caldera is post-implant), TA0011 (sandcat IS the C2 channel).
5. **The runner's preflight is a regression suite for the lab itself.** Each gate corresponds to a specific failure mode caught in the prior session.

---

## 7. Files touched in this conversation

| Path | Change |
|---|---|
| [`infra/simulation/scripts/run_full_simulation.py`](../infra/simulation/scripts/run_full_simulation.py) | New — orchestrator (~750 lines, stdlib only). Pre-flight, Caldera client, ad-hoc adversary builder, per-tactic runner with before/after snapshots, APT-group mode, final report. |
| [`infra/scripts/lab_simulate.sh`](../infra/scripts/lab_simulate.sh) | New — bash wrapper, sources `apps/api/.env`, picks venv python. |
| [`infra/simulation/scripts/simulate.md`](../infra/simulation/scripts/simulate.md) | New — full tactic+technique+APT-group reference. |
| [`memory/reference_lab_simulate_runner.md`](/home/yacine/.claude/projects/-home-yacine-Desktop-GenAI-Detection-Framework/memory/reference_lab_simulate_runner.md) | New — auto-memory pointer for future sessions. |
| [`memory/MEMORY.md`](/home/yacine/.claude/projects/-home-yacine-Desktop-GenAI-Detection-Framework/memory/MEMORY.md) | Updated — added pointer to the new memory above. |

---

## 8. What to read next

- **For running:** [`infra/simulation/scripts/simulate.md`](../infra/simulation/scripts/simulate.md) — full tactic + APT reference
- **For debugging the pipeline if something breaks:** [`docs/SESSION_LOG_CALDERA_AUDIT_PIPELINE.md`](SESSION_LOG_CALDERA_AUDIT_PIPELINE.md) — the prior session that fixed auditd/filebeat/agent-enrollment
- **For Caldera details:** [`docs/CALDERA_PLAYBOOK.md`](CALDERA_PLAYBOOK.md) and [`docs/CALDERA_MITRE_SIMULATION_GUIDE.md`](CALDERA_MITRE_SIMULATION_GUIDE.md)
