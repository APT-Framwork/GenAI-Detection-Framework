# STRIX — GenAI-Powered APT Detection & Response Platform

> A full-stack security platform that fuses five deep-learning models with a reinforcement-learning agent to detect Advanced Persistent Threats (APTs) along the Cyber Kill Chain, and exposes the verdicts through a production-grade web console, mobile app, and live lab simulation environment.

**Role:** End-to-end design and implementation (ML, backend, frontend, mobile, infrastructure).
**Stack:** PyTorch · PyTorch Geometric · Transformers (SecBERT) · FastAPI · PostgreSQL · Redis · ARQ · Next.js 14 · React Native (Expo) · Docker Compose · Prometheus / Grafana · Wazuh · Auditd · Filebeat · Caldera.

---

## 1. Problem

Advanced Persistent Threats unfold over days or weeks across 8 stages of the Cyber Kill Chain (CKC): Reconnaissance → Weaponization → Delivery → Exploitation → Installation → Command & Control → Lateral Movement → Actions on Objectives. Classical signature-based SIEMs detect attacks **after** the damage is done. STRIX targets **early-stage detection** (S1–S2) and **automated response** by combining anomaly detection, sequence prediction, graph-based lateral-movement detection, and a reinforcement-learning policy that decides when to monitor, alert, escalate, isolate the host, or block the user/IP.

---

## 2. ML System

The core of STRIX is a **multi-model ensemble** whose outputs are fused into a 13-dimensional state vector consumed by a DQN agent.

### 2.1 Models (all served from `apps/models/`, hash-pinned in `registry.json`)

| Model | Arch | Input | Role |
|---|---|---|---|
| **AE** (Autoencoder) | Dense, latent-dim 64, LeakyReLU(0.2) | 55-dim feature vector | Reconstruction-error anomaly score |
| **β-VAE** | Encoder [512,256,128] → latent 32, β=0.5 | 55-dim | Calibrated malicious-probability + epistemic uncertainty |
| **Transformer** | CKC next-step predictor, 8 stages, GELU, norm-first | AE 64-dim latent sequence | Predicts the *next* kill-chain stage |
| **GNN** (GraphSAGE) | 3 layers, hidden 128, dropout 0.3 | Host/process graph (55-dim node features) | Detects lateral-movement propagation |
| **SecBERT** | Cybersecurity-domain BERT + PCA-16 | Raw logs & commands | Embeds command-line and log text into the feature vector |
| **DQN agent** | Q-net [128,64], 5 actions, target net + replay | 13-dim ensemble state | Learns the response policy |

**Feature pipeline:** 25 conceptual features → 55 canonical columns (23 individual features + 16 log-SecBERT PCA dims + 16 cmd-SecBERT PCA dims), ordered by `selected_features_top25.json`. Probability calibrators (`probability_calibrators.pkl`) map raw scores to lab-refit calibrated probabilities (Beta-VAE Top-25 lab-refit is the active key).

### 2.2 Reinforcement-Learning agent

- **Environment:** custom Gym-style `apt_env.py` simulating an attacker progressing through the CKC.
- **State (13-dim):** AE score, VAE prob + uncertainty, Transformer next-stage logits, GNN propagation score, temporal features, host context.
- **Actions (5):** `MONITOR`, `LOW_ALERT`, `ESCALATE`, `ISOLATE_HOST`, `BLOCK_USER_IP`.
- **Reward shaping:** strongly positive for early-stage (S1–S2) correct interventions (+15), penalised for false isolations and missed late-stage attacks.
- **Training:** ε-greedy DQN with experience replay and target network on synthetic + real lab sequences; ablation study + scaling-law evaluation included (`ablation_study.py`, `evaluate_scaling.py`).
- **Production safeguard:** the DQN is **gated** behind deterministic ML thresholds — a pure-RL policy was measured to produce 100% false-positive interventions, so production gates are load-bearing.

### 2.3 Synthetic data

`meta_sequence_generator.py` produces APT meta-sequences (progressive, repetitive, advanced) with ReALTabFormer integration plus a rule-based fallback, used to bootstrap RL training before fine-tuning on real Caldera-generated data.

---

## 3. Backend Platform — `apps/api`

A FastAPI service (`strix_api`) exposing the OpenAPI surface consumed by both web and mobile clients.

- **Routing layer:** ~20 route modules — `alerts`, `cases`, `chains`, `hunt`, `intel`, `topology`, `ueba`, `dashboard`, `mitre`, `playbooks`, `simulation`, `streams` (SSE), etc.
- **Service layer:** dedicated services for chain investigation, attribution, MITRE ATT&CK mapping, IOC extraction, drift detection, kill-switch, push dispatch, threat-intel ingestion, host detail, UEBA.
- **Workers (ARQ + Redis):** `inference.py` (ML scoring), `normalizer.py` (event normalisation), `verdicts_writer.py`, `wazuh_bridge.py` (SIEM bridge), `intel_feeds_worker.py`.
- **Persistence:** PostgreSQL via SQLAlchemy 2 async + Alembic migrations; Redis for queue, cache, rate-limit.
- **Auth:** Argon2 password hashing, JWT (PyJWT), SlowAPI rate-limiting.
- **Resilience:** `pybreaker` circuit breakers around external APIs (Anthropic, threat-intel feeds), pinned `tornado`, hash-verified model checksums at worker startup (`MODELS_VERIFY_CHECKSUMS=true`).
- **Observability:** structlog, Prometheus metrics, OpenTelemetry tracing, Grafana dashboards, alerting rules.
- **GenAI integration:** Anthropic Claude API used for case-summary generation and analyst Q&A.

---

## 4. Web Console — `apps/web`

Next.js 14 (App Router) + React 18 + Zustand + TanStack Query + Tailwind + Recharts + ReactFlow.

Major dashboards:
- **AI Engine** — live model verdicts, drift telemetry, calibration health.
- **Attack Analysis / Chains** — kill-chain timeline reconstructed from correlated alerts.
- **Threat Intel** — IOC enrichment, feed status, CTI search.
- **Hunt** — analyst-driven query interface.
- **Topology** — host/process graph rendered with ReactFlow, GNN propagation overlay.
- **Vigilance Feed** — SSE-streamed live alerts.
- **Cases**, **Hosts**, **UEBA**, **Notifications**, **Settings**.

The frontend is type-safe end-to-end: API types are generated from the FastAPI OpenAPI spec via `openapi-typescript`, with a CI check (`check:api-types`) that fails if drift is detected.

---

## 5. Mobile App — `apps/mobile`

React Native (Expo, dev-client build, EAS-managed) — an analyst companion app:
- Auth + onboarding flow
- Dashboard with live alert counters, model verdicts, kill-chain progress
- Push notifications via **Expo Push** (chosen over bare FCM for portability)
- Hand-mirrored model registry (`apps/mobile/lib/model-registry.ts`) kept in sync with the web one
- Import-gated `expo-notifications` via `tryGetNotifications()` to keep the app launchable in environments without push entitlements

---

## 6. Lab & Simulation Infrastructure — `infra/`

A complete reproducible lab that exercises the platform end-to-end with real attacker tooling:

- **Compose stacks:** `compose.lab.yml`, `compose.victim.yml`, `compose.simulation.yml`, `compose.chaos.yml`, `compose.platform-deps.yml`, `compose.api.yml`.
- **Telemetry pipeline:** Auditd → Filebeat → Wazuh → STRIX normaliser → ML inference workers → verdicts → web/mobile.
- **Attack simulation:** MITRE Caldera operator running 9 paper-defined APT tactics end-to-end via `infra/scripts/lab_simulate.sh`, producing per-tactic and final detection reports.
- **Monitoring:** Prometheus + Grafana with custom alerting rules, load tests under `infra/loadtests/`.
- **Process orchestration:** root `Procfile.host` for local dev, `Makefile` targets for common workflows.

---

## 7. Engineering Practices

- **Reproducibility:** every model weight is SHA-256 pinned in `apps/models/registry.json` (registryVersion 4); workers refuse to boot on hash mismatch.
- **Schema discipline:** OpenAPI is the single source of truth between backend and both frontends.
- **Type safety:** Python (Pydantic v2) + TypeScript end-to-end.
- **Testing:** unit + integration tests in `apps/api/tests` (real Postgres, no mocks — chosen after a prior incident where mocked tests masked a broken migration).
- **Documentation:** runbooks under `docs/runbooks`, architecture diagrams under `docs/architectures`, model & data references under `docs/lab` and `apps/models/MANIFEST.json`.
- **Demo tooling:** `jury_demo.sh`, `jury_demo_single.sh` reproduce the full attack-to-response flow for stakeholder presentations.

---

## 8. Key Outcomes

- Built a **production-shaped detection platform** spanning ML research, backend, web, mobile, and lab infrastructure — solo end-to-end ownership.
- Designed and trained a **5-model ensemble + DQN agent** that early-detects APT activity at CKC stages 1–2, where signature SIEMs have no signal.
- Implemented a **hash-pinned model registry** and a **drift-aware inference worker** that protects production from silent model swaps.
- Stood up a **Caldera-driven reproducible lab** that runs 9 APT tactics end-to-end and generates verdict reports — used as the system's regression harness.
- Shipped a **type-safe, OpenAPI-driven** web + mobile experience with live SSE feeds, push notifications, and graph-based topology visualisation.

---

## 9. Repository Map

```
GenAI-Detection-Framework/
├── apps/
│   ├── api/        # FastAPI backend, ARQ workers, Alembic migrations
│   ├── web/        # Next.js 14 analyst console
│   ├── mobile/     # React Native (Expo) analyst app
│   ├── models/     # Hash-pinned model artifacts + registry.json
│   ├── data/       # Datasets / fixtures
│   └── notebooks/  # Training / analysis notebooks
├── RL_agent/       # DQN env, training, evaluation, ablation, web demo
├── infra/          # Compose stacks, Wazuh/Filebeat/Auditd, Prometheus, Caldera scripts
├── docs/           # Architectures, runbooks, lab notes
└── config/         # Shared configuration
```
