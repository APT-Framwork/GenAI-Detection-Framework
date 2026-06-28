# 🗂️ STRIX — Code Structure Walkthrough (Jury)

> Read-along guide for the **code review** part of the defense.
> Goal: show *how the repository is organised* and *how a single alert
> flows from the host all the way to the dashboard / phone*.
>
> One sentence to open with:
> *"STRIX is a monorepo: one backend, two clients (web + mobile), the
> trained ML models, the RL research code, and the lab infrastructure —
> each in its own top-level folder."*

---

## 0. The 30-second map

```
GenAI-Detection-Framework/
├── apps/
│   ├── api/        → Python / FastAPI backend  (the brain)
│   ├── models/     → trained ML artifacts       (the 5 models + RL agent)
│   ├── web/        → Next.js 14 analyst console
│   ├── mobile/     → React Native (Expo) companion app
│   └── notebooks/  → research / training notebooks
├── RL_agent/       → reinforcement-learning training & ablation studies
├── infra/          → Docker Compose, Wazuh/auditd lab, simulation, scripts
├── config/         → Wazuh manager/agent reference configs
├── docs/           → architecture, runbooks, mobile & lab guides
├── report/         → the written PFE / master report
├── Procfile.host   → process list that runs the whole platform on the host
├── Makefile        → make up / make host-up entry points
└── jury_demo.sh    → one-command end-to-end demo
```

---

## 1. The end-to-end data flow (say this first)

> *"Everything in the repo serves this one pipeline:"*

```
auditd / Wazuh (host telemetry)
      │
      ▼
filebeat ──▶ Redis stream ──▶  normalizer worker        (raw → features)
                                     │
                                     ▼
                              inference worker            (5 DL models + DQN)
                                     │
                          ┌──────────┴──────────┐
                          ▼                     ▼
                     PostgreSQL            Redis pub/sub (WS/SSE)
                  (verdicts, chains)            │
                          │                     ▼
                          └──────────▶  FastAPI  ──▶  Web console (:5600)
                                                  └─▶  Mobile app (Expo)
```

Each folder below owns one stage of that pipeline.

---

## 2. `apps/api/` — the backend (FastAPI, Python)

This is the core of the system. Source lives under
`apps/api/src/strix_api/`, split by responsibility:

| Sub-package | Role |
|---|---|
| **`core/`** | Pure domain logic — no I/O. Feature engineering (`feature_engineer.py`), kill-chain sequence/session state (`sequence.py`, `session.py`, `state_builder.py`), MITRE ATT&CK catalog (`mitre.py`, `mitre_catalog.py`), GNN windowing (`gnn_window.py`). |
| **`adapters/`** | Everything that talks to the outside world. **`model_loaders/`** loads the 5 models (`autoencoder.py`, `vae.py`, `transformer.py`, `gnn.py`, `dqn.py`); plus Wazuh, Redis, LLM, Expo-push, VirusTotal and breach-feed adapters; `preprocessing_pipeline.py` turns raw alerts into model-ready tensors. |
| **`workers/`** | The streaming pipeline (long-running processes). `wazuh_bridge.py` (ingest) → `normalizer.py` (raw → features) → `inference.py` (run the models + RL) → `verdicts_writer.py` (persist). Plus `arq_tasks.py`, `intel_feeds_worker.py`, and `demo_isolation.py` (the demo-only auto-isolate). |
| **`services/`** | Business logic behind each API surface — alerts, cases, dashboard, hunt, topology, attribution, UEBA, playbooks, threat-intel, kill-switch, etc. |
| **`api/`** | The HTTP layer. `routes/` = one file per endpoint group (alerts, chains, dashboard, hunt, topology, streams (WS/SSE), simulation…); `schemas/` = Pydantic request/response models; `deps.py`, `middleware.py`, `errors.py`. |
| **`repositories/`** | Data access — SQLAlchemy models (`models.py`) and per-entity repos (users, IOCs, push devices, LLM insights). |
| **`observability/`** | Structured logging, Prometheus metrics, tracing. |
| **`alembic/`** | Database migrations (`alembic upgrade head`). |
| **`tests/`** | Layered: `unit/`, `integration/`, `contract/`, `e2e/`, `chaos/`. |

> Point at: `workers/inference.py` (where the 5 models + DQN run) and
> `adapters/model_loaders/` (one loader per model).

---

## 3. `apps/models/` — the trained artifacts

The output of the ML research, loaded at runtime by the API. *No code —
just the weights and preprocessing pipeline.*

- **The 5 deep-learning models** — `ae_model.pth` (Autoencoder),
  `vae_model.pth` (Beta-VAE), `transformer_model.pth` (SecBERT-based),
  `gnn_model.pth` (graph propagation), plus `rl_agent.pth` (the DQN).
- **Preprocessing** (`preprocess/`) — the **SecBERT** tokenizer + model
  (`secbert/`), PCA reducers (`pca_*_secbert.pkl`), the feature scaler
  (`scaler_55.pkl`, `standard_scaler.pkl`), and the **VAE calibrator**.
- **Calibration & metadata** — `probability_calibrators.pkl`,
  `selected_features_top25.json`, `gnn_metadata.pkl`, `registry.json`,
  `MANIFEST.json`.

> Talking point: *"Five complementary models — reconstruction (AE/VAE),
> sequence (Transformer), graph (GNN) — are fused, then a DQN decides
> the response. The registry + calibrators make verdicts comparable."*

---

## 4. `apps/web/` — the analyst console (Next.js 14, TypeScript)

The production dashboard the jury sees at **:5600**.

- **`app/`** — App-Router pages, grouped by auth vs dashboard.
  `(dashboard)/` holds one route per screen: `topology`, `attack-analysis`,
  `ai-engine`, `hunt`, `cases`, `actions`, `threat-intel`, `host`,
  `vigilance-feed`, …
- **`components/`** — UI by domain: `topology/`, `chains/`, `charts/`,
  `dashboard/`, `model-monitor/`, `feed/`, `playbooks/`, plus a shared
  `ui/` kit.
- **`lib/api/`** — the typed client: one module per backend area, a shared
  `client.ts`, React-Query `hooks.ts`, and **live transports** `sse.ts` /
  `ws.ts` / `socket.ts`. `openapi.json` keeps it type-safe against the API.
- **`stores/`** — lightweight client state (auth, alerts, sidebar).

> Talking point: *"The web client is OpenAPI-driven and fully typed, with
> live SSE/WebSocket feeds — no polling."*

---

## 5. `apps/mobile/` — the analyst companion (React Native / Expo)

Mirrors the web client for on-call analysts.

- **`app/`** — Expo Router screens: `(auth)`, `(onboarding)`, `(tabs)`
  (dashboard etc.), `analysis/`.
- **`lib/api/`** — same shape as web: `client.ts`, `config.ts` (LAN-IP
  resolution for the phone), `sse.ts`, React-Query provider/hooks.
- **`services/notifications.ts`** + **`hooks/usePushNotifications.ts`** —
  **Expo Push** notifications (import-gated so the app still launches
  without push entitlements).
- **`components/`** — `KillChainStrip`, `MitreStrip`, `AlertCard`, `KPICard`…
- **`lib/model-registry.ts`** — a hand-mirror of the web registry, kept in sync.

> Talking point: *"Same OpenAPI contract, same live feed, plus native
> push so an analyst is alerted off-screen."*

---

## 6. `RL_agent/` — the reinforcement-learning research

The **training/experimentation** repo for the DQN response agent (the
trained weights ship to `apps/models/rl_agent.pth`).

- **`env/apt_env.py`** — a custom Gym-style environment modelling the
  APT kill-chain as an MDP.
- **`rl/dqn_agent.py`** — the DQN agent (the policy that picks
  MONITOR / ESCALATE / ISOLATE).
- **`models/`** — loaders that plug the 5 detection models into the RL state.
- **`synthetic/`** — synthetic & replay data generators for training.
- **`ablation_study.py`** + **`outputs_ablation/`** — the ablation proving
  each model's contribution (`no_ae`, `no_vae`, `no_gnn`, `no_transformer`
  vs `full_all_models`).
- **`train.py`, `evaluate*.py`, `demo.py`, `web_app.py`** — train, score,
  and a standalone Flask demo UI.

> Talking point: *"This is where the RL agent is trained and where the
> ablation study lives — evidence that every model earns its place."*

---

## 7. `infra/` — lab, simulation & ops

Everything needed to generate **real** attack telemetry and run the stack.

- **`compose.*.yml`** — composable stacks: `compose.simulation.yml`
  (Wazuh + Caldera + 2 victims), `compose.platform-deps.yml`
  (Postgres + Redis + Filebeat), plus `api`, `lab`, `victim`, `chaos`.
- **`simulation/`** — the attack driver: `scripts/run_full_simulation.py`
  (drives Caldera through APT chains / the non-monotonic demo),
  `attacker/`, `victim/`, and `runs/` (per-run artifacts).
- **`scripts/`** — operational glue: **`lab_simulate.sh`** (the sim runner),
  `lab_up.sh` / `lab_verify.sh`, `calibration_*.py` (model calibration),
  `mobile_dev.sh`, `seed_admin.py`, `dump_openapi.py`, smoke tests.
- **`auditd/strix.rules`** + **`lab-provisioning/wazuh/local_rules.xml`** —
  the host telemetry rules that make detections fire.
- **`filebeat.yml`, `prometheus.yml`, `grafana/`, `loadtests/`** — shipping,
  monitoring, and k6 load tests.

> Talking point: *"The detections aren't mocked — Caldera launches real
> MITRE techniques against two enrolled victims; auditd + Wazuh produce
> genuine telemetry."*

---

## 8. Supporting folders

- **`config/`** — reference Wazuh manager/agent decoders & rules.
- **`docs/`** — architecture, runbooks, mobile (`MOBILE_DEVICE_SETUP.md`),
  lab bring-up, and session logs.
- **`report/`** — the written PFE / master report.
- **`Procfile.host`** — the canonical list of platform processes: `api`,
  `wazuh_bridge`, `normalizer`, `inference`, `verdicts_writer`, `arq`,
  `demo_isolation`, `intel_feeds`, `web`. *"This one file is the whole
  runtime in nine lines."*

---

## 9. If the jury asks "where is X?"

| Question | Answer (file to open) |
|---|---|
| Where do the models run? | `apps/api/.../workers/inference.py` |
| How is a model loaded? | `apps/api/.../adapters/model_loaders/<model>.py` |
| Where's the RL agent? | trained: `RL_agent/rl/dqn_agent.py` · shipped: `apps/models/rl_agent.pth` |
| Raw alert → features? | `apps/api/.../workers/normalizer.py` + `core/feature_engineer.py` |
| The kill-chain logic? | `apps/api/.../core/sequence.py`, `state_builder.py` |
| API endpoints? | `apps/api/.../api/routes/` (one file per area) |
| Live dashboard feed? | `apps/web/lib/api/sse.ts` / `ws.ts` ↔ API `routes/streams.py` |
| Proof each model matters? | `RL_agent/ablation_study.py` + `outputs_ablation/` |
| How attacks are generated? | `infra/simulation/scripts/run_full_simulation.py` |
