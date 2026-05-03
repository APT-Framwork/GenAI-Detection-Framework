# Simulation Fix — Investigation Conversation Log

**Date:** 2026-04-29
**Scope:** Why the STRIX platform UI shows zeros / "Failed to load" while Caldera-driven simulation is actively producing Wazuh alerts.
**Outcome:** [docs/simulation_fix_plan.md](simulation_fix_plan.md) — phased fix plan (no code changes applied yet).

---

## 1. User prompt

> this is from last session. i started the simulation, look at the terminal logs:
>
> ```
> ── [ docker containers up ] ──
> ✓ strix_caldera running
> ✓ strix_postgres running
> ✓ strix_redis running
> ✓ strix_wazuh_manager running
> ✓ strix_filebeat running
>
> ── [ Caldera reachable + agents in group ] ──
> ✓ 2/22 agents in group 'red' fresh (paws: jrnqcx, bpwkvu)
>
> ── [ host auditd is producing audit-wazuh-x events ] ──
> ✓ audit-wazuh-x events present in /var/log/audit/audit.log (last 2k lines: 387 hits)
>
> ── [ Wazuh agents Active ] ──
> ✓ 3 Wazuh agents Active
>
> ── [ Redis stream + Postgres reachable ] ──
> ✓ redis xlen=100001  alerts=589  detections=589  chains=451
>
> ── [ Filebeat agent block survives (normalizer not dropping) ] ──
> ✓ redis entries carry Wazuh agent.name — filebeat config is correct
> · planner: batch  id=788107d5-dc1e-4204-9269-38df0186d3e7
>
> ══════════════════════════════════════════════════════════════════════
> EXECUTION PLAN
> ══════════════════════════════════════════════════════════════════════
>   APT chain — APT41:  Persistence → Privilege Escalation → Defense Evasion → Discovery → Collection → Exfiltration
>     commonly used as backdoor/rootkit; signature exfil over rsync
>
>   • Persistence             techniques=T1136.001,T1098,T1037,T1543.002,T1053.003
>   • Privilege Escalation    techniques=T1548.003,T1068,T1548.001
>   • Defense Evasion         techniques=T1070.003,T1070.004,T1027,T1562.001
>   • Discovery               techniques=T1033,T1057,T1083,T1087.001,T1069.001
>   • Collection              techniques=T1005,T1560.001,T1119
>   • Exfiltration            techniques=T1048,T1048.003,T1041
>
> ══════════════════════════════════════════════════════════════════════
> TACTIC: Persistence  (TA0003)
> ══════════════════════════════════════════════════════════════════════
> ✓ launched op  name=sim-persistence-1777472423  id=ab35e7b1-…  obfuscator=plain-text
> · stop op rc: HTTP 400 on PATCH /api/v2/operations/…: {"error": "This operation has already finished."}
> · dwell 30s for pipeline drain
>   delta over 38s:
>   wazuh alerts.json        113431 ->   113599   +168
>   redis xlen               100000 ->   100000   +0
>   pg alerts                   589 ->      589   +0
>   pg detections               589 ->      589   +0
>   pg attack_chains            451 ->      451   +0
>
> TACTIC: Privilege Escalation
>   delta over 63s:
>   wazuh alerts.json        113599 ->   116950   +3351
>   redis xlen               100000 ->   100000   +0
>   pg alerts                   589 ->      589   +0
>   pg detections               589 ->      589   +0
>   pg attack_chains            451 ->      451   +0
>
> TACTIC: Defense Evasion
>   delta over 114s:
>   wazuh alerts.json        117011 ->   120487   +3476
>   redis xlen               100000 ->   100001   +1
>   pg alerts                   589 ->      589   +0
>   pg detections               589 ->      589   +0
>   pg attack_chains            451 ->      451   +0
>
> TACTIC: Discovery  (still running)
> ```
>
> ...but as you see in the screenshots of all platform tiles, the platform is empty, 0 everywhere, no graph, no forensic logs, no metrics. Please investigate why. Inspect tables, everything. At the end I want to see everything works real-time in the platform. If changes and fixes needed, then prepare the plan under the name `simulation_fix_plan.md`.

---

## 2. Assistant — investigation method

I walked the data path from the producer side to the consumer side, looking for the first place numbers stopped agreeing.

### Step 1 — orient: which services are actually running?

```text
$ docker ps
strix_caldera, strix_redis, strix_postgres, strix_filebeat, strix_wazuh_manager, strix_victim1, strix_victim2  →  all up
```

The host platform processes (api, wazuh_bridge, normalizer, inference, verdicts_writer, arq, web) run via [Procfile.host](../Procfile.host) under `honcho`, not docker. Confirmed all six worker processes alive (`ps -ef`):

```
343828  uvicorn strix_api.main:app --host 0.0.0.0 --port 8000
343831  python -m strix_api.workers.wazuh_bridge
343834  python -m strix_api.workers.normalizer       ← 84% CPU, 3:41:14 CPU time
343837  python -m strix_api.workers.inference
343840  python -m strix_api.workers.verdicts_writer
343842  arq    strix_api.workers.arq_tasks.WorkerSettings
343847  pnpm dev (next)
```

The normalizer at 84 % CPU was the first red flag.

### Step 2 — Redis stream depth + consumer-group lag

```text
strix:alerts:raw    xlen=100000 (capped) — entries-added=140921 → 40921 events lost
                    consumer-group strix-normalizer:  lag=37625, last-delivered-id=…14:14:14 UTC
                    (alerts:raw last-entry-id=…14:35:23 UTC — 21 min behind)

strix:features:0    xlen=50002    consumer strix-inference-0: lag=18 (current)
                    last-delivered-id=…14:35:23 UTC, entries-read=82403

strix:verdicts      xlen=535      consumer strix-writer:      lag=0
                    last-generated-id=…13:26:04 UTC ← FROZEN 1h+
                    entries-added=535 (TOTAL)
```

This pinned the failure: inference is *reading* features (82 403 read) but the verdicts stream has had **exactly 535 entries pushed, ever**, and hasn't grown for over an hour. That's not a flow problem; that's a logic problem.

### Step 3 — Postgres confirms

```sql
alerts          589   max(created_at)=2026-04-29 13:26:04 UTC
detections      589   max(created_at)=2026-04-29 13:26:04 UTC
attack_chains   451   max(created_at)=2026-04-29 13:26:03 UTC
dqn_actions     589
gnn_graph_snapshots  344  max(taken_at)=2026-04-29 15:02 UTC   ← still growing
```

Every chain-bound table has the **identical timestamp** of the last verdict produced. The GNN snapshot table keeps growing because that's a separate `asyncio.create_task` background loop in inference, decoupled from per-message handling.

### Step 4 — UI 401 storm

Filtered the honcho log for non-noise lines:

```
INFO:  GET /api/v1/dashboard/victim-graph?window=1h    → 401 Unauthorized
INFO:  GET /api/v1/dashboard/attack-vector?window=1h   → 401 Unauthorized
INFO:  GET /api/v1/dashboard/global-risk?window=1h     → 401 Unauthorized
INFO:  GET /api/v1/analysis/chains/latest/...          → 401 Unauthorized
INFO:  GET /api/v1/threat-intel/iocs?limit=20          → 401 Unauthorized
INFO:  GET /api/v1/monitoring/models                   → 401 Unauthorized
INFO:  GET /api/v1/topology?window=24h                 → 401 Unauthorized
INFO:  POST /api/v1/auth/refresh                       → 401 Unauthorized
```

```
$ curl -si -X POST http://localhost:8000/api/v1/auth/refresh
HTTP/1.1 401 Unauthorized
{"detail":"refresh token missing","code":"INVALID_TOKEN"}
```

```
apps/api/.env:
ENV=dev
AUTH_DEV_SKIP_AUTH=false
```

The browser has no `strix_refresh` cookie. With `AUTH_DEV_SKIP_AUTH=false`, the API enforces auth, so the SPA can't reach any endpoint — that's the "everything is zero" the user sees on the dashboard, independent of pipeline state.

Seeded users exist:

```
admin@strix.io      admin
analyst1@strix.io   analyst
analyst2@strix.io   analyst
admin@strix.local   admin
```

So the user can log in. No code change required for Phase A.

### Step 5 — normalizer log spam

99 % of [/tmp/strix_honcho.log](/tmp/strix_honcho.log) is a single sklearn `UserWarning` printed *per processed row*:

```
sklearn/utils/validation.py:2691: UserWarning:
  X does not have valid feature names, but StandardScaler was fitted with feature names
```

The warning fires because `scaler.transform(X)` is called with a NumPy array, while the scaler was fit on a pandas DataFrame. ~60 warnings/sec → log noise + measurable CPU.

The other warning category was `VALIDATION_FAILED: alert is missing agent.id` — wazuh-internal events (rule 503, manager events) lacking the agent.id field. They're correctly dropped, but they're spamming WARN-level lines.

### Step 6 — why inference goes silent

[apps/api/src/strix_api/workers/inference.py:300-312](../apps/api/src/strix_api/workers/inference.py#L300-L312):

```python
tasks: list[asyncio.Task[Any]] = []
ids: list[bytes] = []
for _stream, entries in batch:
    for entry_id, fields in entries:
        ids.append(entry_id)
        tasks.append(asyncio.create_task(self._handle_one(entry_id, fields)))

await asyncio.gather(*tasks, return_exceptions=True)  # ← swallows everything
…
await self._redis.ack(self.features_stream, self.consumer_group, *ids)
```

Any exception in `_handle_one` is captured by `return_exceptions=True` and discarded. Then the message is `XACK`'d regardless. Result: > 99 % of feature messages are read, silently fail, and ack'd. No traceback ever reaches the log. The 535 verdicts that *did* land were a ~30-second startup window; after that, every call has been failing.

### Step 7 — verdict path entry: skip + full both publish

To rule out "inference is just filtering":

[inference.py:358-367](../apps/api/src/strix_api/workers/inference.py#L358-L367) — `SKIP_BENIGN` path → `_emit_skip_verdict` → `await self._redis.publish(_VERDICTS_STREAM, …)`.
[inference.py:455-491](../apps/api/src/strix_api/workers/inference.py#L455-L491) — `OPEN_NEW` / `CONTINUE` path → full verdict + `xadd`.

Both paths publish. The fact that *no* verdicts (skip OR full) are coming out means the failure is upstream of the chain decision — i.e. inside model inference / feature transform / session lookup. We can't be more specific without B1's diagnostic logging in place.

---

## 3. Findings (delivered to user)

> **Three independent bugs are stacked.** Caldera → Wazuh → Filebeat → Redis is fine. The break is downstream:
>
> 1. **UI: every API call returns 401.** The browser has no `strix_refresh` cookie and `AUTH_DEV_SKIP_AUTH=false`, so all 7 dashboard endpoints return 401. Even with a working pipeline the dashboard would render `0` until the user logs in.
> 2. **Inference died silently at 13:26:04 UTC.** `strix:verdicts` has `entries-added=535` total — froze 1+ hour ago. But `strix:features:0` consumer-group has `entries-read=82403`, so inference *is* reading messages, ack'ing them, and producing zero verdicts. Cause: `inference.py:307` does `gather(..., return_exceptions=True)` with no per-task error logging — every `_handle_one` exception is swallowed.
> 3. **Normalizer is the bottleneck.** Lag = 37 625 entries (~21 min behind). Process pegged at 84 % CPU. `UserWarning: X does not have valid feature names…` fires once per row.

The plan in [docs/simulation_fix_plan.md](simulation_fix_plan.md) splits the work into four phases:

- **Phase A** — log in (or flip `AUTH_DEV_SKIP_AUTH=true`) — unblocks the UI
- **Phase B** — add per-task error logging in inference, then fix the underlying exception once visible; reset the inference consumer cursor afterwards
- **Phase C** — kill the sklearn warning, demote the `missing agent.id` log to debug
- **Phase D** — raise `MAXLEN` so the lab survives longer runs without losing events

Plus a verification checklist that ends with: *re-run a Caldera op against group `red`, see Live Feed / AI Sentinel Insight / Attack Vector Graph populate live*.

---

## 4. What was NOT changed

- Caldera, Wazuh, Filebeat, victim containers — confirmed working per the 2026-04-29 audit-pipeline fixes.
- Postgres schema, migrations, model files — no drift.
- The MITRE simulation runner ([infra/scripts/lab_simulate.sh](../infra/scripts/lab_simulate.sh)) — its `rc=-3` link statuses are a separate Caldera-agent issue unrelated to platform plumbing.

No code edits were applied. The plan is the deliverable; the user reviews and decides which phases to execute.
