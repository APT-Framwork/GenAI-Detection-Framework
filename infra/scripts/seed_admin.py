#!/usr/bin/env python3
"""Idempotently create the bootstrap admin user.

Run inside the api container (where settings + DB are wired):
    docker exec -it strix_api python /app/infra/scripts/seed_admin.py
                --email admin@strix.local --password '<pw>' [--role admin]

Or from the repo root locally (requires DB env vars + asyncpg):
    DB_HOST=localhost python infra/scripts/seed_admin.py \
        --email admin@strix.local --password 'changeme'

If the user already exists the password is updated (handy for credential
rotation). Exit 0 = success.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "apps" / "api" / "src"))


async def _run(*, email: str, password: str, role: str) -> int:
    from strix_api.repositories.database import init_engine, session_scope
    from strix_api.repositories.user_repo import UserRepo
    from strix_api.services.auth import hash_password
    from strix_api.settings import get_settings

    settings = get_settings()
    init_engine(settings)

    async with session_scope() as session:
        repo = UserRepo(session)
        existing = await repo.get_by_email(email)
        if existing is None:
            user = await repo.create(
                email=email,
                password_hash=hash_password(password),
                role=role,
            )
            print(f"✅ created user {user.email!r} (id={user.user_id}, role={user.role})")
        else:
            await repo.update_password(existing.user_id, hash_password(password))
            print(f"♻️  rotated password for existing user {existing.email!r} (id={existing.user_id})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--role", default="admin", choices=("admin", "analyst"))
    args = p.parse_args()
    return asyncio.run(_run(email=args.email, password=args.password, role=args.role))


if __name__ == "__main__":
    raise SystemExit(main())
