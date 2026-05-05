# Hunt query grammar

The `/hunt` page accepts a KQL/Lucene-lite query string. Parsing is **permissive**:
malformed input never returns 4xx — failed tokens are dropped from the executable
set and listed in `parsed.errors` so the UI can underline the offending span and
still execute the rest.

## Authoritative implementations

The grammar is implemented twice. The two parsers MUST produce the same `Token[]`
shape for a given query; keep them in lock-step when grammar changes.

| Side | File | Notes |
|---|---|---|
| **Server** (authoritative) | [`apps/api/src/strix_api/services/hunt_service.py`](../../apps/api/src/strix_api/services/hunt_service.py) → `parse_query()` | Drives SQL building. The route's empty-DB fallback also calls this so the UI underline still works offline. |
| **Client** (mirror) | [`apps/web/lib/hunt-grammar.ts`](../../apps/web/lib/hunt-grammar.ts) → `parseHunt()` | Drives pill rendering + autocomplete. Returns the same Token shape plus accurate `(start, end)` source spans for the underline UI. |

## Token shape

```ts
type HuntField = "host" | "user" | "technique" | "time" | "text";
type HuntOp    = "eq" | "contains";

interface HuntToken {
  field: HuntField;
  op:    HuntOp;
  value: string;
  // client-side only:
  start: number;  // byte offset in the source query
  end:   number;
}
```

## Operators

| Field | Value form | Example | Backend predicate |
|---|---|---|---|
| `host:` | name substring | `host:db-cluster-7` | `hosts.agent_name ILIKE '%…%'` |
| `user:` | substring | `user:srsysadmin` | `alerts.full_log ILIKE '%…%'` *(see footnote 1)* |
| `technique:` | `Txxxx` or `Txxxx.yyy` | `technique:T1059` | `alerts.mitre_techniques @> ARRAY['…']` (GIN-indexed) |
| `time:` | `Nh \| Nm \| Nd \| Ns \| ISO-8601` | `time:24h`, `time:30m`, `time:2026-05-04T12:00:00Z` | `alerts.occurred_at >= …` |
| (free text) | anything else | `failed login` | `alerts.full_log ILIKE '%…%'` (one ILIKE per chunk) |

Free-text chunks between `field:value` matches are **coalesced** into one
`text` token at the end so the SQL builder doesn't have to OR multiple ILIKEs.

## Quoting

A value can be wrapped in double quotes to allow whitespace:

```
host:"db cluster 7"  technique:T1059  time:24h
```

Bare values match `[^\s"]+`. There's no escape syntax for double quotes inside
quoted values — that's a known limitation.

## Validation rules

Bad-but-recoverable input is reported in `parsed.errors`. Examples:

| Input | Behaviour |
|---|---|
| `technique:bogus` | dropped; error: `'technique:bogus' doesn't look like a MITRE id (Txxxx[.yyy])` |
| `time:tomorrow` | dropped; error: `'time:tomorrow' not understood (try 1h, 30m, 24h, 7d, or ISO)` |
| `host:` (empty value) | dropped; error: `empty value for 'host:'` |

A query with only invalid tokens still returns 200 with `items: []` and the
errors populated — by design.

## Defaults

- **Time horizon** when no `time:` token: last 24 hours. The window floor is
  cut by the most-recent `time:` token if multiple are supplied (last wins).
- **Sort:** `ts_desc` by default. Other supported: `ts_asc`, `ckc_desc`.
- **Limit:** 100 default, 1000 max per request.
- **Cursor:** opaque base64 of `(occurred_at_iso, alert_id)` — use the
  `nextCursor` from a prior response for pagination.

## Sub-technique handling

The API stores both parents and children verbatim in `alerts.mitre_techniques`.
A query for `technique:T1059` matches alerts that carry `T1059`, **not**
`T1059.004`. If you need to roll up sub-techniques, query each one explicitly
or expand to a parent search with a free-text match on the technique name.

The MITRE matrix on the Threat Intel tab does roll children up to the parent
column for visual coverage; that's a display-time choice that doesn't affect
Hunt's `@>` predicate.

## Saved queries

`POST /hunt/saved` upserts by `(user_id, name)`. The unique constraint lives in
`hunt_saved_queries` (migration 0007). Saving with the same name overwrites
the prior `q` value silently.

`DELETE /hunt/saved/{id}` returns 404 if the saved row is owned by a different
user — even when the row exists, callers can't delete other users' queries.

## Adding a new operator

1. Update `_TOKEN_RE` in `hunt_service.py` and the mirror `TOKEN_RE` in
   `hunt-grammar.ts`. Pattern: `(?P<field>your_field|...):...`
2. Add the `HuntField` literal in **both** `schemas/hunt.py` and the TS
   `lib/api/hunt.ts`.
3. Validate the value in `parse_query` (Python) and `parseHunt` (TS) — return
   the token *or* push to `errors`.
4. Add the SQL predicate branch in `HuntService.query()`.
5. Add the pill colour in `query-bar.tsx` `FIELD_TINT`.
6. Update this doc.

The two parsers diverging is the primary failure mode — there's no shared
schema yet that both sides import. A regression test that asserts identical
Token output for the same input across both parsers is the right next move
when the grammar grows beyond five operators.

## Footnotes

1. The `user:` predicate currently uses `full_log ILIKE` because
   `alerts.raw_jsonb` is written as `{}` by `verdicts_writer.py`. When the
   writer starts persisting decoder-specific user fields under a JSONB path
   (e.g. `raw_jsonb -> 'data' -> 'srcuser'`), the predicate switches to a
   JSONB path expression for index-driven matching. The grammar / token
   shape doesn't change.
