# Runbook — Postgres slow

Triggered manually when `verdicts_writer` reports `db_flush_failed` or
when `http_request_duration_seconds` for `/dashboard/*` shoots up.

## Triage

```sql
-- Active queries longer than 5s
SELECT pid, now() - query_start AS dur, state, query
FROM pg_stat_activity
WHERE state = 'active' AND now() - query_start > interval '5 seconds'
ORDER BY dur DESC;

-- Continuous-aggregate refresh status (Phase 4 CAGGs)
SELECT view_name, last_run_started_at, last_run_status, total_failures
FROM timescaledb_information.continuous_aggregates;
```

## Common causes

| Cause | Fix |
|---|---|
| Hypertable chunk count exploding | `SELECT show_chunks('alerts');` — drop oldest if past retention |
| CAGG refresh starving live queries | Lower `schedule_interval` priority; or move heavy CAGGs to a refresh window |
| Verdicts-writer batch too large | Lower `_FLUSH_MAX_ROWS` in `workers/verdicts_writer.py`; the default 500 may be high under heavy load |
| Connection pool exhausted | `DB_POOL_SIZE` × replica count > Postgres `max_connections`? Check `pg_stat_activity` count. |

## Emergency throttle

If the writer is the bottleneck, pause it briefly so the inference path
can keep emitting verdicts to Redis (capped at 100 k by MAXLEN):
```
docker compose -f infra/compose.api.yml stop verdicts_writer
# … fix the DB issue …
docker compose -f infra/compose.api.yml start verdicts_writer
```
Verdicts won't be lost — they sit in the `strix:verdicts` stream and
the writer's consumer group resumes from the right offset.
