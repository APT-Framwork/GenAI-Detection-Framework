# STRIX Web App — UI Reorganization & SOC Gap Implementation Plan

Author: planning session 2026-05-04
Status: pre-implementation
Scope: full-stack (Next.js frontend + FastAPI backend)

This plan reorganises the STRIX web app so each page has one clear role, and adds the SOC-analyst pages that are currently missing (Cases, Host Detail, MITRE Matrix, Hunt, Action Log, UEBA, Playbooks).

---

## 1. Scope summary

### Frontend moves

| Component | From | To |
|---|---|---|
| SimulationTopologyPanel | Dashboard | Topology |
| GraphEvolution (GNN victim graph) | Dashboard | Topology |
| ForensicLogViewer | Dashboard | AI Engine *(replaces existing Live Inference Stream)* |
| Live Status Card (Critical / Warnings / Updates counts) | Vigilance Feed | Dashboard *(KPI strip)* |
| System Integrity card | Notifications | Dashboard *(KPI strip)* |
| Sentinel Status card | Notifications | Dashboard *(KPI strip)* |
| Throughput KPI | AI Engine | Dashboard *(KPI strip)* |
| Composite F1 KPI | AI Engine | Dashboard *(KPI strip)* |
| Compromised Assets (top 3–5 mini-card) | Threat Intel | Dashboard |
| Threat Resolution History (7-day bar chart) | Profile | Dashboard |

### Frontend removals

| Component | From | Reason |
|---|---|---|
| DetectionQualityPanel (829 lines) | Dashboard | Replaced by DetectionVolumePanel on AI Engine |
| PredetectionReceipt — rail variant | Dashboard | Inline variant kept; rail is duplicate noise |
| Live Inference Stream | AI Engine | Replaced by ForensicLogViewer |
| Activity Log Terminal (mock syslog) | Profile | Operational telemetry on a user profile; redundant with ForensicLogViewer |
| Assigned Assets (animated endpoint map) | Profile | Infrastructure telemetry; Topology already owns the canonical view |
| "82% Global Accuracy" badge inside AI Alert Thresholds | Settings | Live metric in a config page; belongs on AI Engine — keep only the sliders & Alert Priority Grid |

### Net-new (frontend + backend)

| Component | Page | Purpose |
|---|---|---|
| **DetectionVolumePanel** *(Kibana-style stacked TN/FP bars over time)* | AI Engine | Replaces DetectionQualityPanel; surfaces false-alarm fatigue trend |
| **Case / Chain Queue** | New `/cases` | Triage list of open chains by status — analyst home screen |
| **Host Detail page** | New `/host/[id]` | Per-host drill-down (processes, network, commands, users, files, chains) |
| **MITRE ATT&CK Coverage Matrix** | Threat Intel *(new tab)* | 14-tactic technique heatmap |
| **Search / Hunt bar** | New `/hunt` | KQL-style query with `host: user: technique: time:` |
| **Response Action Log** | Notifications *(tab)* / `/actions` | DQN-proposed + operator actions ledger |
| **User Risk panel (UEBA)** | Threat Intel *(card)* | Top-risky users from GNN USER edges |
| **Playbook / Runbook viewer** | Attack Analysis detail *(right rail)* | Recommended response per CKC stage / technique |

### Page role changes (no separate work — fall out of moves)

- **Dashboard** → executive / live-demo view: KPI strip + AptAttackTimeline + RlKillChain + PredetectionReceipt + Compromised Assets mini + Threat Resolution chart
- **Vigilance Feed / Notifications** → pure chronological feeds (summary sidebars now on Dashboard)
- **Topology** → canonical network/graph view (gains SimulationTopology + GraphEvolution)
- **AI Engine** → canonical model-performance + live-inference view (gains DetectionVolumePanel + ForensicLogViewer)
- **Profile** → identity-only (loses operational telemetry); MFA *status* read-only here
- **Settings** → configuration-only (loses live metrics); MFA *setup* lives here

---

## 2. Pre-flight (analysis tasks)

Before touching code, perform these read-only validations:

1. **Confirm no stray consumers of moved components.** `grep -rn "DetectionQualityPanel\|SimulationTopologyPanel\|GraphEvolution\|ForensicLogViewer\|PredetectionReceipt" apps/web` — every result outside the files we plan to edit must be acknowledged. Today these are imported only from `apps/web/app/(dashboard)/page.tsx` and a couple of places (the analysis chain page reuses `ForensicLogViewer` in legacy mode via the `logs` prop — that path stays).
2. **Inventory WS/SSE consumers.** `useLogStream(["ae"])`, `useLogStream(["vae"])`, `useLogStream(["gnn"])`, `useLiveFeed`. Confirm that removing `DetectionQualityPanel` from the dashboard does not orphan AE/VAE — it doesn't, because the new `DetectionVolumePanel` will subscribe to the same channels on `/ai-engine`.
3. **Confirm `STRIX_STREAM_PER_MODEL=1` is the canonical run mode** — without it, AE/VAE/GNN frames are never published (`apps/api/src/strix_api/services/live_feed.py` line ~36 docstring). Both `DetectionQualityPanel` today and `DetectionVolumePanel` tomorrow depend on it. Document this in the AI Engine page header subtext.
4. **Inspect chain status states.** `repositories/models.py` `AttackChain.status` is a free-form `Text` defaulting to `"open"`. Today `verdicts_writer.py` only ever writes `"open"` / `"closed"`. The Case Queue introduces `"investigating"` and `"contained"` — these must be additive, not replacing the existing values, to keep the `verdicts_writer` happy. Plan an Alembic migration that adds a `CHECK` constraint for the new vocabulary.
5. **Walk the live-feed wiring.** `LIVE_FEED_CHANNEL = "strix:sse:live-feed"` carries `build_live_feed_event` payloads (alertId, ckcStage, vaeMaliciousProb, gnnNodeRisk, dqnAction, mitreTechniques, etc.). The Case Queue + Hunt page derive much of their data from this same shape — no new WS frames needed.
6. **Capture the existing card pattern.** The `Card` helper inline in `app/(dashboard)/page.tsx` and the `rounded-[48px]` cards on the topology page are the two visual idioms. New pages should pick one — KPI strip + matrices: `rounded-2xl` (dashboard idiom); per-host detail: `rounded-[48px]` (topology idiom).
7. **Log what is already in `model-registry.ts`.** That file holds the source of truth for Throughput + Composite F1 — the dashboard KPI strip should `import { compositeMetrics } from "@/lib/model-registry"` rather than recomputing.

---

## 3. Ordering principle

Removes → Moves → Net-new components → Page role doc.

Removing first opens layout space; moving second produces a working dashboard with the executive view; net-new is then layered without fighting deletions. Backend changes for net-new are gated behind their UI counterparts so a half-shipped phase can't 500 the dashboard.

---

## Phase 1 — Removals

**Goal.** Reduce the dashboard's overload. Each removal is a single import + JSX deletion, no business-logic shift.

**Files edited.**
- `apps/web/app/(dashboard)/page.tsx` — drop imports of `DetectionQualityPanel` and the rail variant of `PredetectionReceipt`; remove the `<aside>` block (lines 108–112) and the `<DetectionQualityPanel/>` row (lines 86–90). Keep the inline-variant receipt (line 95).
- `apps/web/app/(dashboard)/ai-engine/page.tsx` — remove the existing "Live Inference Stream" terminal block (search for `Terminal` icon usage / `liveFeed.events.map`); leave the import-side hook in place because the new `DetectionVolumePanel` needs `useLogStream`.
- `apps/web/app/(dashboard)/profile/page.tsx` — delete the `activityLogEntries` const (lines 28–~70) and its render block; delete the "Assigned Assets" map block (search for `assignedAssets`).
- `apps/web/app/(dashboard)/settings/page.tsx` — delete the "82% Global Accuracy" sub-badge inside the AI Alert Thresholds card (search for `Global Accuracy`).

**Files deleted.**
- `apps/web/components/charts/detection-quality-panel.tsx` (829 lines). Confirm `predetection-receipt.tsx` still exports both `inline` and `rail` variants; we keep the file, only the rail mount point on the dashboard goes.

**Backend.** None.

**Data contract.** Unchanged.

**Integration risks.**
- `DetectionQualityPanel` is the *only* dashboard consumer of AE/VAE WS frames. After deletion the `ws.ts` ring buffers for `ae`/`vae` will be unread on the dashboard route, which is fine (the singleton stays connected via `useLogStreamConnection`). Confirm no pages other than the dashboard `import` it via `grep -rn "detection-quality-panel" apps/web`.
- `predetection-receipt.tsx` `variant="rail"` becomes dead code if no other page uses it. Keep the prop for now — the Attack Analysis page may want it later — but mark it `@deprecated-on-dashboard` in the JSDoc.
- Settings page: the "82% Global Accuracy" string may be referenced in screenshots/tests. `grep -rn "82% Global Accuracy" apps/web` first.

**Testing strategy.**
- `pnpm dev` and visit `/`, `/ai-engine`, `/profile`, `/settings`. Each page must mount with no console errors, no missing-import warnings.
- TypeScript compile (`pnpm tsc --noEmit`) must be clean.
- Visual regression: dashboard should be visibly *shorter*; AI Engine should have an empty card region where Live Inference Stream was — that's the slot Phase 4 fills.

**Order rationale.** Removals first. Adding KPIs back into a dashboard that still hosts the 829-line `DetectionQualityPanel` means juggling row heights twice; remove first so the new KPI strip lands in clean space.

---

## Phase 2 — Frontend moves (relocate existing components, no logic change)

**Goal.** Push existing components to their canonical homes so each page has one role. No new endpoints, no new components — only `import` + JSX shuffles.

**Files edited.**

1. `apps/web/app/(dashboard)/topology/page.tsx`
   - Add a row below the SVG graph: `<SimulationTopologyPanel />` (full-width) and `<GraphEvolution />` (full-width below). Both subscribe to live data, both already have their own loading states. Use the topology page's existing `rounded-[48px]` card chrome to wrap them.
2. `apps/web/app/(dashboard)/ai-engine/page.tsx`
   - Replace the deleted Live Inference Stream block with `<ForensicLogViewer />` (live mode — no `logs` prop). Match the AI Engine's existing card chrome (`rounded-2xl bg-white dark:bg-[var(--strix-bg-card)] border ...`).
3. `apps/web/app/(dashboard)/page.tsx` — build the new **Dashboard KPI strip** as a horizontal flex row of mini-cards above Row 1. Compose existing primitives:
   - `LiveStatusCard` (Critical / Warnings / Updates counts) — extracted from `vigilance-feed/page.tsx` as `apps/web/components/dashboard/live-status-card.tsx` (same component, new home).
   - `SystemIntegrityCard` + `SentinelStatusCard` — extracted from `notifications/page.tsx` as `apps/web/components/dashboard/system-integrity-card.tsx` and `apps/web/components/dashboard/sentinel-status-card.tsx`.
   - `KpiThroughputCard` + `KpiCompositeF1Card` — extracted from `ai-engine/page.tsx` as `apps/web/components/dashboard/kpi-throughput-card.tsx` and `apps/web/components/dashboard/kpi-composite-f1-card.tsx`. Reuse `compositeMetrics()` from `lib/model-registry.ts`.
   - `CompromisedAssetsMini` — extracted from `threat-intel/page.tsx` as `apps/web/components/dashboard/compromised-assets-mini.tsx`. Bound to `useCompromisedAssets(5)` from `lib/api/threat-intel.ts`.
   - `ThreatResolutionHistoryCard` — extracted from `profile/page.tsx` 7-day bar to `apps/web/components/dashboard/threat-resolution-history-card.tsx`. Backed by an existing `/dashboard` query if present; fall back to `useNotifications` aggregated by day.
4. `apps/web/app/(dashboard)/vigilance-feed/page.tsx` — delete the Live Status sidebar block (its source moved).
5. `apps/web/app/(dashboard)/notifications/page.tsx` — delete the System Integrity + Sentinel Status sidebar blocks.
6. `apps/web/app/(dashboard)/threat-intel/page.tsx` — keep the full Compromised Assets table; only the dashboard mini-card is a separate view of the same hook.
7. `apps/web/app/(dashboard)/profile/page.tsx` — delete the 7-day Threat Resolution chart.

**Files created.** Six new files under `apps/web/components/dashboard/` (listed above). Each is ~80–150 lines. They are *not* net-new components functionally — they wrap data hooks already in `lib/api/*` with the existing card visual idiom.

**Backend.** None.

**Data contract.** All hooks already exist. The KPI strip composes:
- `useLiveFeed({ maxEvents: 200 })` for live counts (filter by severity/CKC stage).
- `useQuery({ queryKey: ["monitoring", "models"] })` for system integrity.
- `compositeMetrics()` for F1.
- `useCompromisedAssets(5)`.

**Dashboard KPI strip — visual layout.** A 6-up grid at `min-w-[1280px]`, `grid-cols-6 gap-3`, each card `rounded-2xl px-4 py-3` with a 12 px icon, a 10 px uppercase label, and a 24 px bold value. The Compromised Assets card is a 2-column-spanning mini-list of 3 rows (host, IP, time-since). Threat Resolution History is a 2-column-spanning sparkline (7 vertical bars, teal fill).

**Integration risks.**
- Vigilance Feed and Notifications pages will be visibly *narrower* after losing their summary sidebars — confirm the remaining feed is the full width of the content area and not a half-width card. Use `lg:col-span-12`.
- KPI strip total height: budget 92 px so Row 1 (topology + graph evolution) doesn't push below the fold.
- Composite F1 + Throughput on AI Engine: the KPI cards stay there too (they were a duplicate, not a move). Keep both — Dashboard is "executive snapshot," AI Engine is "engineer detail." Confirm with user; if exclusive, remove from AI Engine.

**Testing strategy.**
- Visit `/` — count six KPI cards, verify each shows non-zero values during a sim run.
- Visit `/topology` — Simulation Topology + Graph Evolution must render below the SVG; no horizontal-scroll regression.
- Visit `/ai-engine` — `<ForensicLogViewer />` ticks once a second; confirm pause button works.
- Run `infra/scripts/inject_traffic.py` (existing smoke harness) and watch the KPI counts rise.

**Order rationale.** Moves come second because the new components (Phase 3+) integrate with KPIs already on the dashboard. Building a Hunt page first, then re-homing the KPI strip, would mean re-grepping every path string twice.

---

## Phase 3 — DetectionVolumePanel (AI Engine)

**Goal.** Replace the deleted `DetectionQualityPanel` with a Kibana-style stacked bar chart — TN (slate/teal) and FP (amber) per ~30 s bucket, 10 min rolling window — that lives on AI Engine, not Dashboard. The component is named after **what** it shows (volume of classifications), not the analytical metric (precision/recall) the old panel emphasised.

**Files created.**
- `apps/web/components/charts/detection-volume-panel.tsx` (~280 lines).

**Files edited.**
- `apps/web/app/(dashboard)/ai-engine/page.tsx` — mount `<DetectionVolumePanel />` in the slot above `<ForensicLogViewer />`. Full-width, `rounded-2xl`.

**Backend.** **No changes required.** `streams.py` already attaches `label: "tp"|"fp"|"tn"|"fn"|"unknown"` on AE/VAE frames via `_attach_label`. The panel reads `label` directly from the WS payload — same field the old `DetectionQualityPanel` used.

**Frontend component shape.**

```ts
DetectionVolumePanelProps {
  windowMs?: number;     // default 600_000 (10 min)
  bucketMs?: number;     // default 30_000  (30 s)
  cap?: number;          // default 4000 events / model
}
```

Internal state:
- `useLogStream(["ae", "vae"])` returns the buffers; the panel keeps its *own* rolling cache `Map<bucketStartMs, {tn: number, fp: number}>` because we only show the *negative* class (`tn`+`fp`). This is the Kibana metaphor: "how loud is the false-alarm baseline." TPs and FNs go to a side legend ("3 TP / 0 FN in window") but are *not* stacked into bars — that keeps the bar metaphor honest (one model, one outcome family).
- `useEffect` with `requestAnimationFrame` clears expired buckets on each tick.
- A model toggle pill (AE | VAE | Both) controls which stream feeds the cache.

**Visual structure.**
- 14 px header: "Detection Volume" + 9 px caption "10 min · 30 s buckets · TN / FP".
- Right of header: three counter pills — `TN 412` (slate), `FP 17` (amber), `TP 3 / FN 0` (small, separate). Each pill animates a single-tick pulse on increment.
- Chart body, 220 px tall: vertical bars, 6 px wide, 2 px gap. X-axis labels every 2 minutes; Y-axis tick at 0/25/50/75/100% of the panel max with right-aligned labels.
- Hover: a vertical guide rail; tooltip shows `bucket [12:34:00–12:34:30] · TN 18 · FP 2 · FP rate 10%`.
- Empty-state: a cyan dotted skeleton frame with "awaiting AE/VAE frames…".
- Legend pills below the chart: `TN slate`, `FP amber`, with hover toggling visibility.

**Data contract.** Pure-frontend derivation from `AePayload.label` / `VaePayload.label`. No new REST.

**Integration risks.**
- The score-inversion gotcha documented in `streams.py _attach_label` is irrelevant here — we use `label` directly, so the inversion is already accounted for.
- `useLogStream` shares its singleton with `ForensicLogViewer`; the cap of 500 frames per type is shared. Confirm 500 × ~1 Hz = 8 min — enough for the 10 min window only because labels arrive batched. If the panel reports gaps, raise the cap with `getClient().setCap(2000)` *before* the first `acquire()` (do it in a top-level `lib/api/ws-bootstrap.ts` so it's not page-order-dependent).

**Testing strategy.**
- Run a sim with `STRIX_STREAM_PER_MODEL=1`. The bar chart must populate within 30 s.
- Toggle AE/VAE/Both — bars must rebuild correctly without flicker.
- Hover on first and last bucket — tooltip must format times relative to local TZ.
- Manual: kill the WS (network panel "offline") and confirm the existing connection-status pill in the topbar reflects it; after 30 s the panel shows "stale" overlay.

**Order rationale.** Net-new but small, single-page, no backend → ship after moves to immediately fill the empty AI Engine card slot from Phase 1.

---

## Phase 4 — Case / Chain Queue (`/cases`) + REST endpoints

**Goal.** A Linear-style operations queue. Operators triage open chains: `new → investigating → contained → closed`.

**Files created (frontend).**
- `apps/web/app/(dashboard)/cases/page.tsx`
- `apps/web/lib/api/cases.ts` (`useCases`, `useUpdateCaseStatus`)
- `apps/web/components/cases/case-row.tsx`
- `apps/web/components/cases/status-pill.tsx`
- `apps/web/components/cases/filters-bar.tsx`

**Files edited (frontend).**
- `apps/web/components/layout/sidebar.tsx` — add `{ label: "CASES", href: "/cases", icon: Inbox, id: "cases" }` between ANALYSIS and THREAT INTEL.

**Files created (backend).**
- `apps/api/src/strix_api/api/routes/cases.py`
- `apps/api/src/strix_api/api/schemas/cases.py`
- `apps/api/src/strix_api/services/cases_service.py`
- Alembic migration `apps/api/alembic/versions/<rev>_attack_chain_status_vocab.py` — extend `attack_chains.status` allowed values.

**Files edited (backend).**
- `apps/api/src/strix_api/main.py` — register `cases.router`.

**Backend endpoints.**

```
GET /api/v1/cases
  query: status?: "new"|"investigating"|"contained"|"closed"  (multi-select via repeat)
         host?: UUID
         min_ckc?: int (0..7)
         since?: ISO-8601
         limit?: int (default 50, max 200)
         cursor?: opaque string (created_at + chain_id)
  response: {
    items: Array<{
      chainId: UUID;
      hostId: UUID;
      hostName: string | null;
      hostIp: string | null;
      openedAt: string;
      lastSeenAt: string;          // last alert occurred_at on this chain
      status: "new"|"investigating"|"contained"|"closed";
      maxCkcStage: number;
      maxCkcStageName: string;
      maxVaeProb: number;
      stepCount: number;
      assignee: { userId: UUID; name: string } | null;
      mitreTechniques: string[];   // unique set across chain alerts
      lastDqnAction: string | null;
    }>;
    nextCursor: string | null;
    counts: { new: number; investigating: number; contained: number; closed: number };
  }

PATCH /api/v1/cases/{chain_id}/status
  body: { status: "new"|"investigating"|"contained"|"closed";
          assigneeUserId?: UUID | null;   // null clears
          note?: string }                  // optional, written to a new
                                           // case_audit_log row
  response: ChainSummary (matches GET item shape)
```

**Data source.** `AttackChain` table (already has `status`, `host_id`, `max_ckc_stage`, `step_count`, `max_vae_prob`, `opened_at`). Join `Host` for name/IP, join `Detection`/`Alert` aggregated for MITRE technique union and last DQN action. New column on `attack_chains`: `assignee_user_id UUID NULL` + new audit table `case_audit_log (id, chain_id, user_id, from_status, to_status, note, at)`.

The chain-state lives in Postgres; `workers/inference.py`'s in-memory tracker doesn't need to expose itself — `verdicts_writer.py` already persists `AttackChain` rows.

**Frontend layout.**
- Sticky top: `<FiltersBar />` — status segmented control with counters (`new 12 · investigating 4 · contained 1 · closed 88`), host search, CKC≥ slider, time-range.
- Body: dense table, 12 px row height, monospace IDs. Columns: status pill (colored left rail strip — slate / amber / teal / muted), chain id (truncated, monospace), host, CKC stage badge (uses `severityFromCkcStage`), MITRE technique chips (max 3 + `+N`), age, assignee avatar, last DQN action badge.
- Row click → `/attack-analysis/<chainId>`.
- Bulk action bar (sticky bottom when selection > 0): "Assign to me" / "Mark contained" / "Close".
- Realtime hint: subscribe to `useLogStream(["raw_log"])`, when a frame's `chainId` matches a row, flash the row left rail for 600 ms — Linear-style "fresh" indicator.

**Visual idiom.** Linear table density. Row height 32 px. No card chrome — table flush to the viewport. Selected row: `bg-strix-cyan/5`.

**Integration risks.**
- `verdicts_writer.py` currently writes `status="open"` and `status="closed"` — if we narrow the vocabulary, those writes will start failing. Solution: in the migration, *map* existing `"open"` → `"new"` (one-time), then alter `verdicts_writer.py` in the SAME PR to write `"new"` on open. Add a backwards-compat alias in `cases_service.py` so old data still queries cleanly.
- The `nextCursor` must be `(opened_at_iso, chain_id)` — opened_at alone is not unique under load.
- `case_audit_log` is new — no Alembic dependency on its absence; ship the migration in the same PR.
- Sidebar: visit `/attack-analysis/latest` still works; the new `CASES` entry must not collide.

**Testing strategy.**
- `curl /api/v1/cases?status=new&limit=10` after a sim run — assert `items[0].chainId` is a valid UUID.
- `curl -X PATCH /api/v1/cases/<id>/status -d '{"status":"investigating"}'` — re-`GET` and confirm the count moved.
- Frontend: filter by status, paginate via cursor, click into Attack Analysis page (existing route).
- Regression: `curl /api/v1/analysis/chains?onlyOpen=true` (the existing chain list endpoint) must still work — `cases` is parallel, not a replacement.

**Order rationale.** Cases is the spine of the operator workflow; everything else (Hunt, Action Log, Playbook) cross-links to it. Build it first among the net-new pages.

---

## Phase 5 — Host Detail (`/host/[id]`) + aggregation endpoint

**Goal.** A CrowdStrike-Falcon-style per-host page. Sticky header (hostname / IP / status / open chains / last seen), tab strip (Overview / Processes / Network / Chains).

**Files created (frontend).**
- `apps/web/app/(dashboard)/host/[id]/page.tsx`
- `apps/web/app/(dashboard)/host/[id]/loading.tsx`
- `apps/web/lib/api/hosts.ts`
- `apps/web/components/host/host-header.tsx`
- `apps/web/components/host/host-overview-tab.tsx`
- `apps/web/components/host/host-processes-tab.tsx`
- `apps/web/components/host/host-network-tab.tsx`
- `apps/web/components/host/host-chains-tab.tsx`

**Files edited (frontend).**
- `apps/web/app/(dashboard)/topology/page.tsx` — Node Details card: change "Investigate in Threat Intel →" to also offer "Open Host →" linking to `/host/<host_id>`.

**Files created (backend).**
- `apps/api/src/strix_api/api/routes/hosts.py`
- `apps/api/src/strix_api/api/schemas/hosts.py`
- `apps/api/src/strix_api/services/host_detail_service.py`

**Endpoint.**

```
GET /api/v1/hosts/{host_id}/detail?since=ISO&limit=200
response: {
  host: { hostId, name, ip, os, agentId, status: "healthy"|"warning"|"compromised",
          firstSeenAt, lastSeenAt };
  summary: { openChains, totalAlerts24h, maxCkcStage24h, lastDqnAction };
  processes: Array<{ pid: int, name: string, parent: string, command: string,
                     user: string, startedAt: string, alertId?: string }>;
  network: Array<{ ts: string, srcIp: string, dstIp: string, dstPort: int,
                    proto: string, action: string, alertId?: string }>;
  commands: Array<{ ts: string, user: string, command: string, alertId?: string }>;
  users: Array<{ user: string, lastLoginAt: string, sessionCount: int }>;
  fileEvents: Array<{ ts: string, path: string, op: "create"|"modify"|"delete",
                       user: string, alertId?: string }>;
  chains: Array<{ chainId, openedAt, status, maxCkcStage, stepCount }>;
}
```

**Data source.** `Alert.raw_jsonb` already carries the Wazuh fields needed (decoder, location, full_log, rule.description). The aggregator extracts processes/network/commands/files by *decoder name* (`auditd`, `syscheck`, `sshd`, etc.) — it's a projection over recent `Alert` rows for the given `host_id`. `chains` joins `AttackChain WHERE host_id = $1`. No new ML inference; everything is read-side.

**Frontend layout.**
- Sticky header (top 0, height 84 px): hostname (28 px bold, mono fallback for IP), large status pill, four tile-style summary metrics (open chains / alerts 24 h / max CKC / last DQN action).
- Tab strip (40 px): Overview · Processes · Network · Chains. Active tab = teal underline.
- Tabs are routed by query param `?tab=processes` so deep-linking works.
- Each tab is a virtualised dense table (use a small custom virtualisation — `react-virtuoso` if already present; otherwise windowed `slice` over 200 items is fine). Row click on `alertId` jumps to `/attack-analysis/<chain_id_for_alert>`.

**Visual idiom.** Topology page's `rounded-[48px]` cards for the header tiles; everything else is dense table. Falcon's grey-on-grey, but with our teal/amber/red accents.

**Integration risks.**
- `Alert.raw_jsonb` shape is decoder-dependent — write the projection as a *defensive* mapper that returns empty arrays per tab when the expected nested keys aren't present. Don't 500 on a malformed alert.
- Host page is the only consumer that needs to *resolve* an alert → chain id. Add a small index check on `alerts(host_id, occurred_at desc)` if not already present.
- Sidebar nav: there's no `HOSTS` top-level — entry to this page is only via topology graph + host links inside Cases / Hunt. That's intentional (it's a drill-down, not a tab).

**Testing strategy.**
- `curl /api/v1/hosts/<uuid>/detail?since=2026-05-04T00:00:00Z` — assert all 7 array keys present (even if empty).
- Click a node on `/topology` → "Open Host" → page renders.
- Tab through all four tabs; switching does not re-fetch (single query keyed on `host_id`+`since`).

**Order rationale.** Cases links *into* host detail (hostName cell click). Build cases first, host second.

---

## Phase 6 — MITRE ATT&CK Coverage Matrix (Threat Intel new tab)

**Goal.** A tactic-column heatmap. 14 tactics × N techniques, color = event count in window, click = drill into Hunt with `technique:Txxxx` pre-filled.

**Files created (frontend).**
- `apps/web/components/threat-intel/mitre-coverage-matrix.tsx` (~320 lines).
- `apps/web/lib/api/mitre.ts`.

**Files edited (frontend).**
- `apps/web/app/(dashboard)/threat-intel/page.tsx` — wrap the existing IOC content in a tab strip; add `<MitreCoverageMatrix />` as a second tab.

**Files created (backend).**
- `apps/api/src/strix_api/api/routes/mitre.py`
- `apps/api/src/strix_api/api/schemas/mitre.py`
- `apps/api/src/strix_api/services/mitre_service.py`
- `apps/api/src/strix_api/data/mitre_catalog.json` — static tactic→technique catalogue (already referenced by FEED_REGISTRY but not present as data; bundle the 14 tactics + their techniques).

**Endpoint.**

```
GET /api/v1/mitre/coverage?since=ISO&until=ISO
response: {
  windowStart: string;
  windowEnd: string;
  tactics: Array<{
    tacticId: "TA0001" | ... ;        // 14 entries
    tacticName: string;
    techniques: Array<{
      techniqueId: "T1059" | ... ;
      techniqueName: string;
      count: number;                  // alerts in window matching this technique
      lastSeen: string | null;        // ISO-8601
      uniqueHosts: number;
    }>
  }>;
}
```

**Data source.** Aggregate `Alert.mitre_techniques` (an `ARRAY(Text)` column) within the window, group by element. Cross-reference with `mitre_catalog.json` to populate names + ensure tactics with zero counts are still rendered (the matrix shape must be stable). 5-minute server-side cache via the existing `services/cache.py`.

**Visual idiom.** 14 columns of stacked technique cells. Each cell is `min-width: 96 px`, height auto; color tinted from `severityColors.benign → severityColors.critical` proportional to `log(count+1)`. Tactic header sticky-top with column total; technique cell shows `T1059 — Command & Scripting Interpreter` (truncated) and the count in the upper right. Hover: a popover shows last-seen timestamp + unique hosts. Click: `router.push('/hunt?q=technique:T1059')`.

The colour ramp uses the platform's teal → amber → red, *not* Mandiant blue: `["rgba(135,237,246,0.06)", "rgba(135,237,246,0.18)", "rgba(234,179,8,0.30)", "rgba(249,115,22,0.45)", "rgba(239,68,68,0.65)"]`.

**Data contract.** REST only — no WS frame needed. Refetch every 60 s via `useQuery(refetchInterval: 60_000)`.

**Integration risks.**
- The static `mitre_catalog.json` has to match what the inference pipeline emits in `mitre_techniques`. If the catalog drifts, "uncatalogued" technique IDs land in a synthetic 15th column "Other". Add a server log line counting unmatched IDs.
- Threat Intel page becomes a tab page; existing deep-links to `/threat-intel?q=foo` must default to the IOC tab. Use `?tab=ioc|mitre` with `ioc` default.

**Testing strategy.**
- `curl /api/v1/mitre/coverage?since=2026-05-04T00:00:00Z` — assert exactly 14 tactics in `tactics`.
- After a Caldera run, click a populated cell → Hunt page loads with the technique pre-filtered.
- Verify the "Other" bucket is empty after a normal run; non-empty buckets indicate catalog drift.

**Order rationale.** Built before Hunt because its drill-down is the *primary* entry path into Hunt.

---

## Phase 7 — Hunt page (`/hunt`) + parsed query endpoint

**Goal.** KQL/Lucene-style query bar with `host: user: technique: time:` operators; sortable result table; saved queries.

**Files created (frontend).**
- `apps/web/app/(dashboard)/hunt/page.tsx`
- `apps/web/components/hunt/query-bar.tsx` (autocomplete pill input)
- `apps/web/components/hunt/results-table.tsx`
- `apps/web/components/hunt/saved-queries.tsx`
- `apps/web/lib/api/hunt.ts`
- `apps/web/lib/hunt-grammar.ts` (parser: tokenise to `Token[]`)

**Files edited (frontend).**
- `apps/web/components/layout/sidebar.tsx` — add `HUNT` (icon: `Search`).

**Files created (backend).**
- `apps/api/src/strix_api/api/routes/hunt.py`
- `apps/api/src/strix_api/api/schemas/hunt.py`
- `apps/api/src/strix_api/services/hunt_service.py` (server-side parser + SQL builder)

**Endpoint.**

```
POST /api/v1/hunt/query
body: {
  q: string;                // raw query, e.g. "host:db-cluster-7 technique:T1059 time:24h"
  limit?: int (default 100, max 1000);
  cursor?: string;
  sort?: "ts_desc" | "ts_asc" | "ckc_desc";
}
response: {
  parsed: { tokens: Array<{ field: "host"|"user"|"technique"|"time"|"text", value: string, op: "eq"|"contains" }>;
            errors: string[] };
  items: Array<{
    alertId: string; ts: string; chainId?: string;
    hostName?: string; hostId?: string;
    user?: string; ruleId?: string; description?: string;
    ckcStage?: number; ckcStageName?: string;
    mitreTechniques: string[];
    vaeMaliciousProb?: number; gnnNodeRisk?: number;
  }>;
  total: number;             // approximate
  nextCursor: string | null;
}

GET    /api/v1/hunt/saved              -> { items: SavedQuery[] }
POST   /api/v1/hunt/saved              body: { name, q }
DELETE /api/v1/hunt/saved/{id}
```

**Data source.** `Alert` table joined with `Host`. The parser maps `host:` → `hosts.name ILIKE`, `technique:` → `mitre_techniques @> ARRAY[$1]`, `time:` → `occurred_at >= now() - interval`, free text → ILIKE on `full_log`. Saved queries: new tiny table `hunt_saved_queries (id, user_id, name, q, created_at)`.

**Frontend layout.**
- Top: query bar (`QueryBar`) — pill rendering of parsed tokens; an unparsed tail rendered as plain text. Autocomplete: when user types `technique:` open a dropdown of techniques from `useMitreCatalog()` (reuses Phase 6 catalog endpoint).
- Right of bar: "Save" button (opens modal), "History" dropdown of last 10 queries (localStorage).
- Below: `<ResultsTable>` virtualised; columns `ts | host | rule | ckc | techniques | scores | actions`. Row expand reveals `description` + `full_log`.
- Right rail: `<SavedQueries>` — clickable list, each entry runs the query.

**Visual idiom.** KQL bar from Microsoft Sentinel — soft inset, mono font 13 px, pill backgrounds mapped to operator color (`host:` teal, `technique:` purple, `time:` amber). Results table density matches Cases page.

**Integration risks.**
- The grammar needs to be permissive — bad input must not 400; instead return `parsed.errors` so the UI can underline the offending token. The server-side parser must mirror the client parser (single source of truth: extract a small TS+Python parallel grammar; document in `docs/hunt-grammar.md`).
- `mitre_techniques @>` requires a GIN index on that column for performance — add migration.
- Saved queries are user-scoped; auth middleware already injects `user_id` via `get_current_user` dep.

**Testing strategy.**
- `curl -XPOST /api/v1/hunt/query -d '{"q":"technique:T1059 time:1h"}'` — assert `parsed.tokens.length == 2`.
- Type a malformed `host:::` — UI underlines, no toast error.
- Save a query, reload the page, run from saved.

**Order rationale.** Depends on the MITRE catalog endpoint (Phase 6) for autocomplete.

---

## Phase 8 — Response Action Log (`/actions`) + actions endpoints

**Goal.** A vertical timeline of DQN-proposed and operator-approved actions, with rollback. Each event shows its provenance (DQN q-values, requires-approval gate, applied-by user) and whether a rollback exists.

**Files created (frontend).**
- `apps/web/app/(dashboard)/actions/page.tsx`
- `apps/web/components/actions/action-timeline.tsx`
- `apps/web/components/actions/action-row.tsx`
- `apps/web/components/actions/rollback-confirm-modal.tsx`
- `apps/web/lib/api/actions.ts`

**Files edited (frontend).**
- `apps/web/app/(dashboard)/notifications/page.tsx` — add a tab strip; "Notifications" + "Action Log" tabs. Action Log tab embeds `<ActionTimeline />` (or stays on `/actions` and the notifications tab links there — pick the deep-link version: `/actions` is the canonical URL, the notifications tab is a shortcut).

**Files created (backend).**
- `apps/api/src/strix_api/api/routes/actions.py`
- `apps/api/src/strix_api/api/schemas/actions.py`
- `apps/api/src/strix_api/services/actions_service.py`

**Endpoints.**

```
GET /api/v1/actions?status=proposed|approved|declined|rolled_back&since=ISO&limit=50&cursor=...
response: { items: ActionItem[]; nextCursor: string | null; counts: {...} }

ActionItem {
  actionId: UUID; chainId: UUID; hostId: UUID; hostName: string;
  decidedAt: string; appliedAt: string | null;
  action: number; actionName: string;          // ISOLATE_HOST | BLOCK_USER_IP | ESCALATE | ...
  qValues: number[];
  ckcStageAtDecision: number;
  requiresApproval: boolean;
  status: "proposed" | "approved" | "declined" | "rolled_back" | "auto_applied";
  appliedBy: { userId: UUID; name: string } | null;
  rollback: { id: UUID; rolledBackAt: string; rolledBackBy: { userId, name }; reason: string } | null;
}

POST /api/v1/actions/{id}/approve    body: { note?: string }
POST /api/v1/actions/{id}/decline    body: { reason: string }
POST /api/v1/actions/{id}/rollback   body: { reason: string }
```

**Data source.** `DqnActionRow` table already has `applied`/`applied_at`/`applied_by`/`rejected_at`/`rejected_by`/`q_values`. New table: `dqn_action_rollbacks (id, action_id, rolled_back_at, rolled_back_by, reason)`. Status is derived: `applied=true && rolled_back is null → approved`, etc.

**Frontend layout.**
- Filter strip (status segmented control + time range + host).
- Timeline: vertical, 32 px gutter, each row = 84 px tall card. Left side: time + status icon (proposed = hourglass amber, approved = check teal, declined = X muted, rolled back = undo red). Body: action name (`ISOLATE_HOST`), host chip, CKC stage badge, q-value sparkline (5 thin bars showing the q-value for each action with the chosen one highlighted). Right side: contextual buttons.
- Rollback button: opens `<RollbackConfirmModal>` requiring the operator to type the host name to confirm (destructive-action hygiene).
- Empty-state: "No actions in window. DQN intervenes only when CKC ≥ X — see Settings."

**Visual idiom.** Vertical timeline with 1 px left gutter rule and inline status dots. Confirm modal is dark, red-tinted, `<input>` validates against `host.name`.

**Integration risks.**
- "Rollback" is a *recorded* operator action — it does NOT undo the original side effect (no `wazuh_bridge` reverse-call yet). Document this in the modal: "Rolling back marks the action as reverted in the audit log; you must manually undo any host-level change (un-isolate, un-block IP) via the Wazuh console."
- The `/actions` REST aggregates the DQN action stream — make sure the polling is 10 s or rely on `useLiveFeed` for incremental updates; full re-fetch on every WS frame would thrash.
- Add a server-side guard: `decline` is only valid when `requires_approval=true`; `rollback` only when `applied=true`.

**Testing strategy.**
- Trigger a sim that crosses the DQN-gate threshold; confirm a `proposed` row appears.
- Click Approve → row moves to "approved", `appliedBy.name` is your username.
- Click Rollback on an approved row → confirm modal blocks until host name typed; on submit, `rollback` field populated.

**Order rationale.** Builds on Cases (operator workflow) and Hunt (links from a Hunt result row to its action). Ship after both.

---

## Phase 9 — User Risk panel (Threat Intel card) + UEBA endpoint

**Goal.** A ranked list of top-risky users derived from GNN USER edges.

**Files created (frontend).**
- `apps/web/components/threat-intel/user-risk-panel.tsx`
- `apps/web/lib/api/ueba.ts`

**Files edited (frontend).**
- `apps/web/app/(dashboard)/threat-intel/page.tsx` — add the panel as a card on the IOC tab.

**Files created (backend).**
- `apps/api/src/strix_api/api/routes/ueba.py`
- `apps/api/src/strix_api/api/schemas/ueba.py`
- `apps/api/src/strix_api/services/ueba_service.py`

**Endpoint.**

```
GET /api/v1/ueba/users?limit=20&since=ISO
response: {
  items: Array<{
    user: string;                 // Wazuh user / process owner
    riskScore: number;            // 0..1, derived from GNN + chain co-occurrence
    hostsTouched: number;
    lastSeen: string;
    chainCount: number;           // open + closed in window
    topChains: Array<{ chainId, maxCkcStage }>;
  }>;
}
```

**Data source.** Read recent `gnn_graph_snapshots.nodes` JSONB, filter where `node.kind == "USER"`, take `node.risk` per user. Aggregate `Alert.raw_jsonb -> 'data' -> 'srcuser'` (or decoder-specific user field) within window for `chainCount` and `hostsTouched`. 5-min cache.

**Visual idiom.** Ranked list, 8 rows, each row: 3-letter user avatar (initials), username (mono), risk bar (0..1 with `severityFromRisk`), small chip "5 chains · 3 hosts". Click row → `/hunt?q=user:<name>`.

**Integration risks.**
- USER edges may be sparse — empty state required. The panel must collapse to a 1-line "no user-risk signals in window" rather than render 8 empty rows.
- Decoder-specific user field varies (`auditd` → `data.audit.uid`, `sshd` → `data.user`); centralise the projection in `ueba_service`.

**Testing strategy.**
- After a Caldera run that uses a known user, the user appears in top 20.
- Click user → Hunt loads filtered.

**Order rationale.** Independent — can ship any time after Hunt. Place here because it shares Threat Intel real estate with the MITRE matrix.

---

## Phase 10 — Playbook / Runbook viewer (Attack Analysis right rail)

**Goal.** Per CKC stage / technique, surface a curated response runbook that the operator can step through; offers "override DQN" buttons that pipe into the Action Log endpoints from Phase 8.

**Files created (frontend).**
- `apps/web/components/playbooks/playbook-viewer.tsx`
- `apps/web/components/playbooks/playbook-step.tsx`
- `apps/web/lib/api/playbooks.ts`

**Files edited (frontend).**
- `apps/web/app/(dashboard)/attack-analysis/[id]/page.tsx` — add a right rail (`w-[340px] sticky top-4`) hosting `<PlaybookViewer chainId={...} />`.

**Files created (backend).**
- `apps/api/src/strix_api/api/routes/playbooks.py`
- `apps/api/src/strix_api/api/schemas/playbooks.py`
- `apps/api/src/strix_api/data/playbooks/*.json` — one JSON per (stage, technique) combo. Bundled, not user-editable in this phase.

**Endpoint.**

```
GET /api/v1/playbooks?stage=int&technique=Txxxx
response: {
  matched: Array<{
    playbookId: string;
    title: string;
    description: string;
    severity: "low"|"medium"|"high"|"critical";
    steps: Array<{
      stepId: string; title: string; rationale: string;
      kind: "manual" | "dqn_override" | "isolate_host" | "block_ip";
      payload?: { action: string; chainIdRequired: boolean };
    }>
  }>;
  fallback: { title: "Generic <stage> playbook"; steps: [...] };
}
```

**Data source.** Static JSON library at `apps/api/src/strix_api/data/playbooks/`. Loaded once at boot into memory.

**Visual idiom.** Collapsible accordion sections per playbook; each step is a card with: step title, 2-line rationale, action button (when `kind != "manual"`). Action button calls the relevant Phase-8 endpoint (`POST /api/v1/actions/<id>/approve`) or, for proactive overrides, a new endpoint shape `POST /api/v1/actions/manual` with `{ chainId, hostId, action: "ISOLATE_HOST", reason }`. Add this to Phase 8's actions router as part of this phase.

**Integration risks.**
- Manual action endpoint creates a `DqnActionRow` with synthetic `q_values=[]` and `requires_approval=false`. The Action Log timeline must handle empty q-values gracefully (Phase 8 spec: q-value sparkline becomes an em-dash).
- Right rail width on the Attack Analysis page may collide with existing layout. Confirm by reading the existing page; budget 340 px.

**Testing strategy.**
- Open a chain at stage 5 with technique T1059 — confirm a non-fallback playbook renders.
- Click "Isolate host" on a step — appears in `/actions` as a new `auto_applied` row, linkable from the timeline.

**Order rationale.** Last because it depends on the Action Log endpoints from Phase 8 and on the chain detail page (already exists).

---

## Post-implementation

**Verification matrix.** With a live sim running (`infra/scripts/inject_traffic.py` + `STRIX_STREAM_PER_MODEL=1`):
1. Each route mounts: `/`, `/cases`, `/host/<id>`, `/hunt`, `/actions`, `/threat-intel`, `/topology`, `/ai-engine`, `/vigilance-feed`, `/notifications`, `/attack-analysis/<id>`, `/profile`, `/settings`.
2. WebSocket singleton stays at one connection (DevTools → Network → WS → exactly 1 entry to `/api/v1/logs/stream`).
3. KPI strip values increment over a 5-minute window.
4. Cases queue triage cycle: new → investigating → contained → closed.
5. Hunt round-trip with all four operators.
6. MITRE matrix populates ≥ 1 cell per active tactic.
7. Action approval + rollback flow.

**Cleanup.**
- `grep -rn "detection-quality-panel" apps/` — must be empty.
- `grep -rn "82% Global Accuracy" apps/web` — must be empty.
- `grep -rn "activityLogEntries" apps/web` — must be empty.
- Remove any `// TODO: legacy` left during the move.
- Update `docs/CLAUDE.md` (if present) with the new page roles.
- Add `docs/hunt-grammar.md` documenting the parser.

**Performance budget.** Dashboard mount-to-interactive < 800 ms on a warm cache. Cases endpoint p95 < 250 ms on 10 k chain rows. Hunt query p95 < 600 ms with the GIN index on `mitre_techniques`.

**Rollback strategy per phase.** Phases 1–2 are pure frontend; revert by `git revert`. Phases 3–10 each ship with a feature flag (`STRIX_FEATURE_<NAME>=1` in env, gating route inclusion in `main.py`); turn off the env var to roll back without re-deploying.

---

## Critical files referenced

- `apps/api/src/strix_api/api/routes/streams.py`
- `apps/api/src/strix_api/repositories/models.py`
- `apps/api/src/strix_api/main.py`
- `apps/web/app/(dashboard)/page.tsx`
- `apps/web/lib/api/ws.ts`
