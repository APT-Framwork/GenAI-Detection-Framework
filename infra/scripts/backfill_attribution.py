#!/usr/bin/env python3
"""One-shot backfill: run attribution against every unattributed open chain.

Useful after lowering ATTRIBUTION_THRESHOLD, or to retroactively label
chains that pre-date the auto-attribution wiring. The service's
"never overwrite" rule means this is safe to run multiple times — it
only touches chains where campaign_id IS NULL.

Run from repo root:
    set -a && . <(grep -v '^#' apps/api/.env | grep -v '^$' | sed 's/ #.*//') && set +a
    apps/api/.venv/bin/python infra/scripts/backfill_attribution.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add the api src dir to path so we can import strix_api modules.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api" / "src"))

from sqlalchemy import select  # noqa: E402

from strix_api.repositories.database import init_engine, session_scope  # noqa: E402
from strix_api.repositories.models import AttackChain  # noqa: E402
from strix_api.services.attribution_service import AttributionService  # noqa: E402
from strix_api.settings import get_settings  # noqa: E402


async def main() -> int:
    init_engine(get_settings())
    attributed = 0
    skipped = 0
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(AttackChain.chain_id).where(AttackChain.campaign_id.is_(None))
            )
        ).all()
        print(f"unattributed chains: {len(rows)}")
        service = AttributionService(session)
        # Process in chunks so partial progress survives any DB hiccup.
        chunk = 200
        chain_ids = [r[0] for r in rows]
        for i in range(0, len(chain_ids), chunk):
            batch = chain_ids[i : i + chunk]
            for cid in batch:
                try:
                    res = await service.attribute_chain(cid)
                    if res is not None:
                        attributed += 1
                    else:
                        skipped += 1
                except Exception as e:  # noqa: BLE001
                    print(f"  error on {cid}: {e}", file=sys.stderr)
                    skipped += 1
            await session.commit()
            print(f"  progress {i + len(batch)}/{len(chain_ids)}  attributed={attributed}  skipped={skipped}")
    print(f"\nDone. attributed={attributed} skipped={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
