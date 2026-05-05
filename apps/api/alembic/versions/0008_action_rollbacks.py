"""DQN action rollbacks — append-only ledger of operator-reverted actions.

Phase 8. Rollback is an *audit-only* state transition: it records that an
operator declared a previously-applied action reverted. STRIX does not
currently issue reverse calls to Wazuh / firewall / etc. — the operator
must un-isolate / un-block manually. The modal in the UI documents this.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dqn_action_rollbacks",
        sa.Column(
            "rollback_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "action_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dqn_actions.action_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,  # one rollback per action; re-rollback is not a thing
        ),
        sa.Column(
            "rolled_back_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "rolled_back_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("reason", sa.Text, nullable=False),
    )
    op.create_index(
        "ix_dqn_action_rollbacks_at",
        "dqn_action_rollbacks",
        [sa.text("rolled_back_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dqn_action_rollbacks_at", table_name="dqn_action_rollbacks"
    )
    op.drop_table("dqn_action_rollbacks")
