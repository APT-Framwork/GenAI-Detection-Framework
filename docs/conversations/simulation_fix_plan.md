# Simulation Fix Plan — why the platform UI is empty during a live Caldera run

**Date:** 2026-04-29
**Symptom:** Caldera operations are firing, Wazuh is producing alerts (delta of ~3.5k alerts per tactic), Filebeat → Redis is working, but every UI tile shows `0` / "Failed to load" — and the per-tactic deltas in the simulation runner show **`pg alerts +0, detections +0, chains +0`** despite the upstream traffic.

This is **not a single bug**. There are three independent failures stacked on top of each other. Each must be fixed for the user-visible dashboard to populate.

---

## What I observed (evidence)

### Stream / DB state at 14:36 UTC (host 15:36)

| Stream / table              | xlen / count | last activity (UTC) | consumer-group lag |
|-----------------------------|-------------:|---------------------|-------------------:|
| `strix:alerts:raw`          | 100 000 (capped) — 140 921 ever added → **40 921 events lost** | 14:35:23 | normalizer **lag 37 625** |
| `strix:features:0`          | 50 002       | 14:35:23            | inference lag 18 (current) |
| `strix:verdicts`            | **535** total — never grew past startup burst | **13:26:04** (1h+ stale) | writer lag 0 |
| `alerts` (PG)               | 589          | 13:26:04            | — |
| `detections` (PG)           | 589          | 13:26:04            | — |
| `attack_chains` (PG)        | 451          | 13:26:03            | — |
| `dqn_actions` (PG)          | 589          | (n/a)               | — |
| `gnn_graph_snapshots` (PG)  | 344          | 15:02 UTC           | — |

The pattern is unmistakable: at **13:26:04 UTC**, `inference` stopped emitting verdicts, so every downstream stage (writer, alerts, detections, chains) froze. The GNN background loop (snapshot persistence) kept running because it's a separate `asyncio.create_task`.

### UI state

Every API request from the SPA returns **401 Unauthorized**:

```
GET  /api/v1/dashboard/victim-graph?window=1h    HTTP 401
GET  /api/v1/dashboard/attack-vector?window=1h   HTTP 401
GET  /api/v1/dashboard/global-risk?window=1h     HTTP 401
GET  /api/v1/analysis/chains/latest/...           HTTP 401
GET  /api/v1/threat-intel/iocs?limit=20           HTTP 401
GET  /api/v1/monitoring/models                    HTTP 401
GET  /api/v1/topology?window=24h                  HTTP 401
POST /api/v1/auth/refresh                         HTTP 401  detail="refresh token missing"
```

The browser has no `strix_refresh` cookie (the SPA never logged in successfully, or the refresh cookie expired / was cleared). `AUTH_DEV_SKIP_AUTH=false` is set in [apps/api/.env](../apps/api/.env), so the API enforces auth. Net effect: even if the pipeline produced rows in real time, the dashboard couldn't read them.

### Worker logs (the smoking guns)

1. **Normalizer is the upstream bottleneck.** Lag grew from 0 to **37 625** entries, ~21 minutes behind real time. Process is pegged at **84 % CPU**.
2. **Normalizer drops events with `alert is missing agent.id`** at thousands per second. These are wazuh-internal events (rule 503 "agent connected", manager events). They're not the cause of the verdict stall — the 589 alerts that *did* make it through prove the path works for valid alerts — but the noise hides every other warning.
3. **`UserWarning: X does not have valid feature names, but StandardScaler was fitted with feature names`** is printed **once per processed row** by the normalizer (and possibly inference). The honcho log is 99 % this single warning. This is wasting CPU and burying real errors.
4. **Inference logs nothing useful** between startup and now except the `gnn_snapshot_refreshed` heartbeat. No `ae_or_vae_failed`, no per-message error. Yet `entries-read=82403` for the inference consumer group while `entries-added=535` for the verdicts stream. **>99 % of feature messages are read but produce no verdict.**

### Why inference goes silent

[apps/api/src/strix_api/workers/inference.py:300-312](../apps/api/src/strix_api/workers/inference.py#L300-L312):

```python
tasks: list[asyncio.Task[Any]] = []
ids: list[bytes] = []
for _stream, entries in batch:
    for entry_id, fields in entries:
        ids.append(entry_id)
        tasks.append(asyncio.create_task(self._handle_one(entry_id, fields)))

await asyncio.gather(*tasks, return_exceptions=True)   # ← swallows everything
```

Any exception in `_handle_one` (validation, sklearn shape mismatch, NaN propagating into the transformer, DQN batcher closure, GNN cache lookup, session repository, …) is collected into the `gather` result list and discarded. Nothing is logged. Then `xack` runs against every id, so the message is *acked* even though it produced no verdict. This is the silent-failure pattern that's wedging the whole pipeline.

The 535 verdicts that DID make it through were emitted in a ~30 s window between 13:25:32 and 13:26:04. After that, every `_handle_one` call has been failing silently. We currently have no traceback to point at; that's the first thing to fix.

---

## Root causes (ranked)

| # | Cause | User-visible impact | Layer |
|---|---|---|---|
| **1** | UI has no auth session → 401 on every endpoint | Dashboard shows `0` / "Failed to load" everywhere | Web/API |
| **2** | `_handle_one` exceptions swallowed by `gather(return_exceptions=True)` with no logging | DB stops growing → all dashboards stale even when logged in | Inference worker |
| **3** | Normalizer pegged at 84 % CPU due to per-row sklearn `UserWarning` | Lag grows unboundedly; events lost when xlen caps at 100 k | Normalizer worker |
| **4** | `alerts:raw` validator drops `alert is missing agent.id` at WARN level | Log noise hides real errors; misleading | Normalizer worker |
| **5** | `strix:alerts:raw` MAXLEN 100 000 too tight for current rate | 40 k+ events already lost; backlog can't recover | Stream config |

---

## Fix plan

### Phase A — make the UI populate (unblocks the user)

**A1. Log in to the SPA (one-shot, no code change).**
Open the web app, navigate to the login route, and log in as `admin@strix.io` (or one of the other seeded users in [users](#) — see `SELECT email, role FROM users`). Once cookies are set the dashboard polls populate immediately for whatever data the DB *does* have (the 589 historical alerts).

If the SPA does not surface a login form on 401, we need to verify the redirect logic in `apps/web` — but for now, hitting `/login` directly should work.

**A2. (Optional) Flip dev-skip-auth.**
For pure platform demos where login isn't part of the story, set `AUTH_DEV_SKIP_AUTH=true` in [apps/api/.env](../apps/api/.env) and restart the api process. Leave `false` if you want to demo the auth flow.

### Phase B — make inference produce verdicts again (the *actual* pipeline fix)

**B1. Surface the silent exception in `_handle_one`.**
Patch [inference.py:300-312](../apps/api/src/strix_api/workers/inference.py#L300-L312) so we see *which* exception is poisoning every message:

```python
results = await asyncio.gather(*tasks, return_exceptions=True)
for entry_id, result in zip(ids, results, strict=True):
    if isinstance(result, BaseException):
        self._log.error(
            "handle_one_failed",
            entry_id=entry_id.decode(errors="replace"),
            exc_info=result,
        )
```

Then restart `inference` and watch one batch. The exception traceback will tell us *exactly* what's wrong (most-likely candidates: a feature-vector shape mismatch from a recent normalizer change; a `sequence_arr` empty when `prior_latents` is empty for a brand-new agent; DQN batcher closed; SecBERT/transformer NaN; session repo schema drift). Until B1 lands, we are guessing.

**B2. Reset the consumer group cursor for `strix:features:0`.**
Once B1 is in place and the bug is fixed, the existing `entries-read=82403` cursor has already advanced past the unprocessed-but-acked features. Move the inference group back to a sane point (or start fresh) so we re-process post-fix:

```bash
docker exec strix_redis redis-cli XGROUP SETID strix:features:0 strix-inference-0 \$
```

(`$` = "from now on" — don't rerun the full backlog.)

### Phase C — unblock the normalizer

**C1. Stop the per-row sklearn warning.**
The warning fires because we call `scaler.transform(X)` with `X` as a NumPy array, while the scaler was fit on a DataFrame. Cheapest fix in [apps/api/src/strix_api/adapters/preprocessing_pipeline.py](../apps/api/src/strix_api/adapters/preprocessing_pipeline.py): wrap the transform call in `warnings.catch_warnings()` once at module load, or — better — pass a DataFrame with the canonical column names so the warning never triggers and the validation is correct. Either fix should drop normalizer CPU significantly.

**C2. Demote the `alert is missing agent.id` warning to debug-level** in [apps/api/src/strix_api/workers/normalizer.py](../apps/api/src/strix_api/workers/normalizer.py). These events are expected (Wazuh-internal). We don't need a per-event WARN line; an aggregated count every N seconds is plenty.

**C3. Drain the existing 37 k backlog.**
After B1+C1 are deployed, restart normalizer and let it catch up. If the backlog still grows after the perf fix, raise the worker count (sharding) or skip the stale prefix:

```bash
docker exec strix_redis redis-cli XGROUP SETID strix:alerts:raw strix-normalizer \$
```

Same caveat as B2 — only do this if the user is OK losing the backlog.

### Phase D — make the lab survivable for longer runs

**D1. Raise stream MAXLEN.** The current cap of 100 000 has *already* lost 40 k+ alerts during this run. Bump to e.g. 1 000 000 in the publish call (search for `_VERDICTS_STREAM_MAXLEN` and similar `maxlen=` kwargs in the workers + `wazuh_bridge`). Memory cost is bounded — Redis trims with `~` so we trade ~100 MB for hours of headroom.

**D2. Increase normalizer parallelism.** If C1 isn't enough, run two normalizer instances behind a sharded consumer name. The current Procfile has a single `normalizer.1` process.

---

## Verification checklist (after applying fixes)

1. `curl -s http://localhost:8000/health` → `{"status":"ok",…}` ✅ (already true)
2. Log in to web → dashboard loads, no 401 in honcho log → **Phase A done**
3. Tail honcho log filtered for inference; force-process a feature → see `handle_one_failed` traceback → **B1 plumbing in place**
4. Apply specific fix B1 reveals → `verdicts_flushed` lines start appearing in honcho log again → **Phase B done**
5. `redis-cli XLEN strix:verdicts` grows over a minute → ✅
6. `SELECT COUNT(*) FROM detections WHERE created_at >= NOW() - INTERVAL '1 min'` returns > 0 → ✅
7. Re-run `bash infra/scripts/lab_simulate.sh` (memory: STRIX full simulation runner). The per-tactic delta should now show **`pg alerts +N`** with N matching the wazuh-alerts delta (minus dropped events) → end-to-end working
8. Rerun a Caldera op against group `red` → frontend tiles update live (Live Feed, AI Sentinel Insight, Attack Vector Graph, Threat Intensity all populate)

---

## What I did NOT change

- Caldera, Wazuh, Filebeat, victim containers — these are working correctly per the host audit pipeline fixes from 2026-04-29.
- Postgres schema, migrations, models — no schema drift suspected.
- The MITRE simulation script — its rc=-3 link statuses are a separate, expected Caldera-agent issue unrelated to platform plumbing.

The platform-side data path is what's broken; the simulation-side data generation is fine.
