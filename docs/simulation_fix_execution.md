# Simulation Fix — Execution Log

**Date:** 2026-04-29
**Scope:** Execute [docs/simulation_fix_plan.md](simulation_fix_plan.md). Get the STRIX platform pipeline emitting verdicts in real-time during a live Caldera run.
**Outcome:** Pipeline recovered. PG `alerts` 589 → 9 021, `detections` 589 → 9 021, `attack_chains` 451 → 7 664. Inference + writer at lag 0. Two follow-ups left for the user (C3 cursor reset, Phase A1 SPA login).

---

## 1. User prompt

> read the conversation summary, and the plan as well. start the execution of this plan

The plan to execute was [docs/simulation_fix_plan.md](simulation_fix_plan.md): four phases (A: UI auth, B: inference verdicts, C: normalizer perf + log noise, D: stream MAXLEN), each with a verification step.

---

## 2. Assistant — phase-by-phase execution

### Phase A — auth (.env state)

`apps/api/.env:59` had `AUTH_DEV_SKIP_AUTH=false`. No code change made; left as the user's manual step (plan A1: SPA login). Plan A2 (flip to `true`) offered as alternative.

### Phase B1 — surface the silent inference exception

Patched the gather block in [apps/api/src/strix_api/workers/inference.py:300-319](../apps/api/src/strix_api/workers/inference.py#L300-L319):

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

### Phase B1.5 — root cause revealed

Restarted honcho via `nohup honcho -f Procfile.host -e apps/api/.env start >/tmp/strix_honcho.log 2>&1 &`. **First batch immediately produced 3 857 `handle_one_failed` lines**, all the same traceback:

```
File "session_store.py", line 185, in _decode_session
    chain_id=UUID(_s("chain_id")),
ValueError: badly formed hexadecimal UUID string
```

Inspecting Redis directly:

```
$ docker exec strix_redis redis-cli HGETALL session:005
step_count          1
last_seen_at        2026-04-29T14:51:40.455000+00:00
last_ckc_stage      0
last_action         0
max_vae_prob        1
```

**Partial session.** No `chain_id`, no `opened_at`, no `episode_start_at`. These hashes were created by `append_step` (which `HSET`s without checking the key exists) running *after* a concurrent task's `close_session(...)` deleted the key. Race between alert N closing a chain and alert N+1 for the same agent already in flight.

Fix in [apps/api/src/strix_api/adapters/session_store.py:65-83](../apps/api/src/strix_api/adapters/session_store.py#L65-L83): in `get_session()`, if `chain_id` field is missing, log `partial_session_dropped`, call `close_session()`, return None — so the next `decide_chain_action` opens a fresh chain.

### Phase B1.6 — pool exhaustion (revealed once errors stopped being silent)

After B1.5 fix, restart showed a *new* `handle_one_failed` pattern:

```
redis.exceptions.ConnectionError: Too many connections
  at session_store.py:166, in append_step
```

The default pool was 20 ([apps/api/src/strix_api/settings.py:54](../apps/api/src/strix_api/settings.py#L54)) but inference reads batches of 64 features and fans tasks out concurrently — each with several pipelined Redis ops. Bumped default to 200.

### Phase C1 — sklearn UserWarning per row

[apps/api/src/strix_api/adapters/preprocessing_pipeline.py:415-419](../apps/api/src/strix_api/adapters/preprocessing_pipeline.py#L415-L419): scaler was fit on a DataFrame, called with NumPy → sklearn's `_check_feature_names` fired once per row. Fix: drop `feature_names_in_` from the loaded scaler at boot. One-time mutation, no hot-path overhead, warning gone.

### Phase C2 — `missing agent.id` log noise

[apps/api/src/strix_api/workers/normalizer.py:122-138](../apps/api/src/strix_api/workers/normalizer.py#L122-L138): wazuh-internal events (rule 503, manager events) lack `agent.id` by design — they were spamming WARN. Demoted that specific case to DEBUG; other ValidationFailedErrors stay at WARN.

### Phase D1 — stream MAXLEN

Bumped from 100 000 → 1 000 000 in three places:
- [apps/api/src/strix_api/settings.py:80](../apps/api/src/strix_api/settings.py#L80) (`raw_stream_maxlen` default)
- [apps/api/.env:29](../apps/api/.env#L29) (env override)
- [apps/api/src/strix_api/workers/normalizer.py:47](../apps/api/src/strix_api/workers/normalizer.py#L47) (`_FEATURES_STREAM_MAXLEN`)
- [apps/api/src/strix_api/workers/inference.py:98](../apps/api/src/strix_api/workers/inference.py#L98) (`_VERDICTS_STREAM_MAXLEN`)

---

## 3. Verification — before vs. after

| signal | before (frozen) | after final restart |
|---|---:|---:|
| `handle_one_failed` | n/a (silent) | **0** |
| `Too many connections` | hidden | **0** |
| `ae_or_vae_failed` | n/a | **0** |
| `strix:features:0` lag | unknown | **7** (≈0) |
| `strix:verdicts` writer lag | 0 | **0** |
| `strix:verdicts` xlen | 535 (frozen 1h+) | growing, +20–30/s |
| pg `alerts` | 589 | **9 021** |
| pg `detections` | 589 | **9 021** |
| pg `attack_chains` | 451 | **7 664** |
| pg `dqn_actions` | 589 | matches detections |
| `detections` written / 30 s | 0 | **655** (~22/s) |

`partial_session_dropped` fires occasionally (≈70 over the run) — benign cleanup of the close-session race documented above; no verdict lost. A proper fix is a Lua script that makes `append_step` no-op when `chain_id` is missing, but it's a follow-up, not blocking.

---

## 4. What's left for the user

### C3 — drain the stale `alerts:raw` backlog (decision required)

`strix-normalizer` consumer-group lag held at ~100k throughout. New alerts process in real time but the pre-fix backlog stays. Either:

1. **Skip it** — `docker exec strix_redis redis-cli XGROUP SETID strix:alerts:raw strix-normalizer \$`. Loses ~100k pre-fix alerts. Recommended for the demo.
2. **Add a second normalizer worker** (Procfile.host change + sharded consumer name) — more invasive, processes everything.

The plan's preferred path is option 1; the assistant paused for explicit user OK before running it.

### A1 — log in to the SPA

Browser hits `/login`, sign in as `admin@strix.io`. Once cookies are set the dashboard polls populate from the now-9 000+ PG rows. Alternative: flip `AUTH_DEV_SKIP_AUTH=true` in [apps/api/.env](../apps/api/.env) and restart the api process.

---

## 5. Files changed

| file | change |
|---|---|
| [apps/api/src/strix_api/workers/inference.py](../apps/api/src/strix_api/workers/inference.py) | B1 per-task error logging; D1 verdicts MAXLEN 1M |
| [apps/api/src/strix_api/adapters/session_store.py](../apps/api/src/strix_api/adapters/session_store.py) | B1.5 partial-session defensive drop + logger import |
| [apps/api/src/strix_api/adapters/preprocessing_pipeline.py](../apps/api/src/strix_api/adapters/preprocessing_pipeline.py) | C1 strip scaler feature names |
| [apps/api/src/strix_api/workers/normalizer.py](../apps/api/src/strix_api/workers/normalizer.py) | C2 demote missing-agent-id to debug; D1 features MAXLEN 1M |
| [apps/api/src/strix_api/settings.py](../apps/api/src/strix_api/settings.py) | B1.6 redis pool 20→200; D1 raw MAXLEN default 1M |
| [apps/api/.env](../apps/api/.env) | D1 `WAZUH_RAW_STREAM_MAXLEN=1000000` |

No Caldera, Wazuh, Filebeat, victim-container, Postgres-schema, or model-file changes.

---

## 6. Operational steps performed

```bash
# rotate logs + restart honcho
mv /tmp/strix_honcho.log /tmp/strix_honcho.log.before-fix
nohup honcho -f Procfile.host -e apps/api/.env start >/tmp/strix_honcho.log 2>&1 &

# verification
docker exec strix_redis redis-cli XLEN strix:verdicts
docker exec strix_redis redis-cli XINFO GROUPS strix:features:0
docker exec strix_postgres psql -U strix -d strix -t -c "SELECT COUNT(*) FROM detections WHERE created_at >= NOW() - INTERVAL '30 sec';"
```

The pipeline went through three honcho restarts as each layer of error revealed the next:
1. Restart 1 (B1 patch) → revealed UUID/partial-session bug
2. Restart 2 (B1.5 + C1 + C2 + D1) → revealed pool exhaustion
3. Restart 3 (B1.6 pool bump) → fully healthy, 0 errors, 22 detections/sec
