You're working in the STRIX monorepo. The previous sessions produced:
- `docs/MODELS_REFERENCE.md` — every model, its features, outputs, exported artifacts
- `docs/DATASET_SCHEMA.md` — training dataset columns
- `docs/WAZUH_MAPPING.md` — how Wazuh logs map to training schema
- `docs/INGESTION_PIPELINE.md` — proposed pipeline

Read ALL four before doing anything else. Also read `apps/web/app/(dashboard)/` to understand what the frontend currently expects, and `SESSION_HANDOFF.md` for recent frontend state.

Your job this session is to produce a complete implementation plan — no code yet. The deliverable is `docs/IMPLEMENTATION_PLAN.md`.

## The plan must cover every function in the platform notes

### Dashboard tab
- Attack Vector Graph (pie of CKC step distribution since platform start)
- Live Feed (MITRE techniques + timeline + explanations)
- AI Sentinel Insight (LLM over detected techniques → insight + remediation)
- Threat Intensity / Global Risk: `0.4 * mean(VAE_prob) + 0.3 * max(GNN_node_risk) + 0.2 * anomaly_rate + 0.1 * risk_growth`
- Attack Timeline (victims-connected-to-each-other graph, derived from logs)
- Remove: "Cyber Kill Chain Progression" widget

### Analysis tab
- Graph Evolution Timeline (from GNN graph structure)
- Cyber Kill Chain Progression (step at which RL agent detected attack)
- AI Predictions (next expected CKC steps, Transformer output)
- Forensic Raw Logs (live from Wazuh)
- Infection Radius (% infected machines, from AE)
- Dwell Time (average intrusion → isolation duration)

### Threat Intel tab
- Reputation Core — IOC Registry (HaveIBeenPwned API, returns reputation/timestamp/source)
- Compromised Assets (infected machines + CKC step + maliciousness degree)
- Breach Feed Integrations (VirusTotal API results + file upload tab)

### Model Monitoring tab
- Remove "Engine Telemetry Stream"

## For each function, the plan must specify

1. **Data source** — Wazuh logs / which model output / which external API
2. **Backend endpoint** — HTTP path, method, request shape, response shape
3. **Backend logic** — which model(s) to load, what transforms to apply, how to aggregate, any caching / streaming considerations
4. **Persistence** — does this need a DB table? what schema? is it time-series (Timescale / Influx) or relational (Postgres)?
5. **Frontend changes** — which file under `apps/web/app/(dashboard)/` consumes this, what state/hook handles it, whether it's polled or streamed (SSE/WebSocket)
6. **Dependencies** — external APIs, API keys required, rate limits to respect

## Architecture-level decisions to propose

- Backend framework (FastAPI recommended — justify)
- Model serving strategy (load in-process vs. separate inference workers)
- Real-time transport (SSE vs. WebSocket) for Live Feed and Forensic Raw Logs
- Job queue for LLM calls and external API enrichment (Celery / RQ / Arq)
- Database(s) — propose the minimal viable set
- Folder structure for `apps/api/` (or wherever the backend lives)

## Sequencing

Produce a phased rollout:
- Phase 1: ingestion + model inference services alive, Dashboard basics working
- Phase 2: Analysis tab + Threat Intel enrichment
- Phase 3: LLM insights, RL agent integration, polish

For each phase, list the concrete tickets (short, actionable) and their dependencies.

## Frontend gaps

Separately list every frontend change needed — new components, new hooks, pages that need rework beyond what's in SESSION_HANDOFF.md, removed widgets, new state management needs.

## Output
Everything into `docs/IMPLEMENTATION_PLAN.md`. No code. Ask me before assuming any infra or choosing between reasonable alternatives on big decisions.