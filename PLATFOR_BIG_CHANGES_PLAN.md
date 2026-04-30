# PLATFORM BIG CHANGES — Implementation Plan

Status: **Draft, awaiting approval. No code written yet.**
Owner: Yacine
Date: 2026-04-30

---

## 0. Scope

This plan covers two concurrent workstreams:

1. **Live pipeline + frontend rebuild** — make all 4 models (AE, VAE, GNN, RL) consume logs as a live stream, expose per-model outputs over a unified WebSocket, and rebuild the dashboard panels (forensics log feed, topology panel, GNN graph, kill-chain, AE/VAE quality).
2. **Model-loader / preprocessing correctness fixes** — resolve the 10 known blocking/high bugs in inference loaders so the live model outputs are actually meaningful (not garbage from permuted feature columns, missing scalers, wrong activations, etc.).

Workstream 2 is sequenced **before Phase 2** of workstream 1 — there is no point streaming per-model scores if the scores are wrong. It can run in parallel with Phase 1 (simulation infra) since they don't touch the same files.

---

## 1. What exists today (anchor for the plan)

- **Stack**: FastAPI + Redis Streams + Postgres backend; Next.js 14 (App Router, TypeScript) + React Query + SSE frontend; Caldera + Wazuh + Filebeat lab.
- **Models** (`apps/models/*.pth`, loaded by [apps/api/src/strix_api/workers/inference.py](apps/api/src/strix_api/workers/inference.py)): AE, β-VAE, Transformer (CKC predictor), GraphSAGE GNN, DQN.
- **Inference**: micro-batched (32 events / 50 ms for AE+VAE; per-event for Transformer+GNN; 16/10ms for DQN). Outputs are written as a *combined* verdict to Postgres + SSE `strix:sse:live-feed`. **Per-model scores are not individually published.**
- **Log path**: Caldera → auditd → Filebeat → Redis `strix:alerts:raw` → normalizer → `strix:features:{shard}` → inference → `strix:verdicts` → Postgres + SSE.
- **No `/logs/stream` endpoint.** No Elasticsearch consumer (docs imply one — contradiction, ignored).
- **Simulation**: [infra/scripts/lab_simulate.sh](infra/scripts/lab_simulate.sh) runs 9 tactics sequentially; output is buffered/batched at end. No benign traffic. No topology manifest.
- **Frontend**: SSE live-feed (`useLiveFeed`, max 8 events), 30s polling for aggregates. Existing components: [forensic-log-viewer.tsx](apps/web/components/charts/forensic-log-viewer.tsx), [graph-evolution.tsx](apps/web/components/charts/graph-evolution.tsx), [kill-chain-timeline.tsx](apps/web/components/charts/kill-chain-timeline.tsx), [ai-predictions-panel.tsx](apps/web/components/charts/ai-predictions-panel.tsx). Custom SVG charts, no chart lib.

---

## 2. Risks flagged before starting

1. **[inference.py](apps/api/src/strix_api/workers/inference.py) is the hot path.** New per-model pubsub publishes will be added as a **strict superset** of current behavior (don't touch existing verdict writes), gated behind `STRIX_STREAM_PER_MODEL=1`.
2. **Pre-existing model-loader bugs** mean per-event scores would be garbage if streamed as-is. Workstream 2 (below) fixes them first.
3. **WebSocket vs SSE**: keep existing SSE endpoints intact for backward compat; add **one new WebSocket** at `/api/v1/logs/stream` for the multiplexed live feed.
4. **Benign-traffic generator** could trip Wazuh rules and pollute real detections. Tagging strategy (after auditing existing rules — no naming collisions, but auditd keys are watch-level not per-command, so a custom `key=` won't ride on existing watch events):
   - **A.** Run the benign generator as a dedicated UNIX user `strixbenign`. Filebeat enriches each event with `strix.synthetic_benign: true` when `auid` matches that user's UID.
   - **B.** Generator also writes a sidecar `infra/simulation/runs/{run_id}/benign_events.jsonl` (`{ts, host, pid, cmd}`) as ground-truth fallback. Backend labeller cross-references on `(host, ts ± 500 ms)`.
   - Both A and B are implemented (A for fast online labelling, B as robust fallback).

---

## 3. Workstream 2 — Model-loader / preprocessing fixes (run before Phase 2)

Each fix is independently testable with unit tests against a held-out dataset and existing checkpoint files.

### Phase A — Export missing preprocessing artifacts
Source: notebooks under `apps/notebooks/`.
- Export and commit to `apps/models/preprocess/`:
  - `scaler_55.pkl` — StandardScaler fitted on the 55-col training matrix.
  - `secbert_tokenizer/` — SecBERT tokenizer dump.
  - `pca_log_secbert.pkl`, `pca_cmd_secbert.pkl` — two PCA-16 objects.
  - `vae_calibrator.pkl` — VAE probability calibrator.
  - `gnn_propagation_metadata.pkl` — Part-2 GNN scaler + threshold (0.7743).
- Add `apps/models/MANIFEST.json` listing each artifact with sha256 + source-notebook ref.

**Test gate A**: load every artifact in a `pytest` smoke test, assert shapes/keys, assert sha256 matches MANIFEST.

### Phase B — Fix feature column order (BLOCKING #1)
- File: `apps/api/src/strix_api/adapters/preprocessing_pipeline.py`.
- Replace ad-hoc column ordering with explicit `FEATURE_COLUMNS` list copied verbatim from training notebook.
- Add `tests/test_feature_order.py` — load a captured training row + its expected normalized vector, assert exact match within 1e-6.

**Test gate B**: regression test passes; pre-fix it must fail (commit the failing test first).

### Phase C — Fix Transformer loader (BLOCKING #3)
- Loader in `inference.py` or `apps/api/src/strix_api/services/` (will be located precisely during execution).
- Set `activation='gelu'`, `norm_first=True`. Add ReLU + Dropout in input projection. Switch to last-token pooling explicitly (matches training, current docstring is wrong — fix doc too).
- Test: load checkpoint, run forward pass on 8 sample sequences, compare logits to a golden file produced from the training notebook (tolerance 1e-4).

### Phase D — Fix VAE calibration (HIGH #4)
- Replace heuristic `sigmoid(2*(recon+0.05*center_dist)−1)` with `vae_calibrator.pkl.predict_proba`.
- Test: 100 calibration samples → expected probs from notebook, assert MAE < 1e-3.

### Phase E — Fix GNN threshold + filename mismatch (HIGH #5, MEDIUM #6, BLOCKING #10)
- Wire `gnn_propagation_metadata.pkl` into the GNN loader (threshold 0.7743).
- Resolve filename mismatch: either rename shipped weights to loader-expected names, or update loader paths. Decision: **update loader paths** (don't rename artifacts post-training).
- Test: 50 graph snapshots → expected node-risk vectors match notebook output.

### Phase F — Port MITRE→CKC name mappings (MEDIUM #9)
- Add name-based mapping dict alongside ID-based.
- Test: 20 known technique names map to correct CKC stage.

### Phase G — Cosmetic doc fixes (LOW #11)
- Update `docs/MODELS_REFERENCE.md` Transformer pooling description.

**Workstream 2 exit gate**: full pytest suite green; a manual smoke run of inference on 1k captured events produces verdicts within 5% of notebook ground truth on a held-out set. **Only after this passes do we start Phase 2 of workstream 1.**

---

## 4. Workstream 1 — Live pipeline + frontend

Each phase ends with a manual test gate. I will pause and wait for your confirmation before proceeding to the next.

### Phase 1 — Simulation: streaming output + benign traffic + topology manifest
Backend/infra only. No frontend changes.
- Refactor [infra/scripts/lab_simulate.sh](infra/scripts/lab_simulate.sh) (and `infra/simulation/scripts/`) so each event flushes immediately. Line-buffered writes (`stdbuf -oL`); ensure auditd→filebeat tail picks up within 2 s.
- New `infra/simulation/scripts/benign_traffic.sh` — `--rate`, `--duration`, `--targets`. Loops realistic SSH login, curl HTTP, dig DNS, cron entries, file reads, `apt list`, `dpkg -l`. Runs as dedicated user `strixbenign` (created in victim image bootstrap). Filebeat adds `strix.synthetic_benign: true` when `auid` matches. Also appends each command to `infra/simulation/runs/{run_id}/benign_events.jsonl` as a ground-truth sidecar. Runs in parallel with malicious tactics.
- Emit `infra/simulation/runs/{run_id}/topology.json`: `{run_id, started_at, attacker_ip, victims:[{ip, hostname, agents:[wazuh, sandcat, auditd]}], apt_group, tactics_planned}`.
- Add `GET /api/v1/simulation/runs/latest` (read-only filesystem read, no DB).

**Test gate 1**: run `lab_simulate.sh --benign-rate 100/min --duration 60s --apt APT29`. Verify (a) Wazuh sees events within 2 s of generation, (b) `topology.json` written, (c) `GET /api/v1/simulation/runs/latest` returns it.

### Phase 2 — Backend: unified `/logs/stream` WebSocket multiplex
Backend only. **Requires workstream 2 complete.**
- Add WS route in `apps/api/src/strix_api/api/routes/streams.py` at `/api/v1/logs/stream`.
- Envelope: `{type: "raw_log"|"ae"|"vae"|"gnn"|"rl"|"topology"|"status", ts, payload}`.
- New Redis pubsub channels published from [inference.py](apps/api/src/strix_api/workers/inference.py): `strix:stream:ae`, `strix:stream:vae`, `strix:stream:gnn`, `strix:stream:rl`. Existing `strix:sse:live-feed` reused for `raw_log`.
- [inference.py](apps/api/src/strix_api/workers/inference.py) modification: after each batch, also publish per-event AE recon error, VAE ELBO, GNN node embedding + affected edges, RL stage + confidence. Gated behind `STRIX_STREAM_PER_MODEL=1`. Existing batch verdict writes untouched.
- TP/FP/TN/FN labelling uses `topology.json` ground truth: attacker IP → malicious; benign-tagged events → benign; else unknown.
- Backpressure: bounded `asyncio.Queue` per ws client (size 500, drop-oldest, emits a `status: dropped:N` frame).

**Test gate 2**: run sim from Phase 1. `wscat -c ws://localhost:8000/api/v1/logs/stream`. Smoke test asserts ≥1 frame of each type within 30 s.

### Phase 3 — Frontend foundation: ws client + global status bar + design tokens
Frontend only, no panel rewrites yet.
- New `apps/web/lib/api/ws.ts` — singleton WebSocket with reconnect/backoff, type dispatcher, `useLogStream(types)` hook returning typed observables. Bounded ring buffer per type (default cap 500). Strict TypeScript types for every envelope variant.
- New `apps/web/components/layout/connection-status-bar.tsx` — LIVE / RECONNECTING / OFFLINE pill + last-event timestamp.
- Extend/create `apps/web/lib/design-tokens.ts` — severity palette (`critical/high/medium/low/benign`) + cluster palette (stable hash → color).
- Mount status bar in [apps/web/app/(dashboard)/page.tsx](apps/web/app/(dashboard)/page.tsx) layout shell.

**Test gate 3**: `pnpm dev`. Status bar shows LIVE during sim. Kill API → RECONNECTING → OFFLINE. Restart → recovers. 5-min React DevTools profile shows flat heap.

### Phase 4 — Forensics live log box (terminal-style)
- Rewrite [apps/web/components/charts/forensic-log-viewer.tsx](apps/web/components/charts/forensic-log-viewer.tsx). 4–5 most-recent lines, smooth slide-up animation, severity color coding, pulsing LIVE badge, pause/resume button (pauses render, not stream).

**Test gate 4**: visual; pause freezes display while ws keeps receiving; resume catches up.

### Phase 5 — Simulation topology panel
- New `apps/web/components/topology/simulation-topology-panel.tsx`. Fetches `topology.json` once + ws for per-event updates.
- SVG: attacker, victims (agent badges), APT label, animated dot-flow edges (severity-colored), pulse on malicious, shimmer on benign.
- Live counters: total / malicious / benign / alerts.

**Test gate 5**: visual; pulse fires per malicious event; counters increment.

### Phase 6 — GNN victim graph rebuild
- Rewrite [apps/web/components/charts/graph-evolution.tsx](apps/web/components/charts/graph-evolution.tsx). Bind to `gnn` ws frames. Node size = anomaly score, color = stable cluster id, edge thickness = weight, edge color = red/gray. 300 ms transitions. Hover tooltip: top-5 features + anomaly sparkline. Confidence gauge + cluster legend.

**Test gate 6**: visual + unit test with mocked frames asserting node radius scales with anomaly score.

### Phase 7 — RL kill-chain timeline
- New `apps/web/components/charts/rl-kill-chain.tsx`. Per-session row, 7 stage nodes, animated progress fill, state colors (completed amber→red, current pulsing, future ghost, mitigated green ✓). Slide-in animation, fade-out 10 s after completion, max 5 rows + "+N more". Mini stage heatmap above.

**Test gate 7**: run two APT profiles in parallel; confirm independent rows progress correctly.

### Phase 8 — AE vs VAE detection-quality panel
- New `apps/web/components/charts/detection-quality-panel.tsx`. Two side-by-side sub-panels. Rolling 60 s stacked-bar (5 s buckets) of TP/FP/TN/FN, 2×2 confusion matrix, precision/recall/F1 cards, threshold slider (recomputes client-side from cached 60 s ring buffer). F1 comparison strip below with delta arrow.

**Test gate 8**: visual; slider recomputes without re-fetch; 5-min sim shows stable metrics.

### Phase 9 — Dashboard layout + perf hardening
- Final layout in [apps/web/app/(dashboard)/page.tsx](apps/web/app/(dashboard)/page.tsx): top = status bar + sim controls; left = topology + kill-chain; right = GNN + detection-quality; bottom = log feed full-width. Min-width 1280 px.
- Audit ring buffers (cap 500), `useEffect` cleanups, intervals/animation-frame cleanups. 5-min @ 500 ev/min sim with Chrome perf recording — heap must stay flat.

**Test gate 9**: final 5-min soak; perf trace + screenshot for review.

---

## 5. Conventions

- **TypeScript** for all new/modified frontend files (matches existing codebase).
- Each new file gets a header comment block stating its purpose.
- No new dependencies without flagging first (animation: prefer CSS keyframes / Framer Motion only if already in `package.json`).
- No unbounded arrays; every stream-bound buffer has an explicit cap.
- Existing SSE endpoints and verdict writes remain untouched.
- Feature flags: `STRIX_STREAM_PER_MODEL` (backend) gates the new pubsub fan-out.

---

## 6. Open questions for you

1. OK to add **Framer Motion** to `apps/web/` if it's not already present? (Phases 4, 7 benefit; pure CSS is doable but more code.)
2. Workstream 2 (loader fixes) — do you want me to do all of it before Phase 2 starts, or only the **BLOCKING** items (B, C, E, A) and defer HIGH/MEDIUM?
3. ~~Confirm benign-traffic auditd marker `key=strix-benign` won't conflict with any existing rule.~~ **Resolved 2026-04-30**: no collision in repo. Auditd keys are watch-level, not per-command, so the marker approach was replaced by `auid`-based filebeat enrichment + sidecar ground-truth file (see Risk #4).
