# Runbook — Secret rotation

Covers `DB_PASSWORD`, `AUTH_JWT_SECRET`, `THREAT_INTEL_HIBP_API_KEY`,
`THREAT_INTEL_VIRUSTOTAL_API_KEY`, `LLM_ANTHROPIC_API_KEY`, Redis password.

## Cadence

| Secret | Rotate every | Notes |
|---|---|---|
| `AUTH_JWT_SECRET` | 90 days | Rotation invalidates ALL active sessions; users must re-login. Schedule a maintenance window. |
| `DB_PASSWORD` | 90 days | Coordinated update — see procedure below. |
| `THREAT_INTEL_HIBP_API_KEY` | per HIBP-side rotation, otherwise yearly | Free tier: monthly token rotation possible. |
| `THREAT_INTEL_VIRUSTOTAL_API_KEY` | yearly or on team change | |
| `LLM_ANTHROPIC_API_KEY` | per Anthropic console policy | Replace via console + secret store; restart `api` + `arq`. |
| Redis password | 90 days | If set; default compose has none on the internal network. |

## DB_PASSWORD rotation procedure

```sql
-- 1. Add a NEW role with the new password
CREATE USER strix_new WITH PASSWORD '<new>';
GRANT ALL PRIVILEGES ON DATABASE strix TO strix_new;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO strix_new;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO strix_new;
```

```bash
# 2. Update .env
DB_USER=strix_new
DB_PASSWORD=<new>

# 3. Rolling restart workers + api
docker compose -f infra/compose.api.yml up -d --no-deps api inference_shard0 verdicts_writer

# 4. Verify everything is connecting
curl -fs http://localhost:8000/health/deep   # checks Postgres + Redis
```

```sql
-- 5. Drop the old role
REASSIGN OWNED BY strix TO strix_new;
DROP USER strix;
ALTER USER strix_new RENAME TO strix;
```

```bash
# 6. Update .env back to canonical name + restart once more
DB_USER=strix
docker compose -f infra/compose.api.yml restart api inference_shard0 verdicts_writer
```

## What lives in `.env`

`.env` is gitignored. The canonical values live in your team's secret
manager (1Password, Vault, AWS SM, …). When you rotate, update both
the manager AND the `.env.example` documentation if the variable name
changes.

`.env.example` shows every var with `<placeholder>` defaults — keep it in
sync so a new dev can boot with `cp .env.example .env` and the right
fields to fill in.

## Audit + monitoring

Every key rotation should leave a paper trail in your secret manager.
Pre-rotation, check that nobody's mid-deploy:
```
git log --oneline -5 && git status
```

Post-rotation, verify Prometheus shows no `strix_external_api_errors_total{error_kind="unauthorized"}`.
