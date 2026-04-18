# Prompt 3 — Backend + Frontend Implementation Plan

You're working in the STRIX monorepo. The previous sessions produced:
- `docs/MODELS_REFERENCE.md` — every model, feature schema, RL environment, data flow trace
- `docs/mitre_to_ckc.json` — MITRE→CKC lookup
- `docs/DATASET_SCHEMA.md` — training dataset columns
- `docs/WAZUH_MAPPING.md` — how Wazuh logs map to the 55-dim training schema
- `docs/INGESTION_PIPELINE.md` — proposed pipeline

Read ALL of these before doing anything else. Also read:
- `apps/architecture/AGENT_ARCHITECTURE.md` and `apps/architecture/ARCHITECTURE.md` — re-read to keep the architecture fresh
- `apps/web/app/(dashboard)/` — to understand what the frontend currently expects
- `SESSION_HANDOFF.md` — recent frontend state

Your job this session is to produce a complete implementation plan — no code yet. The deliverable is `docs/IMPLEMENTATION_PLAN.md`.

---

## How to think about this plan (read this BEFORE you start writing)

You are not just listing endpoints. You are architecting a production ML system, and the quality of the plan matters as much as the completeness of it. Before proposing anything, think like a senior staff engineer:

### Architectural quality
- Choose the **best** architecture, not the first one that works. Justify every major structural decision by comparing it against at least one credible alternative and explaining the tradeoff.
- Apply **proven design patterns** where they fit — and name them explicitly. Repository pattern for data access, Strategy pattern for the "which model triggers which action" decision, Circuit Breaker for external APIs (HIBP, VirusTotal, LLM), Outbox pattern for reliable event emission, Adapter pattern for Wazuh ingestion, Pub/Sub for the Live Feed fan-out, CQRS if read and write paths have very different shapes. Do not apply patterns for their own sake — justify each one.
- Respect SOLID, separation of concerns, and dependency inversion. The feature-engineering layer must not know about FastAPI. The model-inference layer must not know about Postgres. The API layer must not know about the GNN's internal graph structure. Draw the boundaries explicitly.

### Performance and optimization (think hard about this)
- **Caching** — identify every hot path and specify what gets cached, where (in-process LRU? Redis?), with what TTL, and how invalidation works. Candidates: SecBERT embeddings for identical log messages, PCA results for repeated vectors, HIBP/VirusTotal lookups, MITRE→CKC mapping, recent model outputs per alert ID, aggregated dashboard metrics.
- **Latency budgets** — give a target p50/p99 latency for each endpoint and for the end-to-end alert → DQN action pipeline. If a step could blow the budget (e.g. SecBERT on CPU), flag it and propose a fix (batching, async, GPU worker, precompute).
- **Batching** — model inference should batch. Specify batch sizes and flush triggers (size threshold OR time threshold, whichever first). Do not do one-alert-at-a-time inference.
- **Model loading** — all models load ONCE at worker startup, never per-request. Specify warm-up strategy.
- **Async vs sync** — every I/O call (DB, Redis, external API, LLM) is async. CPU-bound work (model inference, SecBERT) runs in a thread/process pool. Be explicit about which is which.
- **Backpressure** — if Wazuh floods us, the system must degrade gracefully, not crash. Specify queue bounds and shed-load policy.
- **Connection pooling** — DB, Redis, HTTP clients. Name the pool sizes.
- **Vectorization** — feature engineering on batches should use NumPy/Pandas vectorized ops, not Python loops.

### Scalability
- Design for horizontal scaling from day one, even if we deploy a single instance. That means: no in-process-only state that can't be moved to Redis, stateless API workers, idempotent event handlers.
- Identify the scaling bottlenecks up front — most likely the inference workers and the session-state store. Propose a sharding/partitioning strategy (e.g. shard by host_id or agent_id so all alerts for one host hit the same worker and session state stays local).
- Specify which components are stateless (trivially scalable) vs stateful (need coordination).

### Clean code
- Strict typing everywhere (Python: Pydantic models for every API boundary, `mypy --strict`; TypeScript: no `any`).
- One concern per module. A 1,000-line `main.py` is a failure.
- Names describe intent, not implementation (`DetectionPipeline`, not `Processor`).
- No magic numbers — constants named and centralized (thresholds, weights, TTLs, batch sizes).
- Errors are typed and meaningful, not bare `except:`.
- Configuration via environment + typed settings object (Pydantic BaseSettings), never hardcoded.

### Consistency and coherence (NON-NEGOTIABLE)
Everything in the plan must be internally consistent. Before you finalize, do a **coherence pass**:
- The same concept has the same name everywhere (e.g. pick `alert_id` or `event_id`, not both; pick `host` or `agent` or `machine`, not all three).
- Every field name used in a backend response matches what the frontend expects. If the Dashboard page reads `globalRisk`, the API returns `globalRisk`, not `global_risk_score`.
- Every data type is consistent end-to-end (timestamps are always ISO 8601 UTC strings on the wire; CKC stages are always the integer 0–7, never a mix of integers and strings; severity levels use the same enum everywhere).
- Every endpoint follows the same conventions: URL style, error format, pagination, auth, versioning prefix (`/api/v1/...`).
- Every DB table follows the same conventions: `id` primary key type, `created_at`/`updated_at` columns, soft-delete vs hard-delete policy, naming (snake_case, plural table names).
- The rollout phases must not contradict each other (a phase can't depend on something a later phase introduces).
- Inconsistency is a bug. Call out and fix any you spot.

---

## Non-negotiable architectural constraints (derived from AGENT_ARCHITECTURE.md)

These are not design choices — they follow from how the system was built and trained. The plan MUST respect them:

1. **The 4 detection models are not independent services.** AE → produces 64-dim latent → consumed by Transformer. Inference must preserve this dependency ordering.
2. **The system is sequence-based, not alert-based.** The Transformer needs the full sequence of AE latents so far, the GNN needs a graph built over recent alerts. A per-alert stateless API will not work — there must be session/episode state per host (or per logical attack chain).
3. **The DQN agent is the decision-maker.** The Global Risk formula in the platform notes (`0.4*mean(VAE_prob) + 0.3*max(GNN_node_risk) + 0.2*anomaly_rate + 0.1*risk_growth`) is a dashboard-level aggregate, but the **per-alert defensive action** comes from the DQN agent consuming the 13-dim state, producing one of 5 actions (Monitor / Low Alert / Escalate / Isolate / Block User/IP).
4. **The 55-dim feature vector is the contract.** Every live Wazuh alert must be transformed into this exact schema before hitting any model. The feature-engineering code (SecBERT + PCA + binary flags) must run in production.
5. **Fitted preprocessing objects must be reused.** The SecBERT tokenizer/model, the PCA fitted objects, any scalers — these must be loaded from `apps/models/` at inference time, NOT refit.

---

## The plan must cover every platform function

### Dashboard tab
- Attack Vector Graph (pie of CKC step distribution since platform start) — requires persisting every detected CKC stage over time
- Live Feed (MITRE techniques + timeline + short explanations)
- AI Sentinel Insight (LLM over detected techniques → insight + remediation)
- Threat Intensity / Global Risk: `0.4 * mean(VAE_prob) + 0.3 * max(GNN_node_risk) + 0.2 * anomaly_rate + 0.1 * risk_growth` — specify the time window for each component
- Attack Timeline (victims-connected-to-each-other graph, derived from logs — this is essentially a projection of the GNN graph)
- **Remove:** "Cyber Kill Chain Progression" widget

### Analysis tab
- Graph Evolution Timeline (from GNN graph structure — snapshots over time)
- Cyber Kill Chain Progression — the CKC step at which the **RL agent** took its intervention action (from DQN output, not just the Transformer prediction)
- AI Predictions (next expected CKC steps — Transformer output directly)
- Forensic Raw Logs (live from Wazuh)
- Infection Radius (% infected machines — specify exactly how "infected" is computed from AE + RL actions)
- Dwell Time (average intrusion → isolation duration — requires tracking per-attack-chain timestamps)

### Threat Intel tab
- Reputation Core — IOC Registry (HaveIBeenPwned API)
- Compromised Assets (infected machines + CKC step + maliciousness degree)
- Breach Feed Integrations (VirusTotal API + file upload tab)

### Model Monitoring tab
- **Remove** "Engine Telemetry Stream"

---

## For each function, the plan must specify

1. **Data source** — Wazuh logs / which model output / which DQN state field / which external API
2. **Backend endpoint** — HTTP path, method, request shape, response shape (Pydantic model sketch)
3. **Backend logic** — which model(s) to load, what transforms to apply, how to aggregate. Be explicit about whether the endpoint needs access to per-host session state (AE latent history for the Transformer, graph state for the GNN).
4. **Caching strategy** — what's cached, where, TTL, invalidation rule
5. **Latency budget** — target p50/p99
6. **Persistence** — DB table + schema, or time-series bucket. Distinguish:
   - Hot/streaming state (AE latent history per session, GNN graph cache) → Redis
   - Warm events (individual alerts + model outputs + DQN actions) → Postgres (with Timescale if needed)
   - Cold analytics (aggregates over days/weeks for dashboard widgets) → materialized views or pre-aggregated tables
7. **Frontend changes** — which file under `apps/web/app/(dashboard)/` consumes this, what state/hook handles it, whether it's polled or streamed (SSE/WebSocket)
8. **Dependencies** — external APIs, API keys, rate limits, failure mode (what happens if HIBP is down?)

---

## Architecture-level decisions to propose (justify each with alternatives considered)

- **Backend framework** — FastAPI recommended. Justify vs alternatives.
- **Inference service layout** — the big decision. Options:
  - (A) One monolithic inference service that loads all 4 models + DQN in-process and processes alerts end-to-end
  - (B) Separate microservices per model
  - Given the AE→Transformer latent dependency and the per-session state requirement, (A) is likely correct — make the case and specify exactly how workers are sharded.
- **Session/state management** — how per-host (or per-attack-chain) episode state is maintained across alerts. Redis data structures (hash? stream? sorted set?), TTLs, eviction policy, recovery on worker restart.
- **Sequence handling** — how incoming Wazuh alerts get grouped into the "sequences" the system was trained on. This is subtle: in training, sequences were hand-constructed from the dataset. In production, we need a rule for sequence boundaries (per-host sliding window? per-user? timeout-based?). Propose a concrete rule with parameters.
- **Real-time transport** — SSE vs. WebSocket for Live Feed and Forensic Raw Logs. Pick one and justify.
- **Job queue** — Celery / RQ / Arq for LLM calls, HaveIBeenPwned, VirusTotal enrichment. Pick one.
- **Database(s)** — propose minimal viable set. Likely Postgres + Timescale extension for time-series alerts + Redis for session state. Justify.
- **Message bus** — if any. Do we need Kafka/NATS between ingestion and inference, or is direct async fine?
- **Folder structure** for `apps/api/` (or wherever the backend lives) — propose a clean layout by feature/domain, not by technical layer
- **Model artifact loading** — where fitted PCA objects, SecBERT, scalers, model .pth files live in the container, how they're loaded at startup, how model versioning is handled
- **Observability** — structured logging (what fields on every log line), metrics (Prometheus-style: which counters, gauges, histograms), tracing (where span boundaries go). This is not an afterthought.
- **Security** — authentication between services, secrets management, input validation, rate limiting, how API keys for HIBP/VirusTotal/LLM are rotated
- **Configuration management** — how config flows from env → settings object → components

---

## Testing plan (this is a dedicated top-level section of the deliverable)

Every component the plan introduces must have a testing strategy. Produce a test matrix with rows for each component and columns for each test type. Specify:

### Unit tests
- Feature engineering functions (SecBERT wrapper, PCA apply, binary flag computation, numerical feature computation) — test each transformation in isolation with fixtures
- Model loader wrappers — test they produce the expected output shapes and dtypes on known inputs
- State vector construction — test the 13-dim vector is assembled correctly from mocked model outputs
- Reward/risk aggregation logic — test the Global Risk formula with known inputs
- MITRE→CKC mapping lookups
- Every Pydantic model (serialization, validation, edge cases)

### Integration tests
- End-to-end inference pipeline on a single alert: raw JSON → 55-dim vector → all 4 models → 13-dim state → DQN action. Use real fitted models and a small fixture dataset.
- Session state persistence: ingest a sequence, verify AE latents accumulate in Redis, verify Transformer sees the right sequence
- GNN graph construction: ingest alerts that should form edges (same user, cross-machine, within window) and verify the graph
- DB migrations apply cleanly, schemas match the Pydantic models
- External API adapters with mocked HIBP/VirusTotal/LLM responses (success, timeout, rate-limit, malformed)

### Contract tests
- Every API endpoint: request/response schema matches what the frontend expects. Generate an OpenAPI schema and have the frontend consume it (or use a shared schema package).
- SSE/WebSocket message formats — documented and tested.

### End-to-end tests
- Replay a known-attack sequence from the real dataset through the live system and assert the DQN agent triggers an intervention at the expected CKC stage
- Replay a benign sequence and assert no intervention fires
- Dashboard widgets render correct values when backed by a seeded DB state

### Performance tests
- Load test: sustained alerts per second the inference pipeline handles before latency breaches the budget
- Stress test: burst of 10x normal load, verify backpressure kicks in and no data is lost
- Memory: 24-hour soak test, no leaks in model workers or session-state store

### Regression tests
- Model output drift: a fixed fixture of alerts must produce the same (or near-identical within tolerance) model outputs across deployments. Guards against accidental model swaps or preprocessing changes.

### Chaos / failure tests
- Redis unavailable: system degrades to what behavior? (probably: session state lost, new episodes start fresh, alerts still stored)
- Postgres unavailable: ingestion queues and retries
- External API down: circuit breaker trips, enrichment marked unavailable, dashboard shows degraded state
- Inference worker crash: alerts re-queued, no duplicate processing

### Test infrastructure
- Which framework (pytest for Python, Vitest/Jest + Playwright for frontend)
- Fixtures: a canonical small alert dataset checked in for reproducible tests
- CI pipeline: which tests run on PR, which run nightly, which run before release
- Coverage targets: minimum line coverage for the inference and feature-engineering modules (aim high here — 90%+)
- Mocking strategy: what gets mocked in unit tests, what stays real

---

## Sequencing

Produce a phased rollout. Each phase has: goals, concrete tickets (short and actionable), dependencies on prior phases, and an exit criterion (when is this phase "done"?).

- **Phase 0: Foundation** — repo structure, CI, typed settings, DB migrations scaffold, Redis, observability skeleton
- **Phase 1: Ingestion + feature pipeline** — Wazuh ingestion, 55-dim vector generation, schema validation, no models yet. Exit: synthetic alerts land as valid 55-dim vectors in the queue.
- **Phase 2: Inference spine** — Load AE + VAE + GNN in a service, process alerts, store outputs. Transformer deferred. Exit: alerts flow through 3 models with batched inference, outputs persisted, p99 within budget.
- **Phase 3: Session state + Transformer + DQN** — Per-host session state in Redis, Transformer wired up, DQN agent inference, actions emitted. Exit: replay test on a known attack sequence triggers intervention at expected stage.
- **Phase 4: Dashboard widgets wired to real data** — Attack Vector Graph, Threat Intensity, Live Feed (SSE), Infection Radius, Dwell Time
- **Phase 5: Analysis tab** — Graph Evolution Timeline, CKC Progression (DQN action), AI Predictions (Transformer), Forensic Logs (SSE)
- **Phase 6: Threat Intel enrichment** — HIBP, VirusTotal, file upload, with circuit breakers and caching
- **Phase 7: AI Sentinel Insight (LLM)** — async job queue, prompt templates, result caching
- **Phase 8: Hardening** — load tests, chaos tests, security review, model monitoring dashboards

---

## Frontend gaps

Separately list every frontend change needed:
- New components (DQN action display, session/attack-chain view if any)
- New hooks (SSE/WebSocket hook for Live Feed, Forensic Logs)
- Pages that need rework beyond SESSION_HANDOFF.md
- Removed widgets (CKC Progression from Dashboard, Engine Telemetry Stream from Model Monitoring)
- New state management needs (streaming alert state, per-attack-chain grouping for the Analysis tab)
- Type safety: a shared schema package (generated from OpenAPI, or hand-written and validated) so frontend types match backend exactly

---

## Things to explicitly flag as open questions

- Is the DQN agent run on EVERY incoming alert, or only when anomaly_score/malicious_prob crosses a threshold? (Training episodes ended on intervention — production semantics need a decision.)
- How are "attack chains" identified in production for the Dwell Time and victims-graph widgets? Propose a rule but flag it as a product decision.
- Should isolate/block actions be **advisory** (displayed to an analyst) or **automated** (actually cut network access)? Flag this as a product/security-team decision — do not assume.
- The dashboard Global Risk formula uses `anomaly_rate` and `risk_growth` — over what time window? The platform notes don't specify.
- Model retraining cadence — out of scope for this session, but flag where hooks should exist

---

## Output

Everything into `docs/IMPLEMENTATION_PLAN.md`. Structure the document exactly like this:

1. Executive summary (half a page — the shape of the system)
2. Non-negotiable constraints (restate from above)
3. Architecture overview (diagram + component responsibilities + design patterns used)
4. Per-function specification (the big table/matrix)
5. Architecture-level decisions (with alternatives and tradeoffs)
6. Data model (DB schemas, Redis key schemas, message formats)
7. Performance & optimization plan (caching map, latency budgets, batching strategy)
8. Security & observability plan
9. Testing plan (the full matrix and strategy from above)
10. Phased rollout with tickets and exit criteria
11. Frontend gaps
12. Open questions
13. Coherence checklist — explicitly confirm naming, types, conventions are consistent across all sections

No code. Ask me before assuming any infra choice or resolving any open question. When in doubt between two reasonable alternatives on a significant decision, present both and recommend one — do not silently pick.