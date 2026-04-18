# STRIX runbooks

One runbook per Prometheus alert in [`infra/prometheus_alerts.yml`](../../infra/prometheus_alerts.yml).
On-call uses these to triage; every alert annotation links to the matching file.

| Alert | Runbook |
|---|---|
| `StrixStreamBacklog` | [redis-backlog.md](redis-backlog.md) |
| `StrixInferenceP99High` | [inference-slow.md](inference-slow.md) |
| `StrixUpstreamErrors` | [external-api-down.md](external-api-down.md) |
| `StrixModelDrift` | [model-drift.md](model-drift.md) |
| `StrixManyChainsOpen` | [many-active-chains.md](many-active-chains.md) |

Other runbooks (no specific alert — invoked manually):

- [postgres-slow.md](postgres-slow.md)
- [inference-worker-oom.md](inference-worker-oom.md)
- [model-loaded-wrong-weights.md](model-loaded-wrong-weights.md)
- [secret-rotation.md](secret-rotation.md)
- [auto-response-kill-switch.md](auto-response-kill-switch.md)
