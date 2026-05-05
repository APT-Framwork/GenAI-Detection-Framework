"""Hunt — saved queries table + GIN index on alerts.mitre_techniques.

Phase 7. The GIN index makes `mitre_techniques @> ARRAY['T1059']` containment
predicates index-driven; without it, the Hunt query degrades to a sequential
scan that's ~2 orders of magnitude slower at 10k+ alerts/window.

`hunt_saved_queries` is per-user. The `(user_id, name)` unique pair lets users
overwrite a saved query by saving with the same name; cross-user collisions
are allowed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----- GIN index for technique containment ------------------------------
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alerts_mitre_techniques_gin "
        "ON alerts USING GIN (mitre_techniques)"
    )

    # ----- per-user saved queries -------------------------------------------
    op.create_table(
        "hunt_saved_queries",
        sa.Column(
            "saved_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("q", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_hunt_saved_queries_user_name",
        "hunt_saved_queries",
        ["user_id", "name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_hunt_saved_queries_user_name", table_name="hunt_saved_queries"
    )
    op.drop_table("hunt_saved_queries")
    op.execute("DROP INDEX IF EXISTS ix_alerts_mitre_techniques_gin")
