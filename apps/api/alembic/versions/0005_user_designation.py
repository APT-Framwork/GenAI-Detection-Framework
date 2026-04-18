"""Add users.designation — optional SOC callsign / shift label.

Populated by the self-register endpoint (POST /auth/register). Nullable
because pre-existing users (seeded admins) don't carry one.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("designation", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "designation")
