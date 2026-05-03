How to run + interact
One-time setup (already done in this session, but for future)

cp apps/api/.env.example apps/api/.env
# edit: set DB_PASSWORD, AUTH_JWT_SECRET, INFERENCE_NUM_SHARDS=1
Bring everything up

docker compose -f infra/compose.api.yml \
  --profile workers --profile queue \
  --env-file apps/api/.env up -d --build
Wait ~5 min for the inference worker to download SecBERT (one-time).

Seed admin (once)

docker exec strix_api python -c "
import asyncio
from strix_api.repositories.database import init_engine, session_scope
from strix_api.repositories.user_repo import UserRepo
from strix_api.services.auth import hash_password
from strix_api.settings import get_settings
async def run():
    init_engine(get_settings())
    async with session_scope() as s:
        await UserRepo(s).create(email='admin@strix.io',
            password_hash=hash_password('changeme123!'), role='admin')
asyncio.run(run())"
Start the dashboard

cd apps/web && pnpm dev
Open http://localhost:3000 → log in with admin@strix.io / changeme123!.

Push a test alert through the pipeline

python3 infra/scripts/smoke.py \
  --redis redis://localhost:6380/0 \
  --admin-email admin@strix.io --admin-password 'changeme123!'
Watch the dashboard — attack-vector count rises, vigilance-feed gets a new SSE event.

Useful URLs once up
Dashboard — http://localhost:3000
API docs — http://localhost:8000/api/v1/docs
Redis CLI — docker exec -it strix_redis redis-cli
Postgres — docker exec -it strix_postgres psql -U strix -d strix
Stop everything

docker compose -f infra/compose.api.yml --profile workers --profile queue down



