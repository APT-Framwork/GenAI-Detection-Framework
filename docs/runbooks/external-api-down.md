# Runbook — `StrixUpstreamErrors`

**Symptom:** `sum(rate(strix_external_api_errors_total[5m])) by (api) > 0.5/s`
for ≥ 5 m.

Possible APIs: `hibp`, `virustotal`, `llm`.

## Triage

```
# Which API and what kind of error?
strix_external_api_errors_total{api,error_kind}
```

`error_kind` values:
- `breaker_open` → circuit breaker tripped (good — system is protecting itself)
- `rate_limited` → 429 from upstream
- `unauthorized` → bad / revoked API key
- `http_5xx` → upstream is having a bad day
- `invalid_json` / `invalid_shape` → upstream returned something we can't parse
- `task_failed` → an Arq job blew up

## Common causes + fixes

| `api` | Likely cause | Fix |
|---|---|---|
| `hibp` | Free tier rate limit hit | Verify paid plan; bump cache TTL in `services/threat_intel_service.py::_HIBP_NEGATIVE_TTL` |
| `virustotal` | 4 req/min cap | Same — caching is the only mitigation; in steady state we should never re-check fresh hashes |
| `llm` | Anthropic outage / key rotated | Check Anthropic status page; re-fetch key from secret store; restart `api` + `arq` |
| any | breaker_open with no upstream errors | `pybreaker` is doing its job — wait 30 s for half-open, then verify recovery |

## Degraded mode (§5.14)

When the LLM breaker is open the dashboard shows a `DegradedModeBanner`
and the Sentinel Insight card returns `stale: true` with the last cached
value. The same pattern applies to HIBP/VT lookups (the IOC search
returns the cached row marked `stale: true`).

This is the desired behaviour — DO NOT suppress the alert by editing
thresholds. Either fix the upstream or tune the breaker (`fail_max`,
`reset_timeout_seconds` in `THREAT_INTEL_*` env).
