# Runbook — `StrixInferenceP99High`

**Symptom:** `histogram_quantile(0.99, strix_inference_duration_seconds_bucket{model})`
\> 500 ms for ≥ 5 m.

## Triage

```
# Which model is the slow one?
strix_inference_duration_seconds_bucket{model}     # check the high label

# Batch size — too small means overhead dominates
strix_inference_batch_size{model}

# AE/VAE go via the SecBERT cache; check hit rate
strix_cache_hits_total{cache="secbert"}
strix_cache_misses_total{cache="secbert"}
```

## Common causes + fixes

| Cause | Fix |
|---|---|
| SecBERT cache cold (just-restarted worker) | Wait ~5 min — LRU fills naturally as alerts repeat |
| Transformer sequence too long | Inspect `session:{agent_id}:latents` length (`LLEN`); should be ≤ 50 |
| GNN graph too dense | Inspect snapshot edge count in inference logs (`gnn_snapshot_refreshed`) |
| Torch threads competing with event loop | `torch.set_num_threads(cpu_count())` is set at boot — verify in logs |
| Single shard handling all agents | Scale: bump `INFERENCE_NUM_SHARDS` + add containers |

## Latency budget (§7.1)

| Stage | p50 | p99 |
|---|:-:|:-:|
| Normalizer (SecBERT etc.) | 35 ms | 120 ms |
| Inference (4 models + DQN) | 40 ms | 150 ms |
| Verdicts writer (Pg INSERT) | 8 ms | 40 ms |
| **End-to-end** | **~100 ms** | **~400 ms** |

If a single model is consistently above p99=150ms, the rest of the budget
slides. Profile with `py-spy`:
```
py-spy record -d 30 -o flame.svg --pid $(pgrep -f workers.inference)
```
