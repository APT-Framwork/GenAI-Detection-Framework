# strix-api

FastAPI backend + workers for the STRIX platform.

**Spec:** [docs/IMPLEMENTATION_PLAN.md](../../docs/IMPLEMENTATION_PLAN.md).
**Models:** [docs/MODELS_REFERENCE.md](../../docs/MODELS_REFERENCE.md).

## Quickstart (Phase 0)

```bash
# 1. Install deps (uv recommended; pip works too)
cd apps/api
pip install -e ".[dev]"

# 2. Copy env template
cp .env.example .env
# edit DB_PASSWORD at minimum

# 3. Boot the stack
cd ../..
docker compose -f infra/compose.api.yml --env-file apps/api/.env up --build

# 4. Verify
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/openapi.json | jq '.info'
curl http://localhost:8000/metrics | head
```

## Layout

See [IMPLEMENTATION_PLAN.md §3.5](../../docs/IMPLEMENTATION_PLAN.md). Enforce
the §3.4 dependency rule: `core/` never imports from anywhere else.

## Running tests

```bash
pytest                                    # unit only
pytest -m integration                     # requires Postgres + Redis testcontainers
pytest --cov=strix_api --cov-report=term-missing
```

## Regenerating OpenAPI client types

```bash
# With the API running locally:
cd apps/web && pnpm gen:api-types

# Offline (CI-friendly) — dump spec first, then generate:
python infra/scripts/dump_openapi.py apps/web/lib/openapi.json
cd apps/web && pnpm gen:api-types:offline
```

## Migrations

```bash
cd apps/api
alembic upgrade head
alembic revision --autogenerate -m "describe change"
```

## Phase status

- [x] **Phase 0** — scaffolding (this package, compose, schema, registry, OpenAPI plumbing)
- [ ] **Phase 0 / P0-5** — CI lint+test gate
- [ ] **Phase 0 / P0-7** — export missing preprocessing artifacts (`*_pca.pkl`, scaler, calibrators, gnn_metadata)
- [ ] **Phase 1+** — see IMPLEMENTATION_PLAN.md §10
