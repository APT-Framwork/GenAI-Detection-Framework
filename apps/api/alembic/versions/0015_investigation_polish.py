"""Investigation polish: TLP on chains, tags, persisted notes.

Bundles four small schema additions that together turn the
`/attack-analysis` page into a real investigation surface:

  - `attack_chains.tlp` (FIRST TLP 2.0 marking) so every case carries a
    sharing classification visible in the header.
  - `tags` + `tag_links` for free-form analyst tagging. `tag_links` is a
    polymorphic join (entity_type, entity_id) so the same tag can stick
    to a chain, an indicator, or a campaign without three join tables.
  - `chain_notes` — backend-persisted analyst journal (replaces the
    localStorage scratchpad that lived in `OperatorNotes`).

Activity-feed support reuses the existing `case_audit_log` table from
migration 0006 — no new table needed, just new event_type values
written by the engine and the new routes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TLP = ("clear", "green", "amber", "amber+strict", "red")
_TAG_ENTITY_TYPES = ("chain", "indicator", "actor", "campaign", "report")


def upgrade() -> None:
    # ----- attack_chains.tlp ----------------------------------------------
    op.add_column(
        "attack_chains",
        sa.Column(
            "tlp",
            sa.Text,
            nullable=False,
            server_default=sa.text("'amber'"),  # default: shareable with trusted peers
        ),
    )
    op.create_check_constraint(
        "ck_attack_chains_tlp", "attack_chains", f"tlp IN {_TLP!r}",
    )

    # ----- tags + tag_links -----------------------------------------------
    op.create_table(
        "tags",
        sa.Column("tag_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("colour", sa.Text, nullable=False, server_default=sa.text("'cyan'")),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    # Polymorphic join. The (entity_type, entity_id, tag_id) triple is
    # the natural unique key — same tag on same object is idempotent.
    op.create_table(
        "tag_links",
        sa.Column("link_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("entity_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tag_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("tags.tag_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "entity_type", "entity_id", "tag_id", name="uq_tag_link_edge",
        ),
    )
    op.create_check_constraint(
        "ck_tag_link_entity_type",
        "tag_links",
        f"entity_type IN {_TAG_ENTITY_TYPES!r}",
    )
    op.create_index(
        "ix_tag_links_entity", "tag_links", ["entity_type", "entity_id"],
    )

    # ----- chain_notes ----------------------------------------------------
    op.create_table(
        "chain_notes",
        sa.Column("note_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "chain_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("attack_chains.chain_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("body_md", sa.Text, nullable=False),
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
    )
    op.create_index(
        "ix_chain_notes_chain_created",
        "chain_notes",
        ["chain_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_chain_notes_chain_created", table_name="chain_notes")
    op.drop_table("chain_notes")

    op.drop_index("ix_tag_links_entity", table_name="tag_links")
    op.drop_constraint("ck_tag_link_entity_type", "tag_links", type_="check")
    op.drop_table("tag_links")
    op.drop_table("tags")

    op.drop_constraint("ck_attack_chains_tlp", "attack_chains", type_="check")
    op.drop_column("attack_chains", "tlp")
