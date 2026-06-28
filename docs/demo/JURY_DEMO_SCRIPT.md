# CAVIX Jury Demo — Script

Complete walkthrough for the thesis defense. Built around a narrative arc
(follow-the-data, attack → detection → response), with talking points per
page and pre-empted jury questions. Designed for **~25 minutes web + ~3 min
mobile**.

---

## Pre-demo (do 15 min before jury arrives)

### Step 1 — Bring up everything with a CLEAN slate

```bash
bash jury_demo.sh stop                       # tear down anything stale
bash jury_demo.sh --non-monotonic            # bring up + curated walk
                                             # NOTE: NO --keep-state.
                                             # The default wipes the DB so the
                                             # dashboard shows only events from
                                             # the live demo, not history.
```

**⚠ Important: do not pass `--keep-state`.** That flag preserves every
chain, alert, and DQN action from earlier runs. The dashboard reads from
the DB — if there are 8 historical chains at S5, they'll show in the
STRIX Intervention Timeline *before the live simulation has produced
anything*, which looks confusing to a jury ("wait, you said this was
live?").

The default `CLEAN_STATE=1` behavior wipes:

```
psql TRUNCATE: attack_chains, detections, alerts, dqn_actions
redis DEL:     strix:stream:*, strix:sse:*, strix:features:*,
               session:*, strix:alerts:raw, strix:alerts:raw:list,
               strix:verdicts
```

It preserves the model artifacts (under `apps/models/`), the calibrator
pickle, the auth tables, threat-intel feeds, and the kill-switch — i.e.
everything that's structural, not the event stream.

### Step 2 — Open the right tabs

In this order, side by side if possible:

```
Tab 1: http://localhost:5600           (Dashboard — opens here)
Tab 2: http://localhost:5600/topology  (flip during setup talk)
Tab 3: http://localhost:5600/ai-engine (live inference panel)
Mobile: physical phone with dev build, screen mirrored if possible
```

### Step 3 — Verify

- SSE indicator **CONNECTED** green
- At least one chain in `/attack-analysis` with **stage ≥ 5** appearing
  *after* simulation start (not before — that's the cleanup point)
- Mobile app logged in, foregrounded

### Troubleshooting

| Symptom | Fix |
|---|---|
| Stale chains visible before sim produces events | You forgot to drop `--keep-state`. Stop and restart cleanly |
| `docker ps` shows <8 containers | `bash infra/scripts/lab_up.sh` — brings up missing pieces |
| `ps -ef \| grep honcho` returns nothing | `nohup honcho -f Procfile.host -e apps/api/.env start &` |
| Want to verify pipeline alive | `bash infra/scripts/lab_simulate.sh --report-only` |

### Manual cleanup (if stack is already up and you don't want to tear down)

Sometimes you've been iterating, the stack is healthy, and you just want
a clean event stream without restarting honcho. Run this snippet — it
mirrors what `CLEAN_STATE=1` does but doesn't touch the workers:

```bash
# 1. Wipe pg event tables
docker exec strix_postgres psql -U strix -d strix -c \
  "TRUNCATE attack_chains, detections, alerts, dqn_actions RESTART IDENTITY CASCADE;"

# 2. Wipe redis transient state
docker exec strix_redis sh -lc '
  for pat in "strix:stream:*" "strix:sse:*" "strix:features:*" "session:*"; do
    redis-cli --scan --pattern "$pat" | xargs -r redis-cli DEL >/dev/null
  done
  redis-cli DEL strix:alerts:raw strix:alerts:raw:list strix:verdicts >/dev/null
'

# 3. (Optional but recommended) bounce honcho to drop in-memory session state
#    held by the inference worker. Skip only if you're sure no chain is
#    mid-flight in worker memory.
pkill -f honcho && sleep 2 && nohup honcho -f Procfile.host -e apps/api/.env start &
```

Then trigger the live walk:

```bash
bash infra/scripts/lab_simulate.sh --non-monotonic
```

---

## Act 0 — Opening (90 seconds, before clicking anything)

**Stand back from the laptop. Talk to the jury, not the screen.**

> "What I'm going to show you is **CAVIX** — an AI-driven SOC platform that
> does three things rule-based SIEMs can't: (1) it reconstructs multi-step
> kill chains from raw host events, (2) it makes the response decision
> automatically using a trained reinforcement-learning agent, and (3) it
> does both in real time on real MITRE ATT&CK telemetry from a Caldera-driven
> lab.
>
> The demo has three parts: first I'll show the live system processing a
> real attack, then I'll show how an analyst would investigate and triage,
> then I'll show how that same analyst gets paged on their phone when
> they're not at their desk."

**Pre-empts**: "what is this", "how is it different", "is it real-time".

---

## Act 1 — The lab (Topology, ~2 min)

**Open `/topology`**

What's on screen: Simulation Topology panel (attacker → 2 victims → wazuh
manager) + GNN Victim Graph.

**Say:**
> "On the left is our lab — one Caldera attacker container running real
> MITRE techniques against two Linux victims. Auditd watches every syscall,
> Wazuh decodes them into alerts, and those alerts feed our ML pipeline.
> **Nothing here is mocked** — these are real T1595, T1543, T1486 techniques
> being executed against real machines.
>
> On the right is the GNN's view of the same network — each node is a host,
> edges are observed lateral-movement patterns. The GNN learns what 'normal'
> graph propagation looks like and flags anomalous spreading."

**Pre-empts**: "is the data real or synthetic" (real), "what does the GNN
do" (graph propagation), "how many hosts" (2 — production would scale; this
is the lab).

---

## Act 2 — What's watching (AI Engine, ~4 min)

**Click `MODEL MONITORING` (`/ai-engine`)**

This is the highest-density slide. Slow down here.

**Top KPI strip:**
> "Three composite metrics across the five models: **89% accuracy**, **0.87
> F1** — these are aggregate test-set numbers from the training notebooks,
> not live. To the right is the live SSE throughput — 500 inference verdicts
> per minute, every event scored by every model."

**Five Live Inference cards — point to each in turn:**

| Model | Say |
|---|---|
| **Autoencoder** | "Behavioral baseline. Trained on benign syscall patterns; high reconstruction error means 'I haven't seen this before'." |
| **VAE** | "Variational classifier. Outputs malicious probability. We recalibrated this model on lab-distribution data — I'll talk about that if asked." |
| **GNN** | "Graph propagation. Looks at the 1-hop neighborhood — is risk spreading?" |
| **Transformer** | "Temporal model. Given the chain so far, predicts the *next* CKC stage." |
| **STRIX Agent** | "The decision-maker. A DQN reinforcement-learning policy that consumes the four model outputs plus chain state and chooses one of five actions: MONITOR, LOW_ALERT, ESCALATE, ISOLATE_HOST, BLOCK_USER_IP." |

**Scroll to the Inference Stream table.**
> "Every row is one event being scored in real time. You can see the
> kill-chain stage on the left, the four model outputs in the middle, and
> the STRIX action on the right. Right now everything reads LOW_ALERT
> because the chain is at stage 4 Exploitation — the system has correctly
> determined evidence is still accumulating but no intervention is warranted
> yet."

**Anticipated Q&A:**
- *"Why five models, not one?"* → Each captures a different signal class:
  behavioral (AE), distributional (VAE), structural (GNN), temporal
  (Transformer), policy (DQN). Ensemble robustness — if one fails, others
  compensate.
- *"Why is the Transformer saying BENIGN on an attack?"* → Honest answer:
  training-distribution shift. AE/VAE/Transformer were trained on a
  different deployment's alerts; only the GNN was trained on lab data.
  We've recalibrated VAE; AE and Transformer encoder refit is documented
  future work.
- *"What's the F1 / AUC?"* → Composite 0.87 F1. Per-model is in the Active
  Models section below — click to expand.

---

## Act 3 — A kill chain forming (Dashboard → Attack Analysis, ~5 min)

**Click `DASHBOARD`.**

> "This is what the SOC analyst sees first thing in the morning. Threat
> Resolution shows interventions over time, active chains, hosts under
> attack."

**Click `ANALYSIS` (`/attack-analysis`).**

> "These are reconstructed kill chains — every chain is a sequence of events
> on a host that our chain-builder believes belong to the same attack.
> They're auto-grouped by host + temporal proximity + MITRE technique."

**Click a chain that reached stage 5.** (Find one with badge "Stage 5".)

This is the **money page**. Slow down. Walk through every panel:

1. **Header** — `2/2 infected · 100% radius`, threat level High, CKC ladder.
2. **Stage Timeline** — *"The full 8-stage Cyber Kill Chain template.
   Filled stages are where this chain has been observed; dashed stages are
   unreached. You can see the chain went Reconnaissance → Delivery →
   Exploitation → Installation — and STRIX's intervention happened HERE at
   Installation."*
3. **Affected Hosts table** — *"Both lab victims. Rose tag means infected —
   past the infection threshold. Emerald means sub-threshold, still being
   watched."*
4. **AI Predictions donut** — *"Click any slice. This is the Transformer's
   full 8-stage probability distribution. Right now it predicts the next
   stage is most likely Installation at 71%, with 16% probability of going
   to Recon. Real distribution, not heuristic."*
5. **STRIX Decisions panel** — *"Every action the DQN took on this chain,
   with Q-values, and crucially — whether the action came from the trained
   policy or a safety gate."*
6. **Operator Notes** — *"Analysts can leave timestamped notes that go into
   an immutable audit log. Edits and deletes are tracked. Authorship is
   enforced — you can't edit someone else's note."*

**Anticipated Q&A:**
- *"How do you know events belong to the same chain?"* → Host + temporal
  proximity + technique progression. Algorithm in `chain_builder.py`. We
  tuned the windowing on lab data.
- *"What if the chain is wrong?"* → Analyst can split/merge chains from the
  Hunt page. Notes preserve their reasoning.
- *"What's 'sub-threshold'?"* → Hosts with VAE probability below the §6.3
  infection threshold. Shown because seeing them is informative for the
  analyst even if they're not officially "infected".

---

## Act 4 — How STRIX decides (Actions, ~3 min)

**Click `ACTIONS` (`/actions`).**

> "This is the action ledger — every decision the DQN has made, in time
> order. You can filter by action type, by host, by chain."

**Filter to ESCALATE.** Show the 12 ESCALATE rows from today's run.

> "Each one of these escalations was triggered when the chain crossed CKC
> stage 5 — Installation. **This is the most important architectural
> decision in the whole system, so let me explain it carefully.**
>
> The DQN learned a policy from a training simulator. But on real lab data,
> the DQN sometimes proposes wrong actions — for example, on benign noise
> it occasionally proposes BLOCK_USER_IP, which would be a false positive.
> So we wrap the DQN in a **safety-gate ladder**: explicit rules that
> override the policy when its proposal is unsafe.
>
> The gates check things like: 'is the chain past stage 5? If yes, force
> ESCALATE regardless of what the DQN says.' Or: 'is the model in an
> out-of-distribution state? If yes, abstain and emit MONITOR.'
>
> **We measured this.** With gates ON: 12 ESCALATEs in this run, 100% true
> positives. With gates OFF — pure RL — the same run produces 22
> interventions all at stage 0 on benign noise: 100% false positives. The
> gates aren't decorative; they're load-bearing."

**Anticipated Q&A — this is the biggest target for hard questions:**
- *"So the DQN doesn't actually work?"* → It works at the architecture
  level: it proposes a *prior* that the gates filter. ML proposes, policy
  gates dispose. This is a defensible separation: the gates encode hard SOC
  rules the policy shouldn't override (compliance, audit, irreversibility),
  and the DQN handles the soft prioritization.
- *"Why not just use the gates without the DQN?"* → Then you have a
  rule-based system that can't adapt to novel patterns the gates don't
  anticipate. The DQN's value is in the *non-gated* regions of state space.
- *"What would full RL look like?"* → Future work: retraining the DQN with
  reward shaping that penalizes the failure modes the gates currently
  catch. Have a slide on this if pressed.

---

## Act 5 — Analyst investigation (Cases / Hunt / Intel, ~5 min)

**Click `CASES`.**

> "Chains can be promoted to cases. Cases get an assignee, a triage status,
> TLP marking, and a campaign attribution. Multi-analyst workflow."

Open a case. Show the Investigation tab + audit trail.

**Click `HUNT`.**

> "Threat-hunting view — analysts can run custom queries across alerts,
> detections, and chains. It's a free-form search surface for when
> something doesn't fit the auto-triage."

**Click `THREAT INTEL` → `Campaigns` → an APT actor.**

> "External threat intel comes in via OTX, MISP, and our own feeds. Chains
> can be tagged to campaigns; campaigns roll up to actors. This is how an
> analyst goes from 'something weird on victim2' to 'this is APT29 Stowaway
> behavior'."

**Click `CTI`** briefly — IOC management.

**Anticipated Q&A:**
- *"Where does threat intel come from?"* → OTX (free), MISP (community),
  custom feeds. Workers in `intel_feeds_worker`.
- *"How do you attribute to APTs?"* → TTP matching against MITRE-tagged
  actor profiles. Not strong attribution — assists the analyst, doesn't
  replace them.

---

## Act 6 — Notifications & operator UX (~1 min)

**Click the bell icon (top right).**

> "Same alerts that the analyst would see on the dashboard also stream into
> this notifications drawer with severity ranking. And these same alerts
> get pushed to the analyst's phone — let me show that now."

---

## Act 7 — Mobile (~3 min)

**Pick up the phone. Mirror screen to projector if possible.**

> "The mobile companion isn't a full SOC console — it's an **always-on
> alerting surface**. The premise is simple: an analyst can't be at their
> desk 24/7, but when something high-severity happens, they need to know
> within seconds."

**Show:**
1. **Mobile Dashboard tab** — same composite KPIs, much sparser layout.
   *"Designed for glance-and-go, not deep investigation."*
2. **Alerts tab** — list of high-severity events. *"Badge counter on the
   tab clears when you open it. Tap any alert to see the chain."*
3. **Model Health tab** — shows the same five models, training-time
   metrics. *"Proves to the analyst that the platform they're getting paged
   from is the same one running in the SOC."*

**Now trigger a notification live.** From your laptop, run:

```bash
# In a side terminal
bash infra/scripts/escalate_demo.py     # forces one ESCALATE through the pipeline
```

Wait ~10s. Phone should buzz, system tray notification appears.

> "That notification just traveled through the same path a real one would:
> SSE event → backend → Expo Push relay → FCM → phone. End-to-end latency
> from event to phone is under 5 seconds.
>
> The full SOC workflow stays on the web platform — investigation, case
> management, threat hunting. Mobile is **purely a paging channel**, and
> that's by design: small screens are bad investigation surfaces."

**Anticipated Q&A:**
- *"Why not a full mobile SOC?"* → Scope decision: SOC work is multi-window,
  dense, and demands keyboard. Mobile is for the moment between "I got
  paged" and "I'm at my laptop".
- *"What about iOS?"* → Backend already speaks APNs through Expo Push. Only
  blocker is Apple Developer Program enrollment ($99/year).

---

## Act 8 — Close (60 seconds)

**Walk back from the laptop.**

> "To summarize: CAVIX is an end-to-end SOC platform that takes raw
> syscalls and produces ranked, audited, intervenable kill-chain
> reconstructions. It uses five neural models in an ensemble, gated by
> SOC-grade safety rules — which we proved empirically are necessary, not
> optional. It runs in real time on real MITRE ATT&CK telemetry, with a
> live web console and a mobile alerting companion.
>
> I'm happy to take questions."

---

## Failure-recovery cheat sheet

Keep this on a sticky note:

| Symptom | Fix |
|---|---|
| Dashboard shows no events | `docker ps` → restart filebeat if down; check honcho with `ps -ef \| grep honcho` |
| All actions LOW_ALERT, no ESCALATE | Run `bash infra/scripts/lab_simulate.sh --non-monotonic` mid-demo — chain will hit S5 within 60s |
| Mobile not pinging | Expected if dev build expired; pre-test 30 min before. Fallback: show the Notifications drawer in web |
| Page doesn't load | F5; if persistent, web hot-reload may have crashed — `pnpm dev` restart |

---

## Pre-empted question bank (the 12 most likely)

1. **"Is this real or simulated data?"** → Real Caldera + real auditd + real
   Wazuh. Lab is contained but the data flow is production-equivalent.
2. **"Why DQN and not a simpler model?"** → DQN handles delayed reward
   (chain progression) better than classification.
3. **"What's the false-positive rate?"** → 0% on interventions in our gated
   runs. The trade is recall — we only intervene at S5+, so earlier-stage
   attacks are LOW_ALERT until they progress.
4. **"How do you handle drift?"** → Drift-KL surfaced per-model;
   recalibrator pipeline in `infra/scripts/calibration_refit.py`.
   Demonstrated this week on the VAE.
5. **"Could an attacker evade by going slow?"** → Yes — same weakness all
   stateful detectors have. Chain decay parameters are tunable.
6. **"Why not transformer-only?"** → Transformer is inverted on our lab
   data; ensemble robustness is exactly why we don't depend on a single
   model.
7. **"What's the scaling story?"** → Inference workers shard by
   `INFERENCE_SHARD_ID`. Wazuh + Postgres are independently scalable. Lab
   runs 500/min on a laptop; would be 10–100× in prod.
8. **"How long did this take to build?"** → [your honest answer]
9. **"What's not yet finished?"** → AE + Transformer encoder refit on lab
   data. Documented as future work.
10. **"Are the models retrainable from new data?"** → Yes;
    `calibration_refit.py` is the demonstrated pattern. Full encoder
    retraining requires more labeled data than we have.
11. **"What about adversarial ML?"** → Out of scope for this thesis.
    Acknowledged as a real concern.
12. **"What would production deployment look like?"** → Replace lab Caldera
    with real endpoint agents; same Wazuh + Filebeat + Redis + Postgres
    backbone scales horizontally.
