# Runbook — `StrixManyChainsOpen`

**Symptom:** `strix_session_active_count > 100` for ≥ 5 m.

## Quick diagnosis

```sql
SELECT host_id, count(*)
FROM attack_chains
WHERE status = 'open'
GROUP BY 1 ORDER BY 2 DESC LIMIT 20;
```

## Common causes

| Cause | Action |
|---|---|
| Real coordinated attack | SOC review. The DQN should be escalating — check `dqn_actions` for ESCALATE / ISOLATE / BLOCK rows. |
| `CHAIN_OPEN_*` thresholds too sensitive | Bump `CHAIN_OPEN_VAE_THRESHOLD` / `CHAIN_OPEN_AE_THRESHOLD` in `core/constants.py`, restart workers. |
| Idle-timeout never firing (clock skew) | Verify `CHAIN_IDLE_TIMEOUT_MINUTES = 120` and Postgres clock matches workers. |
| Test traffic misclassified | Whitelist the agent or use `AUTO_RESPONSE_ENABLED=false` (it is — §12 Q3). |

## Force-close stuck chains

```sql
UPDATE attack_chains SET status = 'closed',
       closed_at = now(),
       close_reason = 'IDLE_TIMEOUT'
WHERE status = 'open' AND first_malicious_at < now() - interval '3 hours';
```

Then drop the corresponding Redis sessions:
```
redis-cli --scan --pattern 'session:*' | xargs redis-cli del
```
(Workers will lazily re-open chains on the next alert per the chain rule.)
