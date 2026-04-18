"""Auto-response scaffold (P8-8) — flag stays OFF in 1.0.

Adds two tables and a Redis-backed kill-switch row:

    auto_response_allowlist  per-host opt-in for ISOLATE/BLOCK auto-apply.
                             A host MUST be in the allowlist for the
                             AUTO_RESPONSE_ENABLED flag to apply to it,
                             even when the flag is globally true.

    auto_response_audit      one row per attempted auto-apply, regardless
                             of whether it actually fired. Used for
                             shadow-mode evaluation pre-flag-flip.

The audit table is a hypertable so it can grow large without manual
maintenance; allowlist is a regular table.

NONE of this changes runtime behaviour by itself — the verdicts-writer
still defaults `applied = AUTO_RESPONSE_ENABLED && allowlist_member`,
and `AUTO_RESPONSE_ENABLED` is hard-coded false in 1.0 (§12 Q3).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auto_response_allowlist",
        sa.Column("host_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", sa.Text, nullable=False),
        sa.Column(
            "allow_isolate", sa.Boolean, nullable=False, server_default=sa.text("false"),
        ),
        sa.Column(
            "allow_block", sa.Boolean, nullable=False, server_default=sa.text("false"),
        ),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.host_id"]),
    )
    op.create_index(
        "ix_auto_response_allowlist_agent_id",
        "auto_response_allowlist", ["agent_id"], unique=True,
    )

    op.create_table(
        "auto_response_audit",
        sa.Column("audit_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("host_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("chain_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("alert_id", sa.Text, nullable=False),
        sa.Column("action", sa.SmallInteger, nullable=False),
        sa.Column("action_name", sa.Text, nullable=False),
        sa.Column(
            "would_have_applied",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("actually_applied", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "kill_switch_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.PrimaryKeyConstraint("audit_id", "decided_at"),
    )
    op.execute(
        "SELECT create_hypertable('auto_response_audit', 'decided_at', "
        "chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE)"
    )
    op.create_index(
        "ix_auto_response_audit_host_decided",
        "auto_response_audit", ["host_id", "decided_at"],
    )


def downgrade() -> None:
    op.drop_table("auto_response_audit")
    op.drop_table("auto_response_allowlist")
