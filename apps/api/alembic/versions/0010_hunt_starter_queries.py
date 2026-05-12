"""Seed starter saved queries for the /hunt page.

The /hunt page reads `hunt_saved_queries` per-user. On a fresh install
(or for a juror's first click-through), the saved-queries panel is
empty — so the page looks dead even though the parser, results table,
and live alerts all work. This migration drops a small starter set into
every existing user's saved-queries list so /hunt has one-click demos
the moment the lab comes up.

The set is intentionally curated to demonstrate the four query operators
the parser supports (technique:, host:, free-text, time:):

  - "Recon burst (T1595)"        — technique: + recent time window
  - "Latest victim activity"     — host: + recent time window
  - "Invalid-user attempts"      — free-text on full_log
  - "Process Discovery (T1057)"  — pure technique:

Idempotent: ON CONFLICT (user_id, name) DO NOTHING so re-running this
migration (or a future user_id seed) doesn't fight the unique index
from migration 0007. Downgrade removes only the rows we inserted.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_STARTER_QUERIES: list[tuple[str, str]] = [
    ("Recon burst (T1595)", "technique:T1595 time:1h"),
    ("Latest victim activity", "host:victim1 time:30m"),
    ("Invalid-user attempts", "Invalid user time:1h"),
    ("Process Discovery (T1057)", "technique:T1057 time:24h"),
]


def upgrade() -> None:
    for name, q in _STARTER_QUERIES:
        op.execute(
            f"""
            INSERT INTO hunt_saved_queries (saved_id, user_id, name, q, created_at)
            SELECT uuid_generate_v4(), u.user_id, '{name.replace("'", "''")}',
                   '{q.replace("'", "''")}', NOW()
            FROM users u
            ON CONFLICT (user_id, name) DO NOTHING;
            """
        )


def downgrade() -> None:
    names = ",".join("'" + n.replace("'", "''") + "'" for n, _ in _STARTER_QUERIES)
    op.execute(f"DELETE FROM hunt_saved_queries WHERE name IN ({names});")
