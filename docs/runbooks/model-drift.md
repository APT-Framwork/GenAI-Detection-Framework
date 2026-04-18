# Runbook — `StrixModelDrift`

**Symptom:** `strix_score_distribution_kl_divergence{model} > 0.2` for ≥ 30 m.

## What it means

The live distribution of one model's output (AE anomaly, VAE prob, GNN
node risk, or Transformer confidence) has drifted from the training-time
baseline shipped in `apps/models/drift_baseline.json`. Either:

1. **Real attack pattern shift** — adversaries are doing things the model
   never saw at train time.
2. **Upstream feature drift** — Wazuh decoders changed, agents added /
   removed, Wazuh ruleset updated. The features look different.
3. **Bad baseline** — the baseline file is stale or computed against a
   different dataset.

## Triage

1. Visit `/api/v1/monitoring/drift?windowMinutes=60` — confirm the alert.
2. Inspect raw inputs:
   ```sql
   SELECT date_trunc('hour', occurred_at), AVG(vae_malicious_prob)
   FROM detections
   WHERE occurred_at > now() - interval '7 days'
   GROUP BY 1 ORDER BY 1;
   ```
3. Check whether decoders / locations changed:
   ```sql
   SELECT decoder_name, count(*) FROM alerts
   WHERE occurred_at > now() - interval '24 hours'
   GROUP BY 1 ORDER BY 2 DESC LIMIT 20;
   ```

## Resolution paths

| Cause | Action |
|---|---|
| Real shift, attack-driven | Trigger SOC review of recent ESCALATE/ISOLATE actions. Consider lowering `CHAIN_OPEN_VAE_THRESHOLD` if recall is suffering. |
| Upstream feature drift (decoder/ruleset change) | Update `core/feature_engineer.py` decoder vocab and the Top-25 list. **Re-run the training notebooks** + re-export `apps/models/*.pth`. |
| Stale baseline | Re-compute the baseline:<br>`python infra/scripts/compute_drift_baseline.py --window 7d > apps/models/drift_baseline.json` |

Per §12 Q7 the full retraining pipeline is post-1.0 — for 1.0 this is a
human-in-the-loop process.

## Suppressing the alert

Tune the threshold in [`infra/prometheus_alerts.yml`](../../infra/prometheus_alerts.yml)
(`StrixModelDrift` rule). Default 0.2 is conservative; bump to 0.3-0.4
during known-noisy operational periods (rule rollouts, agent provisioning).
