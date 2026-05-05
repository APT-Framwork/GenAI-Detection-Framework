"""Case triage workflow — adds operator-owned triage_status + assignee + audit log.

Phase 4: introduces the SOC operator's case-management surface (`/api/v1/cases`).

Design choice — `triage_status` is **orthogonal** to the existing
`attack_chains.status` column:
- `status` (open | closed) is the **lifecycle** state, owned by the inference
  engine (verdicts_writer.py opens chains, AttackChainRepo.close() closes them).
- `triage_status` (new | investigating | contained | closed) is the **workflow**
  state, owned by the operator via the Cases UI.

Keeping them separate avoids touching every existing writer/reader of `status`
and lets the two states evolve independently (e.g. an open chain can already
be marked "contained" by an analyst).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TRIAGE_STATES = ("new", "investigating", "contained", "closed")


def upgrade() -> None:
    # ----- attack_chains: add triage_status + assignee_user_id ------------
    op.add_column(
        "attack_chains",
        sa.Column(
            "triage_status",
            sa.Text,
            nullable=False,
            server_default="new",
        ),
    )
    op.add_column(
        "attack_chains",
        sa.Column(
            "assignee_user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_attack_chains_triage_status",
        "attack_chains",
        f"triage_status IN {_TRIAGE_STATES!r}",
    )
    op.create_index(
        "ix_attack_chains_triage_status_opened_at",
        "attack_chains",
        ["triage_status", sa.text("opened_at DESC")],
    )

    # ----- case_audit_log: who changed what, when, why --------------------
    op.create_table(
        "case_audit_log",
        sa.Column(
            "audit_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "chain_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("attack_chains.chain_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("from_status", sa.Text, nullable=True),
        sa.Column("to_status", sa.Text, nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column(
            "at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_case_audit_log_chain_id_at",
        "case_audit_log",
        ["chain_id", sa.text("at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_case_audit_log_chain_id_at", table_name="case_audit_log")
    op.drop_table("case_audit_log")
    op.drop_index(
        "ix_attack_chains_triage_status_opened_at",
        table_name="attack_chains",
    )
    op.drop_constraint(
        "ck_attack_chains_triage_status",
        "attack_chains",
        type_="check",
    )
    op.drop_column("attack_chains", "assignee_user_id")
    op.drop_column("attack_chains", "triage_status")
