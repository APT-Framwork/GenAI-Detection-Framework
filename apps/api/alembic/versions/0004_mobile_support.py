"""Mobile support — acknowledge columns on alerts + push_devices table.

Additive, zero-downtime:
  * ``alerts.acknowledged_at`` / ``acknowledged_by`` — nullable columns,
    no default required. The web app never reads or writes these, so
    leaving them NULL is safe.
  * ``push_devices`` — new table storing Expo push tokens per user, used
    by the push-dispatcher in ``workers.verdicts_writer`` to fan out
    ≥ ESCALATE interventions to registered mobile clients.

Both changes are strictly additive; downgrade drops them cleanly.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- alerts.acknowledged_{at,by} ---------------------------------
    op.add_column(
        "alerts",
        sa.Column(
            "acknowledged_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "alerts",
        sa.Column(
            "acknowledged_by",
            PG_UUID(as_uuid=True),
            nullable=True,
        ),
    )
    # Partial index — only unacknowledged rows participate; keeps the
    # mobile "unread count" query fast without bloating the hot path.
    op.create_index(
        "ix_alerts_unacknowledged_occurred_at",
        "alerts",
        ["occurred_at"],
        postgresql_where=sa.text("acknowledged_at IS NULL"),
    )

    # --- push_devices ------------------------------------------------
    op.create_table(
        "push_devices",
        sa.Column("device_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("expo_push_token", sa.Text, nullable=False),
        sa.Column(
            "platform", sa.Text, nullable=False,
        ),  # 'ios' | 'android' | 'web'
        sa.Column("app_version", sa.Text, nullable=True),
        sa.Column(
            "registered_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "platform IN ('ios', 'android', 'web')",
            name="push_devices_platform_check",
        ),
    )
    # Unique on (user_id, token) so re-registration is idempotent.
    op.create_index(
        "ix_push_devices_user_token",
        "push_devices", ["user_id", "expo_push_token"], unique=True,
    )
    # Secondary lookup for the dispatcher fan-out.
    op.create_index(
        "ix_push_devices_user_id",
        "push_devices", ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_push_devices_user_id", table_name="push_devices")
    op.drop_index("ix_push_devices_user_token", table_name="push_devices")
    op.drop_table("push_devices")
    op.drop_index(
        "ix_alerts_unacknowledged_occurred_at", table_name="alerts",
    )
    op.drop_column("alerts", "acknowledged_by")
    op.drop_column("alerts", "acknowledged_at")
