# Runbook — `StrixStreamBacklog`

**Symptom:** `strix_stream_depth{stream}` > 10 000 for ≥ 30 s.

## Triage

1. Identify which stream is backed up:
   ```
   redis-cli XINFO STREAM strix:alerts:raw
   redis-cli XINFO STREAM strix:features:0
   redis-cli XINFO STREAM strix:verdicts
   ```
2. Check consumer-group lag:
   ```
   redis-cli XINFO CONSUMERS strix:features:0 strix-inference-0
   ```

## Common causes + fixes

| Cause | Fix |
|---|---|
| Inference worker dead | `docker compose -f infra/compose.api.yml --profile workers ps` → restart `inference_shard0` |
| Model load failed at boot | Check worker logs for `model_registry_loaded missing=…`; ensure `apps/models/*.pkl` present (P0-7) |
| SecBERT thread pool exhausted | Bump `INFERENCE_AE_BATCH_MAX` / `INFERENCE_AE_BATCH_WAIT_MS` in `.env`; restart worker |
| Postgres lock storm in verdicts-writer | See [postgres-slow.md](postgres-slow.md) |
| Genuine traffic spike | Add a shard: bump `INFERENCE_NUM_SHARDS` and run more `inference_shardN` containers |

## Backpressure semantics (§7.6)

`strix:alerts:raw` is `MAXLEN ~ 100 000`. Beyond that, **oldest entries are
dropped** — we prefer losing old alerts over OOM. If you see drops, you
have a sustained capacity problem; scale shards.

## Verify recovery

```
watch -n 5 'redis-cli XLEN strix:alerts:raw strix:features:0 strix:verdicts'
```

Depth should monotonically decrease toward 0.
