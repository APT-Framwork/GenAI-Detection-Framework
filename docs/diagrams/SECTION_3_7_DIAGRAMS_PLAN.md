# Section 3.7 — Platform Architecture & Design: Diagram Brief

> **Purpose.** One document that contains every detail needed to produce
> the seven diagrams under §3.7 of the thesis. Anyone — or any
> diagramming MCP — should be able to read a sub-section and render the
> diagram without re-investigating the codebase.
>
> **Status.** Specification only. No diagrams generated yet.
>
> **Scope.** Grounded in the actual STRIX repository at
> `/home/yacine/Desktop/GenAI-Detection-Framework/`. Every node,
> service, table, port and worker named below has been verified against
> the code on 2026-05-19. We deliberately do not look inside `report/`
> (the user requested it stay out of scope).

---

## 0. Conventions

### 0.1 Tool assignment

| §       | Diagram                       | Tool       | Why                                                                      |
| ------- | ----------------------------- | ---------- | ------------------------------------------------------------------------ |
| 3.7.2   | System Architecture           | **Eraser** | Icon-rich infrastructure view; Eraser has built-in cloud/security icons. |
| 3.7.3   | Platform Components           | **Eraser** | Same — internal-component view continues the visual language of 3.7.2.   |
| 3.7.4   | Class Diagram                 | **drawio** | UML class notation is drawio's native strength.                          |
| 3.7.5   | Workflow Diagram              | **drawio** | Activity / swim-lane notation, drawio handles cleanly.                   |
| 3.7.6.a | Data Flow Diagram (Yourdon)   | **drawio** | DFD shapes (process / store / external) live in drawio.                  |
| 3.7.6.b | Database Schema (ER)          | **drawio** | Crow's-foot ER notation, drawio.                                         |
| 3.7.7   | Sequence Diagram              | **drawio** | UML sequence with lifelines and activations — drawio.                    |
| 3.7.8   | Deployment Architecture       | **Eraser** | Container-network topology — Eraser cloud icons are ideal.               |

The user explicitly requested this split: drawio for class / database /
sequence / workflow, Eraser for system arch / components / deployment.
3.7.6 is split into two sub-diagrams (DFD + ER) to honour both the
section title (Data Flow Design) and the user's "database" mention.

### 0.2 Output filenames

All diagrams land under `report/PFE/figures/ch3/`:

```
report/PFE/figures/ch3/
├── eraser/
│   ├── 3_7_2_system_architecture.{eraser,pdf,png}
│   ├── 3_7_3_platform_components.{eraser,pdf,png}
│   └── 3_7_8_deployment_architecture.{eraser,pdf,png}
└── drawio/
    ├── 3_7_4_class_diagram.{drawio,pdf,png}
    ├── 3_7_5_workflow_diagram.{drawio,pdf,png}
    ├── 3_7_6_a_data_flow_diagram.{drawio,pdf,png}
    ├── 3_7_6_b_database_er.{drawio,pdf,png}
    └── 3_7_7_sequence_diagram.{drawio,pdf,png}
```

Source files (`.eraser`, `.drawio`) live alongside the rendered PDF/PNG
so they can be edited and re-rendered later.

### 0.3 Visual language

Across all seven diagrams, keep the same palette so the chapter reads
as one coherent set. (Eraser allows hex via `[color: #...]` on nodes;
drawio uses `fillColor`.)

| Role / zone                | Hex       | Use it for                                                  |
| -------------------------- | --------- | ----------------------------------------------------------- |
| Red-team / attacker        | `#E55B5B` | Caldera, Sandcat, attacker host                             |
| Victim / sensor            | `#F2A65A` | Wazuh agent, auditd, Sandcat-on-victim                      |
| Ingest / pipeline          | `#3FB984` | Wazuh manager, Filebeat, bridge worker                      |
| Backend core               | `#3C7DD9` | API, workers, models, services                              |
| Data store                 | `#7E57C2` | PostgreSQL, Redis, model registry                           |
| External SaaS              | `#7F8C8D` | abuse.ch, VirusTotal, Anthropic, Expo Push                  |
| Client                     | `#2EC4B6` | Web console, mobile app                                     |
| Decision (DQN / gate)      | `#F4C95D` | DQN agent, gating logic                                     |

### 0.4 Notation rules

- **Arrow direction = data direction**, not invocation direction. For
  request/response interactions in the system-architecture diagram,
  use a thicker arrow back for the response.
- **Label every edge** with the payload type or the protocol (e.g.
  `XADD`, `SELECT`, `HTTP/JSON`, `SSE`, `Expo Push`).
- **Cardinality everywhere it exists** in class and ER diagrams
  (crow's-foot in ER, `1..*` / `0..1` in UML).
- **Ports on the right side of containers** in the deployment
  diagram, network labels above each network boundary.
- **No vendor logos** inside class / sequence / ER diagrams — UML stays
  monochrome. Icons are only for Eraser infrastructure diagrams.

### 0.5 Source-of-truth references

| What                         | Where it lives                                                                        |
| ---------------------------- | -------------------------------------------------------------------------------------- |
| SQLAlchemy ORM models        | `apps/api/src/strix_api/repositories/models.py`                                        |
| API routes                   | `apps/api/src/strix_api/api/routes/*.py` (≈ 20 modules)                                |
| Service classes              | `apps/api/src/strix_api/services/*.py` (≈ 24 services)                                 |
| Workers                      | `apps/api/src/strix_api/workers/*.py` (7 entries)                                      |
| Model loaders                | `apps/api/src/strix_api/adapters/model_loaders/*.py`                                   |
| Compose stacks               | `infra/compose.api.yml`, `infra/compose.platform-deps.yml`, `infra/compose.simulation.yml` |
| Procfile / host orchestration| `Procfile.host`                                                                        |
| Pydantic schemas             | `apps/api/src/strix_api/api/schemas/*.py`                                              |

---

## 3.7.2 System Architecture Diagram — **Eraser**

### Purpose
A top-down "10 000-foot view" of every subsystem the platform touches,
arranged in five visual zones. The diagram answers: *what are the
moving parts, and at what altitude does each one live?*

### Audience
Jury readers seeing STRIX for the first time. Avoid every internal
detail (routes, table names, ports) — those belong to 3.7.3 / 3.7.6 /
3.7.8.

### Zone layout (left → right)

```
┌──────────────┬───────────────┬────────────────┬──────────────┬───────────┐
│   Lab        │   Telemetry   │   Backend      │   External   │  Clients  │
│   (red)      │   (orange)    │   (blue/purple)│   (grey)     │  (teal)   │
└──────────────┴───────────────┴────────────────┴──────────────┴───────────┘
```

### Nodes

| Zone        | Node               | Icon (Eraser)        | Label                                  |
| ----------- | ------------------ | -------------------- | -------------------------------------- |
| Lab         | `caldera`          | `mitre` / `bug`      | MITRE Caldera (C2)                     |
| Lab         | `attacker`         | `terminal`           | Kali attacker host                     |
| Lab         | `victim1`          | `linux`              | Ubuntu 22.04 — Victim 1                |
| Lab         | `victim2`          | `linux`              | Ubuntu 22.04 — Victim 2                |
| Lab         | `sandcat1/2`       | `gear`               | Sandcat agent (in-victim, dotted edge) |
| Telemetry   | `auditd`           | `log-file`           | auditd (52 kill-chain rules)           |
| Telemetry   | `wazuh_agent`      | `wazuh` / `shield`   | Wazuh agent (per host)                 |
| Telemetry   | `wazuh_manager`    | `wazuh` / `shield`   | Wazuh manager (alerts.json)            |
| Telemetry   | `filebeat`         | `elastic`            | Filebeat (1 s tail → Redis)            |
| Backend     | `redis`            | `redis`              | Redis (Streams + queues + cache)       |
| Backend     | `api`              | `fastapi`            | FastAPI service (~20 routes)           |
| Backend     | `workers`          | `python`             | 7 background workers                   |
| Backend     | `models`           | `pytorch`            | 5-model ensemble + DQN                 |
| Backend     | `postgres`         | `postgresql`         | PostgreSQL + TimescaleDB               |
| External    | `urlhaus`          | `cloud`              | URLhaus (abuse.ch)                     |
| External    | `feodo`            | `cloud`              | Feodo Tracker (abuse.ch)               |
| External    | `virustotal`       | `cloud`              | VirusTotal                             |
| External    | `claude`           | `anthropic`          | Anthropic Claude API                   |
| External    | `expo_push`        | `expo`               | Expo Push                              |
| Clients     | `web`              | `nextdotjs`          | Next.js Web Console (`:5600`)          |
| Clients     | `mobile`           | `expo`               | Expo Mobile Companion                  |

### Edges (every one labelled)

```
attacker        → caldera         : "operator UI / red"
caldera         → sandcat1        : "abilities (C2)"
caldera         → sandcat2        : "abilities (C2)"
sandcat1        --> victim1       : (dotted, "executes on")
sandcat2        --> victim2       : (dotted, "executes on")
victim1         → auditd          : "syscalls"
victim1         → wazuh_agent     : "ossec events"
victim2         → wazuh_agent     : "ossec events"
auditd          → wazuh_agent     : "audit-wazuh-*"
wazuh_agent     → wazuh_manager   : "encrypted (1514)"
wazuh_manager   → filebeat        : "alerts.json (NDJSON tail)"
filebeat        → redis           : "RPUSH strix:alerts:raw:list"
redis           ↔ workers         : "Streams (XADD/XREAD)"
workers         → models          : "load(SHA-256-pinned)"
workers         → postgres        : "INSERT verdicts, chains"
api             ↔ postgres        : "SQLAlchemy async"
api             ↔ redis           : "session, rate-limit"
api             → urlhaus         : "feed pull (30 s)"
api             → feodo          : "feed pull (30 s)"
api             → virustotal      : "on-demand IOC scan"
api             → claude          : "case summaries"
api             → expo_push       : "push to mobile"
web             ↔ api             : "REST + SSE"
mobile          ↔ api             : "REST + SSE + Expo Push receipt"
```

### Eraser DSL stub

```eraser
title STRIX — System Architecture

// ── zones ─────────────────────────────────────────────
Lab [color: #E55B5B] {
  attacker      [icon: terminal]
  caldera       [icon: bug, label: "MITRE Caldera (C2)"]
  victim1       [icon: linux, label: "Victim 1 (Ubuntu 22.04)"]
  victim2       [icon: linux, label: "Victim 2"]
  sandcat1      [icon: gear, label: "Sandcat agent"]
  sandcat2      [icon: gear, label: "Sandcat agent"]
}

Telemetry [color: #F2A65A] {
  auditd        [icon: log-file, label: "auditd\n(52 rules)"]
  wazuh_agent   [icon: shield, label: "Wazuh agent"]
  wazuh_manager [icon: shield, label: "Wazuh manager"]
  filebeat      [icon: elastic, label: "Filebeat (1 s tail)"]
}

Backend [color: #3C7DD9] {
  redis    [icon: redis]
  api      [icon: fastapi, label: "FastAPI"]
  workers  [icon: python, label: "7 workers"]
  models   [icon: pytorch, label: "5 models + DQN"]
  postgres [icon: postgresql, label: "PostgreSQL\n+ TimescaleDB"]
}

External [color: #7F8C8D] {
  urlhaus    [icon: cloud]
  feodo      [icon: cloud]
  virustotal [icon: cloud]
  claude     [icon: cloud, label: "Anthropic\nClaude"]
  expo_push  [icon: cloud, label: "Expo Push"]
}

Clients [color: #2EC4B6] {
  web    [icon: nextdotjs, label: "Web console\n(:5600)"]
  mobile [icon: expo,      label: "Mobile app"]
}

// ── edges ─────────────────────────────────────────────
attacker      > caldera        : "operator UI"
caldera       > sandcat1       : "abilities"
caldera       > sandcat2       : "abilities"
sandcat1      --> victim1      : "exec"
sandcat2      --> victim2      : "exec"
victim1       > auditd         : "syscalls"
victim1       > wazuh_agent    : "ossec"
victim2       > wazuh_agent    : "ossec"
auditd        > wazuh_agent    : "audit-wazuh-*"
wazuh_agent   > wazuh_manager  : "tcp/1514"
wazuh_manager > filebeat       : "alerts.json"
filebeat      > redis          : "RPUSH"
redis         <> workers       : "Streams"
workers       > models         : "load"
workers       > postgres       : "INSERT"
api           <> postgres      : "ORM"
api           <> redis         : "cache, queue"
api           > urlhaus        : "30 s pull"
api           > feodo          : "30 s pull"
api           > virustotal     : "on-demand"
api           > claude         : "case summary"
api           > expo_push      : "push notif"
web           <> api           : "REST + SSE"
mobile        <> api           : "REST + SSE + Push"
```

### Things to NOT include
- Individual route or worker names (3.7.3's job).
- Postgres tables (3.7.6 b).
- Ports / container names (3.7.8).
- Class details (3.7.4).
- Message sequencing (3.7.7).

---

## 3.7.3 Platform Components — **Eraser**

### Purpose
Continues 3.7.2's visual style but zooms into the backend. Shows how
the FastAPI service is internally decomposed and how the worker
processes relate to the model artefacts and the database.

### Audience
Software-engineering reviewers — the architecture chapter wants to
demonstrate that the platform is properly layered (routes / services /
repositories / adapters / workers / models), not a monolith.

### Layer layout (top → bottom)

```
              ┌─────────────────────────────────────────┐
Layer 1       │     Clients  (Web · Mobile)             │
              └─────────────────────────────────────────┘
                                 ▲
              ┌─────────────────────────────────────────┐
Layer 2       │   API · ~20 route modules               │
              └─────────────────────────────────────────┘
                                 ▲
              ┌─────────────────────────────────────────┐
Layer 3       │   Services  (~24 stateless classes)     │
              └─────────────────────────────────────────┘
                                 ▲
              ┌─────────────┐  ┌─────────────┐  ┌──────────────┐
Layer 4       │ Repositories│  │  Adapters   │  │ Observability│
              └─────────────┘  └─────────────┘  └──────────────┘
                                 ▲
              ┌────────────────────────────────────────┐
Layer 5       │   Data stores  (Postgres · Redis)      │
              └────────────────────────────────────────┘

                    ┌────────────────┐
Side-channel        │  Worker layer  │  ← consumes Redis Streams, talks
                    │  (7 processes) │     to models, writes to Postgres
                    └────────────────┘
```

### Nodes — verbatim from the codebase

#### Layer 2 — API routes (`apps/api/src/strix_api/api/routes/`)

Group into 5 logical buckets so the box is readable:

| Bucket            | Modules                                                                |
| ----------------- | ---------------------------------------------------------------------- |
| **Auth & system** | `auth`, `health`, `admin`                                              |
| **Live ops**      | `alerts`, `streams`, `dashboard`, `monitoring`                         |
| **Investigation** | `analysis`, `chains`, `cases`, `hunt`, `mitre`, `topology`             |
| **Response**      | `actions`, `playbooks`                                                 |
| **Intelligence**  | `intel`, `threat_intel`, `ueba`, `hosts`, `simulation`                 |

Show as ONE component box `API · 5 route buckets` with the bucket names
listed inside. Don't draw 20 boxes.

#### Layer 3 — Services (`apps/api/src/strix_api/services/`)

Show as one box labelled `Services (24)` with the most user-visible
ones called out:

```
AuthService           AlertService        AnalysisService
ChainInvestigation    ActionsService      ThreatIntelService
AttributionService    DriftService        InsightService
MitreService          UebaService         PlaybooksService
TopologyService       DashboardService    HuntService
HostDetailService     CaseService         KillSwitchService
LiveFeedService       PushDispatcher      IocExtractor
IntelService          CacheService
```

#### Layer 4a — Repositories (`apps/api/src/strix_api/repositories/`)

- `models.py` — SQLAlchemy ORM (19 tables, see 3.7.6.b)
- `repos.py` — `AlertRepo`, `ChainRepo`, `HostRepo`, `DetectionRepo`, `IndicatorRepo`, `ActionRepo`
- `ioc_repo.py`, `file_scan_repo.py`, `push_device_repo.py`, `user_repo.py`, `llm_insight_repo.py`
- `database.py` — async engine + pool

#### Layer 4b — Adapters (`apps/api/src/strix_api/adapters/`)

- `model_loaders/` — six files: `_arch.py`, `autoencoder.py`, `vae.py`, `transformer.py`, `gnn.py`, `dqn.py`
- `preprocessing_pipeline.py`
- `wazuh_adapter.py`, `virustotal_adapter.py`, `xposedornot_adapter.py`
- `redis_adapter.py`, `session_store.py`
- `llm_adapter.py`, `expo_push_adapter.py`
- `model_registry.py`

#### Layer 4c — Observability (`apps/api/src/strix_api/observability/`)

- `logging.py` (structlog)
- `metrics.py` (Prometheus)
- `tracing.py` (OpenTelemetry)

#### Side-channel — Workers (`apps/api/src/strix_api/workers/`)

Seven processes (verbatim from `Procfile.host`):

| Worker              | Verbatim role                                          |
| ------------------- | ------------------------------------------------------ |
| `wazuh_bridge`      | drains Filebeat list → `strix:alerts:raw` stream       |
| `normalizer`        | feature engineering → `strix:features:{shard}` stream  |
| `inference`         | 5-model ensemble + DQN → `strix:verdicts` stream       |
| `verdicts_writer`   | persists verdicts, opens/closes chains, emits SSE      |
| `arq`               | async task queue (intel enrichment, attribution, LLM)  |
| `intel_feeds_worker`| URLhaus + Feodo pull every 30 s                        |
| `demo_isolation`    | demo-mode isolation simulator (no real Wazuh call)     |

### Edges

- Clients → API (HTTP/JSON, SSE)
- API → Services (Python call)
- Services → Repositories → Postgres
- Services → Adapters → External SaaS
- Workers ↔ Redis Streams
- Workers → Models (load from disk)
- Workers → Repositories → Postgres
- Adapters/Models → SHA-pinned artefacts on disk (`apps/models/`)
- All layers → Observability (one-way out)

### Eraser DSL stub

```eraser
title STRIX — Platform Components

Clients {
  web    [icon: nextdotjs]
  mobile [icon: expo]
}

API [color: #3C7DD9, label: "API · 20 route modules"] {
  auth_routes        [label: "Auth & system"]
  liveops_routes     [label: "Live ops"]
  investigation     [label: "Investigation"]
  response_routes    [label: "Response"]
  intel_routes       [label: "Intelligence"]
}

Services [color: #3C7DD9, label: "Services (24)"] {
  auth_svc           [label: "AuthService"]
  alert_svc          [label: "AlertService"]
  analysis_svc       [label: "AnalysisService"]
  chain_inv_svc      [label: "ChainInvestigationService"]
  action_svc         [label: "ActionsService"]
  attrib_svc         [label: "AttributionService"]
  intel_svc          [label: "IntelService"]
  // … list all 24, grouped visually
}

Layer4 {
  Repos [color: #7E57C2] {
    models_py      [label: "ORM models\n(19 tables)"]
    repos_py       [label: "Per-entity repos"]
    ioc_repo
    push_device_repo
    user_repo
    llm_insight_repo
    file_scan_repo
  }
  Adapters [color: #3C7DD9] {
    model_loaders     [label: "5 model loaders"]
    preprocess        [label: "preprocessing_pipeline"]
    wazuh_adapter
    virustotal_adapter
    xposedornot_adapter
    redis_adapter
    session_store
    llm_adapter
    expo_push_adapter
    model_registry
  }
  Observ [color: #7F8C8D, label: "Observability"] {
    logging  [label: "structlog"]
    metrics  [label: "Prometheus"]
    tracing  [label: "OpenTelemetry"]
  }
}

DataStores [color: #7E57C2] {
  postgres [icon: postgresql]
  redis    [icon: redis]
}

Workers [color: #3FB984] {
  wazuh_bridge       [label: "wazuh_bridge"]
  normalizer         [label: "normalizer"]
  inference          [label: "inference (5 models + DQN)"]
  verdicts_writer    [label: "verdicts_writer"]
  arq                [label: "arq tasks"]
  intel_feeds_worker [label: "intel_feeds_worker"]
  demo_isolation     [label: "demo_isolation"]
}

Models [color: #F4C95D, label: "ML artefacts (SHA-pinned)"] {
  ae    [label: "AE"]
  vae   [label: "β-VAE"]
  tx    [label: "Transformer"]
  gnn   [label: "GraphSAGE"]
  dqn   [label: "DQN"]
}

// edges
Clients   > API
API       > Services
Services  > Repos
Repos     > postgres
Services  > Adapters
Adapters  > redis
Workers   <> redis
Workers   > Models
Workers   > Repos
*         --> Observ      // dotted "all layers emit to obs"
```

### Things to NOT include
- Hardware / containers / ports → 3.7.8.
- Database table contents → 3.7.6 b.
- Class attributes → 3.7.4.

---

## 3.7.4 Class Diagram — **drawio**

### Purpose
A UML class diagram capturing the **domain model** (persistent
entities) plus the **ML model layer**. Two clusters in one diagram.

The ML loader classes are deliberately included even though they're
not "domain" classes — they're the bridge between the persistent
verdict table and the model registry, and a reviewer will look here
first to understand how the predictions come into being.

### Notation
UML 2.5 class notation, drawio's built-in "UML" stencil:

```
┌──────────────────────────────┐
│   <<stereotype>>            │
│   ClassName                 │
├──────────────────────────────┤
│  + attr: Type               │   (public)
│  - attr: Type               │   (private)
│  # attr: Type               │   (protected)
├──────────────────────────────┤
│  + method(): ReturnType     │
└──────────────────────────────┘
```

Stereotypes used:
- `<<entity>>` — SQLAlchemy ORM
- `<<service>>` — stateless service class
- `<<model>>` — PyTorch `nn.Module` subclass
- `<<schema>>` — Pydantic DTO (only the most important ones)

### Cluster 1 — Domain entities

(Verbatim from `apps/api/src/strix_api/repositories/models.py`. Skip
created_at / updated_at to reduce clutter; cite them once in a
caption-level note.)

#### `User <<entity>>`
```
+ user_id: UUID (PK)
+ email: str (unique)
- password_hash: str
+ role: 'admin' | 'analyst'
+ is_active: bool
+ designation: str?
─────────────────────────────────────
+ set_password(plain: str): None       (Argon2)
+ verify_password(plain: str): bool
```

#### `Host <<entity>>`
```
+ host_id: UUID (PK)
+ agent_id: str (unique)
+ agent_name: str
+ ip_address: str
+ is_manager: bool
+ first_seen_at: datetime
+ last_seen_at: datetime
```

#### `AttackChain <<entity>>`
```
+ chain_id: UUID (PK)
+ host_id: UUID → Host
+ opened_at: datetime
+ closed_at: datetime?
+ first_malicious_at: datetime?
+ max_ckc_stage: int
+ max_vae_prob: float
+ status: 'open' | 'closed'
+ triage_status: 'new' | 'in_progress' | 'contained' | 'resolved'
+ campaign_id: UUID? → Campaign
+ tlp: 'white' | 'green' | 'amber' | 'red'
+ assignee_user_id: UUID? → User
─────────────────────────────────────
+ close(reason: str): None
+ bump_stage(stage: int): None
+ attribute_to(campaign: Campaign): None
```

#### `Alert <<entity>>` (TimescaleDB hypertable)
```
+ alert_id: str (PK part 1)
+ occurred_at: datetime (PK part 2)
+ host_id: UUID → Host
+ chain_id: UUID? → AttackChain
+ decoder_name: str
+ location: str
+ full_log: str
+ rule_id: int
+ rule_firedtimes: int
+ mitre_tactics: str[]
+ mitre_techniques: str[]
+ ckc_stage: int
+ raw_jsonb: JSONB
+ acknowledged_at: datetime?
+ acknowledged_by: UUID? → User
─────────────────────────────────────
+ acknowledge(user: User): None
```

#### `Detection <<entity>>` (hypertable; 1-to-1 with Alert via composite key)
```
+ alert_id: str (PK part 1)
+ occurred_at: datetime (PK part 2)
+ host_id: UUID
+ chain_id: UUID?
+ step_in_chain: int
+ ae_anomaly_score: float
+ ae_recon_error: float
+ vae_malicious_prob: float
+ vae_uncertainty: float
+ transformer_pred_ckc: int
+ transformer_confidence: float
+ transformer_probabilities: float[8]
+ gnn_node_risk: float
+ gnn_neighbor_risk: float
+ gnn_risk_growth: float
+ state_vector: float[13]
+ model_versions: JSONB
```

#### `DQNAction <<entity>>`
```
+ action_id: UUID (PK)
+ alert_id: str → Alert
+ chain_id: UUID? → AttackChain
+ host_id: UUID → Host
+ decided_at: datetime
+ action: int (0..4)
+ action_name: 'MONITOR' | 'LOW_ALERT' | 'ESCALATE' | 'ISOLATE_HOST' | 'BLOCK_USER_IP'
+ q_values: float[5]
+ ckc_stage_at_decision: int
+ requires_approval: bool
+ applied: bool
+ applied_at: datetime?
+ applied_by: UUID? → User
+ rejected_at: datetime?
+ rejected_by: UUID? → User
─────────────────────────────────────
+ approve(user: User): None
+ reject(user: User, reason: str): None
+ rollback(user: User, reason: str): DqnActionRollback
```

#### `DqnActionRollback <<entity>>`
```
+ rollback_id: UUID (PK)
+ action_id: UUID (unique) → DQNAction
+ rolled_back_by: UUID → User
+ rolled_back_at: datetime
+ reason: str
```

#### `Campaign <<entity>>`
```
+ campaign_id: UUID (PK)
+ name: str (unique)
+ actor_id: UUID? → ThreatActor
+ tactic_chain: JSONB
+ description: str
```

#### `ThreatActor <<entity>>`
```
+ actor_id: UUID (PK)
+ name: str (unique)
+ aliases: str[]
+ mitre_group_id: str
+ country: str
+ motivation: str
+ description: str
```

#### `IocLookupCache <<entity>>`
```
+ indicator: str (PK part 1)
+ indicator_type: str (PK part 2)
+ source: str (PK part 3)
+ reputation: str
+ payload: JSONB
+ checked_at: datetime
+ expires_at: datetime
```

#### `LlmInsightCache <<entity>>`
```
+ payload_hash: str (PK)
+ generated_at: datetime
+ model_version: str
+ insight: str
+ recommended_actions: JSONB
+ expires_at: datetime
```

#### `FileScan <<entity>>`
```
+ scan_id: UUID (PK)
+ sha256: str (unique)
+ filename: str
+ size_bytes: int
+ uploaded_at: datetime
+ uploaded_by: UUID → User
+ vt_result: JSONB
+ vt_scanned_at: datetime?
+ status: 'pending' | 'scanned' | 'error'
```

#### `PushDevice <<entity>>`
```
+ device_id: UUID (PK)
+ user_id: UUID → User
+ expo_push_token: str
+ platform: 'ios' | 'android'
+ app_version: str
+ registered_at: datetime
+ last_seen_at: datetime
```

#### `Tag` + `TagLink` (polymorphic)
```
Tag {
  + tag_id: UUID (PK)
  + name: str (unique)
  + colour: str
  + description: str
}
TagLink {
  + link_id: UUID (PK)
  + entity_type: 'chain' | 'indicator' | 'actor' | 'campaign' | 'report'
  + entity_id: UUID
  + tag_id: UUID → Tag
  + created_by: UUID? → User
}
```

#### `ChainNote` + `CaseAuditLog`
```
ChainNote {
  + note_id: UUID (PK)
  + chain_id: UUID → AttackChain
  + author_user_id: UUID → User
  + body_md: str
}
CaseAuditLog {
  + audit_id: UUID (PK)
  + chain_id: UUID → AttackChain
  + user_id: UUID → User
  + from_status: str
  + to_status: str
  + note: str
  + at: datetime
}
```

#### `HuntSavedQuery`
```
+ saved_id: UUID (PK)
+ user_id: UUID → User
+ name: str
+ q: str (hunt DSL)
+ (user_id, name) is unique
```

#### `GnnGraphSnapshot <<entity>>` (hypertable)
```
+ snapshot_id: UUID (PK part 1)
+ taken_at: datetime (PK part 2)
+ shard_id: int
+ node_count: int
+ edge_count: int
+ nodes: JSONB
+ edges: JSONB
```

### Cluster 2 — ML model layer

(Verbatim from `apps/api/src/strix_api/adapters/model_loaders/_arch.py`.)

#### `RegularizedAutoencoder <<model>>` extends `torch.nn.Module`
```
- encoder: nn.Sequential
- fc_mu: nn.Linear(128 → 64)
- fc_logvar: nn.Linear(128 → 64)
- decoder: nn.Sequential
- center: nn.Parameter(zeros(64))   (learnable)
─────────────────────────────────────
+ forward(x): dict { mu, logvar, recon, recon_error, anomaly_score }
+ encode(x): Tensor
+ decode(z): Tensor
```

#### `BetaVAE <<model>>` extends `torch.nn.Module`
```
- encoder: nn.Sequential (55→512→256→128)
- fc_z_mean: nn.Linear(128 → 32)
- fc_z_log_var: nn.Linear(128 → 32)
- decoder: nn.Sequential (32→128→256→512→55)
- center: nn.Parameter(zeros(32))
─────────────────────────────────────
+ forward(x): dict { z_mean, z_log_var, recon_loss, malicious_prob, uncertainty }
```

#### `Transformer <<model>>` extends `torch.nn.Module`
```
- input_projection: Linear(64 → 128) + LayerNorm + ReLU
- pos_encoder: SinusoidalPositionalEncoding(d_model=128, max_len=500)
- transformer_encoder: 4× TransformerEncoderLayer (8 heads, d_ff=512, GELU, PreLN)
- output_head: Linear(128 → 64) + ReLU + Linear(64 → 8)
─────────────────────────────────────
+ forward(seq: Tensor[T, 64]): dict { logits, pred_ckc, confidence, probabilities }
```

#### `GraphSAGE <<model>>` extends `torch.nn.Module`
```
- convs: ModuleList[SAGEConv(55→128), SAGEConv(128→128), SAGEConv(128→128)]
- bns: ModuleList[BatchNorm(128) × 3]
- head: Linear(128 → 64) + ReLU + Linear(64 → 1) + Sigmoid
─────────────────────────────────────
+ forward(x, edge_index): Tensor[N] (per-node risk ∈ [0,1])
```

#### `DQN <<model>>` extends `torch.nn.Module`
```
- network: nn.Sequential
    Linear(13 → 128) + ReLU + Dropout(0.1)
    Linear(128 → 64) + ReLU + Dropout(0.1)
    Linear(64 → 5)
─────────────────────────────────────
+ forward(state: Tensor[13]): Tensor[5] (Q-values)
+ select_action(state: Tensor[13]): int (argmax)
```

#### `ModelRegistry <<service>>`
```
+ load(name: str, version: str): nn.Module
+ verify_sha256(path: str, expected: str): bool
+ active_calibrator: str = "Beta-VAE (Top 25) lab-refit"
```

### Relationships (UML cardinality)

| Source           | Target            | Cardinality | Note                         |
| ---------------- | ----------------- | ----------- | ---------------------------- |
| Host             | AttackChain       | 1 — 0..*    | hosts have many chains       |
| AttackChain      | Alert             | 1 — 0..*    |                              |
| Alert            | Detection         | 1 — 1       | composite-PK 1-to-1          |
| Alert            | DQNAction         | 1 — 0..*    | sometimes 1, sometimes 0     |
| AttackChain      | Campaign          | 0..* — 0..1 | optional attribution         |
| Campaign         | ThreatActor       | 0..* — 0..1 |                              |
| AttackChain      | ChainNote         | 1 — 0..*    |                              |
| AttackChain      | CaseAuditLog      | 1 — 0..*    |                              |
| User             | DQNAction         | 1 — 0..*    | approved/rejected by         |
| DQNAction        | DqnActionRollback | 1 — 0..1    |                              |
| User             | PushDevice        | 1 — 0..*    |                              |
| User             | HuntSavedQuery    | 1 — 0..*    |                              |
| User             | FileScan          | 1 — 0..*    | (uploader)                   |
| Tag              | TagLink           | 1 — 0..*    | polymorphic                  |
| ModelRegistry    | AE/VAE/Tx/GNN/DQN | 1 — 1       | dependency (dotted)          |

### Layout hints (drawio)
- Two horizontal swimlanes: **Domain entities** (top) and **ML model layer** (bottom).
- Cluster entities related to *Chains* on the left, *Auth + Intel + Tags* on the right.
- Use orthogonal connectors. Place crow's-foot endings on FK arrows.
- Drawio's "Layout → Vertical Tree" works well as a starting layout
  before manual tuning.

### Source skeleton (drawio XML, the *important* parts only)

```xml
<mxGraphModel dx="1400" dy="900" grid="1" gridSize="10"
              guides="1" tooltips="1" connect="1" arrows="1"
              fold="1" page="1" pageScale="1" pageWidth="1700"
              pageHeight="2200" math="0" shadow="0">
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>

    <!-- Swimlane: Domain -->
    <mxCell id="ln-domain" value="Domain entities" style="swimlane;..."
            vertex="1" parent="1">
      <mxGeometry x="20"  y="40"  width="1660" height="1100" as="geometry"/>
    </mxCell>

    <!-- Swimlane: ML layer -->
    <mxCell id="ln-ml" value="ML model layer" style="swimlane;..."
            vertex="1" parent="1">
      <mxGeometry x="20"  y="1160" width="1660" height="800" as="geometry"/>
    </mxCell>

    <!-- One UML class cell per entity -->
    <mxCell id="cls-User" value="&lt;&lt;entity&gt;&gt;User"
            style="shape=umlClass;..."
            vertex="1" parent="ln-domain">
      <mxGeometry x="60" y="80" width="220" height="170" as="geometry"/>
    </mxCell>
    <!-- … one cell per class as listed above … -->

    <!-- One edge per relationship, crow's-foot for cardinality -->
    <mxCell id="rel-host-chain"
            style="endArrow=ERmany;startArrow=ERone;..."
            edge="1" parent="1"
            source="cls-Host" target="cls-AttackChain">
      <mxGeometry relative="1" as="geometry"/>
    </mxCell>
    <!-- … one edge per relationship … -->

  </root>
</mxGraphModel>
```

### MCP invocation

`mcp__drawio__open_drawio_xml` with the full XML above (expand each
`...` to a concrete class definition). Save the rendered diagram as
`3_7_4_class_diagram.drawio`, export to PDF.

### Things to NOT include
- Service classes (the 24 of them) — keep this diagram to entities +
  ML layer. Mention services in passing in a footnote.
- Created_at / updated_at columns — boilerplate; mention once.
- Methods that are pure ORM accessors.

---

## 3.7.5 Workflow Diagram — **drawio**

### Purpose
The end-to-end **analyst response workflow**: from "an alert appears
on the dashboard" to "the case is closed". Three swim-lanes: the
analyst, the backend, and the response target (Wazuh manager).

This is the diagram that proves the human-in-the-loop story —
auto-everything is *off* on production paths, the DQN suggests, the
analyst decides.

### Notation
UML 2.5 Activity Diagram with three swim-lanes.

```
┌──────────────┐  ┌───────────────────────┐  ┌──────────────────┐
│   Analyst    │  │     STRIX backend     │  │  Wazuh manager   │
└──────────────┘  └───────────────────────┘  └──────────────────┘
```

### Steps (in chronological order)

| # | Lane     | Activity                                                                | Notes                                |
| - | -------- | ----------------------------------------------------------------------- | ------------------------------------ |
| 0 | backend  | ●  Receive alert via Filebeat → Redis                                   | start node                           |
| 1 | backend  | normalizer + inference produce verdict                                  |                                      |
| 2 | backend  | verdicts_writer persists row, opens / bumps chain                       |                                      |
| 3 | backend  | DQN proposes action                                                     |                                      |
| 4 | backend  | <gate> action gated by AE/VAE/Tx/GNN thresholds                         | decision diamond                     |
| 4a| backend  |     gate fails → record LOW_ALERT only                                  | merge into step 6                    |
| 4b| backend  |     gate passes → flag `requires_approval=True`                         | high-risk actions only               |
| 5 | backend  | SSE push to web/mobile vigilance feed                                   |                                      |
| 6 | backend  | Expo push notification if CKC ≤ S2                                      |                                      |
| 7 | analyst  | Sees alert on dashboard or phone                                        |                                      |
| 8 | analyst  | Opens Attack Analysis page → reads forensic report                      |                                      |
| 9 | analyst  | <decision> approve or reject DQN action                                 | decision diamond                     |
| 9a| analyst  |     reject → record rejection                                           | go to step 12                        |
| 9b| analyst  |     approve → continue                                                  |                                      |
| 10| backend  | actions_service.apply() called via API                                  |                                      |
| 11| wazuh    | Wazuh manager executes isolation / block via active response            |                                      |
| 12| backend  | case_audit_log row recorded                                             |                                      |
| 13| analyst  | <decision> case resolved or escalate?                                   |                                      |
|13a| analyst  |     escalate → reassign chain to another user                           |                                      |
|13b| analyst  |     resolve → set triage_status = 'resolved'                            |                                      |
| 14|          | ●  End                                                                  | end node                             |

### drawio swim-lane construct (XML skeleton)

```xml
<mxCell id="pool" value="Analyst response workflow"
        style="swimlane;horizontal=0;startSize=20;..."
        vertex="1" parent="1">
  <mxGeometry x="20" y="40" width="1600" height="900" as="geometry"/>
</mxCell>

<mxCell id="lane-analyst" value="Analyst" parent="pool" vertex="1"
        style="swimlane;horizontal=0;startSize=20;..."/>
<mxCell id="lane-backend" value="STRIX backend" parent="pool" vertex="1"
        style="swimlane;horizontal=0;startSize=20;..."/>
<mxCell id="lane-wazuh" value="Wazuh manager" parent="pool" vertex="1"
        style="swimlane;horizontal=0;startSize=20;..."/>

<!-- start node -->
<mxCell id="start" style="ellipse;fillColor=#000000;..."/>

<!-- activity nodes -->
<mxCell id="act1" value="Normalize + Infer" style="rounded=1;..."/>
<mxCell id="act2" value="Persist verdict" style="rounded=1;..."/>
<!-- … -->

<!-- decision diamonds -->
<mxCell id="dec1" value="Gate passes?" style="rhombus;..."/>
<mxCell id="dec2" value="Approve?" style="rhombus;..."/>

<!-- end node -->
<mxCell id="end" style="ellipse;fillColor=#000000;strokeWidth=3;..."/>

<!-- edges with labels: "yes", "no", etc. -->
```

### MCP invocation
`mcp__drawio__open_drawio_xml` with the full XML — opens the editor
in the browser. Manually tune the swim-lane heights, then export to
PDF for the chapter.

### Alternative workflows worth a sentence in the chapter
- **Alert-only-no-action workflow**: same diagram, but with `gate
  fails` taken at step 4 and no analyst approval needed (`Monitor` is
  the silent action).
- **Onboarding workflow**: admin invites analyst → analyst registers
  push device → device receives test push. Probably overkill for the
  thesis; can be mentioned in a footnote.

### Things to NOT include
- Worker-internal sequencing (3.7.7's job).
- Specific Redis stream keys (3.7.6).

---

## 3.7.6 Data Flow Design — **drawio (two sub-diagrams)**

The user specifically asked for "database" *and* "data flow" under
drawio. Splitting 3.7.6 makes both fit cleanly without overloading a
single picture.

### 3.7.6.a Process-Level Data Flow Diagram (Yourdon/DeMarco)

#### Notation
Classic DFD:

| Element            | Shape                          | Used for                              |
| ------------------ | ------------------------------ | ------------------------------------- |
| External entity    | rectangle                      | Wazuh manager, Operator, Mobile, etc. |
| Process            | rounded rectangle (or circle)  | Each worker                           |
| Data store         | open-ended rectangle (`|=|`)   | Redis stream / Postgres table         |
| Data flow          | arrow with payload label       | XADD message, JSON, SQL row           |

Drawio has a "Data Flow" stencil with these exact shapes.

#### External entities

```
[wazuh_mgr]  Wazuh manager
[op]         Operator (browser)
[op_mobile]  Operator (mobile)
[urlhaus]    URLhaus feed
[feodo]      Feodo Tracker feed
[claude]     Anthropic Claude API
[vt]         VirusTotal API
[expo]       Expo Push API
```

#### Processes (numbered Yourdon-style)

```
1.0  filebeat
2.0  wazuh_bridge
3.0  normalizer
4.0  inference
5.0  verdicts_writer
6.0  api  (REST + SSE)
7.0  arq_tasks  (LLM enrichment, attribution)
8.0  intel_feeds_worker
9.0  push_dispatcher  (within api / arq)
```

#### Data stores

```
D1  alerts.json                      (file on disk)
D2  strix:alerts:raw:list            (Redis list, staging)
D3  strix:alerts:raw                 (Redis stream)
D4  strix:features:{shard}           (Redis stream)
D5  strix:verdicts                   (Redis stream)
D6  hosts, users, attack_chains, alerts, detections, dqn_actions, … (Postgres)
D7  intel_indicators, threat_actors, campaigns                       (Postgres)
D8  ioc_lookup_cache, llm_insight_cache                              (Postgres)
D9  apps/models/* (SHA-pinned)        (file system)
```

#### Data flows (each one with a payload label)

```
wazuh_mgr      → D1                : "alerts.json (NDJSON)"
D1             → 1.0 filebeat      : "tail (1 s)"
1.0            → D2                : "RPUSH"
D2             → 2.0 wazuh_bridge  : "BLPOP"
2.0            → D3                : "XADD raw"
D3             → 3.0 normalizer    : "XREAD"
3.0            → D9                : "load scaler/PCA"
3.0            → D4                : "XADD features (55-dim)"
D4             → 4.0 inference     : "XREAD batch 32"
4.0            → D9                : "load 5 models"
4.0            → D5                : "XADD verdict + DQN"
D5             → 5.0 verdicts_writer : "XREAD batch (5 s window)"
5.0            → D6                : "INSERT alerts + detections + dqn_actions"
5.0            → 6.0 api           : "SSE event"
6.0            → op                : "REST + SSE"
6.0            → op_mobile         : "REST + SSE + Expo Push"
op             → 6.0               : "approve/reject action"
6.0            → D6                : "UPDATE chain.triage_status, case_audit_log"
urlhaus        → 8.0 intel_feeds   : "30 s pull"
feodo         → 8.0 intel_feeds   : "30 s pull"
8.0            → D7                : "UPSERT intel_indicators"
api            → claude            : "case summary request"
claude         → api               : "summary response"
api            → vt                : "IOC scan"
vt             → 6.0               : "scan result"
6.0            → D8                : "UPSERT ioc_lookup_cache"
6.0            → expo              : "push notification"
arq_tasks      → D7                : "attribution updates"
arq_tasks      → D8                : "LLM cache UPSERT"
```

#### Layout hints
- External entities: column 1 (left) and column 5 (right).
- Processes: columns 2–4, top to bottom by stage in the pipeline.
- Data stores below the processes that own them.
- Arrows: orthogonal connectors only.

#### drawio XML stub
Use stencil `mxgraph.flowchart.terminator` for external entities,
`shape=process` for processes, `shape=cylinder3` for stores (or the
classic open-rectangle if you want strict DFD style). Save as
`3_7_6_a_data_flow_diagram.drawio`.

### 3.7.6.b Database ER Diagram

#### Purpose
The thesis "database" diagram. Crow's-foot notation. Source of truth:
`apps/api/src/strix_api/repositories/models.py`.

#### Tables (19)

(Already enumerated in 3.7.4's Cluster 1, plus a few that don't make
the class diagram because they're 100 % storage with no behaviour.)

| Group               | Tables                                                                                        |
| ------------------- | --------------------------------------------------------------------------------------------- |
| **Identity**        | `users`                                                                                       |
| **Inventory**       | `hosts`                                                                                       |
| **Detection**       | `alerts`, `detections`, `attack_chains`, `dqn_actions`, `dqn_action_rollbacks`                |
| **CTI**             | `threat_actors`, `campaigns`                                                                  |
| **Caches**          | `ioc_lookup_cache`, `llm_insight_cache`                                                       |
| **Files**           | `file_scans`                                                                                  |
| **Metadata**        | `tags`, `tag_links`, `chain_notes`, `case_audit_log`                                          |
| **Hunt**            | `hunt_saved_queries`                                                                          |
| **Mobile**          | `push_devices`                                                                                |
| **ML state**        | `gnn_graph_snapshots`                                                                         |

#### Column-by-column

Full column list for each table is in 3.7.4's Cluster 1. Reproduce
them here in ER style. For the ER diagram, **include** the boilerplate
`created_at` / `updated_at` columns (they're real columns; the chapter
needs to look like a real schema).

#### Foreign-key relationships (crow's-foot)

| Parent (1)              | Child (many)             | Column                                  |
| ----------------------- | ------------------------ | --------------------------------------- |
| hosts                   | attack_chains            | host_id                                 |
| hosts                   | alerts                   | host_id                                 |
| attack_chains           | alerts                   | chain_id                                |
| alerts                  | detections               | (alert_id, occurred_at) composite       |
| alerts                  | dqn_actions              | alert_id                                |
| attack_chains           | dqn_actions              | chain_id                                |
| users                   | dqn_actions              | applied_by + rejected_by (two FKs)      |
| dqn_actions             | dqn_action_rollbacks     | action_id                               |
| users                   | dqn_action_rollbacks     | rolled_back_by                          |
| campaigns               | attack_chains            | campaign_id                             |
| threat_actors           | campaigns                | actor_id                                |
| attack_chains           | chain_notes              | chain_id                                |
| users                   | chain_notes              | author_user_id                          |
| attack_chains           | case_audit_log           | chain_id                                |
| users                   | case_audit_log           | user_id                                 |
| tags                    | tag_links                | tag_id                                  |
| users                   | tag_links                | created_by                              |
| users                   | hunt_saved_queries       | user_id                                 |
| users                   | push_devices             | user_id  (ON DELETE CASCADE)            |
| users                   | file_scans               | uploaded_by                             |

#### Layout hints
- **Identity & inventory** on the left (users, hosts).
- **Detection core** in the centre (alerts, detections, chains,
  actions, rollbacks).
- **CTI** in the upper right (threat_actors → campaigns → chains).
- **Metadata** lower right (tags, tag_links, chain_notes, audit log).
- **Caches & files** in a small cluster bottom-left, with no FKs out.
- Composite PK columns underlined twice (drawio supports HTML in
  labels — use `<u>x</u><u>y</u>` for composite).
- TimescaleDB hypertables marked with a small "TS" badge in the
  table header (alerts, detections, gnn_graph_snapshots).

#### MCP invocation
`mcp__drawio__open_drawio_xml` with the XML built from the table list
above. Drawio's ER stencil:
- Header row: `shape=html;fillColor=#dae8fc;startSize=24`
- Row cell: `shape=row;startSize=0`
- Crow's-foot endings: `endArrow=ERmany;startArrow=ERone` (or
  `ERzeroOne`, `ERzeroToMany` as appropriate).

### Things to NOT include
- The Wazuh manager's own database (separate concern, not ours).
- Redis (it's not a relational store).
- Migration history (Alembic file names).

---

## 3.7.7 Sequence Diagram — **drawio**

### Purpose
A single canonical sequence: **what happens, in chronological order,
when Caldera fires the Discovery tactic against a victim host**.

This is the "interaction" view that proves the pipeline isn't a
black box — every component participates, with a deterministic order
and a measurable latency.

### Notation
UML 2.5 sequence diagram. Lifelines vertical, time downward, messages
left-to-right. Use drawio's UML stencil "Sequence".

### Actors / lifelines (left → right, 12 total)

```
1.  Caldera                  [external]
2.  Sandcat agent (victim)   [external]
3.  auditd                   [external]
4.  Wazuh agent              [external]
5.  Wazuh manager            [external]
6.  Filebeat                 [external]
7.  Redis Streams            [data store]
8.  wazuh_bridge worker
9.  normalizer worker
10. inference worker (with AE, VAE, Tx, GNN, DQN)
11. verdicts_writer worker
12. Postgres                 [data store]
13. Web client (via SSE)     [external]
```

13 lifelines is dense but readable in drawio's wide-page layout. If
the chapter prefers a narrower diagram, collapse 3–5 into one
"Telemetry stack" composite lifeline.

### Messages — verbatim, in order

| # | From → To                        | Message label                                       |
| - | -------------------------------- | --------------------------------------------------- |
| 1 | Caldera → Sandcat                | `run_ability("whoami")`                             |
| 2 | Sandcat → auditd                 | exec syscall (SYS_execve)                           |
| 3 | auditd → Wazuh agent             | audit-wazuh-x record                                |
| 4 | Wazuh agent → Wazuh manager      | TCP/1514 encrypted event                            |
| 5 | Wazuh manager → Filebeat         | append to alerts.json                               |
| 6 | Filebeat → Redis Streams         | `RPUSH strix:alerts:raw:list`                       |
| 7 | wazuh_bridge → Redis             | `BLPOP strix:alerts:raw:list`                       |
| 8 | wazuh_bridge → Redis             | `XADD strix:alerts:raw {…}`                         |
| 9 | normalizer → Redis               | `XREAD strix:alerts:raw`                            |
|10 | normalizer → normalizer          | feature engineering (55-dim)                        |
|11 | normalizer → Redis               | `XADD strix:features:shard0 {features}`             |
|12 | inference → Redis                | `XREAD strix:features:shard0 (batch=32)`            |
|13 | inference → AE                   | forward(x) ▶ anomaly_score                          |
|14 | inference → β-VAE                | forward(x) ▶ malicious_prob, uncertainty            |
|15 | inference → Transformer          | forward(seq) ▶ pred_ckc, confidence                 |
|16 | inference → GraphSAGE            | forward(graph) ▶ node_risk                          |
|17 | inference → DQN                  | select_action(state) ▶ action_idx                   |
|18 | inference → inference            | apply gate (deterministic thresholds)               |
|19 | inference → Redis                | `XADD strix:verdicts {verdict + action}`            |
|20 | verdicts_writer → Redis          | `XREAD strix:verdicts (window=5 s)`                 |
|21 | verdicts_writer → Postgres       | `INSERT alerts, detections, dqn_actions`            |
|22 | verdicts_writer → Postgres       | `UPSERT attack_chains (open or bump stage)`         |
|23 | verdicts_writer → Web client     | SSE event on `/api/v1/streams/live-feed`            |
|24 | Web client → Web client          | render verdict + chain timeline                     |

### Activations / lifelines visual

- Active rectangles on each lifeline from the message it receives to
  the message it sends out.
- The 5 model calls (msg 13–17) are nested under inference's active
  rectangle — use drawio's nested activation (small rectangle inside
  the bigger one).
- `inference → inference` (msg 18, gate) is a self-call: dashed arc.

### Timing notes (annotate top-right corner)

```
T = 0          Caldera fires ability
T ≈ 50 ms      Wazuh manager writes alerts.json
T ≈ 250 ms     filebeat picks up + RPUSH
T ≈ 400 ms     wazuh_bridge to XADD
T ≈ 700 ms     normalizer feature build complete
T ≈ 1.3 s      inference batch flushes
T ≈ 1.5 s      Postgres INSERT + SSE
T ≈ 1.7 s      Web client renders
```

(Numbers from the per-tactic report in section 3.5 — quote, don't
re-derive.)

### MCP invocation

`mcp__drawio__open_drawio_xml` with the XML scaffolded for 13
lifelines and the 24 messages above. Drawio's sequence stencil:
- Lifeline: `shape=umlLifeline;perimeter=lifelinePerimeter`
- Message: `endArrow=open;html=1;rounded=0;exitX=…`
- Activation: a thin rectangle child of the lifeline cell.

### Alternative sequences worth mentioning in the chapter
- **DQN action approval** — analyst clicks "Approve" → backend hits
  Wazuh active-response API → audit log row. 7 lifelines, much
  smaller.
- **Auth + push token registration** — barely interesting, omit.

### Things to NOT include
- Service-class internals (3.7.3 already showed them).
- Class methods (3.7.4's job).
- Anything happening before `Caldera fires` — the diagram starts at
  that moment.

---

## 3.7.8 Deployment Architecture — **Eraser**

### Purpose
Where everything actually runs. Containers, networks, ports, volumes.
The reproducibility story.

### Audience
The reader who wants to spin STRIX up on their own machine. Should
match what `make up-d && make workers && make sim-up` produces.

### Layout — one developer host, two Docker bridge networks

```
┌──────────────────────────────  Developer host (16 GB RAM)  ────────────────────────────┐
│                                                                                          │
│  ┌──────────────── Docker network: strix_net ──────────────────────────────────────┐    │
│  │   strix_postgres   strix_redis   strix_api   strix_wazuh_bridge                  │    │
│  │   strix_normalizer strix_inference_shard0  strix_verdicts_writer                 │    │
│  │   strix_arq        strix_intel_feeds  strix_prometheus  strix_grafana            │    │
│  └───────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
│  ┌────────────── Docker network: strix_lab_net  ───────────────────────────────────┐    │
│  │  strix_wazuh_manager  strix_caldera  strix_victim1  strix_victim2                │    │
│  │  strix_attacker       strix_filebeat                                             │    │
│  └───────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
│  Host-network processes (Honcho-managed, dev mode):                                      │
│    • Next.js dev server on host port 5600                                                │
│    • (optional) honcho-driven workers if `make host-up`                                  │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘

  External SaaS (off-host):
    abuse.ch · VirusTotal · Anthropic Claude · Expo Push · GitHub
```

### Nodes (verbatim from `infra/compose.api.yml`,
`infra/compose.platform-deps.yml`, `infra/compose.simulation.yml`)

#### `strix_net` (platform network)

| Container                  | Image                                      | Ports (host:cont) | Volumes                                |
| -------------------------- | ------------------------------------------ | ----------------- | -------------------------------------- |
| `strix_postgres`           | timescale/timescaledb:2.17.2-pg16          | 5435:5432         | `strix_postgres_data → /var/lib/postgresql/data` |
| `strix_redis`              | redis:7-alpine                             | 6380:6379         | `strix_redis_data → /data`             |
| `strix_api`                | (built) `python:3.11-slim + apps/api`      | 8000:8000         | `apps/models → /app/apps/models:ro`    |
| `strix_wazuh_bridge`       | same image                                 | —                 |                                        |
| `strix_normalizer`         | same image                                 | —                 |                                        |
| `strix_inference_shard0`   | same image                                 | —                 | `apps/models → /app/apps/models:ro`    |
| `strix_verdicts_writer`    | same image                                 | —                 |                                        |
| `strix_arq`                | same image                                 | —                 |                                        |
| `strix_intel_feeds`        | same image                                 | —                 |                                        |
| `strix_prometheus` (obs)   | prom/prometheus                            | 9091:9090         | `prometheus.yml`                       |
| `strix_grafana` (obs)      | grafana/grafana                            | 3000:3000         | dashboards JSON                        |

#### `strix_lab_net` (simulation network)

| Container                  | Image                                      | Ports (host:cont)                      | Notes                                    |
| -------------------------- | ------------------------------------------ | -------------------------------------- | ---------------------------------------- |
| `strix_wazuh_manager`      | wazuh/wazuh-manager:4.5.2                  | 1514:1514, 1515:1515, 1514/udp, 55000:55000 | manager API + agent ingestion       |
| `strix_caldera`            | (built from infra script)                  | 8888:8888 (operator UI), 7010/tcp, 7011/udp, 7012/tcp (C2), 8080 (payload) | persistent volume |
| `strix_victim1`            | ubuntu:22.04 + wazuh-agent + auditd        | —                                      | Sandcat agent inside                     |
| `strix_victim2`            | ubuntu:22.04 + wazuh-agent + auditd        | —                                      | Sandcat agent inside                     |
| `strix_attacker`           | kalilinux/kali-rolling                     | —                                      | runs `recon_burst.sh`                    |
| `strix_filebeat`           | elastic/filebeat:8.15.3                    | —                                      | mounts wazuh-manager's alerts dir RO     |

#### Host (not in any compose)

| Process     | Command                              | Port | Notes                       |
| ----------- | ------------------------------------ | ---- | --------------------------- |
| Next.js dev | `pnpm dev` (Procfile.host:web)       | 5600 | dev only; prod via Vercel   |
| Honcho      | `honcho -f Procfile.host start`      | —    | alternative to `make workers` |

#### External SaaS (off the host)

Cloud icons in their own column on the right:

```
abuse.ch (URLhaus, Feodo)
VirusTotal
Anthropic (Claude API)
Expo Push
GitHub (source)
```

### Edges to draw
- Every container → its network (membership; thin line).
- `strix_api` ↔ `strix_postgres` (5435) and ↔ `strix_redis` (6380).
- Worker containers ↔ `strix_redis` (Streams).
- `strix_filebeat` → `strix_redis` (cross-network: filebeat lives in
  `strix_lab_net` and the redis lives in `strix_net`; this is enabled
  by `external: true` network config in
  `compose.platform-deps.yml`. Mark this edge **dashed** to highlight
  the cross-network hop.).
- `strix_wazuh_manager` ← `strix_victim1/2` (1514).
- `strix_caldera` ← `strix_attacker` (browser to 8888).
- `strix_caldera` → `strix_victim1/2` (Sandcat C2 over 7010/7011/7012).
- `strix_api` → external SaaS (outbound HTTPS).
- Mobile / Web (laptop browsers, drawn outside the host) → host port
  8000 (api) and 5600 (web).
- `strix_api` → Expo Push (outbound, dotted).

### Eraser DSL stub

```eraser
title STRIX — Deployment Architecture

Host "Developer host (16 GB RAM, Docker engine)" {

  Network "strix_net" [color: #3C7DD9] {
    pg          [icon: postgresql, label: "strix_postgres\n5435:5432\nvol postgres_data"]
    rd          [icon: redis,      label: "strix_redis\n6380:6379"]
    api         [icon: fastapi,    label: "strix_api\n8000:8000"]
    wbridge     [icon: python,     label: "strix_wazuh_bridge"]
    norm        [icon: python,     label: "strix_normalizer"]
    inf         [icon: pytorch,    label: "strix_inference_shard0\n→ apps/models (ro)"]
    vw          [icon: python,     label: "strix_verdicts_writer"]
    arq         [icon: python,     label: "strix_arq"]
    intel       [icon: python,     label: "strix_intel_feeds"]
    prom        [icon: prometheus, label: "strix_prometheus\n9091:9090"]
    graf        [icon: grafana,    label: "strix_grafana\n3000:3000"]
  }

  Network "strix_lab_net" [color: #E55B5B] {
    wmgr        [icon: shield, label: "strix_wazuh_manager\n1514/1515/55000"]
    cald        [icon: bug,    label: "strix_caldera\n8888 + 7010/7011/7012 + 8080"]
    v1          [icon: linux,  label: "strix_victim1"]
    v2          [icon: linux,  label: "strix_victim2"]
    att         [icon: terminal, label: "strix_attacker"]
    fb          [icon: elastic, label: "strix_filebeat"]
  }

  Host {
    nextjs   [icon: nextdotjs, label: "Next.js dev\nhost:5600"]
  }
}

External [color: #7F8C8D] {
  abuse    [icon: cloud, label: "abuse.ch\nURLhaus + Feodo"]
  vt       [icon: cloud, label: "VirusTotal"]
  claude   [icon: cloud, label: "Anthropic Claude"]
  expo     [icon: cloud, label: "Expo Push"]
}

LaptopBrowsers [color: #2EC4B6] {
  web_browser    [icon: chrome, label: "Web browser\n→ host:5600 + host:8000"]
  mobile_device  [icon: smartphone, label: "Expo dev-client\n→ host:8000"]
}

// edges — platform network
api      <> pg
api      <> rd
wbridge  <> rd
norm     <> rd
inf      <> rd
inf      > apps_models_volume   // dotted: read-only mount
vw       <> rd
vw       > pg
arq      <> rd
intel    > rd

// cross-network
fb       --> rd               : "cross-network bridge"

// lab edges
att      > cald               : "browser to :8888"
cald     > v1                 : "C2"
cald     > v2                 : "C2"
v1       > wmgr
v2       > wmgr
wmgr     > fb                 : "alerts.json mount"

// external
api      > claude             : "summaries"
api      > vt                 : "scans"
intel    > abuse              : "30 s feeds"
api      > expo               : "push"

// clients
web_browser    <> nextjs
web_browser    <> api
mobile_device  <> api
```

### Things to NOT include
- File-level paths inside containers (mention only the volume mounts).
- Internal port numbers of subordinate processes (use the container's
  *exposed* port, not the worker's internal listen port — workers
  don't listen, they consume Redis).
- Compose YAML keys (`depends_on`, `healthcheck`) — out of scope.

---

## 4. Asset checklist (do once)

- [ ] Confirm output directory `report/PFE/figures/ch3/{eraser,drawio}` exists.
- [ ] Decide on a single font for all 7 diagrams (drawio's `Helvetica`
      matches the report's LaTeX body font reasonably; Eraser's
      `Inter` is fine for the infrastructure diagrams since they don't
      mix with body prose).
- [ ] Resolve the `data flow` vs `database` ambiguity in 3.7.6 by
      committing to two sub-diagrams (3.7.6.a + 3.7.6.b) and adding
      the corresponding `\subsection` headings to the chapter source
      before drawing.
- [ ] Capture the 5 timing measurements for 3.7.7 from the per-tactic
      report (median over the last 5 runs of `lab_simulate.sh`).
- [ ] Decide whether the obs profile (`strix_prometheus`,
      `strix_grafana`) is in or out of 3.7.8. We keep it in — it's in
      the actual compose and reviewers will look for it.

---

## 5. Generation order (recommended)

1. **3.7.6.b ER diagram** first. The class diagram (3.7.4) re-uses
   its content with method annotations added, so producing the ER
   diagram first means the class diagram is "ER + a few methods".
2. **3.7.4 Class diagram** second.
3. **3.7.2 System Architecture** — Eraser; gives us the colour
   palette baseline used by 3.7.3 and 3.7.8.
4. **3.7.3 Platform Components** — Eraser; same palette as 3.7.2.
5. **3.7.8 Deployment** — Eraser, last of the Eraser triplet.
6. **3.7.6.a Data Flow** — drawio; references the workers from 3.7.3
   and the data stores from 3.7.6.b.
7. **3.7.7 Sequence** — drawio; references the same workers in
   chronological order.
8. **3.7.5 Workflow** — drawio; the only one that includes the
   analyst as an actor, so leave it for last to make sure the human
   side is well-thought.

Each diagram is independent — generation order is suggested for
**consistency**, not for correctness. Re-generation in any order
will produce the same final assets.

---

## 6. After-generation checklist (per diagram)

- [ ] Source file saved under `report/PFE/figures/ch3/{eraser,drawio}/`.
- [ ] PDF exported (vector) for LaTeX inclusion.
- [ ] PNG exported (raster, 300 DPI) as a sanity check for the IDE
      preview.
- [ ] Caption drafted (one paragraph) in the chapter's `.tex` file,
      pointing at the figure with `\autoref{fig:ch3:<slug>}`.
- [ ] All node labels match the verbatim names in the codebase. No
      "API Service" if the actual file is `api/main.py`; either say
      `strix_api` (the container name) or `FastAPI service`, but be
      consistent across diagrams.

---

## 7. Things this brief deliberately leaves open

- **Drawio sequence diagram density** — 13 lifelines may overflow a
  single page. If it does, the fallback is a two-page diagram split
  at the inference activation, or a single diagram with the
  Telemetry stack (auditd + Wazuh agent + Wazuh manager + Filebeat)
  collapsed into one composite lifeline labelled "Telemetry stack".
  Decide at render time.
- **Eraser license** — Eraser's free tier limits export resolution.
  If the PDF doesn't look crisp at 100 % zoom, the workaround is to
  export as SVG and convert via `inkscape --export-pdf`.
- **Tooltips and hover labels** — both tools support extra
  description text that doesn't render in the exported image but
  shows up in the editor. Use these for source-of-truth file paths
  (e.g. node `verdicts_writer` gets tooltip
  `apps/api/src/strix_api/workers/verdicts_writer.py`). Helps the
  reviewer who opens the source file.

---

**End of brief.** When ready to generate, point this document at the
relevant MCP (`mcp__eraser__create` for the eraser ones,
`mcp__drawio__open_drawio_xml` for the drawio ones) and feed it
section by section.
