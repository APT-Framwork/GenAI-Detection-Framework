# Runbook — Inference worker OOM

The worker holds AE + VAE + Transformer + GNN + DQN weights + SecBERT
in memory. Rough budget per worker: **~600 MB resident, peaks to ~1.2 GB
under burst batches.** A `Killed` exit from the container is OOM.

## Triage

```
docker logs strix_inference_shard0 | tail -100
docker inspect strix_inference_shard0 --format '{{ .State.OOMKilled }}'
```

## Common causes

| Cause | Fix |
|---|---|
| GNN window too large | The 60-min window can grow unbounded under burst. Check `gnn_snapshot_refreshed nodes=N` in logs; if N > 10 000 reduce window with `GNN_WINDOW_MINUTES`. |
| Transformer batch padding too aggressive | Lower `INFERENCE_TRANSFORMER_BATCH_MAX` from 8 to 4 |
| SecBERT LRU never evicting | Default cap is 10 000; if heap grows, check `_LRU_MAX` in `preprocessing_pipeline.py` |
| Memory leak under torch.inference_mode | Restart worker; if recurring within 24 h, capture with `tracemalloc.start()` + `tracemalloc.snapshot()` |

## Recovery

Workers are stateless apart from their per-shard Redis cache. Just restart:
```
docker compose -f infra/compose.api.yml --profile workers restart inference_shard0
```

The worker's consumer-group offset is preserved in Redis; in-flight
messages get re-delivered after the PEL idle timeout (5 s default).
