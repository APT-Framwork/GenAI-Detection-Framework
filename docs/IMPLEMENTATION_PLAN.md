# STRIX — Backend + Frontend Implementation Plan

> **Scope:** full plan for wiring the four detection models + DQN agent behind a FastAPI backend, replacing frontend mock data with live feeds, and delivering every platform function listed in the Prompt 3 brief.
> **Source of truth for ML behavior:** [MODELS_REFERENCE.md](./MODELS_REFERENCE.md). For Wazuh↔feature mapping: [WAZUH_MAPPING.md](./WAZUH_MAPPING.md). For transport: [INGESTION_PIPELINE.md](./INGESTION_PIPELINE.md). For MITRE: [mitre_to_ckc.json](./mitre_to_ckc.json).
> **No code in this document.** Schemas, tables, and flows are illustrative, not executable.

---

## 1. Executive Summary

STRIX ingests Wazuh alerts, transforms each alert into the fixed 55-dim feature vector the training pipeline expects, runs four detection models in a fixed dependency order (AE → Transformer; VAE + GNN in parallel), fuses outputs into a 13-dim state vector, and asks a DQN agent which of 5 defensive actions (Monitor / Low Alert / Escalate / Isolate / Block) to take. All model outputs and DQN actions are persisted to Postgres and fanned out to the Next.js dashboard via SSE.

The system is **sequence-based**, not alert-based: the Transformer and GNN require context across time. To honor that, per-host session state (AE latent history, recent alert graph window) lives in Redis and is sharded by `agent_id` so every alert from one host hits the same inference worker. The inference layer is a single Python process per worker that loads all four models + the DQN once at startup — microservice-per-model was rejected because it would have split the AE→Transformer latent hand-off across a network boundary.

Deployment target is Docker Compose on a single VM (confirmed). The stack is: Wazuh manager + Filebeat + Redis (Streams + session-state) + normalizer-worker + inference-worker + FastAPI API + Postgres (with Timescale for alert time-series) + Arq for async jobs (LLM, HIBP, VirusTotal). The rollout is 8 phases; the critical path is Phases 0–3 (foundation → ingestion → inference spine → session state + DQN). Phases 4–7 wire the dashboard widgets to real data and add enrichment. Phase 8 is hardening.

Two open questions must be resolved by the product/security team before Phase 3 finalizes: (a) is the DQN run on every alert or only after a gate, and (b) are `Isolate`/`Block` actions advisory-only or does the system actually cut access. Both are called out in §12.

---

## 2. Non-Negotiable Architectural Constraints

These are structural invariants derived from how the models were trained. The plan respects every one; no phase should violate them.

| # | Constraint | Source |
|:---:|:---|:---|
| C1 | **AE → Transformer latent hand-off.** Transformer consumes AE's 64-dim `mu`. Any deployment shape that splits AE and Transformer across a network hop pays a round-trip per alert. | [MODELS_REFERENCE.md §5.2](./MODELS_REFERENCE.md#52-input) |
| C2 | **Sequence-based processing.** Transformer needs the sequence of AE latents seen so far this episode; GNN needs a graph over the last N minutes of alerts. Per-alert stateless APIs cannot work. | [MODELS_REFERENCE.md §5, §6.7](./MODELS_REFERENCE.md) |
| C3 | **DQN is the decision-maker.** The Dashboard Global Risk formula is an aggregate for humans; the per-alert action comes from the DQN consuming the 13-dim state. | AGENT_ARCHITECTURE.md §5 |
| C4 | **The 55-dim vector is the contract.** Every live alert must be transformed to exactly this schema before any model runs. | [MODELS_REFERENCE.md §2](./MODELS_REFERENCE.md#2-canonical-55-dim-feature-schema) |
| C5 | **Preprocessing artifacts are frozen at training time.** SecBERT tokenizer + base model, two PCA-16 reducers, StandardScaler, GNN metadata pickle — all must be loaded from disk, never refit. | [MODELS_REFERENCE.md §11.1](./MODELS_REFERENCE.md#111--blocking--must-fix-before-inference) |
| C6 | **Column ordering matches training.** `TOP_25_FEATURES` ordering in `data_loader.py` is wrong relative to trained weights; the backend must feed features in the notebook training order. | [MODELS_REFERENCE.md §2.2, §11.1](./MODELS_REFERENCE.md) |
| C7 | **Model loaders have known bugs.** The Transformer loader has wrong `activation` / `norm_first` flags; GNN loader's fallback threshold is wrong; VAE uses a heuristic instead of the fitted calibrator. These must be fixed (or frozen re-trained checkpoints shipped) before inference ships. | [MODELS_REFERENCE.md §11](./MODELS_REFERENCE.md#11-discrepancies--open-questions) |

---

## 3. Architecture Overview

### 3.1 High-level diagram

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                        Single VM / Docker Compose host                         │
│                                                                                │
│   ┌─────────────┐      ┌──────────────────┐                                    │
│   │  Wazuh       │──TCP──▶ Wazuh manager    │                                  │
│   │  agents × N  │ 1514 │  (decoders+rules)│ writes alerts.json                │
│   └─────────────┘      └────────┬─────────┘                                    │
│                                 │ shared volume                                │
│                                 ▼                                              │
│                        ┌─────────────────┐                                     │
│                        │  Filebeat       │ tails alerts.json                   │
│                        └────────┬────────┘                                     │
│                                 │ XADD                                         │
│                                 ▼                                              │
│                  ┌──────────────────────────────┐                              │
│                  │  Redis                       │ streams + hashes + pubsub    │
│                  │  - strix:alerts:raw (stream) │                              │
│                  │  - strix:features:<shard>    │                              │
│                  │  - strix:session:<agent_id>  │                              │
│                  │  - strix:verdicts:out (ps)   │ SSE fan-out                  │
│                  └──┬────────────┬──────────────┘                              │
│                     │            │                                             │
│          XREADGROUP │            │ XREADGROUP                                  │
│                     ▼            ▼                                             │
│     ┌────────────────────┐  ┌──────────────────────────────────────────────┐   │
│     │ normalizer-worker  │  │ inference-worker  (sharded by agent_id)      │   │
│     │  (N replicas,      │  │ loads AE, VAE, Transformer, GNN, DQN once    │   │
│     │   stateless)       │  │ maintains per-agent session state in Redis   │   │
│     │  Wazuh JSON →      │  │ - AE batch inference (size=32 OR 50ms)       │   │
│     │  55-dim vector     │  │ - VAE batch inference                        │   │
│     │  (SecBERT+PCA+     │  │ - Transformer on AE latent sequence          │   │
│     │   scaler)          │  │ - GNN on rolling 60-min graph slice          │   │
│     └─────────┬──────────┘  │ - build 13-dim state → DQN → action          │   │
│               │ XADD        └──────────────────┬───────────────────────────┘   │
│               ▼                                │ XADD + NOTIFY                 │
│     strix:features:<shard>              strix:verdicts + pg NOTIFY             │
│                                                │                               │
│                                                ▼                               │
│                                     ┌──────────────────────┐                   │
│                                     │ Postgres + TimescaleDB│                  │
│                                     │  - alerts             │                  │
│                                     │  - detections         │ (Timescale      │
│                                     │  - dqn_actions        │  hypertable)    │
│                                     │  - attack_chains      │                  │
│                                     │  - gnn_graph_snapshots│                  │
│                                     │  - ioc_lookup_cache   │                  │
│                                     │  - llm_insight_cache  │                  │
│                                     └──────────┬───────────┘                   │
│                                                │                               │
│     ┌──────────────────┐        ┌──────────────┴──────────┐                    │
│     │  FastAPI         │◀──SQL──│  api-server (stateless) │                    │
│     │  /api/v1/...     │        │  + SSE publisher        │                    │
│     │  Pydantic models │        │  + OpenAPI → client SDK │                    │
│     └─────┬────────────┘        └──────────┬──────────────┘                    │
│           │ HTTP/SSE                       │                                   │
│           ▼                                ▼                                   │
│     ┌──────────────────────────────────────────────────────┐                   │
│     │  apps/web (Next.js 14, App Router) + apps/mobile     │                   │
│     └──────────────────────────────────────────────────────┘                   │
│                                                                                │
│     ┌────────────────┐                                                         │
│     │ Arq (async job │ enrichment (HIBP, VirusTotal), LLM insights             │
│     │  queue, Redis) │                                                         │
│     └────────────────┘                                                         │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component responsibilities (one line each)

| Component | Responsibility |
|:---|:---|
| **Wazuh manager** | Terminate agents, decode logs to alerts JSON. (Unchanged from INGESTION_PIPELINE.) |
| **Filebeat** | Tail `alerts.json`, publish to `strix:alerts:raw`. |
| **Redis** | Streams (broker), hashes (per-agent session state), pub/sub (SSE fan-out). |
| **normalizer-worker** | Stateless. Flatten JSON → strip leaky cols → feature-engineer → scale → emit 55-dim vector. |
| **inference-worker** | Stateful (per-agent session). Batch inference AE+VAE+GNN, sequence inference Transformer, assemble 13-dim state, run DQN, emit verdict. |
| **verdicts-writer** | Consume `strix:verdicts`, upsert into Postgres (alerts + detections + dqn_actions + attack_chains). |
| **api-server** | FastAPI. Stateless. Serves dashboard queries + SSE streams. No model code here. |
| **Arq worker** | Async jobs: LLM insight generation, HIBP lookups, VirusTotal lookups, file upload scans. |
| **apps/web** | Next.js dashboard. Consumes REST + SSE. |

### 3.3 Design patterns used (and justified)

| Pattern | Where | Why |
|:---|:---|:---|
| **Hexagonal / Ports & Adapters** | Whole backend. `core/` (domain), `adapters/` (Wazuh, Redis, Postgres, HIBP, VT, LLM, model loaders), `api/` (FastAPI routes). | Keeps the 55-dim feature engineer and the 13-dim state builder unit-testable without FastAPI or Redis. Makes it trivial to swap transports or the DB later. |
| **Repository** | Data access for alerts, detections, attack_chains, IOC cache. | Keeps ORM concerns out of business logic; lets us swap Timescale hypertables for materialized views without rewriting callers. |
| **Adapter** | Wazuh ingestion (`WazuhAlertAdapter`), HIBP / VirusTotal / LLM. | Each external integration exposes a small, typed interface; the circuit breaker wraps the adapter, the adapter doesn't know about it. |
| **Strategy** | Per-alert inference pipeline (AE → VAE+GNN parallel → Transformer → DQN). Each stage is a `PipelineStage` with a fixed `execute(ctx)` contract so ablations / reorderings are one-line changes. | Matches the natural dependency graph. Also makes ablation tests (§9) drop-in. |
| **Circuit Breaker** | HIBP, VirusTotal, LLM. | External APIs will fail. Don't wedge a request queue on a downstream 500. Use `pybreaker` or equivalent; half-open every 30 s. |
| **Outbox** | `detections` and `dqn_actions` tables get written by the verdicts-writer in the **same transaction** as the event that will be SSE-published; the SSE publisher reads new rows via `LISTEN/NOTIFY`. | Guarantees at-least-once SSE delivery even if Redis pubsub drops. |
| **CQRS-lite** | Write path = normalizer → inference → verdicts-writer (row-per-alert). Read path = FastAPI queries precomputed aggregates + Timescale continuous aggregates. | Dashboard widgets (Attack Vector pie, Global Risk over 1h) can't afford per-request full table scans. |
| **Pub/Sub** | Redis pub/sub for SSE fan-out from inference-worker to every api-server replica. | Stateless api-servers can subscribe and fan out to whichever client holds the SSE connection. |
| **Pipeline** | Inference pipeline inside `inference-worker`: AE ▸ (VAE ∥ GNN) ▸ Transformer ▸ state-builder ▸ DQN. | Each stage has a typed input/output; easy to time each stage individually for latency budgets. |
| **Dependency Injection** | FastAPI `Depends()` for DB session, Redis, settings, model registry. | Every unit test supplies fakes. |
| **Factory** | `ModelRegistry.load()` at worker startup — one place knows about `apps/models/*.pth`, fitted PCAs, scaler. | Versioning and warm-up happen in one place. |

### 3.4 Explicit layer boundaries (SOLID / Dependency inversion)

```
┌─────────────────────────────────────────────────────────────────────┐
│  api/          →  depends on services/                              │
│  (FastAPI,        imports Pydantic schemas; no SQL, no torch        │
│   routes,         knowledge)                                        │
│   deps)                                                             │
├─────────────────────────────────────────────────────────────────────┤
│  services/     →  depends on core/ + repositories/ + adapters/      │
│  (use-cases:      e.g. GetDashboardKpis, AckAlert, EnrichIoc        │
│   one class                                                         │
│   per use case)                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  core/         →  NO outward dependencies (pure domain)             │
│  (55-dim          - feature_engineer.py (FeatureEngineerNoLeakage)  │
│   feature         - state_builder.py (13-dim from model outputs)    │
│   engine,         - mitre.py (MITRE→CKC lookup)                     │
│   state           - reward.py (training parity, used for replay)    │
│   builder,        - risk.py (Global Risk formula)                   │
│   enums,          - enums/ (CkcStage, DqnAction, Severity, …)       │
│   constants)                                                        │
├─────────────────────────────────────────────────────────────────────┤
│  repositories/ →  depends on core/ + SQLAlchemy                     │
│                   (AlertRepo, DetectionRepo, AttackChainRepo, …)    │
├─────────────────────────────────────────────────────────────────────┤
│  adapters/     →  depends on core/ (read-only) + external libs      │
│  (external       - wazuh_adapter.py                                 │
│   world)         - hibp_adapter.py (+ CircuitBreaker)               │
│                  - virustotal_adapter.py                            │
│                  - llm_adapter.py (Anthropic SDK)                   │
│                  - model_registry.py (loads .pth, PCAs, scaler)     │
├─────────────────────────────────────────────────────────────────────┤
│  workers/      →  depends on adapters/ + services/ + repositories/  │
│                  - normalizer_worker.py                             │
│                  - inference_worker.py                              │
│                  - verdicts_writer.py                               │
│                  - arq_tasks.py                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Dependency rule: arrows go up-to-down only.** `core/` cannot import from any other layer. `api/` cannot import `torch` or `sqlalchemy`. If a test needs to exercise `state_builder`, it fabricates a `ModelOutputs` dataclass and calls `build_state()` — no FastAPI, no Redis, no Postgres.

### 3.5 Proposed repository layout

```
apps/
├── api/                              ← NEW: this session
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic/                      Postgres migrations
│   ├── src/strix_api/
│   │   ├── main.py                   FastAPI factory
│   │   ├── settings.py               Pydantic BaseSettings
│   │   ├── api/
│   │   │   ├── deps.py               DI providers
│   │   │   ├── errors.py             typed exceptions → HTTP
│   │   │   ├── schemas/              Pydantic response models
│   │   │   │   ├── dashboard.py
│   │   │   │   ├── analysis.py
│   │   │   │   ├── threat_intel.py
│   │   │   │   └── monitoring.py
│   │   │   └── routes/
│   │   │       ├── dashboard.py
│   │   │       ├── analysis.py
│   │   │       ├── threat_intel.py
│   │   │       ├── monitoring.py
│   │   │       ├── alerts.py
│   │   │       ├── streams.py        SSE endpoints
│   │   │       └── health.py
│   │   ├── services/
│   │   │   ├── dashboard_service.py
│   │   │   ├── analysis_service.py
│   │   │   ├── enrichment_service.py
│   │   │   ├── insight_service.py    LLM
│   │   │   └── attack_chain_service.py
│   │   ├── core/
│   │   │   ├── feature_engineer.py   ported from notebook
│   │   │   ├── state_builder.py      13-dim assembly
│   │   │   ├── mitre.py              JSON-driven lookup
│   │   │   ├── risk.py               Global Risk formula
│   │   │   ├── sequence.py           session-sequence logic
│   │   │   └── enums.py
│   │   ├── repositories/
│   │   ├── adapters/
│   │   │   ├── wazuh_adapter.py
│   │   │   ├── model_registry.py     torch .pth + PCA + scaler
│   │   │   ├── redis_adapter.py
│   │   │   ├── hibp_adapter.py
│   │   │   ├── virustotal_adapter.py
│   │   │   └── llm_adapter.py
│   │   ├── workers/
│   │   │   ├── normalizer.py
│   │   │   ├── inference.py
│   │   │   ├── verdicts_writer.py
│   │   │   └── arq_tasks.py
│   │   ├── observability/
│   │   │   ├── logging.py            structlog config
│   │   │   ├── metrics.py            prometheus_client
│   │   │   └── tracing.py            opentelemetry (optional)
│   │   └── fixtures/                 reusable test fixtures
│   │       └── sample_alerts.json
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── contract/
│       └── e2e/
├── models/                           ← ship .pth + PCA + scaler here
│   ├── ae_model.pth
│   ├── vae_model.pth
│   ├── transformer_model.pth
│   ├── gnn_model.pth
│   ├── rl_agent.pth
│   ├── secbert_log_pca.pkl           ← MUST be exported from notebooks (§11)
│   ├── secbert_cmd_pca.pkl           ← same
│   ├── standard_scaler.pkl           ← same
│   ├── gnn_metadata.pkl              ← same
│   └── registry.json                 version + checksum manifest
└── web/
    └── (existing Next.js app — see §11)

infra/
├── docker-compose.yml                extends training compose
├── compose.api.yml                   adds api, workers, postgres, arq
└── prometheus.yml
```

---

## 4. Per-Function Specification

Notation:
- **Source:** which models / data produce the value
- **Endpoint:** HTTP path under `/api/v1/`, method (GET unless noted)
- **Polling vs streaming:** how the frontend consumes it
- **p50 / p99:** latency budget (p50 = median, p99 = 99th percentile)
- **Cache:** key, TTL, invalidation trigger

### 4.1 Dashboard tab

| Function | Source | Endpoint / stream | Response shape (abridged) | Persistence | Cache | p50 / p99 | Frontend component |
|:---|:---|:---|:---|:---|:---|:---|:---|
| **Attack Vector Graph** (pie of CKC distribution since platform start) | Every `detection.predicted_ckc_stage` from all alerts in platform lifetime | `GET /dashboard/attack-vector?window=all\|7d\|24h` | `{ window, totalAlerts, stages: [{ ckcStage, ckcName, count, percent }] }` | Timescale continuous aggregate `ckc_stage_hourly` | Redis `cache:dashboard:attack-vector:{window}`, TTL 30 s, invalidated by pg trigger on each batch insert into `detections` (bumps a cache-gen counter) | 50 / 200 ms | `AttackVectorChart` (exists) |
| **Live Feed** (MITRE techniques + timeline + short explanation per alert) | `alerts.mitre_techniques` + `detections.ckc_stage_name` + Haiku-generated 1-line summary (see §5.14) | `GET /streams/live-feed` (SSE) | Event `alert.new`: `{ alertId, agentName, occurredAt, mitreTechniques, ckcStage, severity, oneLineSummary }` | Hot buffer in Redis list `live-feed:recent` (last 100), Postgres `alerts` | In-process LRU on the Haiku result keyed by SHA-1(`mitreTechniques + decoderName + ruleId`); 1 h TTL. Breaker open → static fallback `"MITRE {tactic}: {technique}"` | 80 ms to first event / 300 ms p99 | `LiveAlertCard` (exists); new SSE hook |
| **AI Sentinel Insight** (Opus-generated insight + remediation over current platform context — see §5.14) | LLM (Opus 4.7) over {last 10 detected techniques, last 3 DQN interventions, current Global Risk, prompt-cached MITRE reference} | `GET /dashboard/sentinel-insight` (JSON) + `POST /dashboard/sentinel-insight/refresh` (enqueues Arq job) | `{ generatedAt, modelVersion, insight, recommendedActions: [{ label, rationale }], confidence, stale? }` | `llm_insight_cache` table, keyed by `hash(input_payload)` | Postgres cache TTL = 5 min; LLM queue dedup by payload hash; breaker open → last cached value with `stale: true` | 150 ms (cache hit) / 4 s (cache miss; runs Arq job, UI shows skeleton) | New `SentinelInsightCard` |
| **Threat Intensity / Global Risk** (`0.4·mean(VAE_prob) + 0.3·max(GNN_node_risk) + 0.2·anomaly_rate + 0.1·risk_growth`) | `detections` table, rolling window | `GET /dashboard/global-risk?window=1h` | `{ window, globalRisk, components: { vaeMeanProb, gnnMaxNodeRisk, anomalyRate, riskGrowth }, delta1h, trend: [{ts, value}] }` | Timescale continuous aggregate `global_risk_minutely` | Redis `cache:dashboard:global-risk:{window}` 30 s TTL | 30 / 120 ms | `CircularProgress` (exists) |
| **Attack Timeline — victims-connected graph** (projection of GNN graph: which hosts are linked through a common attacker/IOC) | GNN `gnn_graph_snapshots` + `detections.gnn_node_risk` aggregated per host | `GET /dashboard/victim-graph?window=1h` | `{ nodes: [{ hostId, hostName, severity, infected, riskScore }], edges: [{ from, to, edgeType, sharedIndicator }] }` | Snapshot rows in `gnn_graph_snapshots` (taken every 5 min) | Redis `cache:dashboard:victim-graph:{window}` 60 s TTL | 80 / 300 ms | New `VictimGraph` component (D3 / react-flow) |
| ~~Cyber Kill Chain Progression~~ | **REMOVED** from Dashboard per brief | n/a | n/a | n/a | n/a | n/a | Remove `KillChainTimeline` from `page.tsx` |

### 4.2 Analysis tab (`attack-analysis/[id]`)

**URL shape:** `id` refers to an `attack_chain_id` (UUID). See §6 for how chains are formed.

| Function | Source | Endpoint | Response shape | Persistence | Cache | p50 / p99 | Frontend |
|:---|:---|:---|:---|:---|:---|:---|:---|
| **Graph Evolution Timeline** (GNN graph snapshots over time for this chain) | `gnn_graph_snapshots` filtered to the chain's hosts | `GET /analysis/chains/{id}/graph-evolution` | `{ chainId, snapshots: [{ ts, nodes, edges }] }` (≤ 24 snapshots) | Existing snapshot table | 5 min TTL | 100 / 400 ms | `GraphEvolution` (exists) |
| **Cyber Kill Chain Progression** (CKC step at which the **DQN** acted, NOT the Transformer) | `dqn_actions` joined to `detections` | `GET /analysis/chains/{id}/ckc-progression` | `{ chainId, stages: [{ ckcStage, enteredAt, dqnAction, actionedAt }] }` | `dqn_actions` | per-chain, invalidated on chain update | 40 / 150 ms | `KillChainProgression` (exists) — pass real data |
| **AI Predictions** (next expected CKC — direct Transformer output) | `detections.transformer_predicted_next_ckc` + `transformer_prediction_confidence` for the last alert in chain | `GET /analysis/chains/{id}/predictions` | `{ currentStage, predictedNextStage, confidence, probabilities: [{ stage, prob }] }` | — | 30 s per chain | 30 / 100 ms | `AIPredictionsPanel` (exists) |
| **Forensic Raw Logs** (live Wazuh alerts for this chain) | `alerts` table + SSE stream filtered by chain | `GET /analysis/chains/{id}/logs?cursor=...` (paged) + `GET /streams/chains/{id}/logs` (SSE) | `{ items: [{ alertId, ts, agentName, rawLog, ruleDescription, decoder, location }], nextCursor }` | `alerts` | — | 60 / 250 ms | `ForensicLogViewer` (exists) + SSE hook |
| **Infection Radius** (% infected machines) | "Infected" = host had ≥1 `dqn_action ≥ ESCALATE` in the chain window OR `detections.ae_anomaly_score` over host-level threshold within chain window. **Exact rule in §6.3.** | `GET /analysis/chains/{id}/infection` | `{ infectedCount, totalCount, percent, infectedHosts: [{ hostId, hostName, firstSeen, currentStage }] }` | Derived on read from `detections` + `dqn_actions` | chain-scoped cache 60 s | 50 / 200 ms | New metric card in `attack-analysis` |
| **Dwell Time** (intrusion-start → isolation time) | `attack_chains.first_malicious_at` → `attack_chains.closed_at` (if closed) or `now()` (if open) | `GET /analysis/chains/{id}/dwell-time` | `{ startedAt, closedAt, durationSeconds, status: "open"\|"closed" }` | `attack_chains` | — | 20 / 80 ms | Existing metric card |

### 4.3 Threat Intel tab

| Function | Source | Endpoint | Response shape | Persistence | Cache | p50 / p99 | Frontend |
|:---|:---|:---|:---|:---|:---|:---|:---|
| **IOC Registry / HIBP lookup** | HaveIBeenPwned (emails), our own IOC table (IPs, hashes) | `GET /threat-intel/iocs?q=...&type=email\|ip\|hash&page=...` | `{ items: [{ indicator, type, reputation: "malicious"\|"suspicious"\|"clean"\|"unknown", source, lastChecked, breachCount? }], page }` | `ioc_lookup_cache` | Postgres cache 24 h for HIBP (per brief's rate limits); Redis negative-result cache 5 min (so a clean IP isn't repeatedly re-looked-up) | 40 / 2 s (first time miss → Arq job) | `threat-intel/page.tsx` IOC table |
| **Compromised Assets** (infected hosts + CKC stage + maliciousness) | Join `hosts` view over `dqn_actions` + `detections` | `GET /threat-intel/compromised-assets` | `{ items: [{ hostId, hostName, ipAddress, currentCkcStage, maxMaliciousProb, lastAction, lastSeen }] }` | continuous aggregate `compromised_assets_view` | 60 s TTL | 40 / 150 ms | Replace hardcoded `compromisedAssets` in `threat-intel/page.tsx` |
| **VirusTotal scan** (on-demand) | VT public API | `POST /threat-intel/virustotal/scan` `{ indicator, type }` | `{ jobId, status: "queued" }` + SSE event later: `{ jobId, status: "complete", result: { malicious: int, suspicious: int, undetected: int, harmless: int, engines: { name: verdict } } }` | `ioc_lookup_cache` row with `source='virustotal'` | Postgres 24 h | 80 ms enqueue / 6 s result | Breach-feed panel + SSE hook |
| **File upload scan** | File → hash (SHA-256) → VT lookup → optional LLM sandbox summary | `POST /threat-intel/files/scan` (multipart) | `{ jobId, status, sha256, size }` + SSE result event | `file_scans` table | by SHA-256 indefinitely (hashes are immutable) | 200 ms upload ack / 8 s VT result | New drag-drop upload tab |

### 4.4 Model Monitoring tab (`ai-engine/page.tsx`)

**Removes:** "Engine Telemetry Stream" (per brief). Adds: explicit cards for AE and Transformer (the current UI only shows GNN/VAE/RL — missing two).

| Function | Source | Endpoint | Response shape | Persistence | Cache | p50 / p99 |
|:---|:---|:---|:---|:---|:---|:---|
| **Per-model metrics** (accuracy, F1, throughput, avg latency) | Prometheus gauges / counters + static metadata in `registry.json` | `GET /monitoring/models` | `{ models: [{ name: "AE"\|"VAE"\|"TRANSFORMER"\|"GNN"\|"DQN", version, weightsSha256, status: "active"\|"degraded", accuracy?, f1?, throughputPerMin, p50LatencyMs, p99LatencyMs, lastHealthCheck }] }` | in-mem metrics + `registry.json` | 10 s TTL | 20 / 80 ms |
| **Composite accuracy gauge** | Weighted average across models | `GET /monitoring/composite-accuracy` | `{ value, computedAt }` | — | 60 s | 15 / 60 ms |
| **Confidence trend (10-day)** | Continuous aggregate over `detections.vae_malicious_prob` and `detections.transformer_prediction_confidence` | `GET /monitoring/confidence-trend?window=10d` | `{ points: [{ ts, aeAnomaly, vaeProb, transformerConfidence, gnnRisk }] }` | `confidence_trend_daily` continuous aggregate | 5 min | 60 / 200 ms |

---

## 5. Architecture-Level Decisions

Each decision gets: **Options** → **Tradeoffs** → **Recommendation** (or explicit "needs confirmation").

### 5.1 Backend framework

- **Option A — FastAPI (Starlette + Pydantic v2 + uvicorn):** native async, auto OpenAPI, typed DI, gigantic ML ecosystem, trivial to co-locate model code.
- **Option B — Litestar:** faster OpenAPI, cleaner DI, smaller community.
- **Option C — Django REST Framework:** batteries included (admin, auth, migrations) but sync-first and heavy.

**Recommend: FastAPI.** Matches the team's presumed Python ML fluency, has the biggest ecosystem for the stack we need (SQLAlchemy async, structlog, Prometheus, OpenTelemetry), and gives us OpenAPI generation for the shared-schema TypeScript package.

### 5.2 Inference service layout (the big one)

- **Option A — Monolithic inference worker (all 4 models + DQN in-process).** Loads `ae_model.pth`, `vae_model.pth`, `transformer_model.pth`, `gnn_model.pth`, `rl_agent.pth` once. Sharded by `agent_id` so session state is worker-local.
- **Option B — Microservice per model.** Four FastAPI services + a gateway.
- **Option C — Triton Inference Server.** NVIDIA's dedicated inference runtime.

**Recommend: A.** Three reasons:
1. **AE→Transformer latent hand-off** (C1) is the critical path. In Option B this is a network round-trip per alert; in Option A it's a Python function call. At a target of p99 < 200 ms end-to-end, we cannot afford 4 extra network hops.
2. **Per-session state** (AE latent sequence for the Transformer, GNN rolling graph) is naturally co-located with the models.
3. Option C's benefits (GPU batching, model ensembling, ONNX) are overkill for CPU inference on a single VM. Revisit if we move to GPU.

**Sharding strategy:** `agent_id % num_workers`. `num_workers = CPU_cores / 2` initially (rough budget: each worker holds ~500 MB model weights + ~200 MB torch activation overhead per concurrent batch, so 2 workers per physical core with HT is fine on modest hardware). All alerts for a given `agent_id` hit the same worker → session state stays local.

### 5.3 Session / episode state management

A single Redis instance handles both the Streams broker and session-state hash space. For inference-worker session state per host:

| Key | Data type | Contents | TTL |
|:---|:---|:---|:---|
| `session:{agent_id}` | Redis Hash | `chain_id, opened_at, last_seen_at, step_count, last_ckc_stage, last_action` | 2 h idle expiry — matches `CHAIN_IDLE_TIMEOUT_MINUTES = 120` (§5.4) |
| `session:{agent_id}:latents` | Redis List (LPUSH, LTRIM to 50) | AE mu vectors (msgpack-encoded float32[64]) for this chain | 2 h idle expiry |
| `gnn:window:{shard_id}` | Redis ZSET scored by ts | alertIds in the rolling 60-min GNN window for this shard | ZREMRANGEBYSCORE every 60 s; plus 90-min hard TTL |
| `gnn:graph:{shard_id}:current` | Redis Hash | serialized `edge_index` + node mapping, rebuilt every 60 s (amortized, not per-alert) | 90 min |

**Why Hash + List (not Stream) for per-session state:** we need O(1) random access to "latest 50 latents for agent N", cheap expiry, and non-durable semantics. A Stream would be overkill and lossy on TTL semantics.

**Recovery on worker restart:** the worker reads `session:{agent_id}` for every active shard on startup. If Redis is down, new episodes start fresh — no replay. Documented as chaos-test expected behavior (§9).

### 5.4 Sequence / episode boundary rule

**Decision (resolved §12 Q2/Q5):**

> **A sequence (attack chain) for host `H` starts when**: (a) `H` has no open chain, AND (b) a new alert arrives with `detection.vae_malicious_prob ≥ CHAIN_OPEN_VAE_THRESHOLD` OR `ae_anomaly_score ≥ CHAIN_OPEN_AE_THRESHOLD`.
>
> **The sequence continues** for every subsequent alert from `H` while (a) `time_since_last_alert ≤ CHAIN_IDLE_TIMEOUT_MINUTES` (**2 hours**) AND (b) no intervention (DQN action ≥ ESCALATE) has been taken.
>
> **The sequence closes** when any of:
> - DQN emits action ≥ ESCALATE (intervention ends the chain — mirrors training semantics).
> - 2 hours with no new alert from `H` (the `CHAIN_IDLE_TIMEOUT_MINUTES` default).
> - A hard max of 50 alerts (matches `APTEnvironment.max_steps`).

Benign-only hosts never open a chain; their alerts are still scored (AE+VAE for Live Feed) but the Transformer is skipped (not enough signal to justify cost).

**Why 2 hours, not 30 min:** the DQN was trained against a Mandiant-derived 11-day dwell-time distribution (`T_DWELL_SECONDS` in `data_loader.py`). A 30-min timeout would fragment slow-burn APTs into many disjoint chains and break Dwell Time reporting. 2 h is the compromise: survives natural attacker inactivity patterns (coffee / meetings / off-hours waits) without bloating session state with stale chains.

**⚠️ Threshold values are preliminary.** `CHAIN_OPEN_VAE_THRESHOLD = 0.5` (sigmoid midpoint) and `CHAIN_OPEN_AE_THRESHOLD = 1.0` are placeholders. The VAE notebook's `probability_calibrators.pkl` and the AE's `recon + 0.1·center_dist` scoring (loader formula, different from the notebook's `recon + β·KL`) mean both numbers must be **recalibrated on a real-stream sample** before Phase 3 freezes them. Phase 2 ticket P2-9 covers this.

### 5.5 Real-time transport: SSE vs WebSocket

- **SSE**: one-way, HTTP-native, auto-reconnect, no client library needed. Works through every proxy/CDN. Browser limit ~6 concurrent SSE streams per domain.
- **WebSocket**: bidirectional, lower overhead per message, but needs upgrade handling, heartbeats, and some proxies strip it.

We only push server→client (live alerts, forensic logs, scan results). **Recommend: SSE.** Simpler, more robust. Each page that streams uses a dedicated endpoint; connection pooling handled by the browser. If we ever need client→server messages (e.g. subscribe/unsubscribe filters), a WebSocket endpoint can be added later without breaking SSE consumers.

### 5.6 Async job queue

- **Arq** (Redis-based, async-native): tiny, integrates with asyncio, Redis is already in the stack.
- **Celery**: mature, many knobs; typically pairs with a broker (Redis/RabbitMQ).
- **RQ**: sync-first, simpler than Celery.

**Recommend: Arq.** No new broker (reuses the Redis we already run), native asyncio (our whole backend is async), and ~400 lines of source — easy to reason about. Celery is heavier than we need on a single VM.

### 5.7 Databases

**Recommend: Postgres 16 + TimescaleDB extension + Redis 7.**

- **Postgres**: `alerts`, `detections`, `dqn_actions`, `attack_chains`, `hosts`, `users`, `ioc_lookup_cache`, `llm_insight_cache`, `file_scans`, `gnn_graph_snapshots`.
- **TimescaleDB**: hypertables on `detections` and `dqn_actions` keyed by `occurred_at` (one week chunks). Continuous aggregates for dashboard widgets.
- **Redis**: streams, session state, Arq queue, cache.

Alternative considered: **ClickHouse for analytics.** Rejected — overkill at our data rate (~ 10 alerts/s sustained, maybe 100/s peaks); Timescale's continuous aggregates cover the dashboard cases. Revisit past 1k alerts/s.

### 5.8 Message bus

Already settled in INGESTION_PIPELINE: Redis Streams. No Kafka/NATS — single-VM deploy doesn't justify the operational cost.

### 5.9 Model artifact loading + versioning

- Every `apps/models/*.pth` + `*.pkl` has a row in `apps/models/registry.json`: `{name, version, weightsSha256, trainedOn, inputSchemaVersion}`.
- On worker startup (`ModelRegistry.load()`):
  1. Compute SHA-256 of each file; fail fast if mismatch.
  2. Instantiate the fixed-architecture loaders (see §5.10) and call `load_state_dict(strict=True)`.
  3. Run a warm-up pass: a synthetic 10-alert sequence through every stage to trigger lazy CUDA / JIT compilation.
  4. Expose current versions at `GET /monitoring/models`.
- Hot swap NOT supported in this session. To deploy a new model: rebuild the worker image with new artifacts; compose rolling restart.

### 5.10 Fixing the loader bugs from MODELS_REFERENCE §11

The API package owns **vendored, fixed copies** of the four loader classes in `apps/api/src/strix_api/adapters/model_loaders/`, with explicit fixes:
- `AutoencoderLoader`: `LeakyReLU(0.2)` matches training.
- `TransformerCKCPredictor`: `activation='gelu', norm_first=True`, `input_projection` = `Linear → LayerNorm → ReLU → Dropout(0.1)`.
- `VAELoader`: loads the pickled `probability_calibrators.pkl` (wired through as the source of `malicious_probability`).
- `GNNLoader`: reads threshold from `gnn_metadata.pkl`; raises at startup if pickle absent (no silent fallback to 0.918).
- **Feature column order:** `core/feature_engineer.py` emits a fixed-order 55-dim vector using the notebook training order (23 individuals → 16 log_secbert → 16 cmd_secbert). The upstream `data_loader.FEATURE_COLUMNS` is explicitly NOT used.

### 5.11 Observability stack

- **Logging:** structlog → JSON lines to stdout → Docker log driver (or Loki in later phase). Every log line has the standard fields listed in §8.1.
- **Metrics:** prometheus_client → `/metrics` endpoint. Prometheus container scrapes every 15 s.
- **Tracing:** OpenTelemetry OTLP → Jaeger (optional, Phase 8). Span boundaries: HTTP request, pipeline stage, model inference, external API call, DB transaction.

### 5.12 Security

| Concern | Decision |
|:---|:---|
| Inter-service auth | mTLS is overkill on a single-VM compose. We rely on the compose network not being exposed. |
| User auth (frontend) | Session cookies + JWT, short-lived (15 min) access token + 7 d refresh. Single admin account in Phase 0; proper user store in Phase 8. |
| Secrets | `.env` file read once by Pydantic `Settings`. **No secret values in git**; commit `.env.example` only. API keys (HIBP, VT, Anthropic) live in the `.env`. Future: external secret manager. |
| Input validation | Every external input (Wazuh alerts, API requests, file uploads) parses through a Pydantic model; reject on schema failure. File uploads are size-capped (10 MB) and type-sniffed. |
| Rate limiting | `slowapi` middleware. Global 100 req/s per IP; 10 req/min per authed user for `POST /threat-intel/files/scan`. |
| API key rotation | Rotating HIBP/VT/LLM keys = restart API container. Long-lived credentials stored only in `.env` for now. |

### 5.13 Configuration management

One `Settings` class (Pydantic v2 `BaseSettings`), read from `.env` at startup. Hierarchical: `AppSettings { Database, Redis, ModelRegistry, Wazuh, ThreatIntel, Llm, Observability }`. Every component DI's `Settings`; nothing reads env vars directly.

### 5.14 LLM strategy — two models, one adapter (resolved §12 Q10)

There are two LLM workloads with opposite cost/latency profiles. Both flow through **one `LlmAdapter`** with two typed methods; different Anthropic model IDs per call.

| Workload | Model | Why | Cache |
|:---|:---|:---|:---|
| **Sentinel Insight** (Dashboard card — deep analysis of ~10 techniques + last 3 interventions + current Global Risk) | **Claude Opus 4.7** | Reasoning-heavy; infrequent call (5-min result cache); ~1–4k output tokens | `cache_control` on the static system prefix (system prompt + MITRE ref + attack-pattern library) — every call is a cache hit on that prefix. Result cached 5 min in `llm_insight_cache`. |
| **Per-alert 1-line summary** (Live Feed card — "APT-29 signature match, spear-phishing vector on HR VLAN.") | **Claude Haiku 4.5** | High volume (one per alert surfaced to Live Feed), latency-sensitive, cheap | In-process LRU keyed by SHA-1(`mitreTechniques + decoderName + ruleId`) — most alerts repeat patterns. 1 h TTL. |

Both use **prompt caching** via the Anthropic SDK. Opus's system prefix (MITRE reference + instructions + few-shot examples) is cached once; each request pays only for the per-alert delta. Haiku calls are short enough that caching is limited to the LRU on the result side.

**Failure behavior** (both workloads):
- `LlmAdapter` wraps calls in `pybreaker` circuit breaker (5 failures in 60 s → open → 30 s half-open).
- Breaker open → Sentinel Insight returns last cached value with a `stale: true` flag; Live Feed summary falls back to a static one-liner (`"MITRE {tactic}: {technique}"`).
- UI shows a `DegradedModeBanner` when any LLM breaker is open.

---

## 6. Data Model

### 6.1 Naming conventions (apply everywhere)

| Convention | Value |
|:---|:---|
| DB table names | `snake_case`, plural (`alerts`, `detections`) |
| DB column names | `snake_case` |
| Python class names | `PascalCase` |
| Python variables / functions | `snake_case` |
| TypeScript types | `PascalCase` |
| TypeScript variables | `camelCase` |
| API wire format (JSON field names) | `camelCase` |
| API paths | `kebab-case` under `/api/v1/` |
| Enum values on the wire | UPPER_SNAKE_CASE strings (`ACTION_ESCALATE`) |
| Enum values in DB | same (persist as text) |
| Timestamps | `TIMESTAMP WITH TIME ZONE` in DB; ISO-8601 UTC strings on the wire (e.g. `"2026-04-17T08:34:12.107Z"`) |
| CKC stage | integer `0..7` on the wire AND in DB. Use `ckcStage` (wire) / `ckc_stage` (DB). Separate display field `ckcStageName` when needed. |
| Identifier terminology | `alertId` (the Wazuh `_source.id`, string) / `agentId` (Wazuh `agent.id`, string) / `hostId` (our own UUID; 1:1 with agent but stable across Wazuh re-registrations) / `chainId` (UUID) |
| Severity levels | `"critical" \| "high" \| "medium" \| "low" \| "info"` (already in frontend `types/index.ts`) |
| DQN action names | `"MONITOR" \| "LOW_ALERT" \| "ESCALATE" \| "ISOLATE_HOST" \| "BLOCK_USER_IP"` on the wire; `0..4` in DB |
| Primary keys | UUID v7 (sortable by creation) except `alerts.alert_id` which is the Wazuh native string ID |
| Common columns | Every table has `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`. Mutable tables also `updated_at`. |
| Soft-delete | We do NOT soft-delete; hard delete + audit log. |

Pydantic response models use `alias_generator=to_camel, populate_by_name=True` so snake_case python ↔ camelCase JSON is mechanical.

### 6.2 Postgres schema (abridged)

```
hosts
  host_id                UUID PK
  agent_id               TEXT UNIQUE NOT NULL        -- Wazuh agent.id
  agent_name             TEXT NOT NULL
  ip_address             INET
  is_manager             BOOLEAN NOT NULL DEFAULT FALSE
  first_seen_at          TIMESTAMPTZ NOT NULL
  last_seen_at           TIMESTAMPTZ NOT NULL
  created_at, updated_at TIMESTAMPTZ

alerts  (TimescaleDB hypertable, chunk = 1 day on occurred_at)
  alert_id               TEXT PK                    -- Wazuh _source.id
  host_id                UUID REFERENCES hosts
  chain_id               UUID NULL REFERENCES attack_chains
  occurred_at            TIMESTAMPTZ NOT NULL       -- _source.@timestamp
  decoder_name           TEXT
  location               TEXT
  full_log               TEXT
  rule_id                TEXT
  rule_firedtimes        INT
  mitre_tactics          TEXT[] NOT NULL DEFAULT '{}'
  mitre_techniques       TEXT[] NOT NULL DEFAULT '{}'
  ckc_stage              SMALLINT NULL              -- 0..7, derived via MITRE→CKC at ingest
  raw_jsonb              JSONB NOT NULL             -- flattened Wazuh doc
  created_at             TIMESTAMPTZ

detections  (TimescaleDB hypertable, chunk = 1 day on occurred_at)
  alert_id               TEXT PK REFERENCES alerts
  occurred_at            TIMESTAMPTZ NOT NULL
  host_id                UUID NOT NULL
  chain_id               UUID NOT NULL
  step_in_chain          INT NOT NULL               -- 0-indexed
  -- 55-dim features are NOT stored inline (blows up storage); kept in Redis only during chain
  -- Model outputs:
  ae_anomaly_score       REAL
  ae_recon_error         REAL
  vae_malicious_prob     REAL
  vae_uncertainty        REAL
  transformer_pred_ckc   SMALLINT
  transformer_confidence REAL
  gnn_node_risk          REAL
  gnn_neighbor_risk      REAL
  gnn_risk_growth        REAL
  state_vector           REAL[13]                   -- pgvector optional later
  model_versions         JSONB                      -- {"ae":"v1","vae":"v1","transformer":"v1","gnn":"v1"}
  created_at             TIMESTAMPTZ

dqn_actions
  action_id              UUID PK
  alert_id               TEXT NOT NULL REFERENCES alerts
  chain_id               UUID NOT NULL
  host_id                UUID NOT NULL
  decided_at             TIMESTAMPTZ NOT NULL
  action                 SMALLINT NOT NULL          -- 0..4
  action_name            TEXT NOT NULL              -- MONITOR|LOW_ALERT|ESCALATE|ISOLATE_HOST|BLOCK_USER_IP
  q_values               REAL[5] NOT NULL
  ckc_stage_at_decision  SMALLINT NOT NULL
  requires_approval      BOOLEAN NOT NULL           -- TRUE for ISOLATE_HOST/BLOCK_USER_IP when AUTO_RESPONSE_ENABLED=false
  applied                BOOLEAN NOT NULL DEFAULT FALSE
  applied_at             TIMESTAMPTZ
  applied_by             UUID NULL REFERENCES users  -- analyst who clicked "Apply", NULL if auto-applied
  rejected_at            TIMESTAMPTZ NULL
  rejected_by            UUID NULL REFERENCES users

attack_chains
  chain_id               UUID PK
  host_id                UUID NOT NULL
  opened_at              TIMESTAMPTZ NOT NULL
  closed_at              TIMESTAMPTZ NULL
  close_reason           TEXT NULL                  -- "INTERVENTION"|"IDLE_TIMEOUT"|"MAX_STEPS"
  first_malicious_at     TIMESTAMPTZ NOT NULL
  max_ckc_stage          SMALLINT NOT NULL DEFAULT 0
  max_vae_prob           REAL NOT NULL DEFAULT 0
  intervention_action_id UUID NULL REFERENCES dqn_actions
  step_count             INT NOT NULL DEFAULT 0
  status                 TEXT NOT NULL DEFAULT 'open'   -- 'open'|'closed'

gnn_graph_snapshots  (TimescaleDB hypertable, chunk = 1 day)
  snapshot_id            UUID PK
  shard_id               INT NOT NULL
  taken_at               TIMESTAMPTZ NOT NULL
  node_count             INT
  edge_count             INT
  nodes                  JSONB                      -- [{hostId, riskScore, severity, infected}]
  edges                  JSONB                      -- [{from, to, edgeType, sharedIndicator}]

ioc_lookup_cache
  indicator              TEXT NOT NULL
  indicator_type         TEXT NOT NULL              -- "ip"|"email"|"domain"|"hash"
  source                 TEXT NOT NULL              -- "hibp"|"virustotal"|"local"
  reputation             TEXT NOT NULL              -- "malicious"|"suspicious"|"clean"|"unknown"
  payload                JSONB NOT NULL             -- raw response
  checked_at             TIMESTAMPTZ NOT NULL
  expires_at             TIMESTAMPTZ NOT NULL
  PRIMARY KEY (indicator, indicator_type, source)

llm_insight_cache
  payload_hash           TEXT PK                    -- sha256 of input
  generated_at           TIMESTAMPTZ NOT NULL
  model_version          TEXT NOT NULL
  insight                TEXT NOT NULL
  recommended_actions    JSONB NOT NULL
  expires_at             TIMESTAMPTZ NOT NULL

file_scans
  scan_id                UUID PK
  sha256                 TEXT UNIQUE NOT NULL
  filename               TEXT NOT NULL
  size_bytes             BIGINT NOT NULL
  uploaded_at            TIMESTAMPTZ NOT NULL
  uploaded_by            UUID NULL
  vt_result              JSONB NULL
  vt_scanned_at          TIMESTAMPTZ NULL
  status                 TEXT NOT NULL              -- "queued"|"scanning"|"complete"|"error"
```

**DQN-action application semantics (resolved §12 Q3):**

| `action_name` | `requires_approval` | `applied` at insert time | Notes |
|:---|:---:|:---:|:---|
| `MONITOR` | FALSE | TRUE | no-op, just logged |
| `LOW_ALERT` | FALSE | TRUE | auto-emitted to SOC notification channel |
| `ESCALATE` | FALSE | TRUE | auto-emitted to SOC queue + email/webhook |
| `ISOLATE_HOST` | `!AUTO_RESPONSE_ENABLED` | `AUTO_RESPONSE_ENABLED` | advisory by default; UI shows "Apply" + "Reject"; Phase-8+ flag enables auto-apply after shadow-mode validation |
| `BLOCK_USER_IP` | `!AUTO_RESPONSE_ENABLED` | `AUTO_RESPONSE_ENABLED` | same |

The `AUTO_RESPONSE_ENABLED` env flag is **FALSE in all environments for 1.0**. Flipping it requires (a) pentest sign-off, (b) ≥ N weeks of shadow-mode precision data exceeding an agreed threshold, (c) per-host allow-list excluding production-critical assets, (d) immediate kill switch. Not in 1.0 scope.

**Continuous aggregates (Timescale):**

- `ckc_stage_hourly`: `time_bucket('1 hour', occurred_at)`, group by `ckc_stage`, count(*). Refreshes every 5 min, lag 15 min.
- `global_risk_minutely`: pre-computes the components of the Global Risk formula over a 1-min bucket.
- `confidence_trend_daily`: daily averages of `vae_malicious_prob`, `ae_anomaly_score`, `transformer_confidence`, `gnn_node_risk`.
- `compromised_assets_view`: materialized, refreshed every 30 s, joining `dqn_actions` (max ACTION, last_seen) with `detections` (max `vae_malicious_prob`).

### 6.3 Infection Radius — exact rule

A host `H` is **infected** at time `t` relative to chain `C` iff:
- `H` is in `C.hosts` (any alert in `C` originated from `H`), AND
- there exists an alert on `H` within `[C.opened_at, t]` such that either:
  - `detections.vae_malicious_prob ≥ 0.7` OR
  - A `dqn_actions.action ≥ ACTION_ESCALATE` was emitted for an alert on `H`.

`infectionPercent = infected_host_count / total_monitored_host_count`.

**Constants** (`core/constants.py`):
- `INFECTION_VAE_PROB_THRESHOLD = 0.7`
- `CHAIN_OPEN_VAE_THRESHOLD = 0.5`   ⚠️ **preliminary — recalibrate in Phase 2 P2-9**
- `CHAIN_OPEN_AE_THRESHOLD = 1.0`    ⚠️ **preliminary — recalibrate in Phase 2 P2-9** (notebook Youden-J used a different score formula; see §5.4)
- `CHAIN_IDLE_TIMEOUT_MINUTES = 120` (2 h — resolved §12 Q5; justification in §5.4)
- `CHAIN_MAX_STEPS = 50`
- `GNN_WINDOW_MINUTES = 60`
- `GNN_SNAPSHOT_INTERVAL_SECONDS = 300`
- `GLOBAL_RISK_WINDOW_MINUTES = 60` (resolved §12 Q4; widget exposes 15m / 1h / 24h / 7d / all selectors, same formula different window)
- `LLM_SENTINEL_RESULT_TTL_SECONDS = 300`
- `LLM_LIVE_FEED_SUMMARY_CACHE_SIZE = 10000`

### 6.4 Redis key schema

| Key pattern | Type | Purpose | TTL |
|:---|:---|:---|:---|
| `strix:alerts:raw` | Stream | Wazuh → normalizer | `MAXLEN ~ 100000` |
| `strix:features:{shard}` | Stream | Normalizer → inference-worker (sharded) | `MAXLEN ~ 50000` |
| `strix:verdicts` | Stream | Inference-worker → verdicts-writer | `MAXLEN ~ 100000` |
| `strix:sse:live-feed` | Pub/Sub channel | Inference → api-server SSE publishers | n/a |
| `strix:sse:chain:{chainId}` | Pub/Sub | Per-chain forensic log stream | n/a |
| `session:{agentId}` | Hash | Episode state | 2 h idle (`CHAIN_IDLE_TIMEOUT_MINUTES`) |
| `session:{agentId}:latents` | List (LTRIM 50) | AE latents in this chain | 2 h idle |
| `gnn:window:{shardId}` | ZSET by ts | Alert IDs in rolling 60-min window | 90 min TTL |
| `gnn:graph:{shardId}:current` | Hash | Serialized graph (edge_index) | 90 min TTL |
| `cache:dashboard:{widget}:{window}` | String (JSON) | Dashboard response cache | 30–60 s |
| `cache:ioc:negative:{indicator}` | String | Negative-cache flag | 5 min |
| `arq:queue:default` | Stream | Arq job queue (managed by library) | n/a |

### 6.5 Message schemas (stream payloads)

All stream messages are MessagePack-encoded on the wire. Pydantic models in `core/messages.py`:

```
RawAlertMessage
  alertId: str
  ingestedAt: str (ISO-8601)
  rawJson: dict              # flattened Wazuh doc (no _index, _id, _version, _score)

FeatureMessage
  alertId: str
  agentId: str
  hostId: UUID
  occurredAt: str
  featureVector: list[float]         # 55 floats, fixed order
  schemaVersion: Literal["v1"]

VerdictMessage
  alertId: str
  chainId: UUID
  stepInChain: int
  occurredAt: str
  aeAnomalyScore: float
  aeReconError: float
  aeLatent: list[float]              # 64 floats (kept in message for verdicts-writer if debug flag on)
  vaeMaliciousProb: float
  vaeUncertainty: float
  transformerPredCkc: int
  transformerConfidence: float
  gnnNodeRisk: float
  gnnNeighborRisk: float
  gnnRiskGrowth: float
  stateVector: list[float]           # 13 floats
  dqnAction: int
  dqnActionName: str
  qValues: list[float]
  modelVersions: dict[str, str]
```

---

## 7. Performance & Optimization Plan

### 7.1 Latency budgets

End-to-end (Wazuh writes alert → DQN action persisted):

| Stage | p50 | p99 | Notes |
|:---|:---:|:---:|:---|
| Filebeat → Redis Streams | 10 ms | 80 ms | Filebeat tails at 100 ms poll interval worst case |
| Normalizer-worker (feature engineering) | 35 ms | 120 ms | SecBERT is the long pole — see §7.2 |
| Inference-worker (all 4 models + DQN) | 40 ms | 150 ms | see §7.3 |
| Verdicts-writer (Postgres INSERT) | 8 ms | 40 ms | batched every 50 ms |
| **End-to-end** | **~100 ms** | **~400 ms** | |

API endpoints (see §4 tables for per-endpoint budgets). Typical dashboard widgets 30–80 ms p50 / 200–300 ms p99 (all cached reads). LLM-backed `sentinel-insight` is the exception — 4 s p99 on cache miss.

### 7.2 Caching map

| Cache | Where | TTL | Invalidation | Rationale |
|:---|:---|:---:|:---|:---|
| SecBERT embeddings | In-process LRU (`functools.lru_cache(maxsize=10000)`) keyed by SHA-1(text) | process lifetime | n/a | Wazuh emits many identical `full_log` strings (same decoder firing). Big hit-rate win on feature-engineering p50. |
| SecBERT → PCA result | Piggy-backs on the embedding cache (PCA is cheap). | same | n/a | |
| Normalized feature vector | NOT cached — each alert is unique once you include timestamp-derived features (`hour_of_day`, etc.). | — | — | Caching here would hurt hit-rate and bloat RAM. |
| Model inference results | NOT cached per-alert — same reason; every alert's 55-dim vector differs. | — | — | |
| Dashboard widgets (attack-vector, global-risk, victim-graph) | Redis `cache:dashboard:...` | 30–60 s | bumped generation counter on `detections` insert | Widgets read-heavy, tolerant of 30 s staleness |
| HIBP lookup | Postgres `ioc_lookup_cache` (positive) + Redis `cache:ioc:negative:...` (clean-result short cache) | 24 h positive, 5 min negative | on-demand refresh | HIBP has strict rate limits (1 req/1.5 s free tier, paid plans 10/s) |
| VirusTotal lookup | Postgres `ioc_lookup_cache` | 24 h | on-demand | VT free tier = 4 req/min |
| LLM insight | Postgres `llm_insight_cache` keyed by SHA-256 of input payload | 5 min | on-demand refresh | Keeps "insight" fresh but not regenerated every poll |
| MITRE→CKC lookup | In-process dict loaded from `mitre_to_ckc.json` once | process lifetime | n/a | Pure data |
| Model weights + preprocessing artifacts | In-process, loaded at startup | process lifetime | n/a | Never reload per-request |
| OpenAPI schema → TypeScript client | Build-time | on schema change | Regenerated in CI | Not a runtime cache; called out for completeness |

### 7.3 Batching strategy (model inference)

Each inference-worker runs a micro-batcher per model. Batch is flushed when **either** size or time threshold hits:

| Model | Max batch size | Max wait | Reason |
|:---|:---:|:---:|:---|
| AE | 32 | 20 ms | Cheap forward; bigger batches have diminishing returns on CPU |
| VAE | 32 | 20 ms | Same |
| GNN | (graph-level, not alert-level) | 1/60 s | Rebuild rolling-window subgraph once per minute; score all nodes in one call |
| Transformer | 8 | 30 ms | Variable-length sequences; padding+attention-mask |
| DQN | 16 | 10 ms | Tiny MLP, cheap to run; batch anyway to keep GPU utilization sane if we migrate later |

The batcher uses an `asyncio.Queue` with a background task that wakes on `asyncio.wait_for(queue.get(), timeout=max_wait_ms)` and drains up to `max_batch_size` items before firing the model.

### 7.4 Model load-once policy

Every worker instantiates `ModelRegistry.load()` in its startup hook. Models are `torch.nn.Module.eval()` + `torch.inference_mode()` wrapped. **No lazy loading** inside the request path. Warm-up runs a synthetic 10-alert sequence through every stage so the first real alert doesn't pay JIT/BN stats cost.

### 7.5 Async vs sync

| Operation | Kind | Where it runs |
|:---|:---|:---|
| HTTP handlers | async | FastAPI event loop |
| DB (asyncpg via SQLAlchemy 2 async) | async | Event loop |
| Redis (aioredis / redis.asyncio) | async | Event loop |
| External APIs (HIBP, VT, LLM) via httpx | async | Event loop |
| Model inference (torch) | blocking CPU-bound | `asyncio.to_thread()` / dedicated thread pool (size = cpu_count) |
| SecBERT encode | blocking CPU-bound | thread pool |
| File SHA-256 hashing | blocking CPU-bound | thread pool |
| GNN graph rebuild | blocking CPU-bound | dedicated background asyncio task (not per-request) |

### 7.6 Backpressure

- **Redis Streams MAXLEN = 100000** on `strix:alerts:raw`. If normalizer-workers fall behind, Filebeat keeps publishing but Redis trims the oldest — **we prefer losing old alerts over OOM**.
- Metric `strix_stream_depth{stream}` alerts if any stream depth > 10000 for > 30 s.
- **Inference worker queue:** per-shard `asyncio.Queue(maxsize=200)`. Full queue → drop oldest with a counter increment; log WARN.
- **DB writer:** batched inserts every 50 ms OR 500 rows, whichever first. Circuit breaker: if DB unavailable for > 10 s, writer stops consuming from `strix:verdicts` (backs up to Redis MAXLEN, trims oldest).
- **API rate limiting:** `slowapi` — 100 req/s per IP, 10/min for `POST /threat-intel/files/scan`.
- **SSE:** per-connection queue maxsize 100; drop client if it can't drain.

### 7.7 Connection pools

| Pool | Size | Notes |
|:---|:---:|:---|
| Postgres (SQLAlchemy async) | 10 per API replica, 5 per worker | `pool_size=10, max_overflow=5, pool_timeout=2s, pool_recycle=300s` |
| Redis | 20 per process | `ConnectionPool(max_connections=20)` |
| httpx (HIBP, VT, LLM) | 20 globally, 5 per host | `httpx.AsyncClient(limits=Limits(max_connections=20, max_keepalive_connections=5))` |
| Torch thread pool | `cpu_count()` | set in `torch.set_num_threads()` at worker start |

### 7.8 Vectorization

Feature engineering operates on one alert at a time in the normalizer (low batch latency > throughput), but every numerical / binary flag uses vectorized numpy/pandas primitives for repeated string scans (compiled regex, `re.compile` cached). SecBERT encode is batched when normalizer sees `≥ 16` queued alerts (see §7.3).

---

## 8. Security & Observability Plan

### 8.1 Logging (structured)

Every log line (JSON) carries:

```
ts, level, logger, service, host, pid,
traceId, spanId,                  # OpenTelemetry correlation
alertId?, chainId?, hostId?,       # request-scope keys
message, extra{...}
```

- `structlog.contextvars.bind_contextvars(alert_id=...)` at pipeline entry.
- Unhandled exceptions log full stack with `exc_info=True`.
- No PII in logs (usernames, IPs of srcuser/srcip are truncated to `/24` for IPv4).

### 8.2 Metrics (Prometheus)

| Metric | Type | Labels |
|:---|:---|:---|
| `strix_alerts_ingested_total` | Counter | `source` (`wazuh`) |
| `strix_normalizer_duration_seconds` | Histogram | stage (`parse`, `flatten`, `secbert`, `pca`, `scale`) |
| `strix_inference_duration_seconds` | Histogram | `model` (`ae`, `vae`, `transformer`, `gnn`, `dqn`) |
| `strix_inference_batch_size` | Histogram | `model` |
| `strix_stream_depth` | Gauge | `stream` |
| `strix_session_active_count` | Gauge | — |
| `strix_attack_chain_opened_total` | Counter | — |
| `strix_attack_chain_closed_total` | Counter | `close_reason` |
| `strix_dqn_action_total` | Counter | `action_name` |
| `strix_external_api_duration_seconds` | Histogram | `api` (`hibp`, `virustotal`, `llm`) |
| `strix_external_api_errors_total` | Counter | `api`, `error_kind` |
| `strix_cache_hits_total` / `strix_cache_misses_total` | Counter | `cache` |
| `strix_sse_clients_active` | Gauge | `endpoint` |
| `http_request_duration_seconds` | Histogram | `method`, `path`, `status` |

### 8.3 Tracing

Phase 1 optional, Phase 8 mandatory. Spans:
- `api.{route}` per HTTP request
- `pipeline.normalizer` → child spans `parse`, `secbert`, `pca`, `scale`
- `pipeline.inference` → child spans `ae`, `vae`, `transformer`, `gnn`, `state_builder`, `dqn`
- `db.{operation}`, `redis.{cmd}`, `http.{adapter}`

`traceId` propagated via Redis Stream entry ID → copied into the next stage's span.

### 8.4 Security checklist (Phase-gated)

- **Phase 0:** `.env` pattern, no secrets in git, Docker network isolation, Redis password set.
- **Phase 2:** Input validation on Wazuh JSON (Pydantic), drop malformed alerts, size-cap stream messages.
- **Phase 4:** User auth, session cookies, CSRF protection (double-submit token), rate limiting on auth endpoints.
- **Phase 6:** File upload sanitization (MIME sniffing, size limits, malware quarantine), VT key rotation doc.
- **Phase 8:** Full penetration test (scope = the API), dependency CVE scan (`pip-audit`, `npm audit`), secret rotation runbook.

---

## 9. Testing Plan

### 9.1 Test matrix

Columns: **Unit** / **Integration** / **Contract** / **E2E** / **Performance** / **Regression** / **Chaos**.

| Component | U | I | C | E | P | R | Ch | Notes |
|:---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:---|
| `core/feature_engineer.py` | ✅ | ✅ | — | — | ✅ | ✅ | — | SecBERT + PCA + binary flags; regression = fixture-based output-diff |
| `core/state_builder.py` | ✅ | — | — | — | — | — | — | 13-dim vector assembly with mocked model outputs |
| `core/mitre.py` | ✅ | — | — | — | — | — | — | Every rule in `mitre_to_ckc.json` |
| `core/risk.py` | ✅ | — | — | — | — | — | — | Global Risk formula |
| `core/sequence.py` | ✅ | ✅ | — | — | — | — | — | Chain open/close logic with time-travel fixtures |
| Model loaders (AE/VAE/Transformer/GNN/DQN) | ✅ | ✅ | — | — | ✅ | ✅ | — | Known-input → known-output snapshots (regression); SHA-256 check (unit) |
| Normalizer-worker | ✅ | ✅ | — | ✅ | ✅ | — | ✅ | Chaos = Redis down, malformed alerts, SecBERT stalls |
| Inference-worker | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | Chaos = session Redis down, model load fail; E2E = replay real attack sequence |
| Verdicts-writer | ✅ | ✅ | — | ✅ | ✅ | — | ✅ | Chaos = Postgres down → retries/queues |
| Repositories | ✅ | ✅ | — | — | — | — | — | Fake DB (SQLAlchemy `async`) |
| Service layer | ✅ | ✅ | — | — | — | — | — | |
| FastAPI routes | — | ✅ | ✅ | ✅ | ✅ | — | — | Contract = OpenAPI schema ↔ generated TS client |
| SSE endpoints | — | ✅ | ✅ | ✅ | ✅ | — | ✅ | Chaos = client slow reader, backpressure |
| HIBP / VT / LLM adapters | ✅ | ✅ | — | — | — | — | ✅ | Chaos = HTTP 429, 5xx, timeouts; circuit breaker trips |
| Arq tasks | ✅ | ✅ | — | — | — | — | — | |
| Frontend components | ✅ (Vitest + RTL) | — | ✅ | ✅ (Playwright) | — | — | — | |
| Full pipeline | — | — | — | ✅ | ✅ | ✅ | ✅ | Replay fixture on every release |

### 9.2 Test strategies by kind

**Unit.** pytest + pytest-asyncio. `core/` has zero external dependencies — these tests run in milliseconds. Pydantic models: property-based tests (`hypothesis`) for serialization round-trips.

**Integration.** pytest + `testcontainers` (real Postgres + Redis in Docker). Every test starts with `alembic upgrade head` on a clean schema. No shared state between tests.

**Contract.** Generate OpenAPI schema on backend build; `openapi-typescript` generates the TS client in `apps/web/lib/api-types.ts`. CI fails if the committed client is stale. Additionally `schemathesis` hits every endpoint with property-based fuzzing.

**E2E.** Two flavors:
1. **Backend E2E:** docker-compose-up of the whole backend, feed synthetic Wazuh alerts via Filebeat stub, assert Postgres rows + SSE events.
2. **Full-stack E2E:** Playwright against `apps/web` + running backend. Asserts dashboard widget values match seeded DB state.

**Performance.** `locust` or `k6` load tests against the backend. Targets:
- Sustained 50 alerts/s end-to-end within latency budget for 10 min.
- Burst 500 alerts/s for 30 s; backpressure kicks in, no data loss, budget recovers within 1 min.
- API: 200 rps on `/dashboard/*` endpoints, p99 < 500 ms.

**Regression.** A fixed fixture of 100 representative alerts in `apps/api/tests/fixtures/regression/alerts.jsonl` + expected model outputs in `expected_outputs.jsonl`. CI runs the full pipeline against these on every PR and diffs within numerical tolerance (`rtol=1e-4` for model outputs). Guards against accidental model swaps, preprocessing drift, loader-bug re-introduction.

**Chaos.** `toxiproxy` between components. Scenarios:
- Redis unavailable: workers retry with exponential backoff; API returns degraded-mode response (empty Live Feed + banner).
- Postgres unavailable: verdicts-writer buffers to disk (SQLite WAL), drains on recovery.
- HIBP/VT down: circuit breaker trips; cached results served; "Threat Intel enrichment unavailable" banner on Threat Intel tab.
- Inference worker killed mid-batch: in-flight batch re-delivered via Redis Stream pending-entries-list (PEL) within 5 s.

### 9.3 Test infrastructure

- **pytest**, **pytest-asyncio**, **pytest-cov**, **hypothesis**, **testcontainers**, **respx** (httpx mocking), **schemathesis**.
- **Frontend:** **Vitest** + **@testing-library/react** for component tests, **Playwright** for E2E.
- **Fixtures:**
  - `apps/api/tests/fixtures/alerts/` — 50 canonical alerts covering every decoder and CKC stage.
  - `apps/api/tests/fixtures/sequences/` — 10 attack chains + 10 benign chains.
  - Shared with the training notebooks so the regression set doubles as model-drift guard.
- **CI (GitHub Actions or similar):**
  - `on: pull_request` — unit + integration + contract + frontend component tests (< 10 min).
  - `on: merge to main` — + E2E + regression (< 30 min).
  - `on: schedule (nightly)` — + performance + chaos (up to 90 min).
- **Coverage targets:**
  - `core/` and `adapters/model_loaders/`: **≥ 95%** line.
  - `services/` and `workers/`: **≥ 85%**.
  - `api/routes/`: **≥ 80%** (contract tests pick up the rest).
  - Frontend components: **≥ 70%**.
- **Mocking policy:**
  - Unit tests mock everything outside the module under test.
  - Integration tests use real Postgres + Redis (testcontainers); mock ONLY external HTTP APIs.
  - E2E mocks nothing except Wazuh ingest (synthetic alert generator).

---

## 10. Phased Rollout

Each phase has: **Goal**, **Tickets** (short, actionable), **Exit criterion**, **Dependencies**.

### Phase 0 — Foundation

**Goal:** repo + infra skeleton, no business logic.
**Dependencies:** none.
**Tickets:**
- P0-1 Create `apps/api/` scaffold (pyproject, Dockerfile, settings, main.py, empty package layout per §3.5).
- P0-2 Add Postgres 16 + Timescale + Redis 7 services to `infra/compose.api.yml`.
- P0-3 Alembic scaffold + first migration (all tables in §6.2 + hypertables).
- P0-4 structlog + Prometheus `/metrics` scaffolding. Single example counter.
- P0-5 CI pipeline (lint: ruff + mypy --strict; test: pytest with coverage gate).
- P0-6 Pydantic `Settings` class + `.env.example`. Refuses to boot on missing required keys.
- P0-7 **Export missing training artifacts:** re-run feature_selection_final + TP1 + TP2 VAE + GNN notebooks to emit `secbert_log_pca.pkl`, `secbert_cmd_pca.pkl`, `standard_scaler.pkl`, `probability_calibrators.pkl`, `gnn_metadata.pkl` into `apps/models/`. (Blocks every subsequent phase.)
- P0-8 `registry.json` manifest + SHA-256 checksums.
- P0-9 Shared schema package skeleton (`apps/web/lib/api-types.ts` auto-generated from OpenAPI on each `api` build).

**Exit:** `docker compose up` brings the full stack up healthy; `pytest` green on empty tests; CI gate enforced; all 5 artifacts present in `apps/models/` and verified by `ModelRegistry.load()` dry run.

### Phase 1 — Ingestion + feature pipeline

**Goal:** synthetic alerts land as valid 55-dim vectors in `strix:features:{shard}`. No models yet.
**Dependencies:** P0.
**Tickets:**
- P1-1 `adapters/wazuh_adapter.py`: parse flattened Wazuh JSON into `RawAlert` Pydantic model; drop envelope + leaky cols.
- P1-2 `core/feature_engineer.py`: port `FeatureEngineerNoLeakage` from notebook, fixed column order (§5.10).
- P1-3 `adapters/model_registry.py`: load SecBERT tokenizer + model + two PCAs + scaler. Warm-up pass.
- P1-4 `workers/normalizer.py`: consume `strix:alerts:raw`, emit `FeatureMessage` to `strix:features:{shard}`. In-process LRU for SecBERT embeddings.
- P1-5 Filebeat config in `infra/` pointing at synthetic-alerts-generator (for Phase 1 test) and, when available, the real Wazuh volume.
- P1-6 Unit + integration tests for every transformation; regression fixture with 50 alerts.

**Exit:** load 1000 synthetic alerts through `strix:alerts:raw`; verify each produces a valid 55-dim vector on `strix:features:{shard}`; regression fixture diffs within tolerance against a reference set generated from the training notebooks.

### Phase 2 — Inference spine (AE + VAE + GNN, no Transformer, no DQN)

**Goal:** alerts flow through 3 models with batched inference, outputs persisted. Transformer + DQN deferred to Phase 3 (they need session state).
**Dependencies:** P1.
**Tickets:**
- P2-1 Vendored fixed model loaders (AE, VAE, GNN) with bug fixes from §5.10. Unit tests on loader output shapes.
- P2-2 Micro-batcher framework (`core/batcher.py`) — generic size-OR-time flush.
- P2-3 `workers/inference.py` AE + VAE pipeline (no Transformer yet). Shard by `agent_id`.
- P2-4 GNN rolling-window graph builder (§5.3). Background task rebuilds graph every 60 s.
- P2-5 `verdicts-writer` consumes `strix:verdicts` (partial `VerdictMessage` without Transformer/DQN fields).
- P2-6 Postgres writes: `alerts`, `detections` (partial).
- P2-7 `api/routes/dashboard.py` stub returning empty aggregates so frontend connects.
- P2-8 Performance test: 50 alerts/s sustained, p99 end-to-end < 300 ms.
- P2-9 **Calibrate `CHAIN_OPEN_VAE_THRESHOLD` and `CHAIN_OPEN_AE_THRESHOLD`** on a ≥ 1-week sample of the real alert stream. Method: collect AE anomaly-score and VAE malicious-prob distributions; pick thresholds such that chain-open rate matches the dataset's malicious-alert base rate (~22%) ±10% and false-open rate on a known-benign window stays < 5%. Lock chosen values in `core/constants.py` before Phase 3.

**Exit:** 50-alert/s load test passes budget; `detections` rows written correctly; `/dashboard/attack-vector` returns data (based on ingested MITRE CKC mapping, not model predictions yet); `CHAIN_OPEN_*` thresholds are calibrated and committed.

### Phase 3 — Session state + Transformer + DQN (the real behavior)

**Goal:** per-host session state, Transformer wired, DQN decides, attack chains open/close correctly.
**Dependencies:** P2.
**Tickets:**
- P3-1 Redis session adapter (§5.3). Hash + List + TTL management.
- P3-2 `core/sequence.py`: chain open/close/continue logic (§5.4). Fully unit-tested.
- P3-3 Fixed Transformer loader (GELU + norm_first). Batched sequence inference.
- P3-4 Vendored DQN loader. `core/state_builder.py` assembles 13-dim vector.
- P3-5 `workers/inference.py` full pipeline: AE → (VAE ∥ GNN) → Transformer → state → DQN.
- P3-6 `dqn_actions` + `attack_chains` writes in `verdicts-writer`. Chain lifecycle transitions.
- P3-7 Replay E2E test: feed a labeled attack sequence from `apps/data/` through the live system; assert intervention fires at ≤ S5.
- P3-8 Chaos test: restart inference-worker mid-chain — verify session is restored from Redis, chain continues or new chain opens per spec.

**Exit:** replay test passes; `attack_chains` rows consistent with training-time semantics; no dropped alerts under sustained 50 alerts/s.

### Phase 4 — Dashboard widgets wired to real data

**Goal:** the Dashboard tab shows live data, end-to-end.
**Dependencies:** P3.
**Tickets:**
- P4-1 Timescale continuous aggregates for `ckc_stage_hourly`, `global_risk_minutely`, `compromised_assets_view`.
- P4-2 `/dashboard/attack-vector`, `/dashboard/global-risk` endpoints + response caches.
- P4-3 SSE endpoint `/streams/live-feed` + Redis pubsub channel.
- P4-4 Victim graph builder (GNN snapshot projection). New `/dashboard/victim-graph` endpoint.
- P4-5 Frontend: replace mock-data imports in `page.tsx` with hooks: `useAttackVector`, `useGlobalRisk`, `useLiveFeed` (SSE), `useVictimGraph`. Remove `KillChainTimeline` from Dashboard.
- P4-6 New `VictimGraph` component (react-flow).
- P4-7 SSE hook abstraction: `useSseStream<T>(url)` handles reconnect + backoff.
- P4-8 AI Sentinel Insight card — calls `/dashboard/sentinel-insight`, shows skeleton on cache miss. (Backend logic deferred to Phase 7.)
- P4-9 **Authentication** (resolved §12 Q8 — moved from Phase 8): login endpoint, session cookie + short-lived JWT (15 min access) + refresh token (7 d), CSRF via double-submit token, logout endpoint. `DEV_SKIP_AUTH` flag honored only when `ENV=dev`.
- P4-10 **RBAC** — two roles: `admin` (all actions including Apply/Reject on ISOLATE/BLOCK), `analyst` (read-only + acknowledge + Apply/Reject). `users` table + role column. Middleware gate on every non-GET route.
- P4-11 Frontend: login page, `useAuth` hook, role-gated UI (hide Apply buttons for `analyst` if a later policy restricts), 401-aware API client with auto-refresh.

**Exit:** Playwright test asserts every Dashboard widget shows values sourced from the DB / SSE, not mock data; auth flow works end-to-end; unauthenticated requests return 401 except on whitelisted paths (`/health`, `/metrics`, `/api/v1/auth/*`).

### Phase 5 — Analysis tab

**Goal:** `attack-analysis/[id]` shows real chain data.
**Dependencies:** P4.
**Tickets:**
- P5-1 Endpoints in §4.2: `/analysis/chains/{id}/graph-evolution`, `/ckc-progression`, `/predictions`, `/logs`, `/infection`, `/dwell-time`.
- P5-2 `/streams/chains/{id}/logs` SSE.
- P5-3 Frontend: wire `GraphEvolution`, `KillChainProgression`, `AIPredictionsPanel`, `ForensicLogViewer` to real endpoints.
- P5-4 Chain list page (if not present) + sidebar badge = open chains count.
- P5-5 Playwright test: attack-analysis page for a seeded chain renders expected values.

**Exit:** clicking any chain in Live Feed navigates to its analysis page with correct data.

### Phase 6 — Threat Intel enrichment

**Goal:** IOC registry + compromised assets + VT + file upload, all with circuit breakers and caching.
**Dependencies:** P4 (dashboard exists), P0 (Arq ready).
**Tickets:**
- P6-1 `adapters/hibp_adapter.py` with `pybreaker` circuit breaker.
- P6-2 `adapters/virustotal_adapter.py` same.
- P6-3 `/threat-intel/iocs` endpoint + Arq job for lookup on cache miss.
- P6-4 `/threat-intel/compromised-assets` endpoint (reads `compromised_assets_view`).
- P6-5 `/threat-intel/virustotal/scan` + SSE result stream.
- P6-6 `/threat-intel/files/scan` multipart endpoint; SHA-256 → VT; `file_scans` table.
- P6-7 Frontend: replace hardcoded `compromisedAssets` + `breachFeeds`; new file-upload tab + drag-drop.
- P6-8 Chaos tests for external API outages.

**Exit:** HIBP + VT live lookups work; file upload round-trips; degraded-mode banner surfaces when an upstream is down.

### Phase 7 — AI Sentinel Insight (LLM)

**Goal:** Dashboard card serves a real, cached LLM-generated insight.
**Dependencies:** P4.
**Tickets:**
- P7-1 `adapters/llm_adapter.py` (Claude, prompt caching enabled).
- P7-2 Prompt templates in `services/insight_service.py` (one for Dashboard insight, one for Analysis-page summary).
- P7-3 `llm_insight_cache` Arq job + result reconciliation.
- P7-4 `/dashboard/sentinel-insight` live data; SSE event when Arq job completes.
- P7-5 Frontend: "Refresh insight" button → POST + optimistic skeleton.

**Exit:** cache hit under 200 ms; cache miss under 6 s p99; degraded mode when LLM unreachable.

### Phase 8 — Hardening

**Goal:** production-ready.
**Dependencies:** all prior.
**Tickets:**
- P8-1 Load test suite tuned; budgets locked in CI (regression fails on > 10% drift).
- P8-2 Chaos test suite (toxiproxy) in nightly CI.
- P8-3 Security review: pentest (scope = the API + auth flow from Phase 4), `pip-audit` + `npm audit` in CI, secret rotation runbook.
- P8-4 Observability: OpenTelemetry OTLP, Jaeger, Grafana dashboards (service health, stream depths, inference latency per model).
- P8-5 Model retraining hooks (resolved §12 Q7): `/monitoring/models/retrain` placeholder endpoint + drift-detection metric `strix_score_distribution_kl_divergence{model}` with Prometheus alert rule when divergence exceeds training-baseline threshold. Full retraining pipeline out of 1.0 scope.
- P8-6 Dockerfile hardening (non-root user, multi-stage build, smallest base).
- P8-7 Runbooks: "Redis full", "Inference worker OOM", "Postgres slow", "HIBP down", "Model loaded wrong weights", "Drift alert triggered".
- P8-8 **`AUTO_RESPONSE_ENABLED` infrastructure** (feature-flag scaffolding only — stays OFF in 1.0): per-host allow-list schema, kill-switch endpoint, shadow-mode data collection for future enable decision. No auto-isolation in 1.0.

**Exit:** green on full regression + performance + chaos; runbooks linked from `/support`; pentest sign-off on the Phase-4 auth flow; drift-detection alerts in Prometheus.

---

## 11. Frontend Gaps

### 11.1 Pages

| Page | Current state | Changes required |
|:---|:---|:---|
| `(dashboard)/page.tsx` (Home) | Mocked. Has `KillChainTimeline`, `AttackVectorChart`, `CircularProgress` (Threat Intensity), "AI Sentinel Insight" (hardcoded), `TimelineChart`, `LiveAlertCard`, KPI bar | **Remove** `KillChainTimeline`. **Replace** `TimelineChart` → `VictimGraph` (new component). **Wire** everything else to real endpoints. **Extract** "AI Sentinel Insight" block into `SentinelInsightCard`. |
| `(dashboard)/attack-analysis/[id]/page.tsx` | Mocked | Wire to `/analysis/chains/{id}/*`. Ensure `KillChainProgression` consumes `dqn_actions` (the stage the DQN acted at), not just MITRE-mapped CKC. |
| `(dashboard)/ai-engine/page.tsx` (Model Monitoring) | Mocked; missing AE and Transformer cards. Has "Engine Telemetry Stream". | **Remove** `telemetryStream` block. **Add** AE and Transformer model cards. **Wire** metrics to `/monitoring/models` + `/monitoring/composite-accuracy` + `/monitoring/confidence-trend`. |
| `(dashboard)/threat-intel/page.tsx` | Mocked `compromisedAssets`, `breachFeeds`, `threatIntensity` | Wire IOC table to `/threat-intel/iocs`. Wire compromised assets to `/threat-intel/compromised-assets`. Add file-upload panel → `/threat-intel/files/scan`. Add VT on-demand scan form. |
| `(dashboard)/topology/page.tsx` | Status uncertain per SESSION_HANDOFF | Not specified in brief — leave as-is this session unless it overlaps with Victim Graph. |
| `(dashboard)/vigilance-feed/page.tsx` | Fully rewritten | Wire to the same SSE stream used by Dashboard's Live Feed; this page is the "expanded" view. |
| `(dashboard)/notifications/page.tsx` | Static | Wire to a future `/notifications` endpoint backed by `dqn_actions` records where `action_name = ESCALATE/ISOLATE_HOST/BLOCK_USER_IP`. |
| `(dashboard)/settings/profile/support` | Static | Unchanged this session. |

### 11.2 New components

| Component | Purpose | Library |
|:---|:---|:---|
| `VictimGraph` | Interactive network of infected/linked hosts (Dashboard + Analysis) | `react-flow` or `cytoscape.js` |
| `SentinelInsightCard` | LLM-driven advice panel with refresh button + skeleton state | — |
| `DqnActionBadge` | Color-coded `MONITOR/LOW_ALERT/ESCALATE/ISOLATE/BLOCK` tag | — |
| `ChainStatusPill` | Open / closed attack-chain indicator | — |
| `SseConnectionStatus` | Small dot + auto-reconnect state, shown in Topbar | — |
| `FileUploadDropzone` | For Threat Intel file scan tab | `react-dropzone` |
| `DegradedModeBanner` | Shown when an upstream (HIBP/VT/LLM) is down | — |

### 11.3 New / updated hooks

| Hook | Signature | Purpose |
|:---|:---|:---|
| `useApi<T>(path, params)` | typed REST query wrapper (Tanstack Query under the hood) | all cacheable GETs |
| `useSseStream<T>(path)` | `{ events: T[], status, reconnect }` | Live Feed, forensic logs, VT scan results |
| `useAttackVector`, `useGlobalRisk`, `useVictimGraph`, `useSentinelInsight`, `useCompromisedAssets`, `useModelHealth` | typed wrappers | per-widget |
| `useAttackChain(chainId)` | combines multiple analysis endpoints | Analysis page |

### 11.4 State management

- **Tanstack Query (React Query v5)** for server state: replaces most of the bespoke zustand stores.
- **zustand** retained for client UI state: sidebar collapsed, filter selections, SSE connection state.
- **Shared schema package:** `apps/web/lib/api-types.ts` is auto-generated from the OpenAPI spec on every backend build. No hand-written types for API responses. `openapi-typescript` in a pnpm script.

### 11.5 Removed widgets

- **Dashboard:** `KillChainTimeline` (the "Cyber Kill Chain Progression" on the home page).
- **Model Monitoring:** `telemetryStream` block.

---

## 12. Resolved Decisions

All 12 questions from the prior draft are resolved below. Five of the initial proposals changed on closer inspection (Q2, Q3, Q5, Q8, Q10) — those are marked **⚠️ revised**. Items flagged **⚠️ preliminary** require empirical validation during phase execution before locking (these blocks are called out as tickets in §10).

| # | Question | Resolution | Where it shows up in the plan |
|:---:|:---|:---|:---|
| Q1 | **DQN on every alert, or gated?** | **Every alert, inside an open chain.** Alerts on hosts without an open chain run AE + VAE only (for Live Feed scoring) and skip Transformer + DQN — this is the gate, applied at chain level, not DQN level. Rationale: DQN cost is ~1 ms; gating on AE/VAE thresholds would miss graph-context malice (quiet per-alert signal on a GNN-risky host) and break training parity (DQN was trained to MONITOR benign-looking steps inside sequences). | §3.1 pipeline; §5.4 chain rule; §4.1 |
| Q2 ⚠️ revised | **Attack chain identification rule.** | **Structure fixed; threshold numbers preliminary.** Open on `vae_prob ≥ CHAIN_OPEN_VAE_THRESHOLD OR ae_anomaly ≥ CHAIN_OPEN_AE_THRESHOLD`; continue within `CHAIN_IDLE_TIMEOUT_MINUTES` on same host; close on intervention OR idle-timeout OR 50 steps. **The numbers (`VAE_THRESHOLD=0.5`, `AE_THRESHOLD=1.0`) must be recalibrated against a ≥ 1-week real-stream sample — see P2-9.** Reason: the AE loader scoring formula differs from the notebook's Youden-J reference, and the VAE has a fitted calibrator we need to consult. | §5.4; §6.3; §10 ticket P2-9 |
| Q3 ⚠️ revised | **Isolate/Block automated or advisory?** | **Per-action split, stronger than originally proposed.** `MONITOR`, `LOW_ALERT`, `ESCALATE` are always auto-applied (they are notifications/routing, no infrastructure blast radius). `ISOLATE_HOST` and `BLOCK_USER_IP` are **advisory-only in 1.0** — DB schema marks `requires_approval=TRUE`, UI surfaces Apply/Reject buttons for authorized roles. Phase 8 ships the `AUTO_RESPONSE_ENABLED` scaffolding (allow-list + kill-switch) but **the flag stays OFF in 1.0**. Flipping requires shadow-mode precision data, pentest sign-off, and production-critical asset allow-lists. | §6.2 `dqn_actions` table + semantics table; §10 ticket P8-8 |
| Q4 | **Global Risk window.** | **60 min rolling default**, matches GNN's `risk_growth` window (self-consistency). Widget exposes `?window=15m\|1h\|24h\|7d\|all` selector so analysts can zoom. | §6.3 `GLOBAL_RISK_WINDOW_MINUTES`; §4.1 attack-vector / global-risk endpoints |
| Q5 ⚠️ revised | **Session idle timeout.** | **2 hours (revised from 30 min).** The DQN was trained on a Mandiant-derived 11-day dwell-time distribution — a 30-min timeout would shred slow-burn APTs into disjoint chains and break Dwell Time. 2 h is the compromise between reactivity and capture of real attacker inactivity patterns. Hard-close at 50 steps unchanged. | §5.4; §6.3 `CHAIN_IDLE_TIMEOUT_MINUTES = 120` |
| Q6 | **Dashboard refresh cadence.** | **30 s polled for all slow aggregates** (attack-vector, global-risk, victim-graph, compromised-assets, model-monitoring, IOC list) via Tanstack Query `refetchInterval` (pauses on hidden tab). **SSE reserved for Live Feed, Forensic Logs, and async-job completion events** (VT / LLM) — browser per-domain SSE cap (~6) forbids SSE-everywhere. | §4.1, §4.2, §7.2 caching map |
| Q7 | **Model retraining.** | **Manual, ad-hoc for 1.0.** Drift-detection metric `strix_score_distribution_kl_divergence{model}` + Prometheus alert rule when divergence exceeds training-baseline threshold. When alert fires, a human re-runs the training notebooks on accumulated `alerts.raw_jsonb` data, bumps `registry.json` version, rolling-restarts workers. Aspirational cadence: monthly. Full MLOps pipeline = post-1.0. | §10 ticket P8-5 |
| Q8 ⚠️ revised | **Auth and multi-tenancy.** | **Auth moved from Phase 8 to Phase 4.** Phase 0 ships a `DEV_SKIP_AUTH` flag (dev-only). Phase 4 delivers real login (session cookie + short-lived JWT + refresh token), CSRF, and two roles (`admin` = full including Apply/Reject; `analyst` = read + acknowledge + Apply/Reject). Multi-tenancy is **out of scope indefinitely** for 1.0 — single-tenant is a hard constraint, reversible later via `tenant_id` + Postgres RLS without rewriting. Rationale: this is a security platform; shipping unauthenticated to anyone beyond the dev is unacceptable. | §10 Phase 4 tickets P4-9 / P4-10 / P4-11; §5.12 |
| Q9 | **Export DQN actions to Wazuh Active Response?** | **No in 1.0.** Only relevant if Q3 enables the `AUTO_RESPONSE_ENABLED` path. If/when that happens, the integration is a custom AR script polling `/api/v1/actions/pending/{agent_id}`. Not in 1.0 scope. | §10 ticket P8-8 note |
| Q10 ⚠️ revised | **LLM provider.** | **Anthropic SDK, two models, one adapter.** **Opus 4.7** for Sentinel Insight (deep reasoning, 5-min result cache, `cache_control` on MITRE + system prefix). **Haiku 4.5** for per-alert Live Feed one-liners (high-volume, cheap, LRU cache by `hash(mitre+decoder+ruleId)`). Circuit-breaker around both; degraded-mode fallbacks defined. | §5.14 (new); §4.1 updated rows |
| Q11 | **Wazuh topology.** | **Single self-hosted manager** (matches training data). Cluster is only needed past ~2000 agents; ingestion path is cluster-agnostic (Filebeat tails whichever node writes `alerts.json`), so this is reversible later. | INGESTION_PIPELINE §1 |
| Q12 | **"Active" chain meaning in UI.** | `chain.status = "open"` → UI label **"Active"**; `status = "closed"` → **"Resolved"**. Drop the "Industry Average" placeholder label on Dwell Time (mockup artifact, no reference value exists). | §6.2 `attack_chains.status`; §11.1 `attack-analysis` changes |

---

## 13. Coherence Checklist (pre-delivery pass)

Verified against the whole document.

- [x] **Identifiers:** `alertId` (string, Wazuh native), `agentId` (string, Wazuh), `hostId` (UUID, our own), `chainId` (UUID), `actionId` (UUID). No `event_id` anywhere; no `machine_id` anywhere; no `userId` for hosts. Consistent in §4, §6, §11, message schemas.
- [x] **CKC stage:** integer `0..7` on the wire and in DB. `ckcStage` on the wire; `ckc_stage` in DB. `ckcStageName` (display only) optional. Consistent §6, §4, §11.
- [x] **DQN actions:** `MONITOR/LOW_ALERT/ESCALATE/ISOLATE_HOST/BLOCK_USER_IP` (UPPER_SNAKE on wire, 0..4 in DB via `action` column; `action_name` mirrors). Consistent §4, §6, §11.
- [x] **Timestamps:** `TIMESTAMPTZ` in DB; ISO-8601 UTC string on the wire with millisecond precision; field names always `*At` in camelCase, `*_at` in snake_case. Never mixed.
- [x] **Severity enum:** `"critical"|"high"|"medium"|"low"|"info"` — matches existing `apps/web/types/index.ts`. Don't redefine.
- [x] **Model names (for metrics / monitoring):** `"AE"|"VAE"|"TRANSFORMER"|"GNN"|"DQN"` — used identically in §4.4 and §6.
- [x] **Window nomenclature:** `?window=1h|24h|7d|all` — not `since=...` in some endpoints and `period=...` in others. Single convention.
- [x] **Path convention:** `/api/v1/{resource}-{sub-resource}` (kebab-case); resource names plural; no verbs except for `/scan`, `/refresh` explicit action endpoints.
- [x] **Response envelope:** paginated lists return `{ items: T[], page: { cursor, hasMore } }`; aggregates return flat objects; collections for dashboards return `{ window, ...data }`. No endpoint returns a bare array.
- [x] **Frontend field mapping:** the existing `page.tsx` reads `dashboardKPIs`, `killChainStages`, `timelineEvents`, `mockAlerts`. Those are replaced by typed hooks (`useAttackVector`, etc.) whose response types come from the generated OpenAPI client — no manual typing mismatch possible.
- [x] **Phase dependencies:** no phase depends on a deliverable from a later phase. Phase 4 depends on P3 (inference + chains); Phase 5 depends on P4; Phase 7 depends on P4 (dashboard exists + Arq ready from P0); Phase 6 depends on P4 + P0.
- [x] **Chain close semantics:** only one rule creates `close_reason = "INTERVENTION"` (DQN action ≥ ESCALATE). Two rules create non-intervention closes (`IDLE_TIMEOUT`, `MAX_STEPS`). Consistent across §5.4, §6.2, §6.3.
- [x] **Constants:** listed in §6.3; no magic numbers elsewhere. (`INFECTION_VAE_PROB_THRESHOLD`, `CHAIN_IDLE_TIMEOUT_MINUTES`, etc.)
- [x] **Error format:** RFC 7807 Problem+JSON on every error response: `{ type, title, status, detail, instance, code }`. No ad-hoc `{ error: "..." }` envelopes.
- [x] **OpenAPI as contract:** mentioned consistently in §3.3, §9 (contract tests), §11.4. Single source of truth for FE types.
- [x] **Observability metrics:** every metric name in §8.2 has the `strix_` prefix or the HTTP default (`http_request_*`). No bare counters.
- [x] **Redis key prefixes:** always `strix:`, `session:`, `gnn:`, `cache:`, `arq:` — no unprefixed keys. Listed in §6.4.
- [x] **Design patterns applied only where they fit** — each pattern in §3.3 has a concrete "where" and "why". No Circuit Breaker on internal calls, no CQRS on trivial reads, no Repository over `select_one_by_id`.
- [x] **§12 is resolved decisions, not open questions.** Every resolution cross-links to the section(s) of the plan that enforce it. The five ⚠️ revised items changed from their initial draft proposals; the five ⚠️ preliminary / empirically-validated items have explicit tickets.
- [x] **Auth phase consistency.** Auth lives in Phase 4 everywhere (P4-9/10/11). Phase 0 only has the `DEV_SKIP_AUTH` stub flag. Phase 8 P8-3 references "the Phase-4 auth flow" as the pentest scope, not "implement auth."
- [x] **DQN action semantics consistency.** The per-action split (auto-applied vs `requires_approval`) is defined once in §6.2 and referenced everywhere (§4.2 Analysis page Apply/Reject UI, §11.2 `DqnActionBadge`, §12 Q3). No contradictions between "advisory" and "automated" anywhere.
- [x] **LLM model-per-workload consistency.** §4.1 Live Feed row and Sentinel Insight row both link to §5.14; §5.14 is the single source of truth for which model runs which workload and with what caching. No endpoint says "LLM" generically — always "Opus 4.7" or "Haiku 4.5".
- [x] **Timeout constants consistency.** `CHAIN_IDLE_TIMEOUT_MINUTES = 120` is used in §5.4 narrative, §6.3 constants, and the session-state 30-min idle TTL in §5.3 is updated to match (see post-edit note: the Redis `session:{agent_id}` TTL rises from 30 min to 2 h to match the chain idle rule — handled in P3-1).
- [x] **`AUTO_RESPONSE_ENABLED` is OFF in 1.0 everywhere.** §6.2 table, §12 Q3, §10 P8-8 — all say OFF. No contradicting "automated" claims elsewhere.

---

## End of plan

Next step once this plan is approved: spin up Phase 0 tickets and begin the artifact export work (P0-7), which is on the critical path because every subsequent phase needs `secbert_*_pca.pkl`, `standard_scaler.pkl`, `probability_calibrators.pkl`, and `gnn_metadata.pkl` in `apps/models/`.
