# INGESTION_PIPELINE — Wazuh → STRIX Inference

> **Scope:** real-time scoring path for the AE, VAE, and Transformer models. GNN / batch scoring is deferred to a later session (per this session's decision).
> **Deployment confirmed:** Docker Compose on a single VM.
> **Wazuh topology (default to be confirmed):** single self-hosted manager + indexer + 5+ agents — mirrors the training data layout (`manager.name = ubuntu`, agents `Machine-1-New … Machine-5-New`).

---

## 1. Decisions captured from this session

| Question | Answer |
|---|---|
| Deployment target | Docker Compose on a single VM |
| Wazuh deployment | **Proposed default:** single self-hosted Wazuh manager + indexer, same shape as training |
| Transport | **Recommended:** Filebeat tailing `alerts.json` → **Redis Streams** → normalization worker → FastAPI inference. Rationale: fits single-VM/compose, lightweight, gives backpressure + replay (consumer groups), no Kafka/Zookeeper overhead |
| Real-time GNN path | Skipped — real-time only scores AE / VAE / Transformer. GNN stays batch/offline (future session) |

Open items (flagged, not blocking this plan):
- Persisted SecBERT PCA-16 artifact location (needed by the normalization service — see §5)
- Confirmation that the proposed Wazuh topology is acceptable
- Where to store scored alerts for the UI/mobile apps (likely Postgres in the same compose stack)

---

## 2. Flow overview (ASCII)

```
                      VM / Docker Compose host
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                                                                              │
 │  ┌────────────┐      ┌──────────────────────┐                                │
 │  │ Wazuh      │      │ Wazuh manager        │                                │
 │  │ agent(s)   │──────▶│  (single-node)       │                               │
 │  │ 5× linux   │ 1514 │  decoders + rules    │                                │
 │  └────────────┘      │  ↓ writes             │                               │
 │                      │  /var/ossec/logs/     │                               │
 │                      │     alerts/alerts.json│                               │
 │                      └──────────┬────────────┘                               │
 │                                 │ (shared volume: ossec-logs)                │
 │                                 ▼                                            │
 │                         ┌──────────────┐                                     │
 │                         │  Filebeat    │  tails alerts.json                  │
 │                         │  (sidecar)   │  (wazuh module OR raw json)         │
 │                         └──────┬───────┘                                     │
 │                                │ publish                                     │
 │                                ▼                                             │
 │                ┌────────────────────────────┐                                │
 │                │  Redis Streams             │                                │
 │                │  key: strix:alerts:raw     │   durable, replayable          │
 │                │  retention: 24h (MAXLEN)   │   consumer-group: strix-norm   │
 │                └──────────────┬─────────────┘                                │
 │                               │ XREADGROUP                                   │
 │                               ▼                                              │
 │                ┌────────────────────────────┐                                │
 │                │  normalizer-worker         │  Python / FastAPI worker        │
 │                │  (1..N replicas)           │                                │
 │                │  - flatten JSON (_source.*)│                                │
 │                │  - drop envelope + leaky   │                                │
 │                │  - FeatureEngineer...      │                                │
 │                │    (same code as training) │                                │
 │                │  - SecBERT → PCA-16        │  loads persisted PCA artifact  │
 │                │  - StandardScaler.transform│  loads persisted scaler artfct │
 │                └──────┬─────────────────┬───┘                                │
 │                       │ feature vector  │                                    │
 │                       │  XADD strix:features                                 │
 │                       ▼                 ▼                                    │
 │         ┌──────────────────┐   ┌────────────────────┐                        │
 │         │ inference-api    │   │ (future) GNN batch │                        │
 │         │ FastAPI + uvicorn│   │ scorer (offline)   │                        │
 │         │                  │   └────────────────────┘                        │
 │         │  AE.pth          │                                                 │
 │         │  VAE.pth         │   emits score + verdict                         │
 │         │  Transformer.pth │                                                 │
 │         └─────────┬────────┘                                                 │
 │                   │ POST / XADD strix:verdicts                               │
 │                   ▼                                                          │
 │         ┌──────────────────┐        ┌──────────────────┐                     │
 │         │ Postgres         │◀───────│ verdicts writer  │                     │
 │         │ (alerts +        │        └──────────────────┘                     │
 │         │  verdicts)       │                                                 │
 │         └────────┬─────────┘                                                 │
 │                  │                                                           │
 │                  ▼                                                           │
 │         ┌──────────────────────────────────┐                                 │
 │         │  apps/web (Next.js) + apps/mobile│   queries verdicts              │
 │         │  (Expo)                          │                                 │
 │         └──────────────────────────────────┘                                 │
 │                                                                              │
 └──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component responsibilities

### 3.1 Wazuh manager
- Terminates agent connections on TCP 1514.
- Runs built-in decoders (`auditd`, `syscheck`, `pam`, `sudo`, `dpkg-decoder`, `web-accesslog`, `sca`, `ossec`, `rootcheck`, `sshd`) — already sufficient for the training schema (see `WAZUH_MAPPING.md` §10: no custom decoder needed).
- Writes alerts to `/var/ossec/logs/alerts/alerts.json` (native Wazuh JSON, one alert per line).
- Volume-shares that directory to the Filebeat container.

### 3.2 Filebeat (sidecar)
- Tails `alerts.json` with the `wazuh` Filebeat module (or plain JSON input).
- Parses each line as JSON and publishes the **full alert document** to Redis Streams key `strix:alerts:raw`.
- Uses the `redis` output (Filebeat's built-in) — no custom forwarder.
- Rationale for choosing Filebeat over Wazuh's `<integration>` webhook:
  - Backpressure-safe: if the normalizer crashes, Filebeat re-emits from its registry.
  - Replayable: Redis Streams consumer-group offsets give us replay within the retention window.
  - Native to the Wazuh ecosystem (the same Filebeat module ships with Wazuh OVA images).

### 3.3 Redis Streams (broker)
- Single Redis container, persistent AOF volume.
- Streams used:
  - `strix:alerts:raw` — ingress from Filebeat.
  - `strix:features` — normalizer output (feature vectors) consumed by inference-api.
  - `strix:verdicts` — inference output consumed by the verdicts writer.
- Retention: `MAXLEN ~ 100000` or 24h, whichever first — enough to recover from a normalizer restart.
- Consumer groups: `strix-norm` on raw, `strix-infer` on features.
- **Not highly available** — matches the single-VM constraint. Redis AOF + periodic snapshot is the durability story.

### 3.4 normalizer-worker (Python)
- Consumes `strix:alerts:raw`, produces `strix:features`.
- Steps per alert (must be byte-identical to training):
  1. Parse JSON, **flatten** nested keys to the dotted-path layout (`rule.mitre.technique` → key `_source.rule.mitre.technique`).
  2. Drop envelope (`_index`, `_id`, `_version`, `_score`) and leaky columns (see `WAZUH_MAPPING.md` §2).
  3. Coerce types: `_source.rule.firedtimes` → int, `_source.data.srcport` → int, etc.
  4. Run `FeatureEngineerNoLeakage.transform()` on a single-row DataFrame (code lifted verbatim from `apps/notebooks/feature_selection_final.ipynb`, cell 7 — should be packaged as `apps/normalizer/feature_engineer.py` in the **next** session).
  5. Apply the persisted **StandardScaler** (fit at training time).
  6. Emit the feature vector as a fixed-order `float32[]` to `strix:features` along with a correlation ID (`_source.id`).
- Stateless — OK to scale replicas by raising the `XREADGROUP` worker count.

### 3.5 inference-api (FastAPI)
- Loads `ae_model.pth`, `vae_model.pth`, `transformer_model.pth` on startup (CPU or CUDA).
- Consumes `strix:features`, runs all three models concurrently per alert (asyncio + torch no-grad).
- Produces a verdict record: `{alert_id, ae_score, vae_recon_err, transformer_prob, ckc_stage_pred, verdict, model_versions}` → `strix:verdicts`.
- Exposes HTTP endpoints too (for ad-hoc scoring, health, `/docs`).

### 3.6 verdicts-writer
- Consumes `strix:verdicts`, upserts into Postgres (alert row + verdict row).
- Same compose network as `apps/web` and `apps/mobile` consumers.

---

## 4. Schema transformation boundaries (where drift can happen)

The entire training-vs-live drift surface collapses to **three files** we will write in the next session:

| File | Purpose |
|---|---|
| `apps/normalizer/feature_engineer.py` | Port of `FeatureEngineerNoLeakage` — single source of truth for feature construction. Imported by both normalizer-worker and the offline training notebook going forward. |
| `apps/normalizer/artifacts/secbert_pca.pkl` | Persisted SecBERT 768→16 PCA. **Must be exported from the training notebook** (currently not in `apps/models/` — see open items). |
| `apps/normalizer/artifacts/scaler.pkl` | Persisted `StandardScaler`. Same caveat. |

If these three are unchanged, live data and training data are in the same feature space. If any of them mutates, **models must be retrained**.

---

## 5. Where aggregated / engineered features are computed

- **All current engineered features are per-alert** (regex flags, one-hots, SecBERT + PCA). No sliding windows, no session state.
- The normalizer-worker is therefore **stateless** today.
- If/when the GNN path is reintroduced, it will need a stateful aggregator (per-agent attack-graph builder). That service would sit between `strix:features` and a new `strix:graph` stream — out of scope for this session.

---

## 6. Final shape pushed into inference

The inference-api receives a JSON message from `strix:features`:

```json
{
  "alert_id": "1704027595.258",
  "agent_id": 4,
  "agent_name": "Machine-1-New",
  "timestamp": "2026-04-17T08:34:12.107Z",
  "features": {
    "hour_of_day": 8, "day_of_week": 5, "is_weekend": 1, "is_night": 0, "is_business_hours": 0,
    "firedtimes": 12, "firedtimes_log": 2.5649,
    "ip_is_private": 1, "ip_is_missing": 0, "srcip_is_private": -1, "srcip_is_missing": 1,
    "path_depth": 0, "path_is_sensitive": 0, "path_is_hidden": 0, "path_is_suspicious_ext": 0, "path_is_temp": 0, "path_is_missing": 1,
    "cmd_sudo_usage": 0, "cmd_wget_curl": 0, "cmd_nc_netcat": 0, "cmd_base64": 0, "cmd_length": 0, "cmd_is_missing": 1,
    "has_md5": 0, "has_sha256": 0,
    "syscheck_added": 0, "syscheck_modified": 0, "syscheck_deleted": 0,
    "srcport": 0, "is_privileged_port": 0, "is_high_port": 0,
    "decoder_auditd": 1, "decoder_web-accesslog": 0, "...": "...",
    "location__var_log_audit_audit.log": 1, "...": "...",
    "cmd_secbert_emb_0": 0.0, "...": "cmd_secbert_emb_15",
    "log_secbert_emb_0": -0.34, "...": "log_secbert_emb_15"
  },
  "feature_vector_order": "v1",
  "schema_version": 1
}
```

The `feature_vector_order` field pins the column order against a version constant so drift is detectable before models silently mis-score.

---

## 7. Out-of-scope (explicit TODOs for later sessions)

- Real GNN inference (needs session state + graph builder).
- Production HA (multi-node Wazuh, Kafka, Postgres replicas).
- Authentication/authorization on Redis and FastAPI (compose-internal for now).
- Multi-tenant label semantics (single customer in the training dataset).
- Re-labeling strategy — `malicious` as-trained equates to "alert has MITRE mapping", which is a lower bar than true SOC-confirmed malicious. Human-in-the-loop verdict review is future work.
