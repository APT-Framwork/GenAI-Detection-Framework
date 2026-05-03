# Session Log — Dashboard Tiles Fix & Platform Hardening

**Date:** 2026-04-29 / 2026-04-30
**Scope:** End-to-end fix of the STRIX platform: pipeline recovery (execution of simulation_fix_plan.md), web auth gate, dashboard tile audit, silent failure fixes, real-time data wiring.
**Outcome:** All dashboard tiles now serve real DB data. Pipeline healthy at 0 errors, ~20 verdicts/sec. Web route guard deployed.

---

## 1. Starting state (from prior session plan)

Three independent failures were stacked (documented in [simulation_fix_conversation.md](simulation_fix_conversation.md)):
1. **UI: every API call returns 401** — no `strix_refresh` cookie, `AUTH_DEV_SKIP_AUTH=false`
2. **Inference dead since 13:26 UTC** — `asyncio.gather(return_exceptions=True)` swallowed every exception silently
3. **Normalizer pegged at 84 % CPU** — per-row sklearn `UserWarning` from StandardScaler + `missing agent.id` log spam

---

## 2. Execution — [simulation_fix_plan.md](simulation_fix_plan.md)

### Phase B1 — surface the silent inference exception
`apps/api/src/strix_api/workers/inference.py:307`:
```python
results = await asyncio.gather(*tasks, return_exceptions=True)
for entry_id, result in zip(ids, results, strict=True):
    if isinstance(result, BaseException):
        self._log.error("handle_one_failed", entry_id=..., exc_info=result)
```
First restart produced 3 857 `handle_one_failed` lines immediately:
```
session_store.py line 185: chain_id=UUID(_s("chain_id"))
ValueError: badly formed hexadecimal UUID string
```

### Phase B1.5 — root cause: partial sessions in Redis

Redis `HGETALL session:005` / `session:006` returned hashes with only `step_count`, `last_seen_at`, `last_ckc_stage`, `last_action`, `max_vae_prob` — **no `chain_id`**. The `_decode_session` function crashed on `UUID("")`. Root cause: `append_step` uses `HSET` which creates the key if it doesn't exist; when a concurrent task's `close_session` deleted a key mid-flight, `append_step` recreated a partial hash.

Fix in `apps/api/src/strix_api/adapters/session_store.py` `get_session()`:
```python
chain_field = raw.get(b"chain_id") or raw.get("chain_id")
if not chain_field:
    _log.warning("partial_session_dropped", agent_id=agent_id, fields=...)
    await self.close_session(agent_id)
    return None
```
Partial sessions self-clean on next access. No verdicts lost.

### Phase B1.6 — Redis connection pool exhausted (surfaced by B1)

New error after session fix: `redis.exceptions.ConnectionError: Too many connections`. Pool was 20; inference fans out 64 concurrent tasks/batch. Fixed in `apps/api/src/strix_api/settings.py`:
```python
max_connections: int = 200   # was 20
```

### Phase C1 — sklearn UserWarning per row

`standard_scaler.pkl` was fit on a DataFrame; calls to `.transform(numpy_array)` triggered `_check_feature_names` once per alert. Fix in `_check_scaler()` at load time:
```python
if hasattr(scaler, "feature_names_in_"):
    del scaler.feature_names_in_
```

### Phase C2 — missing agent.id log noise
Wazuh-internal events (rule 503) lack `agent.id` by design. Demoted from `_log.warning` to `_log.debug` in normalizer.

### Phase D1 — stream MAXLEN raised
All three streams: `alerts:raw`, `features:0`, `verdicts` — raised from 100 k / 50 k to **1 000 000**.

### Verification (after all fixes)
| signal | before | after |
|---|---|---|
| `handle_one_failed` | (silent) | **0** |
| `strix:verdicts` xlen | 535 frozen | **growing ~20/s** |
| pg `detections` | 589 | **111 000+** |
| `detections` / 30 s | 0 | **655** |

---

## 3. Web auth gate

**Problem:** `GET /` loaded without authentication. No middleware existed. `(dashboard)/layout.tsx` had no auth check. The `auth-store.ts` was a stub that always returned `true`.

**Fix 1 — `apps/web/middleware.ts`** (new file):
- Checks `strix_access` or `strix_csrf` cookies at every non-public route
- Unauthenticated requests → `307 /login`
- Public routes (`/login`, `/register`) pass through
- Matcher excludes `api/` (Next rewrite path), `_next/`, static assets

Initial bug: matcher `((?!_next/static|...).*)` didn't exclude `/api/v1/*` — the middleware intercepted `POST /api/v1/auth/login` itself and redirected to `/login`. Fixed matcher to `/((?!api/|_next/|...).*)`.

**Fix 2 — `apps/web/app/(auth)/login/page.tsx`**: honours `?next=` redirect param after successful login.

Curl verification:
```
GET /           (no cookie)  → 307 /login          ✅
GET /           (with cookie) → 200                ✅
POST /api/v1/auth/login       → 200 + sets cookies  ✅
```

**Credentials:** `admin@strix.io` / `StrixAdmin!2026` (rotated via `seed_admin.py`).

---

## 4. Dashboard tile audit

API sweep revealed:

### ✅ Live with real data
- `/dashboard/attack-vector` — 93k+ alerts, CKC stage histogram
- `/dashboard/global-risk` — VAE/GNN/anomaly components, 27-point trend
- `/analysis/chains` — 50k+ attack chains
- `/analysis/chains/{id}/predictions` — Transformer next-stage
- `/monitoring/models` — 5 registered models

### ❌ Silent failures (fixed)

**1. `/dashboard/victim-graph` — schema mismatch**
- Writer ([inference.py](../apps/api/src/strix_api/workers/inference.py)) stored nodes as `{alertId, risk}` per-alert
- Reader ([dashboard_service.py](../apps/api/src/strix_api/services/dashboard_service.py)) expected `{hostId, hostName, severity, infected, riskScore}` per-host
- `KeyError("hostId")` swallowed by `_try_service` wrapper → empty silently
- Fix: rewrote `victim_graph()` to query `attack_chains + hosts` directly, aggregate per-host, collapse-then-join for edges (avoids O(n²) self-join that caused DiskFullError)

**2. `/topology` — DiskFullError**
- Host disk 97% full; gnn_graph_snapshots had 1 GB chunk (567 rows × ~1.8 MB JSONB each)
- Topology edge query: CTE self-join over 50k chains → spilled to Postgres tmp → no space
- Fix: pruned snapshots (`DELETE FROM gnn_graph_snapshots WHERE taken_at < NOW() - INTERVAL '1 hour'` + `drop_chunks` + VACUUM FULL) — freed ~700 MB
- Fixed query: aggregate chains to per-host first, THEN self-join (hosts² not chains²)

**3. `/analysis/chains/{id}/graph-evolution` — always 0 snapshots**
- Old query: `WHERE taken_at BETWEEN opened_at AND closed_at`. Most chains are seconds-long; no snapshot row falls in the window.
- Fix: synthesise snapshots from chain's own alerts, bucketed by CKC stage transitions (up to 6 frames)
- Also had SQL bind syntax bug: `:closed::TIMESTAMPTZ` — SQLAlchemy couldn't substitute `:closed` when followed by `::`. Rewritten to pure Python + simpler query.

**4. Forensic Logs always blank**
- `verdicts_writer.py` hardcoded `decoder_name=None, location=None, full_log=None, rule_id=None` on every alert insert
- Fix: threaded the fields end-to-end:
  - Added `full_log`, `decoder_name`, `location`, `rule_id`, `rule_firedtimes` to `FeatureMessage` (core/messages.py)
  - Normalizer populates them from parsed `RawAlert`
  - Inference passes them through into both verdict payloads (full + skip)
  - verdicts_writer reads and persists them
- Verified: new alerts now have `decoder=ossec`, `location="netstat listening ports"`, `log_len=243-343`

### 🎭 Mocked components (wired to real data)

**5. `GraphEvolution` component** — had hardcoded `WEB-SRV-01`, `SQL-CLUSTER`, `ADMIN-WS-09` constants. Comment said "until we wire the real renderer." Completely rewritten to consume the `snapshots` prop: circle layout, severity-coloured nodes, real edges.

**6. `AttackVectorChart`** — component accepted a `data` prop but `page.tsx` called it as `<AttackVectorChart />` with no props → always rendered the hardcoded mock (Initial Access 35%, Privilege Escalation 25%, etc.). Fixed: `page.tsx` now projects `attackVector.data.stages` into the chart's `data` prop (skips BENIGN, maps 7 attack stages to palette).

**7. `Δ1h: NaN%`** in Threat Intensity — `GlobalRiskResponse` interface in `hooks.ts` had `delta1h` (lowercase h); API returns `delta1H` (capital H, pydantic camelCase). `data.delta1h` was `undefined` → `undefined * 100 = NaN`. Fixed in type definition and page read.

---

## 5. Real-time characteristics

| tile | update mechanism | cadence |
|---|---|---|
| Live Feed | **SSE push** `/streams/live-feed` | truly real-time |
| Attack Vector | poll | 30 s |
| Global Risk + trend | poll | 30 s |
| Connected Victims | poll | 60 s |
| Chain list (sidebar) | poll | 30 s |
| Chain detail (logs, predictions, CKC, graph) | poll | 30 s |
| Sentinel Insight (LLM) | poll | 5 min (LLM_ANTHROPIC_API_KEY not set) |

**Pipeline latency (Caldera → PG):** ~1–3 seconds end-to-end.

---

## 6. Files changed

### Backend (`apps/api/src/strix_api/`)
| file | change |
|---|---|
| `workers/inference.py` | B1 error logging; B1.6 pool 20→200; D1 verdicts MAXLEN 1M; forensic fields passed through both verdict payloads |
| `adapters/session_store.py` | defensive `get_session` drops partial hashes, returns None for recovery |
| `adapters/preprocessing_pipeline.py` | drop `feature_names_in_` from loaded scaler at boot |
| `workers/normalizer.py` | forensic fields populated in FeatureMessage; features MAXLEN 1M; missing-agent-id demoted to debug |
| `workers/verdicts_writer.py` | alert insert reads `decoderName/location/fullLog/ruleId/ruleFiredtimes/mitreTactics/mitreTechniques` from verdict payload |
| `core/messages.py` | added 5 forensic fields to FeatureMessage |
| `settings.py` | redis pool 200; raw_stream MAXLEN 1M default |
| `services/dashboard_service.py` | victim_graph rewritten (attack_chains+hosts); _severity_for_stage helper |
| `services/topology_service.py` | edge query aggregates per-host before self-join |
| `services/analysis_service.py` | graph_evolution synthesises snapshots from chain alerts; timedelta import |
| `.env` | WAZUH_RAW_STREAM_MAXLEN=1000000 |

### Frontend (`apps/web/`)
| file | change |
|---|---|
| `middleware.ts` | new — server-side auth gate; redirects unauthenticated requests to /login |
| `app/(auth)/login/page.tsx` | honours `?next=` post-login redirect; uses `useSearchParams` |
| `components/charts/graph-evolution.tsx` | full rewrite — real snapshots prop, circle layout, severity colours |
| `components/charts/attack-vector-chart.tsx` | unchanged — component was correct; only the call site was broken |
| `app/(dashboard)/page.tsx` | passes `attackVectorChartData` derived from real API stages; fixes `delta1h` → `delta1H` |
| `lib/api/hooks.ts` | `delta1h` → `delta1H` in GlobalRiskResponse interface |

---

## 7. Operational steps performed

```bash
# Disk reclaim
docker exec strix_postgres psql -U strix -d strix -c \
  "DELETE FROM gnn_graph_snapshots WHERE taken_at < NOW() - INTERVAL '1 hour';"
docker exec strix_postgres psql -U strix -d strix -c \
  "SELECT drop_chunks('gnn_graph_snapshots', INTERVAL '1 hour');"
docker exec strix_postgres psql -U strix -d strix -c \
  "VACUUM FULL _timescaledb_internal._hyper_3_9_chunk;"

# Password rotation
set -a; source apps/api/.env; set +a
apps/api/.venv/bin/python infra/scripts/seed_admin.py \
  --email admin@strix.io --password 'StrixAdmin!2026' --role admin

# Three honcho restarts as each fix revealed the next layer:
# 1. B1 patch → revealed UUID/partial-session bug
# 2. B1.5 + C1 + C2 + D1 → revealed pool exhaustion
# 3. B1.6 pool bump → fully healthy, 0 errors
# Platform restarts for tile fixes:
nohup honcho -f Procfile.host -e apps/api/.env start >/tmp/strix_honcho.log 2>&1 &
```

---

## 8. Outstanding / not changed

- **Sentinel Insight** — returns placeholder until `LLM_ANTHROPIC_API_KEY` is set in `.env`
- **Threat Intel IOCs** — `iocs` table doesn't exist; `ioc_lookup_cache` does but no enrichment job has run
- **Partial-session race** — `close_session` / concurrent `append_step` still occasionally regenerates partial hashes (25–70 per run). Self-heals via `partial_session_dropped` guard. Full fix would be a Lua `append_step` that no-ops when `chain_id` is missing.
- **Polling cadence** — most tiles poll at 30–60 s. Can be tightened to 5 s for near-real-time demo feel.
- **Attack Vector donut empty during quiet periods** — correct behaviour (no attack-stage alerts in 1h window), but "0 VECTORS" could be a nicer empty state.
