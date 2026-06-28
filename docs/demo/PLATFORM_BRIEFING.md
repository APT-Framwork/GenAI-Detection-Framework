# CAVIX Platform — Pre-Demo Briefing

Everything the jury should understand **before** the live demo begins. This
is the explanatory layer: what the lab is, how Caldera drives it, how
telemetry flows, how chains are built, what each ML model does, where the
honest limitations are.

Companion document to [JURY_DEMO_SCRIPT.md](./JURY_DEMO_SCRIPT.md).

---

## 1. What CAVIX is — in one paragraph

CAVIX is an AI-driven Security Operations Center (SOC) platform that
ingests raw host telemetry, reconstructs multi-step kill chains in real
time, scores each event with an ensemble of five neural models, and uses a
reinforcement-learning agent (wrapped in safety gates) to decide whether
and how to intervene. The whole stack runs on a contained lab with two
Linux victims attacked by a real adversary-emulation tool — **MITRE
Caldera** — producing genuine MITRE ATT&CK telemetry, not synthetic data.

The web platform is the SOC analyst's primary console; the mobile app is a
remote-paging channel for high-severity events.

---

## 2. The lab environment

### 2.1 Containers

The lab runs as a Docker Compose stack with two Docker networks:

```
strix_lab_net          (the attack range)
strix_platform_net     (the CAVIX platform itself)
```

**On `strix_lab_net`** (where the attack happens):

| Container | Image | Role |
|---|---|---|
| `strix_caldera` | `caldera:latest` | MITRE Caldera C2 server (web UI on :8888) |
| `strix_attacker` | `strix/attacker:lab` | Host running external recon (T1595 SSH probes) |
| `strix_victim1` | Ubuntu + Sandcat agent + auditd + wazuh-agent | Target 1 |
| `strix_victim2` | Ubuntu + Sandcat agent + auditd + wazuh-agent | Target 2 |
| `strix_wazuh_manager` | `wazuh/wazuh-manager:4.9.2` | Decodes agent events into Wazuh alerts |
| `strix_filebeat` | `filebeat:8.15.3` | Tails `alerts.json` and ships to Redis |

**On `strix_platform_net`** (the SOC platform):

| Container | Image | Role |
|---|---|---|
| `strix_postgres` | `timescaledb:2.17.2-pg16` | Time-series + relational store |
| `strix_redis` | `redis:7-alpine` | Stream + cache |

**On the host** (via `honcho -f Procfile.host`):

| Process | Role |
|---|---|
| `api` | FastAPI on :8000 — REST + SSE |
| `wazuh_bridge` | Drains `strix:alerts:raw:list` → Redis stream |
| `normalizer` | Stream → feature extraction (55-d vector) |
| `inference` | Runs all 5 models per event |
| `verdicts_writer` | Writes detections + DQN actions + opens/closes chains |
| `arq` | Background jobs (cleanups, periodic refreshes) |
| `demo_isolation` | Applies ISOLATE_HOST actions to victims |
| `intel_feeds` | OTX/MISP feed ingestion |
| `web` | Next.js on :5600 |

### 2.2 Why a contained lab is methodologically valid

The jury may ask why we don't run this against "real" production traffic.
The answer has three parts:

1. **The data flow is production-equivalent.** Auditd, Wazuh, Filebeat,
   Redis, Postgres are exactly what you'd see in a real SOC. No part of
   the pipeline is mocked or simplified.
2. **MITRE techniques are real.** Caldera executes actual T1595, T1543,
   T1486 commands. These are bit-identical to what a real attacker would
   run.
3. **Ground truth is available.** A contained lab is the only environment
   where we can label every alert as benign or malicious with certainty —
   essential for measuring false-positive rates and recalibrating models.

The trade-off is **scale**: 2 victims is not 2,000. We address this by
showing that the ingestion pipeline shards horizontally
(`INFERENCE_SHARD_ID`/`INFERENCE_NUM_SHARDS`) — but we don't claim to have
demonstrated production scale.

---

## 3. MITRE Caldera — how it works

Caldera is MITRE's open-source adversary-emulation platform. It exists
specifically so that defenders can test their detection and response
against the techniques real adversaries use, in a controlled and repeatable
way.

### 3.1 Anatomy

| Concept | What it is |
|---|---|
| **Server** | The Caldera process (`strix_caldera:8888`) — web UI, REST API, knowledge base |
| **Agent (Sandcat)** | A small binary the server deploys to each target host. The agent is the C2 channel — it polls the server for instructions |
| **Ability** | One scripted action implementing one MITRE technique. E.g. ability `T1057-process-listing` runs `ps -ef` on the target |
| **Adversary** | A curated *ordered list* of abilities. E.g. the "Stowaway" adversary chains 5–6 persistence abilities (T1136 + T1098 + T1037 + T1543.002 + T1053.003) |
| **Operation** | An execution instance: pick an adversary, pick target hosts, pick a planner, kick it off |
| **Planner** | The decision logic that picks the next ability to run. We use the default "atomic" planner — runs each ability in sequence |
| **Stockpile** | The bundled library of community-contributed abilities + adversaries |

### 3.2 What our runner does

[run_full_simulation.py](../../infra/simulation/scripts/run_full_simulation.py)
walks Caldera through 10 tactic groups, mapped to specific adversaries:

| # | Tactic | MITRE ID | Caldera adversary | Notes |
|---|---|---|---|---|
| 1 | Reconnaissance | TA0043 | (custom — not Caldera) | SSH probe burst from `strix_attacker` → T1595 |
| 2 | Discovery | TA0007 | Discovery / Enumerator | `whoami`, `ps`, `id`, `ls /etc/passwd` etc. |
| 3 | Defense Evasion | TA0005 | Defense Evasion / Undercover | log clearing, T1070.003/004 |
| 4 | Persistence | TA0003 | Stowaway | cron, systemd, .bashrc backdoors |
| 5 | Privilege Escalation | TA0004 | Privileged Operations | sudo abuse, SUID hunt |
| 6 | Credential Access | TA0006 | Brute Force | brute, `/etc/shadow` read |
| 7 | Lateral Movement | TA0008 | Lateral Movement (SSH) | SSH pivot between victims |
| 8 | Collection | TA0009 | Collection / Thief | stages files under `/tmp/staged` |
| 9 | Exfiltration | TA0010 | Advanced Thief via FTP | FTP upload (link fails — no FTP server on lab — still produces audit signal) |
| 10 | Impact | TA0040 | Ransack | destructive ops, scoped to `/tmp` |

Each tactic = 1 Caldera operation, ~37–127 seconds depending on link count.

### 3.3 Caldera limitations (be candid about these)

| Limitation | Reality | How we work around it |
|---|---|---|
| **No real Weaponization / Delivery phase** | The Sandcat agent is pre-implanted; Caldera assumes initial access already happened | The CKC stage 2 (Weaponization) maps to "Defense Evasion" as a host-telemetry proxy |
| **C2 is implicit** | The Sandcat poll *is* the C2 channel; there's no separate C2 ability | Stage 6 (C2) maps to "Persistence" — keeps the channel warm, similar audit signature |
| **Some abilities fail (rc ≠ 0)** | E.g. FTP exfil fails when no FTP server exists on the lab net | Failures **still produce audit signals** because the syscalls fired — the auditd record exists regardless of exit code |
| **Abilities are MITRE-mapped, not stealthy** | They run commands as visibly as possible to *be detected* | Acceptable: we're testing detection, not red-team evasion |
| **Stockpile ages** | Some stockpile abilities don't target newer kernels well | We patched ~3 abilities for our Ubuntu version (in `infra/simulation/caldera/`) |

---

## 4. Telemetry & ingestion pipeline

The data path, end-to-end:

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ON EACH VICTIM                                                          │
│                                                                          │
│  syscall → auditd (kernel) ──→ /var/log/audit/audit.log                  │
│                                       │                                  │
│  wazuh-agent reads ─────────────────  ┘                                  │
│       │                                                                  │
│       └── encrypted → wazuh_manager (decoder + rule engine)              │
└──────────────────────────────────────────────────────────────────────────┘
                       │
                       ▼
       /var/ossec/logs/alerts/alerts.json   (JSONL, one alert per line)
                       │
              Filebeat tails ─────────────────┐
                                              ▼
              Redis LIST  strix:alerts:raw:list  (Filebeat can't write streams)
                                              │
              wazuh_bridge worker BLPOPs ─────┘
                       │
                       ▼
              Redis STREAM  wazuh:alerts  (replayable, consumer-grouped)
                       │
              normalizer worker reads ─────────┐
                       │                       │
                       ▼                       │
              Postgres `alerts` table          │
                                               │
                       ┌───────────────────────┘
                       │
                       ▼
              inference worker (the 5 models)
                       │
                       ▼
              Per-event verdict on Redis stream  inference:verdicts
                       │
                       ▼
              verdicts_writer worker
                       │
                       ├─→ Postgres `detections`     (per-event ML scores)
                       ├─→ Postgres `attack_chains`  (open/continue/close)
                       └─→ Postgres `dqn_actions`    (the response decision)
                                               │
                                               ▼
                                        Web SSE + Mobile Push
```

### 4.1 Why this many hops?

The jury will ask "why not one queue?" The honest answer:

- **Filebeat → Redis LIST**: Filebeat's Redis output supports `list` and
  `channel` only — not Streams. Rather than running Logstash just to
  convert, we wrote a 30-line bridge worker.
- **LIST → STREAM**: Streams give us consumer groups (replay, sharding,
  backpressure). The bridge converts.
- **STREAM → normalizer → inference → verdicts**: Three workers because
  feature extraction (CPU-heavy), inference (GPU/CPU-heavy), and writes
  (DB-heavy) have different scaling characteristics. Separating them
  means inference can shard independently.

### 4.2 What ends up in Postgres

Five core tables:

| Table | Rows per event | Why |
|---|---|---|
| `alerts` | 1 | The raw Wazuh alert (rule, technique tags, host, timestamp) |
| `detections` | 1 | All 5 model outputs + state vector + transformer probabilities |
| `attack_chains` | 0–1 | New row only when this event **opens** a chain |
| `dqn_actions` | 0–1 | Only when the chain is open (skipped events run AE+VAE for telemetry but no DQN) |

Postgres is **TimescaleDB** — the `detections` and `dqn_actions` tables
are hypertables, time-partitioned by `occurred_at`. Lets us query recent
data without scanning history.

---

## 5. Attack-chain reconstruction

This is one of the system's most important pieces and worth understanding
in detail before the demo.

### 5.1 The lifecycle

An event arrives. The chain decider
([sequence.py](../../apps/api/src/strix_api/core/sequence.py#L79)) does one
of three things:

```
┌──────────────────────────────────────────────────────────────┐
│  Is there an OPEN chain for this host?                       │
│                                                              │
│  NO  ──→  GNN node-risk ≥ 0.7743?                            │
│           YES → OPEN_NEW (mint a new chain_id)               │
│           NO  → SKIP_BENIGN (score AE+VAE for telemetry,     │
│                              don't run Transformer/DQN)      │
│                                                              │
│  YES ──→  Was the prior step ≥ ESCALATE?                     │
│           YES → close the old chain, OPEN_NEW                │
│                                                              │
│           Has session been idle > 120 min?                   │
│           YES → close on IDLE_TIMEOUT, OPEN_NEW              │
│                                                              │
│           step_count ≥ 50?                                   │
│           YES → close on MAX_STEPS, OPEN_NEW                 │
│                                                              │
│           Otherwise → CONTINUE existing chain                │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 Why GNN-only gates the open decision

There's a subtle but important point: the chain-open gate uses **GNN
node-risk only**. AE, VAE, and Transformer are computed and surfaced in
the UI, but they don't participate in chain-open decisions.

Why? Because — as documented in
[sequence.py:7-12](../../apps/api/src/strix_api/core/sequence.py#L7-L12)
and demonstrated empirically yesterday — AE/VAE/Transformer have an
**inverted malice signal on lab data**. They were trained on a different
deployment's alert distribution; on our lab they fire higher on benign
shell activity than on Caldera attacks. The GNN is the only model that
was trained on lab data, so it's the only one trusted for the chain-open
gate.

We recalibrated the VAE this week (Beta-VAE Top 25 lab-refit, AUC 0.42 →
0.58 — directionally correct now). AE and Transformer encoder retraining
remain documented future work.

### 5.3 Chain closure

A chain closes for one of three reasons:

| Reason | Meaning |
|---|---|
| `INTERVENTION` | DQN took an action ≥ ESCALATE — the chain is "responded to" |
| `IDLE_TIMEOUT` | 120 min with no new events on this host |
| `MAX_STEPS` | 50 events accumulated — we cap to keep state bounded |

### 5.4 CKC stages

Every event has a Cyber Kill Chain stage (0–7):

```
0  BENIGN                 (default)
1  RECONNAISSANCE
2  WEAPONIZATION
3  DELIVERY
4  EXPLOITATION
5  INSTALLATION           ← the "is this a real compromise?" threshold
6  COMMAND_AND_CONTROL
7  ACTIONS_ON_OBJECTIVES  ← endpoint — game over for the defender
```

The stage is derived from the alert's MITRE technique via
[mitre_catalog.py](../../apps/api/src/strix_api/core/mitre_catalog.py). A
chain's `max_ckc_stage` is the highest stage it ever reached.

---

## 6. The five ML models

Quick reference. Full details are in
[docs/web/MODELS_REFERENCE.md](../web/MODELS_REFERENCE.md) if it exists.

| Model | Type | Input | Output | Trained on |
|---|---|---|---|---|
| **Autoencoder (AE)** | Regularized AE, 55 → 64 → 55 | 55-d feature vector | `recon_error` + `anomaly_score` | combined_dataset_final.xlsx (115K Wazuh alerts, *different* deployment) |
| **VAE** | Beta-VAE, 55 → μ,σ → 55 | 55-d feature vector | `recon_loss` → calibrated `malicious_prob` | Same source; calibrator refit on lab data this week |
| **GNN** | GraphSAGE, 1-hop neighborhood | host graph + per-host risk vector | `node_risk`, `neighbor_risk`, `risk_growth` | **Lab data** — only model trained on the lab distribution |
| **Transformer** | 8-class CKC predictor | sequence of chain events | 8-d softmax over next CKC stage + argmax + confidence | combined_dataset_final.xlsx |
| **DQN** | Q-learning, 13-d state, 5 actions | state vector | Q-values per action + argmax action | Custom training simulator (not the lab) |

### 6.1 The honest section: signal inversion

AE, VAE, and Transformer all show **inverted malice signals on lab data**:

| Model | Pre-refit MAL p50 | Pre-refit BEN p50 | Inverted? |
|---|---:|---:|:-:|
| AE anomaly score | 0.07 | 0.41 | **Yes** (benign 5.7× higher) |
| VAE malicious prob (pre-refit) | 4.7% | 9.7% | **Yes** |
| VAE malicious prob (post-refit) | 47.7% | 10.6% | **No — fixed** |
| Transformer next-stage pred | BENIGN @ 67% conf on real attacks | — | **Yes** |
| GNN node-risk on attack events | 0.90 typical | <0.3 typical | **No — correct** |

Root cause is training distribution shift. The remediation arc:

1. **GNN**: trained on lab data → correct out of the box.
2. **VAE**: 1-D logistic-regression calibrator refit on JSONL-labeled
   lab data. AUC 0.42 → 0.58 (directionally correct but encoder signal is
   weak — full encoder retraining is the proper fix).
3. **AE + Transformer**: documented future work. Same calibration pipeline
   should fix direction; encoder retraining is the deeper fix.

**Why doesn't this break the system?** Because the chain-open gate uses
GNN-only, and the DQN's intervention actions are gated by stage-based
rules (see §7). The inverted signals show up in the UI as anomaly
diagnostics but don't drive critical decisions.

---

## 7. The STRIX Agent and the safety gates

This is the single most important architectural decision in the platform.
Expect it to be the focus of the hardest jury questions.

### 7.1 The DQN

The STRIX Agent is a Deep Q-Network. State: 13-d vector summarizing the
current event + chain history + model outputs. Actions: 5 discrete choices.

```
0  MONITOR          (lowest — no analyst attention)
1  LOW_ALERT        (visible on dashboard but no intervention)
2  ESCALATE         (page the analyst — intervention threshold)
3  ISOLATE_HOST     (cut the host's network)
4  BLOCK_USER_IP    (firewall the user's IP)
```

Trained on a custom simulator (not the lab) using PPO-style Q-learning
with a custom reward shape rewarding TP detection and penalizing FPs and
late detection.

### 7.2 Why the DQN alone isn't enough

When evaluated on lab data, the trained DQN exhibits two systematic
failures:

1. **Late-stage timidity.** At CKC stage 5+, `Q(ESCALATE)` is *negative*
   — the DQN actively prefers no-action over escalation. Concretely, at
   S5: Q(LOW_ALERT) = +8.67, Q(ESCALATE) = −3.64. Without intervention
   the DQN would do nothing while the chain reaches Installation.
2. **OOD aggression.** At stage 0 on benign noise events,
   Q(BLOCK_USER_IP) = +6.59 is the **max action**. The DQN's natural
   pick on saturated-VAE benign noise is to BLOCK_USER_IP — a 100%
   false-positive intervention.

These aren't theoretical. We measured them directly from the trained
policy's Q-values on yesterday's 26K-action gated run.

### 7.3 The safety-gate ladder

To correct both failures, the inference worker wraps the DQN's argmax
in a 5-priority gate ladder before emitting the action:

| Priority | Gate | When it fires | Override |
|---|---|---|---|
| 1 | OOD abstain | AE recon-error > threshold | Force MONITOR |
| 2 | Q-margin abstain | Argmax Q − second-place Q < margin | Force MONITOR |
| 3 | Stage gate (ESCALATE) | CKC stage ≥ 5 | Force ESCALATE |
| 4 | Stage gate (ISOLATE) | CKC stage ≥ 6 + chain has spread | Force ISOLATE_HOST |
| 5 | Stage gate (BLOCK) | CKC stage ≥ 7 + external IP known | Force BLOCK_USER_IP |

The gates are controlled by `STRIX_DQN_GATES_ENABLED` (default true). Setting
it to `false` reverts to pure-DQN behavior — useful for ablation runs.

### 7.4 The empirical justification

Same 10-tactic simulation, same time budget, gates flipped:

| Metric | Gates ON | Gates OFF (pure RL) |
|---|---:|---:|
| Confident interventions (ESCALATE+BLOCK+ISOLATE) | 8 | 29 |
| ...at stage 0 (benign noise) | 0 | 22 |
| ...at stage 5+ (real attacks) | 8 | 0 |
| TP/FP ratio of interventions | ∞ | 0 |
| Max chain stage reached | 5 | 4 (chains die early to FPs) |

This is the headline result for the thesis: **the gates aren't decorative,
they're load-bearing**. Without them, the system is worse than no policy
at all — it's worse than gates-without-DQN, and worse than gates-only.

### 7.5 Framing for the jury

The defensible architectural claim is:

> "ML proposes, policy gates dispose."

The DQN is the soft prior — it ranks actions on the regions of state space
where the gates are silent. The gates encode the hard SOC rules the policy
shouldn't be allowed to override: compliance, irreversibility, audit. This
is the same separation real SOCs use between SOAR runbooks (hard rules)
and analyst judgement (soft prior).

The claim is **not** "the DQN learned optimal response" — that would be
dishonest given the Q-table evidence. The claim is "the DQN, gated, beats
both the ungated DQN and the no-DQN-rules-only system."

---

## 8. Simulation modes

The runner ([lab_simulate.sh](../../infra/scripts/lab_simulate.sh)) supports
several modes:

| Mode | Command | Use for |
|---|---|---|
| **Generic 10-tactic** | `bash infra/scripts/lab_simulate.sh` | Empirical baselines, scientific posture |
| **APT profile** | `--apt APT29` (or APT28, APT41, Turla) | "What does a real APT look like" narrative |
| **Curated non-monotonic** | `--non-monotonic` | Demo / screenshots — hand-tuned to make the dashboard light up. Walk: `[1,3,4,5,1,3,4,5,7]` |
| **Custom stage sequence** | `--ckc-stages "1,3,4,1,3,4,1,4"` | Specific story (e.g. "attacker stuck at exploit") |
| **Subset** | `--only Discovery,Persistence` | Fast iteration when testing a specific change |
| **Dry-run** | `--dry-run` | Plan-only, no Caldera ops launched |
| **Report only** | `--report-only` | Show current platform state, no simulation |

`jury_demo.sh` is a higher-level wrapper that also brings up Docker +
honcho before running the simulation. Use `bash jury_demo.sh
--non-monotonic` for the actual defense.

---

## 9. Known limitations & future work

Honesty is defensible. Pretending these don't exist is not.

### 9.1 Model limitations

| Limitation | Status | Future work |
|---|---|---|
| AE encoder learned wrong "normal" cluster on lab data | Inverted; surfaced as anomaly diagnostic only, not gating | Fine-tune encoder on lab-labeled data (15,766 rows already prepared in `/tmp/strix_calib/labeled.csv`) |
| VAE encoder representations weak on lab distribution | Calibrator refit fixes direction; AUC ceiling at 0.58 | Same — encoder fine-tune is the proper fix |
| Transformer next-stage pred still inverted | Documented; surfaced in UI but not in gates | Multi-class calibration head refit (~1 day) |
| DQN trained on simulator, not lab | Gates handle the failure modes | Retrain DQN on lab trajectories with revised reward shaping |

### 9.2 Lab limitations

| Limitation | Reality |
|---|---|
| 2 victims, not production scale | Pipeline shards horizontally — design is scale-aware, not scale-proven |
| No real Internet egress | Caldera Exfiltration ability fails (link rc≠0) — still produces audit signal |
| No iOS push | Backend speaks APNs via Expo Push relay; blocked on Apple Developer enrollment |
| Honcho restart fragility | Documented operational bug — manual restart sometimes needed after host reboot |

### 9.3 Out of scope (explicitly)

- **Adversarial ML.** A motivated attacker could craft commands that
  evade specific model signatures. We don't claim adversarial robustness;
  the ensemble + chain reconstruction makes single-event evasion harder
  but doesn't make it impossible.
- **Encrypted-traffic analysis.** We work from host telemetry (auditd),
  not network capture. Encrypted traffic is invisible at this layer by
  design.
- **Insider threats.** The threat model is external attackers using MITRE
  TTPs. Privileged insiders with legitimate credentials are out of scope.

---

## 10. Quick reference card

For your sticky-note moment during the defense:

```
Pipeline:    auditd → wazuh → filebeat → redis(list) → bridge → redis(stream)
             → normalizer → inference → verdicts_writer → pg (alerts, detections,
             attack_chains, dqn_actions) → SSE → web + mobile

Lab:         1 attacker + 2 victims + caldera + wazuh, all in Docker

Caldera:     Server (:8888) + Sandcat agent on each victim. 10 tactics walked
             via the runner. Real MITRE techniques.

Chain gate:  GNN-only, threshold 0.7743 node-risk. AE/VAE/Transformer are
             inverted on lab — surfaced for telemetry, not for gating.

DQN:         5 actions (MONITOR, LOW_ALERT, ESCALATE, ISOLATE_HOST,
             BLOCK_USER_IP). Argmax wrapped in 5-priority safety-gate ladder.
             Empirical: gates ON = 100% TP interventions; gates OFF = 100% FP.

Stages:      CKC 0–7. Intervention threshold = stage 5 (Installation).

Postgres:    TimescaleDB hypertables for detections + dqn_actions.

Web:         Next.js on :5600. Live updates via SSE.
Mobile:      Expo dev build. Push via Expo → FCM → Android.
```

---

This briefing exists so the jury can ask informed questions during and
after the demo. The companion document
[JURY_DEMO_SCRIPT.md](./JURY_DEMO_SCRIPT.md) is the live walkthrough.
