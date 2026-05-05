# UI reorganization — deferred follow-ups

These are the design-pivot items I noted in code comments during phases 4–9.
None block the shipped UI; each unlocks a richer view when the corresponding
inference / writer change lands. Listed in order of (value, safety): do the
smaller, lower-risk ones first.

Items 1–5 in this doc were closed as part of the post-implementation pass
(2026-05-04): migrations applied, hunt-grammar.md written, LiveFeedEvent
extended with `chainId` and Cases row-flash re-enabled.

---

## A. Persist structured `raw_jsonb` in `verdicts_writer`

**Currently:** [`workers/verdicts_writer.py`](../../apps/api/src/strix_api/workers/verdicts_writer.py)
writes `raw_jsonb={}` (line ~224). Downstream readers — Host Detail, Hunt's
`user:` filter — fall back to substring matches on `full_log`.

**Unblocks:**
- [`Host Detail`](../../apps/web/app/(dashboard)/host/[id]/page.tsx) per-tab
  structured projections (process tree, network connections, file events)
  instead of the current alert-list-bucketed-by-decoder view
- [`Hunt`](../../apps/web/services/hunt_service.py) `user:` predicate switches
  from `full_log ILIKE` → JSONB path expression (`raw_jsonb -> 'data' -> 'srcuser'`)
  for index-driven matching. **No grammar change** — same `Token[]`, different
  SQL builder branch.

**Surface area:**
- One file: `verdicts_writer.py:_alert_row()` — the assignment around line 224
- One field on the wire envelope: `verdict["rawJsonb"]` (or whatever the
  upstream worker projects)

**Risk:** writes to a hot path. Wrong projection bloats `raw_jsonb` and slows
ingestion. Pick a small allowlist of fields per decoder family up front
(suggested below) rather than dumping the whole Wazuh payload.

**Suggested decoder allowlists (Phase 1 cut):**

| Decoder | Keys to project |
|---|---|
| `auditd` | `data.audit.uid`, `data.audit.auid`, `data.audit.exe`, `data.audit.cmd` |
| `web-accesslog` | `data.srcip`, `data.url`, `data.status_code` |
| `sshd` (location: auth.log) | `data.srcuser`, `data.srcip`, `data.srcport` |
| `syscheck*` | `syscheck.path`, `syscheck.event`, `syscheck.md5_after` |

Anything else: write `{}` so blob size stays bounded.

**Migration:** none — column is already JSONB. Add a GIN index *only* if Hunt's
`user:` predicate becomes a hot query: `CREATE INDEX … ON alerts USING GIN
(raw_jsonb jsonb_path_ops)`.

---

## B. Add USER nodes to GNN snapshot

**Currently:** [`workers/inference.py:_persist_snapshot`](../../apps/api/src/strix_api/workers/inference.py)
serialises nodes as `{alertId, risk}` only — alert-keyed, no entity discriminator.

**Unblocks:**
- [`UebaService`](../../apps/api/src/strix_api/services/ueba_service.py) switches
  from regex on `full_log` → graph-derived per-user risk. The response carries
  a `source` field for provenance — flip from `"alerts.full_log"` to
  `"gnn.user_nodes"` and the UI doesn't need to change.

**Surface area:**
- `_persist_snapshot()` payload schema — add a `kind: "ALERT" | "USER" | "HOST"`
  discriminator on each node, plus per-kind fields (USER nodes carry the
  username string)
- The graph-builder upstream of the snapshot serialiser must know how to
  emit USER node objects (likely already does — check `core/feature_engineer.py`
  graph construction)
- `UebaService.top_users()` adds a path that reads recent
  `gnn_graph_snapshots.nodes[*]` filtered by `kind == "USER"` instead of
  scanning alerts; gates on whether any recent snapshot has USER nodes

**Risk:** the GNN snapshot is large (nodes + edges as JSONB). Adding a `kind`
field on every node grows blob size linearly. Mitigation: emit `{kind, ref}`
where `ref` is a compact int — most nodes are alerts, only USERs need the
extra field. Or: store users in a side array on the snapshot row.

**Migration:** none required if the new shape stays in JSONB; optional
`gin (jsonb_path_ops)` index on `nodes` if UEBA queries become hot.

---

## C. `chainId` on `LiveFeedEvent` for Cases row flash

**Status: shipped 2026-05-04** during the post-implementation pass.

`build_live_feed_event()` was already publishing `chainId`; only the frontend
TypeScript type needed updating + the Cases page flash logic re-enabled.

---

## D. Documentation updates

- ✅ `docs/web/hunt-grammar.md` — written (post-impl pass).
- ⏳ `docs/CLAUDE.md` (if your repo carries one) — mention the new page roles
  per the [reorg plan §Page role changes](./UI_REORGANIZATION_PLAN.md).
  Skipped here because there's no existing CLAUDE.md to extend; create one
  only if the agent context starts to grow stale.

---

## E. Performance budget validation

Plan targeted (`§Post-implementation > Performance budget`):

| Surface | Target |
|---|---|
| Dashboard mount-to-interactive (warm cache) | < 800 ms |
| `GET /api/v1/cases` (10 k chains) | p95 < 250 ms |
| `POST /api/v1/hunt/query` | p95 < 600 ms (with the GIN index applied in 0007) |

Not measured. To measure, run `infra/scripts/inject_traffic.py` to seed
~10 k chains, then `hey` / `k6` against the three endpoints. The MITRE GIN
index that ships in 0007 also serves Hunt — make sure `EXPLAIN` confirms
`Bitmap Heap Scan on alerts using ix_alerts_mitre_techniques_gin` for any
`technique:` query before signing off.

---

## F. Feature-flag rollback (intentionally deferred)

Plan §Rollback strategy called for `STRIX_FEATURE_<NAME>=1` env gates per
phase. I shipped phases inline. Each phase's commits are clean enough for
`git revert` without flag plumbing; add flags only if you have a staged
rollout reason. The router-registration sites in `main.py` are the natural
gating points if you want to add this later.
