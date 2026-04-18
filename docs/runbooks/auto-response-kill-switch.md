# Runbook — Auto-response kill switch

The kill switch (P8-8) is the single piece of operational infrastructure
that controls automatic ISOLATE/BLOCK execution. Per §12 Q3 the
`AUTH_AUTO_RESPONSE_ENABLED` flag stays OFF in 1.0 — but if a future
release flips it on, this is your panic button.

## State

Backed by Redis key `strix:auto_response:kill_switch` (`"on" | "off"`).
**Default = "on" (engaged)** — every fresh deploy is safe by default.

## Inspect

```bash
curl -H "Authorization: Bearer $JWT" http://localhost:8000/api/v1/admin/kill-switch
# { "engaged": true, "setBy": "<uuid>", "setAt": "..." }

# Or directly:
redis-cli get strix:auto_response:kill_switch
```

## Engage (panic — stop all auto-applies)

```bash
curl -XPOST http://localhost:8000/api/v1/admin/kill-switch \
  -H "Authorization: Bearer $JWT" \
  -H "X-CSRF-Token: $CSRF" \
  -H "Content-Type: application/json" \
  -d '{"engaged": true}'
```

Effect: every subsequent `dqn_actions` row with `action ≥ ESCALATE` is
written with `applied = false, requires_approval = true`. Operators must
hit the Apply button manually.

## Disengage (turn auto-apply back on)

```bash
curl -XPOST http://localhost:8000/api/v1/admin/kill-switch \
  -H "Authorization: Bearer $JWT" \
  -H "X-CSRF-Token: $CSRF" \
  -H "Content-Type: application/json" \
  -d '{"engaged": false}'
```

Auto-apply only fires when ALL of the following are true:
1. `AUTH_AUTO_RESPONSE_ENABLED=true` (env, restart-required)
2. Kill switch is disengaged
3. Host is in `auto_response_allowlist` with the matching action allowed
4. Action is ISOLATE_HOST or BLOCK_USER_IP (lower-severity actions are
   always auto-applied, even with the switch engaged)

## Audit

Every attempted auto-apply (whether it actually fired or not) writes a
row to `auto_response_audit`. Use this to evaluate shadow-mode results
before flipping the global flag:

```sql
SELECT
  date_trunc('day', decided_at) AS day,
  count(*)                        AS attempts,
  sum(CASE WHEN actually_applied THEN 1 ELSE 0 END) AS applied,
  sum(CASE WHEN kill_switch_active THEN 1 ELSE 0 END) AS killswitch_blocked
FROM auto_response_audit
WHERE decided_at > now() - interval '7 days'
GROUP BY 1 ORDER BY 1 DESC;
```

## Pre-flight before flipping `AUTH_AUTO_RESPONSE_ENABLED=true`

Per §10 P8-8 the requirements are:
- ≥ N weeks of shadow-mode precision exceeding agreed threshold
- Pentest sign-off
- Per-host allow-list excluding production-critical assets
- Kill switch documented + tested (this runbook)

If you're not sure all four are true, **leave the flag off**.
