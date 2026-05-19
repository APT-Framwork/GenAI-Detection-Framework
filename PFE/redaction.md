# Chapter 5 — Implementation: Drafting Brief (redaction.md)

> **Purpose.** Single source of truth for writing `ch5_implementation.tex`. Every number, version, file path, and configuration value has been verified against the repo at `/home/yacine/Desktop/GenAI-Detection-Framework` as of 2026-05-18. Do not invent values — if a value is missing here, mark it `TBD` in the LaTeX and come back.
>
> **Proposed final structure** (Caldera promoted to its own section as requested):
>
> 1. Introduction
> 2. Hardware and Software Environment — Hardware / Libraries / Dev Tools
> 3. Dataset Description — Linux APT Dataset 2024 / Statistics / Simulated APT Groups
> 4. **Attack Simulation with MITRE Caldera (NEW)** — Deployment / 9 Tactics / Topology Discovery / Per-Tactic Reports
> 5. Platform Description — Wazuh SIEM / Auditd-Filebeat Pipeline / Backend Integration / Threat Intelligence Module / APT Early-Detection Dashboard
> 6. Conclusion

---

## 0. Figure Plan — Master Inventory

> The chapter must feel **visual**, not encyclopaedic. Below is the full asset list, numbered consecutively. Every figure is referenced inline in its section as `[FIG 5.x]`. Three types: **L** = logo/badge collage (PNG), **D** = original diagram (TikZ PDF), **S** = annotated screenshot (PNG).
>
> Conventions: all assets live under `report/PFE/figures/ch5/`. Use `\includegraphics[width=…]{figures/ch5/<subdir>/<name>}` (no extension; LaTeX picks the right one). Caption with `\caption{}` and label with `\label{fig:ch5:<slug>}`. Reference in text with `\autoref{fig:ch5:<slug>}`.
>
> **Status legend:** ✅ produced and committed | ⏳ pending (needs live platform) | 🟡 needs manual asset.

| # | Slug | Type | § | Status | Path (relative to `report/PFE/`) | Suggested width |
|---|---|---|---|---|---|---|
| 5.1  | `overview_pillars`        | D | §5.1   | ✅ | `figures/ch5/diagrams/overview_pillars.pdf`        | `0.95\textwidth` |
| 5.2  | `lab_topology`            | D | §5.2.1 | ✅ | `figures/ch5/diagrams/lab_topology.pdf`            | `0.85\textwidth` |
| 5.3  | `stack_logos_backend`     | L | §5.2.2 | ✅ | `figures/ch5/logos/stack_logos_backend.pdf`        | `0.85\textwidth` |
| 5.4  | `stack_logos_rl`          | L | §5.2.2 | ✅ | `figures/ch5/logos/stack_logos_rl.pdf`             | `0.6\textwidth`  |
| 5.5  | `stack_logos_web`         | L | §5.2.2 | ✅ | `figures/ch5/logos/stack_logos_web.pdf`            | `0.85\textwidth` |
| 5.6  | `stack_logos_mobile`      | L | §5.2.2 | ✅ | `figures/ch5/logos/stack_logos_mobile.pdf`         | `0.75\textwidth` |
| 5.7  | `ci_pipeline`             | D | §5.2.3 | ✅ | `figures/ch5/diagrams/ci_pipeline.pdf`             | `0.95\textwidth` |
| 5.8  | `type_safety_chain`       | D | §5.2.3 | ✅ | `figures/ch5/diagrams/type_safety_chain.pdf`       | `0.75\textwidth` |
| 5.9  | `dataset_timeline`        | D | §5.3.1 | ✅ | `figures/ch5/diagrams/dataset_timeline.pdf`        | `0.95\textwidth` |
| 5.10 | `dataset_class_split`     | D | §5.3.2 | ✅ | `figures/ch5/charts/dataset_class_split.pdf`       | `0.45\textwidth` |
| 5.11 | `dataset_tactic_bars`     | D | §5.3.2 | ✅ | `figures/ch5/charts/dataset_tactic_bars.pdf`       | `0.55\textwidth` |
| 5.12 | `feature_pipeline`        | D | §5.3.2 | ✅ | `figures/ch5/diagrams/feature_pipeline.pdf`        | `\textwidth`     |
| 5.13 | `apt_groups_cards`        | L+D | §5.3.3 | ✅ | `figures/ch5/diagrams/apt_groups_cards.pdf` (uses `flags/{cn,ru}.png` from flagcdn) | `\textwidth` |
| 5.14 | `caldera_architecture`    | D | §5.4.1 | ✅ | `figures/ch5/diagrams/caldera_architecture.pdf`    | `0.9\textwidth`  |
| 5.15 | `caldera_ports`           | D | §5.4.2 | ✅ | `figures/ch5/diagrams/caldera_ports.pdf`           | `0.4\textwidth`  |
| 5.16 | `nine_tactics_kcc`        | D | §5.4.3 | ✅ | `figures/ch5/diagrams/nine_tactics_kcc.pdf`        | `\textwidth`     |
| 5.17 | `topology_run_manifest`   | D | §5.4.4 | ✅ | `figures/ch5/diagrams/topology_run_manifest.pdf`   | `0.95\textwidth` |
| 5.18 | `per_tactic_report`       | S | §5.4.5 | ✅ | `figures/ch5/screenshots/per_tactic_report.png` (rendered from `lab_simulate.sh --only Discovery` via `aha` + styled HTML) | `0.85\textwidth` |
| 5.19 | `simulation_envir`        | D | §5.4.5 | ✅ | `figures/ch5/diagrams/simulation_envir.pdf`        | `\textwidth`     |
| 5.20 | `wazuh_logo_rules`        | D | §5.5.1 | ✅ | `figures/ch5/diagrams/wazuh_logo_rules.pdf`        | `0.95\textwidth` |
| 5.21 | `auditd_filebeat_flow`    | D | §5.5.2 | ✅ | `figures/ch5/diagrams/auditd_filebeat_flow.pdf`    | `0.95\textwidth` |
| 5.22 | `data_flow_master`        | D | §5.5.3 | ✅ | `figures/ch5/diagrams/data_flow_master.pdf`        | `\textwidth`     |
| 5.23 | `dqn_gating_logic`        | D | §5.5.3 | ✅ | `figures/ch5/diagrams/dqn_gating_logic.pdf`        | `0.6\textwidth`  |
| 5.24 | `threat_intel_schema`     | D | §5.5.4 | ✅ | `figures/ch5/diagrams/threat_intel_schema.pdf`     | `0.9\textwidth`  |
| 5.25 | `dashboard_ai_engine`     | S | §5.5.5 | ✅ | `figures/ch5/screenshots/dashboard_ai_engine.png` (MODEL MONITORING tab, 5-model live panels) | `0.95\textwidth` |
| 5.26 | `dashboard_chains`        | S | §5.5.5 | ✅ | `figures/ch5/screenshots/dashboard_chains.png` (Chain 34422f12 — BENIGN forensic report, AI predictions donut, APT28 attribution) | `0.95\textwidth` |
| 5.27 | `dashboard_topology`      | S | §5.5.5 | ✅ | `figures/ch5/screenshots/dashboard_topology.png` (attacker + 2 victims, tactic chips, GNN Victim Graph) | `0.95\textwidth` |
| 5.28 | `dashboard_mobile`        | S | §5.5.5 | ⏳ device capture (Expo dev-client)                  | — | `0.45\textwidth` |
| 5.29 | `dashboard_mobile_chain`  | S | §5.5.5 | ⏳ same                                              | — | `0.45\textwidth` |

**Reproduction commands** (everything is scripted):

```bash
# data charts (donut + per-tactic bars) — from labels.parquet
cd report/PFE/figures/ch5/charts && python3 make_dataset_charts.py

# logo grids (simpleicons CDN, cached locally)
cd report/PFE/figures/ch5/logos   && python3 make_logo_grids.py

# all TikZ diagrams → PDF
cd report/PFE/figures/ch5/diagrams && make
```

**Tally:** **27 / 29 figures produced and committed**. The 2 still outstanding are mobile screenshots (FIG 5.28, 5.29) which require an Expo dev-client device capture and so can't be automated from the host.

Breakdown of what's done:
- 16 TikZ diagrams (`figures/ch5/diagrams/*.pdf`)
- 4 logo grids (`figures/ch5/logos/*.pdf`)
- 2 data charts (`figures/ch5/charts/*.pdf`)
- 4 web/terminal screenshots (`figures/ch5/screenshots/*.png`) — AI Engine, Chains, Topology, per-tactic report
- 1 flag-asset set (`figures/ch5/diagrams/flags/{cn,ru}.png` from flagcdn)

**Asset-production checklist** (status as of last build):

- [x] Logos: pulled from simpleicons CDN by `figures/ch5/logos/make_logo_grids.py`; SVGs cached under `_cache/`; libraries without a simpleicons entry (Zustand, ReactFlow, Recharts, Matplotlib, Gym) fall back to clean text tiles.
- [x] Web dashboard screenshots (FIG 5.18, 5.25–5.27): captured via Playwright against live `apps/web` on `:5600` after a `lab_simulate.sh --only Discovery` run populated platform state. Screenshots stored under `figures/ch5/screenshots/`.
- [ ] Mobile screenshots (FIG 5.28, 5.29): capture from the Expo dev-client build on device, then annotate.
- [x] All 16 TikZ diagrams written as `standalone` files under `figures/ch5/diagrams/`; compiled by `make`. Shared style in `_style.tex` (colour palette + node/edge styles) so the chapter has one consistent visual language.
- [x] Data charts: `figures/ch5/charts/make_dataset_charts.py` reads `apps/models/labels.parquet` and emits PDF + PNG.
- [x] FIG 5.9 `dataset_timeline`: ribbon-style 14-week TikZ; FIG 5.13 `apt_groups_cards`: 2×2 grid with PNG flags from flagcdn (cn, ru).

---

## 5.1 Introduction (½ page)

Chapter 4 described the *conception* of the STRIX framework: the dataset choice, the preprocessing pipeline, the five detection models, the synthetic-data augmentation, and the reinforcement-learning agent. This chapter moves from design to **realisation**: the concrete software stack that supports the framework, the dataset as it is materialised inside the system, the live attack-simulation lab that exercises the platform end-to-end, and the production platform itself — its SIEM integration, its asynchronous workers, its threat-intelligence module, and its analyst-facing dashboards.

The implementation is intentionally **production-shaped**: model weights are SHA-256 pinned, the OpenAPI surface is the single contract between the FastAPI backend and the two type-safe frontends (Next.js web console and Expo mobile app), and the entire alert-to-verdict pipeline is reproducible from a Docker Compose stack and a single shell script.

Talking points:
- Five distinct sub-systems (ML, backend, web, mobile, lab) integrated end-to-end.
- Solo ownership; no proprietary services — everything runs locally.
- Emphasis on reproducibility (hash-pinned models, deterministic seeds, Compose-orchestrated lab).

> **[FIG 5.1 — `overview_pillars`]** Place at the end of §5.1 as a half-page figure. The five-pillars diagram gives the reader a roadmap for the entire chapter; every subsequent section drills into one or two pillars.

---

## 5.2 Hardware and Software Environment

### 5.2.1 Hardware

**Reference sources:** `apps/api/Dockerfile`, `docs/runbooks/inference-worker-oom.md`, `infra/compose.api.yml`, `RL_agent/README.md`.

| Component | Specification | Justification |
|---|---|---|
| Development & training host | CPU-only (no GPU/CUDA mandated) | PyTorch is pinned to the CPU wheel (`torch==2.4.1+cpu`) to keep the API container under ~600 MB instead of ~3.6 GB; training scripts accept `--device cuda` as an opt-in flag but the production path is CPU. |
| Inference-worker RAM | ~600 MB resident, 1.2 GB peak | Documented budget for a single `inference` worker shard (`docs/runbooks/inference-worker-oom.md`). |
| Redis | 512 MB max-memory (default), `noeviction` policy | Historical incident forced bump to 4 GB once; default is the lab value. |
| PostgreSQL | TimescaleDB 2.17.2 on PG 16 | Hypertables used for `detections` (time-partitioned alert verdict table). |
| Lab topology | 1 attacker container (Kali + Caldera) + N victim containers (Ubuntu 22.04 + Wazuh-agent + Auditd) on a shared Docker bridge network | Mirrors the Linux APT Dataset 2024 collection setup. |

> **[FIG 5.2 — `lab_topology`]** Insert here. A small diagram showing developer laptop → Docker Compose bridge network → containers (attacker + victims). Mention in the caption that the same stack can be deployed on a single 16 GB VM for the jury demo (`jury_demo.sh`).

### 5.2.2 Libraries

Split the discussion into **four stacks** so the reader sees the framework's breadth.

> **[FIG 5.3 — `stack_logos_backend`]** Place at the start of §5.2.2.1 as a one-row logo grid. A wall of logos immediately conveys breadth before the reader hits the table.

#### 5.2.2.1 Backend & ML stack (Python ≥ 3.11, < 3.13)

| Domain | Library | Pinned version |
|---|---|---|
| Web framework | FastAPI / Uvicorn | `>=0.115,<0.118` / `>=0.32,<0.36` |
| Validation | Pydantic v2 / pydantic-settings | `>=2.9,<3` / `>=2.5,<3` |
| ORM & migrations | SQLAlchemy (async) / Alembic | `>=2.0.36,<2.1` / `>=1.14,<1.16` |
| DB driver | asyncpg | `>=0.30,<0.31` |
| Queue | ARQ (over Redis) / redis-py | `>=0.26,<0.27` / `>=5.2,<6` |
| Auth | argon2-cffi / PyJWT | `>=23.1,<26` / `>=2.10,<3` |
| ML core | PyTorch / torch-geometric | `>=2.4,<3` (CPU wheel) / `>=2.5,<3` |
| NLP | transformers (SecBERT) | `==4.57.6` (single pinned minor) |
| Numerics | NumPy / pandas / scikit-learn / joblib | `>=1.26,<3` / `>=2.2,<3` / `>=1.5,<2` / `>=1.4,<2` |
| GenAI | anthropic | `>=0.40,<0.50` |
| Resilience | pybreaker / tornado | `>=1.2,<2` / `>=6.0,<7` |
| Observability | structlog / prometheus-client / opentelemetry-{api,sdk} | `>=24.4,<26` / `>=0.21,<0.23` / `>=1.28,<2` |
| Rate limiting | slowapi | `>=0.1.9` |
| SSE | sse-starlette | `>=2.1,<4` |

> Mention: `transformers` is **single-minor pinned** (`==4.57.6`) because the SecBERT PCA bases were fit against tokeniser behaviour from that release; a minor bump risks silent PCA drift.

> **[FIG 5.4 — `stack_logos_rl`]** Small logo strip above this sub-section.

#### 5.2.2.2 Reinforcement-learning training stack (`RL_agent/requirements.txt`)

- `torch`, `torchvision`, `numpy`, `pandas`
- `gym>=0.21.0` (custom `APTEnv` extends `gym.Env`)
- `scikit-learn`, `matplotlib`, `seaborn`, `tqdm`, `openpyxl`

> **[FIG 5.5 — `stack_logos_web`]** Logo grid above this sub-section.

#### 5.2.2.3 Web console (`apps/web/package.json`)

| Library | Version | Role |
|---|---|---|
| Next.js | `14.2.29` | App Router, SSR, route handlers |
| React | `^18.3.1` | UI runtime |
| TypeScript | `^5.8.3` | Static typing end-to-end |
| Tailwind CSS | `^3.4.17` | Utility-first styling |
| Zustand | `^5.0.5` | Client state |
| TanStack Query | `^5.62.0` | Server-state cache, retries, polling |
| Recharts | `^2.15.3` | Time-series and bar charts |
| ReactFlow | `^11.11.4` | Topology / GNN graph rendering |
| openapi-typescript | `^7.4.4` | Generates TS types from FastAPI's OpenAPI |
| next-themes | `^0.4.6` | Light/dark theme switching |
| lucide-react | `^0.511.0` | Icon set |

> **[FIG 5.6 — `stack_logos_mobile`]** Logo grid above this sub-section.

#### 5.2.2.4 Mobile app (`apps/mobile/package.json`)

| Library | Version | Role |
|---|---|---|
| Expo SDK | `~54.0.34` | Managed React-Native build chain |
| React Native | `0.81.5` | Runtime |
| React | `19.1.0` | UI |
| expo-router | `~6.0.23` | File-based routing |
| @tanstack/react-query | `^5.59.0` | Same data layer as web |
| Zustand | `^5.0.12` | Same store pattern as web |
| expo-notifications | `~0.32.17` | Push (import-gated through `tryGetNotifications()`) |
| expo-secure-store | `~15.0.7` | JWT storage |
| react-native-sse | `^1.2.1` | SSE client for Vigilance feed |
| react-native-reanimated | `~4.1.1` | Animations |
| react-native-svg | `15.12.1` | Vector graphics |

> Suggested table layout: one merged table per stack so the chapter does not feel like a bibliography.

### 5.2.3 Development Tools

**Languages & quality gates**

- **Python:** `ruff` (target Py 3.11, line length 100) + `mypy --strict` (advisory on advisory paths) + `pytest` + `pytest-asyncio` + `hypothesis` + `schemathesis`.
- **TypeScript (web):** ESLint via `eslint-config-next`, TypeScript 5.8.3 strict mode.
- **TypeScript (mobile):** TypeScript ~5.9.2, Expo CLI.

**Build & runtime**

- **Docker images:**
  - API & workers: `python:3.11-slim` (multi-stage builder → slim runtime, CPU-only torch wheel).
  - Web: `node:20-bookworm-slim` (pnpm via `corepack`).
- **Compose stacks under `infra/`:** `compose.api.yml`, `compose.lab.yml`, `compose.victim.yml`, `compose.simulation.yml`, `compose.chaos.yml`, `compose.platform-deps.yml`.
- **Local Procfile orchestration:** `Procfile.host` (managed by Honcho) for running api + 4 workers + web outside of Docker.
- **Make targets:** `make smoke`, `make up`, `make down`, `make test`, `make migrate`, `make seed`.

**Continuous Integration (`.github/workflows/`)**

| Workflow | Job summary |
|---|---|
| `api.yml` | ruff + mypy + unit (pytest, ≥55 % coverage gate) + integration (real Postgres+Redis service containers) + Alembic round-trip migration drift check + buildx Docker cache. |
| `web.yml` | Type-check (incl. `check:api-types` — fails on OpenAPI ↔ TS drift) + lint + build. |
| `mobile.yml` | Type-check + Expo build sanity. |
| `security.yml` | Dependency-vulnerability scan + secret scanning. |
| `loadtest.yml` | k6 load test triggered manually against the simulation compose stack. |

> Mention the **end-to-end type-safety chain**: Pydantic models → FastAPI OpenAPI → `openapi-typescript` → web + mobile clients. A CI failure on `check:api-types` is how silent API/UI drift is prevented.
>
> **[FIG 5.7 — `ci_pipeline`]** Place after the CI table — a swimlane showing the 5 workflows triggered by a single push.
>
> **[FIG 5.8 — `type_safety_chain`]** Place immediately after the type-safety paragraph above. Visualises the Pydantic → OpenAPI → TS pipeline with the CI gate highlighted.

---

## 5.3 Dataset Description

### 5.3.1 Linux APT Dataset 2024

Reference: Karim, S. S., Afzal, M., Iqbal, W., & Al Abri, D. (2024). *Advanced Persistent Threat (APT) and intrusion-detection evaluation dataset for Linux systems 2024*. **Data in Brief, 54, 110290**. [→ add `\cite{karim2024linux}` to `references.bib`].

Collection setup, summarised:

- Period: **2023-10-01 → 2024-01-07** (~14 weeks).
- Environment: 1 Kali attacker (≈ APT41/28/29/Turla TTPs replayed) → 3 Ubuntu 22.04 victims. Each victim ran the Wazuh agent (v4.5.2) + Auditd + Kaspersky Security Center 14.2. Caldera orchestrated the attacks; YARA enriched detections.
- Raw size on disk: ~125 898 records.

What is materialised inside STRIX:

- `apps/models/feature_matrix_no_leakage.parquet` — **115 726 rows × 119 columns**, the canonical pre-scaled feature matrix used by all four supervised neural models.
- `apps/models/labels.parquet` — labels (binary + CKC stage) aligned 1-for-1 with the matrix.

> **[FIG 5.9 — `dataset_timeline`]** Insert at the end of §5.3.1. 14-week timeline (Oct 2023 → Jan 2024) with the four emulated APT actors annotated as ribbons above. Source the data from `docs/lab/CALDERA_MITRE_SIMULATION_GUIDE.md`.

### 5.3.2 Statistics

Use real counts; copy verbatim into a table.

> **[FIG 5.10 + FIG 5.11 — `dataset_class_split` + `dataset_tactic_bars`]** Place these two side-by-side immediately after the two tables below. The donut chart visualises the binary split; the bar chart visualises the per-tactic skew (S2/S6 effectively absent — sets up the discussion of the Transformer's class-weights). Produce both from `apps/models/labels.parquet` with `matplotlib`, export to PDF.

**Binary class distribution (115 726 alerts):**

| Class | Count | % |
|---|---:|---:|
| Benign | 90 308 | 78.0 % |
| Malicious | 25 418 | 22.0 % |
| **Total** | **115 726** | **100 %** |

**Train/val/test split** — stratified 70/15/15 with `seed=42`, identical across AE, β-VAE, Transformer, and GNN.

**Distribution per MITRE tactic / CKC stage** (from `docs/lab/CALDERA_MITRE_SIMULATION_GUIDE.md:22-39`):

| MITRE tactic | CKC stage | Records |
|---|---:|---:|
| Defense Evasion | S5 | 18 124 |
| Privilege Escalation | S4 | 17 164 |
| Initial Access | S3 | 16 624 |
| Discovery | S7 | 14 058 |
| Impact | S7 | 2 868 |
| Persistence | S5 | 1 709 |
| Execution | S4 | 1 655 |
| Reconnaissance | S1 | 643 |
| Lateral Movement | S5 | 240 |
| Credential Access | S7 | 35 |
| Collection | S7 | 3 |
| Command & Control | S6 | 2 |

> **Critical talking point** for the chapter: Weaponisation (S2) and C&C (S6) are effectively absent — 0 and 2 records respectively. The Transformer's output heads for these stages therefore degenerate, which is **why a deterministic gate is enforced in front of the DQN in production** (see §5.5.3). This is also why class weights `[0.2115, 29.9953, 0.0000, 1.1650, 4.4948, 15.0562, 0.0000, 10.8537]` were used for the Transformer (S2 and S6 hard-zeroed).

> **[FIG 5.12 — `feature_pipeline`]** Insert here. End-to-end diagram of the feature pipeline (raw JSON → 25 conceptual features → 55 canonical columns → `StandardScaler`). Annotate the SecBERT branches with their PCA variance retained (77.82 % / 97.05 %). This is one of the chapter's most informative figures.

**Feature engineering — the 55 canonical columns** (`apps/models/selected_features_top25.json`):

- **23 individual features:**
  - 16 binary indicators: `decoder_auditd`, `srcip_is_private`, `decoder_web-accesslog`, `path_is_missing`, `has_md5`, `has_sha256`, `syscheck_added`, `cmd_is_missing`, `decoder_dpkg-decoder`, `syscheck_deleted`, `syscheck_modified`, `decoder_syscheck_deleted`, `path_is_sensitive`, `decoder_syscheck_integrity_changed`, `location_syscheck`, `path_is_temp`.
  - 3 location indicators: `location__var_log_audit_audit.log`, `location__var_log_apache2_access.log`, `location__var_log_auth.log`.
  - 4 numerics: `firedtimes`, `firedtimes_log` (`log1p` transform), `cmd_length`, `path_depth`.
- **16 log-SecBERT PCA components** (`log_secbert_emb_0..15`): SecBERT(`_source.full_log`, max_len = 128, mean-pool with attention mask) → PCA-16 → **77.82 %** variance retained. Artifact: `apps/models/secbert_log_pca.pkl`.
- **16 cmd-SecBERT PCA components** (`cmd_secbert_emb_0..15`): SecBERT(`_source.data.command`) → PCA-16 → **97.05 %** variance retained. Artifact: `apps/models/secbert_cmd_pca.pkl`.

The canonical column order is `[23 individuals] → [log_pca_0..15] → [cmd_pca_0..15]`, materialised by `selected_features_top25.json` and consumed by the inference workers via `apps/api/src/strix_api/core/state_builder.py`.

**Production preprocessing artifacts** (all SHA-256 pinned in `apps/models/registry.json`, version 4):

| Artifact | File | Size |
|---|---|---|
| Selected features manifest | `selected_features_top25.json` | 2.2 KB |
| `StandardScaler` (55 cols) | `standard_scaler.pkl` | 3.0 KB |
| Log-SecBERT PCA | `secbert_log_pca.pkl` | 53.1 KB |
| Cmd-SecBERT PCA | `secbert_cmd_pca.pkl` | 53.1 KB |
| Probability calibrators | `probability_calibrators.pkl` | 2.0 KB |
| GNN metadata | `gnn_metadata.pkl` | 3.3 KB |
| SecBERT tokenizer & model | `apps/models/preprocess/secbert*/` | — (hermetic snapshot) |

> **Active calibrator key:** `"Beta-VAE (Top 25) lab-refit"` — this was refit on 2026-05-13 against fresh lab data because the original calibrator was over-confident outside the training distribution.

### 5.3.3 Simulated APT Groups

The dataset emulates **four real-world APT actors** drawn from MITRE ATT&CK group descriptions (referenced in `docs/lab/CALDERA_MITRE_SIMULATION_GUIDE.md:7`):

- **APT41** (China, espionage + financially motivated dual-use TTPs)
- **APT28** (Russia, GRU, espionage)
- **APT29** (Russia, SVR, long-dwell espionage)
- **Turla** (Russia, FSB, custom Linux backdoors)

Plus three opportunistic scenarios that share TTPs with these groups: Apache Struts exploit chains, keylogger deployments, and reverse-shell backdoors.

> **[FIG 5.13 — `apt_groups_cards`]** Replace the loose-table suggestion with a single page-width figure built as four cards (one per actor). Each card has: country flag, origin agency, primary motivation, 2–3 representative TTPs as seen in the dataset, signature malware family. Pull TTPs from `infra/lab-provisioning/wazuh/local_rules.xml` and the Caldera adversary YAMLs under `infra/`. This is the chapter's most visually striking figure — design it carefully.

---

## 5.4 Attack Simulation with MITRE Caldera (NEW SECTION)

> This section is **new** versus the original outline — you requested it. It bridges the dataset (which was generated by Caldera on Karim et al.'s lab) and the live STRIX platform (which is exercised by an in-house Caldera replay).

> **[FIG 5.14 — `caldera_architecture`]** Open §5.4 with this figure. Caldera operator UI ↔ C2 server ↔ Sandcat agents on victim hosts; adversaries/abilities loaded from the stockpile. Frames the whole section.

### 5.4.1 What Caldera is, and why we use it

MITRE Caldera is a Python red-team automation framework: it runs an HTTP/TCP/UDP C2 server, ships pluggable "abilities" (TTP scripts) and "adversaries" (ability sequences), and deploys lightweight **Sandcat** agents on victim hosts to execute those abilities on demand. For STRIX, Caldera plays three complementary roles:

1. **Dataset realism check.** We replay APT41/28/29 adversary profiles against an in-house lab and confirm that the resulting Wazuh alerts match the distributional shape of the Karim et al. dataset.
2. **End-to-end regression harness.** Every change to the ML stack, the Wazuh rules, or the workers is validated by running the same 9-tactic scenario and comparing the per-tactic detection report.
3. **Jury / demo driver.** `jury_demo.sh` and `infra/scripts/lab_simulate.sh` produce a deterministic attack story stakeholders can watch live on the web console.

### 5.4.2 Deployment

`infra/lab-provisioning/01-attacker-caldera.sh` builds Caldera from source (`VARIANT=full`) and runs it as a Docker container on the lab bridge network with persistent volumes:

| Port | Purpose |
|---|---|
| 8888 | Operator web UI (red / blue logins, auto-rotated credentials) |
| 7010 | HTTP C2 contact (Sandcat default) |
| 7011 | UDP C2 contact |
| 7012 | TCP C2 contact |
| 8080 | Payload staging server (systemd `strix-payload-server`) |

Persistent state (`persist/conf`, `persist/data`) lives outside the container so operations survive a rebuild.

> **[FIG 5.15 — `caldera_ports`]** Insert here. A compact box showing the Caldera container and its 5 exposed ports (8888 UI, 7010 HTTP-C2, 7011 UDP-C2, 7012 TCP-C2, 8080 payload). Helps the reader visualise the attack-surface footprint.

### 5.4.3 The Nine Paper-Aligned Tactics

`infra/scripts/lab_simulate.sh:132-136` runs the **nine MITRE tactics** that align with the kill-chain stages most represented in the Karim dataset:

```text
Discovery, Defense Evasion, Persistence, Privilege Escalation,
Credential Access, Lateral Movement, Collection, Exfiltration, Impact
```

| # | Tactic | MITRE ID | CKC stage | Implementation source |
|---|---|---|---|---|
| 1 | Reconnaissance | TA0043 | S1 | `recon_burst.sh` (out-of-band; not Caldera) — SSH-invalid-user bursts + nmap sweep |
| 2 | Discovery | TA0007 | S7 | Caldera adversary abilities: `whoami`, `id`, `ps`, `netstat`, `uname -a` |
| 3 | Defense Evasion | TA0005 | S5 | `wtmp`/`btmp` tampering, log rotation abuse |
| 4 | Persistence | TA0003 | S5 | Crontab drops, systemd unit installs, `.bashrc` injection |
| 5 | Privilege Escalation | TA0004 | S4 | `sudo -l` enumeration, SUID-binary abuse |
| 6 | Credential Access | TA0006 | S7 | `/etc/passwd`, `/etc/shadow` reads; SSH-key exfil |
| 7 | Lateral Movement | TA0008 | S5 | SSH pivot to a second victim subnet |
| 8 | Collection | TA0009 | S7 | `tar`-archive of `/home`, memory snapshot |
| 9 | Exfiltration / Impact | TA0010 / TA0040 | S7 | HTTPS exfil to attacker, then encryption / deletion |

> Note: step 1 is run by a custom script rather than Caldera because Caldera does not emit a pre-implant reconnaissance ability cleanly; this is also the only tactic that targets a host *before* the Sandcat agent is dropped.
>
> **[FIG 5.16 — `nine_tactics_kcc`]** Place after the table. A horizontal CKC spine (S1→S7) with the 9 tactics overlayed as labelled boxes mapped to their CKC stage. Reuses the visual language of Chapter 2's CKC figure for continuity.

### 5.4.4 Topology Discovery and the Run Manifest

Before any tactic fires, `lab_simulate.sh:79-138` introspects the live Compose stack and emits a deterministic run manifest:

```bash
docker ps --format '{{.Names}}' | grep '^strix_victim'
docker inspect strix_caldera \
  --format '{{.NetworkSettings.Networks}}{{.IPAddress}}'
```

Output: `infra/simulation/runs/{RUN_ID}/topology.json`

```json
{
  "run_id": "20260518T143022Z-1234",
  "started_at": "2026-05-18T14:30:22Z",
  "attacker_ip": "172.18.0.x",
  "victims": [
    {"ip": "172.18.0.y", "hostname": "victim1",
     "agents": ["wazuh", "sandcat", "auditd"]},
    {"ip": "172.18.0.z", "hostname": "victim2",
     "agents": ["wazuh", "sandcat", "auditd"]}
  ],
  "apt_group": "APT29",
  "tactics_planned": ["Discovery", "Defense Evasion", "..."]
}
```

This manifest is what binds a run's detection report back to the actual hosts and abilities executed — essential for reproducibility.

> **[FIG 5.17 — `topology_run_manifest`]** Place after the JSON. Two-panel figure: left = rendered diagram of one lab run (attacker + 2 victims with IPs); right = the JSON snippet above. Demonstrates that the manifest is a faithful machine-readable copy of the diagram.

### 5.4.5 Per-Tactic and Final Detection Reports

The orchestrator `infra/simulation/scripts/run_full_simulation.py` (lines 444-483) drives the loop:

```
for tactic in tactics_planned:
    fire_caldera_ability(tactic)
    sleep(settle_time)       # allow Wazuh→STRIX pipeline to flush
    report = aggregate_db(tactic)
    print(report)
final_report = aggregate_all_runs()
```

For each tactic the report queries:

- `attack_chains` (Postgres) — chains opened in the last `T` seconds, with their CKC-stage trajectory.
- `detections` (TimescaleDB hypertable) — verdicts with matching MITRE tactic tags; counted by CKC stage.
- `dqn_actions` — the action the DQN chose (`MONITOR`, `LOW_ALERT`, `ESCALATE`, `ISOLATE_HOST`, `BLOCK_USER_IP`) and whether the deterministic gate authorised the intervention.

The **final aggregate** computes precision, recall, and F1 per tactic across both hosts, plus the median detection latency from `caldera.ability.started_at` to `detection.created_at`. This output is the regression artefact used in Chapter 6 to compare model versions.

> **[FIG 5.18 — `per_tactic_report`]** Insert here. Annotated terminal screenshot of `run_full_simulation.py` per-tactic output (tactic name, alert count, CKC distribution, DQN action, median latency). Captured live from one of the `infra/simulation/runs/` directories.
>
> **[FIG 5.19 — `simulation_envir`]** Place at the **end of §5.4** as a full-page figure with the caption *"STRIX simulation environment: from Caldera ability to dashboard verdict."* This is the **single picture** that ties Caldera and the STRIX runtime together — readers will refer back to it for the rest of the chapter. Strongly recommend designing this one first.

> **Warning to include in the chapter** (use the `\customwarning{}` macro): *Audit rules in `/etc/audit/rules.d/strix.rules` are persisted across reboots, but after a host reboot the kernel may load them in a different order. `lab_simulate.sh:40` re-validates with `sudo auditctl -l | grep audit-wazuh-x` before firing the first tactic.*

---

## 5.5 Platform Description

### 5.5.1 Wazuh SIEM

Wazuh is the host-sensor + log-aggregator layer. STRIX does **not** modify the Wazuh manager binary — instead it provides:

- Auditd rules optimised for the Linux APT kill chain (§5.5.2).
- Custom Wazuh decoders and rules in `infra/lab-provisioning/wazuh/local_rules.xml`, deployed to `/var/ossec/etc/rules/local_rules.xml` and reloaded with `systemctl restart wazuh-manager`.
- A custom rule muting hierarchy: parent rules 80789 (execve), 80784 (write), 80785 (read) are forced to `level=0` so they do not flood the alert stream; child rules 100100+ inherit via `<if_sid>` and only fire on attack-relevant patterns.
- Pre-implant detection rules (100050/100051) flagging SSH-invalid-user bursts and nmap fingerprinting — mapped to T1595 (Reconnaissance, CKC S1).

The Wazuh manager writes alerts as newline-delimited JSON to `/var/ossec/logs/alerts/alerts.json`. From the STRIX perspective, this file is the single integration contract with Wazuh: **everything downstream is owned by us**.

> **[FIG 5.20 — `wazuh_logo_rules`]** Place at the end of §5.5.1. Wazuh logo + a small tree showing the rule muting hierarchy (parent rules 80789/80784/80785 muted at level 0; child rules 100050/100051/100100+ inheriting via `<if_sid>`). Helps the reader grasp why we need *both* parent muting *and* child overrides.

### 5.5.2 Auditd → Filebeat Ingestion Pipeline

The kernel-level signal source is **Auditd**, configured by `infra/auditd/strix.rules` — 52 rules covering 7 kill-chain phases:

| Rule key | Wazuh parent | Coverage |
|---|---|---|
| `audit-wazuh-x` | 80789 (execve) | Process execution: shell injection, LOLBAS abuse, discovery commands |
| `audit-wazuh-w` | 80784 (write) | File writes to crontabs, systemd units, `.bashrc`, init.d |
| `audit-wazuh-r` | 80785 (read) | Sensitive reads on `/etc/{passwd,shadow}`, `/root/.ssh`, `/home/*/.ssh` |
| `audit-wazuh-a` | 80786 (attribute) | `chmod`/`chown` on logs and security tooling |

Installation:

```bash
sudo cp infra/auditd/strix.rules /etc/audit/rules.d/strix.rules
sudo augenrules --load
sudo auditctl -l | grep audit-wazuh-x   # validation
```

**Filebeat 8.15.3** tails the Wazuh alerts file with a 1-second scan interval and pushes alerts to a Redis list (`infra/filebeat.yml`):

```yaml
filebeat.inputs:
  - type: filestream
    paths: [/var/ossec/logs/alerts/alerts.json]
    prospector.scanner.check_interval: 1s
    parsers:
      - ndjson: { target: "", overwrite_keys: true }
output.redis:
  key: "strix:alerts:raw:list"
  datatype: list
```

A small JS processor on Filebeat tags events from UID 4242 (`strixbenign` synthetic user) with `strix.synthetic_benign=true`, letting later workers filter out the noise the lab itself generates. The Filebeat registry file lives in a Docker volume (`strix_filebeat_data`), giving **at-least-once** delivery: if Redis or the bridge dies, the offset is not advanced and Filebeat resumes from the last successful push.

> **[FIG 5.21 — `auditd_filebeat_flow`]** Place at the end of §5.5.2. Kernel syscalls → Auditd rules (52, grouped by CKC phase) → Wazuh decoder → `alerts.json` → Filebeat (1 s tail) → Redis List. Show the at-least-once guarantee as a labelled feedback arrow.

### 5.5.3 Backend Integration — Workers and Redis Streams

This is the heart of the production platform: a five-stage pipeline from raw Wazuh JSON to a persisted, dashboard-visible verdict.

> **[FIG 5.22 — `data_flow_master`]** **The single most important figure in the chapter.** Place at the very start of §5.5.3 as a full-page (`\textwidth`) diagram. The 5-stage Redis-Streams pipeline with every stream key and worker file labelled. The ASCII art below is the storyboard — render it cleanly in TikZ or Excalidraw. Every other system-level discussion in the chapter refers back to this figure.

```text
Wazuh alerts.json
   ↓ (Filebeat tails, RPUSH)
strix:alerts:raw:list (Redis List, staging)
   ↓ (wazuh_bridge BLPOP → XADD)
strix:alerts:raw (Redis Stream)
   ↓ (normalizer: 55-dim feature extraction, shards by SHA-1(agent_id) % N)
strix:features:{shard_id} (Redis Stream)
   ↓ (inference: AE + β-VAE + Transformer + GNN + DQN, batch 32)
strix:verdicts (Redis Stream)
   ↓ (verdicts_writer: SQL UPSERT, chain bump, SSE broadcast)
PostgreSQL (hosts, alerts, detections, attack_chains, dqn_actions)
   ↓ (sse-starlette)
Web + Mobile vigilance feed
```

| Worker | File | Responsibility |
|---|---|---|
| `wazuh_bridge` | `apps/api/src/strix_api/workers/wazuh_bridge.py` | Drains the Filebeat list into the Redis Stream; restores messages to the list head on XADD failure (no message loss). |
| `normalizer` | `apps/api/src/strix_api/workers/normalizer.py` | Parses raw Wazuh JSON, builds the 55-dim feature vector, applies the canonical column order, shards downstream. |
| `inference` | `apps/api/src/strix_api/workers/inference.py` | Loads all five models from `apps/models/` (hash-verified at boot if `MODELS_VERIFY_CHECKSUMS=true`), batches features, emits a `VerdictMessage`. |
| `verdicts_writer` | `apps/api/src/strix_api/workers/verdicts_writer.py` | UPSERTs hosts, INSERTs alerts/detections, opens or bumps `attack_chains`, persists DQN actions, fans out SSE. |
| `intel_feeds_worker` | `apps/api/src/strix_api/workers/intel_feeds_worker.py` | Pulls URLhaus + FeodoTracker every 30 s (§5.5.4). |
| `arq_tasks` | `apps/api/src/strix_api/workers/arq_tasks.py` | On-demand jobs (VirusTotal lookups, case-summary LLM calls). |

> **[FIG 5.23 — `dqn_gating_logic`]** Place immediately after the production-safety bullet list below. A decision diagram: DQN proposes action → 4 deterministic gates (AE / β-VAE / Transformer / GNN) → action authorised or down-graded. The caption must mention the 100 % FPR finding to justify the visual complexity.

**Production-safety gates inside `inference`:**

- **Hash-pinned model loading.** `apps/models/registry.json` (version 4) carries the SHA-256 of every weight; if `MODELS_VERIFY_CHECKSUMS=true`, the worker refuses to boot on mismatch.
- **DQN is gated.** A pure-RL policy in isolation was measured to produce **100 % false-positive interventions** (cf. §4.x of Chapter 4). In production the DQN's chosen action is filtered through deterministic thresholds (AE score, calibrated β-VAE probability, Transformer confidence, GNN node-risk). Only when all gates agree does an `ISOLATE_HOST` or `BLOCK_USER_IP` action propagate.
- **Drift detection.** Per-shard rolling distributions are compared against the training reference; an alert is raised when KL > threshold.
- **Circuit breakers.** `pybreaker` wraps the Anthropic API, VirusTotal, URLhaus, and FeodoTracker — half-open after 60 s, fully open after 5 consecutive failures.

### 5.5.4 Threat Intelligence Module

`apps/api/src/strix_api/workers/intel_feeds_worker.py` polls two open-source CTI feeds every 30 seconds:

| Feed | URL | Indicator types |
|---|---|---|
| URLhaus | `urlhaus.abuse.ch/downloads/json_recent/` | URL, domain, IPv4, SHA-256 payload hash |
| Feodo Tracker | `feodotracker.abuse.ch/downloads/ipblocklist.json` | IPv4 with malware family, port, confidence |

Each indicator is upserted into `intel_indicators` with a tracked `internal_hit_count`. The corresponding service `apps/api/src/strix_api/services/threat_intel_service.py` exposes:

- `GET /api/v1/threat-intel/feeds` — feed health (last pull, status, count).
- `GET /api/v1/threat-intel/indicators?search=…` — search by type / source.
- `GET /api/v1/threat-intel/observable-hits/{indicator}` — cross-references the indicator against the internal `detections` table, surfacing **Tier-1 "observable hits"** (the moment an external IOC is seen on our hosts).

Supported indicator types: `ip`, `domain`, `url`, `hash` (MD5/SHA-256), `email`.

The intelligence service also joins `threat_actors` → `campaigns` → `attack_chains` so analysts can attribute a live chain to a known group with a single click.

> **[FIG 5.24 — `threat_intel_schema`]** Insert at the end of §5.5.4. URLhaus + FeodoTracker feeds → `intel_feeds_worker` (30 s tick) → `intel_indicators` table → join with internal `detections` → "observable hit" surfaced in the UI. Shows clearly how external CTI lands inside the platform.

### 5.5.5 APT Early-Detection Dashboard

Two type-safe clients consume the same OpenAPI surface.

**Web console (`apps/web`, Next.js 14 App Router):**

| Tab | Backend route | What it shows |
|---|---|---|
| AI Engine | `GET /api/v1/dashboard/attack-vector` | Live model verdicts; CKC-stage distribution over 1 h / 24 h / 7 d. |
| Attack Analysis / Chains | `GET /api/v1/chains/{chain_id}` | Kill-chain timeline reconstructed from correlated alerts. |
| Threat Intel | `GET /api/v1/intel/overview` | Actors, campaigns, indicators, internal observable hits. |
| Hunt | `GET /api/v1/hunt/queries` | Analyst-driven MITRE-technique query interface. |
| Topology | `GET /api/v1/topology` | Host/process graph rendered with ReactFlow + GNN propagation overlay. |
| Vigilance Feed | `GET /api/v1/streams/verdicts` (SSE) | Server-pushed alert stream. |
| Cases | `GET /api/v1/cases` | Incident tracking + LLM-generated case summaries (Claude Opus 4.7). |
| Hosts | `GET /api/v1/hosts` | Host inventory, agent status, alert counts. |
| UEBA | `GET /api/v1/ueba/baselines` | User-behaviour baselines and peer-group anomalies. |

**Mobile companion (`apps/mobile`, Expo dev-client build):**

- Authentication + onboarding flow.
- Dashboard with live alert counters, model verdicts, kill-chain progress.
- Vigilance feed via `react-native-sse`.
- Push notifications through Expo Push (kept over bare FCM for portability; the EAS projectId is bound to owner `yacine_na`).
- Hand-mirrored model registry (`apps/mobile/lib/model-registry.ts`) kept in sync with the web one.

> **Screenshot quintet** (capture all five during one live `lab_simulate.sh` run so the data is internally consistent):
>
> - **[FIG 5.25 — `dashboard_ai_engine`]** Annotated screenshot of the AI Engine tab during a Caldera run.
> - **[FIG 5.26 — `dashboard_chains`]** The Chains tab showing a reconstructed APT29 kill chain with CKC stages highlighted.
> - **[FIG 5.27 — `dashboard_topology`]** The Topology tab with the GNN propagation overlay on a 2-victim lab.
> - **[FIG 5.28 — `dashboard_mobile`]** Mobile vigilance feed with a pushed alert (paired side-by-side with FIG 5.29).
> - **[FIG 5.29 — `dashboard_mobile_chain`]** Mobile chain-detail screen with a one-tap "Isolate host" action.
>
> Production tip for the screenshots: capture web in dark mode (matches the platform's default theme), mobile in the Expo device frame, and overlay red arrows + numbered callouts in Figma / Inkscape so each screenshot tells one specific story.

> Talking point: the **type-safety contract**. Add a short paragraph explaining that the OpenAPI spec is generated by FastAPI, transformed into TypeScript via `openapi-typescript`, and a CI job (`check:api-types`) fails the pipeline if the generated types diverge from what the web client expects. This is the single mechanism preventing silent backend/frontend drift across three independent codebases.

---

## 5.6 Conclusion

Wrap-up beats:

- We mapped the conceptual framework of Chapter 4 onto a concrete, reproducible system: real PyTorch model artefacts, real Wazuh integration, a real Caldera-driven lab, a real type-safe web + mobile experience.
- The platform is **production-shaped**: SHA-256 pinned models, deterministic gates around the DQN, hash-verified loading, drift detection, circuit breakers around every external dependency.
- Caldera + Auditd + Filebeat + Wazuh + STRIX form a **closed loop** that turns red-team activity into ML-driven verdicts within seconds, and exposes those verdicts through SSE to an analyst's screen or phone.
- The next chapter (Evaluation) takes this exact stack and measures it end-to-end: model-level metrics on the Karim dataset, RL-agent metrics on the 1 100-sequence training set, and **system-level** metrics (per-tactic detection rate, latency, false-positive rate) from running `lab_simulate.sh`.

---

## Appendix — Quick-reference file map (cite in footnotes)

| Area | Key files |
|---|---|
| Model artefacts & registry | `apps/models/registry.json`, `apps/models/MANIFEST.json`, `apps/models/{ae,vae,transformer,gnn,rl_agent}_model.pth`, `apps/models/probability_calibrators.pkl` |
| Feature pipeline | `apps/models/selected_features_top25.json`, `apps/models/standard_scaler.pkl`, `apps/models/secbert_{log,cmd}_pca.pkl`, `apps/api/src/strix_api/core/state_builder.py` |
| Workers | `apps/api/src/strix_api/workers/{wazuh_bridge,normalizer,inference,verdicts_writer,intel_feeds_worker,arq_tasks}.py` |
| Services | `apps/api/src/strix_api/services/{threat_intel_service,intel_service,dashboard_service}.py` |
| Wazuh / Auditd / Filebeat | `infra/auditd/strix.rules`, `infra/filebeat.yml`, `infra/lab-provisioning/wazuh/local_rules.xml`, `infra/lab-provisioning/02-wazuh-server.sh` |
| Caldera lab | `infra/lab-provisioning/01-attacker-caldera.sh`, `infra/scripts/lab_simulate.sh`, `infra/simulation/scripts/run_full_simulation.py`, `docs/lab/CALDERA_MITRE_SIMULATION_GUIDE.md` |
| Compose stacks | `infra/compose.{api,lab,victim,simulation,chaos,platform-deps}.yml` |
| Dashboards | `apps/web/app/**`, `apps/mobile/app/**` |
| CI | `.github/workflows/{api,web,mobile,security,loadtest}.yml` |

## Appendix — Citations to add to `references.bib`

- `karim2024linux` — Karim et al. 2024, *Data in Brief* 54, 110290.
- `mitre_caldera` — MITRE Caldera framework, https://caldera.mitre.org.
- `wazuh` — Wazuh open-source SIEM, https://wazuh.com.
- `auditd` — Linux Audit Subsystem, kernel.org.
- `pytorch` — Paszke et al. 2019, PyTorch.
- `fastapi` — Ramírez, FastAPI, https://fastapi.tiangolo.com.
- `next` — Vercel, Next.js, https://nextjs.org.
- `expo` — Expo, https://expo.dev.
- `urlhaus`, `feodotracker` — abuse.ch CTI feeds.
