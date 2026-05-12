"""CTI core schema — actors, campaigns, indicators, feeds, relationships, reports.

Foundation for moving STRIX from "SOC with IOC lookups" to a defensible
CTI platform. Tables introduced here are *additive* — none of the
existing detection / response surface reads or writes them yet, so this
migration is safe to apply on a live lab. The follow-up migrations seed
the actor/campaign rows from the simulator's APT_GROUPS catalogue and
wire downstream consumers (chain attribution, feed workers, /intel/*
pages).

Schema choices:

- `intel_indicators` is a *superset* of `ioc_lookup_cache`. We keep the
  cache table as the read-through enrichment cache (used by the live
  XON/VirusTotal lookups in `threat_intel_service`) and use this new
  table for first-class intel objects with confidence, TLP, lifecycle
  fields, and a `source_id` FK to `intel_feeds`. Migration of cached
  rows into here is deliberately deferred — the cache TTL will sweep
  legacy rows naturally.

- `intel_relationships` is a generic edge table (from_id, from_type,
  to_id, to_type, rel) so the pivot graph can express any of: indicator
  → indicator, indicator → actor, actor → campaign, campaign →
  technique, etc., without a per-edge join table.

- `tlp` follows the FIRST.org TLP 2.0 vocabulary (clear|green|amber|
  amber+strict|red). Stored as text + check constraint rather than an
  enum to keep migrations cheap if FIRST adds a new level later.

- `confidence` is 0..100 (admiralty-style, but normalised to a
  percentage for UI sliders). Constraint enforces the range.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID


revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TLP = ("clear", "green", "amber", "amber+strict", "red")
_INDICATOR_TYPES = ("ip", "domain", "url", "email", "hash", "user", "host", "process")
_REL_KINDS = (
    "indicates", "attributed-to", "uses", "targets", "related-to",
    "duplicate-of", "variant-of", "based-on", "delivered-by",
)
_ENTITY_TYPES = ("indicator", "actor", "campaign", "technique", "report", "host", "chain")
_FEED_KINDS = ("taxii", "misp", "otx", "abuse_ch", "rss", "manual", "internal")


def upgrade() -> None:
    # ------------------------------------------------------------------ feeds
    op.create_table(
        "intel_feeds",
        sa.Column("feed_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("auth", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("pull_interval_s", sa.Integer, nullable=False, server_default=sa.text("1800")),
        sa.Column("last_pulled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_status", sa.Text, nullable=True),  # "ok" | "error: ..." | NULL
        sa.Column("last_indicator_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("default_confidence", sa.SmallInteger, nullable=False, server_default=sa.text("60")),
        sa.Column("default_tlp", sa.Text, nullable=False, server_default=sa.text("'clear'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_check_constraint(
        "ck_intel_feeds_kind", "intel_feeds", f"kind IN {_FEED_KINDS!r}",
    )
    op.create_check_constraint(
        "ck_intel_feeds_default_tlp", "intel_feeds", f"default_tlp IN {_TLP!r}",
    )

    # ------------------------------------------------------------------ actors
    op.create_table(
        "threat_actors",
        sa.Column("actor_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("aliases", ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("mitre_group_id", sa.Text, nullable=True),  # e.g. "G0016"
        sa.Column("country", sa.Text, nullable=True),
        sa.Column("motivation", sa.Text, nullable=True),  # "espionage" | "financial" | ...
        sa.Column("first_observed", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_threat_actors_mitre_group_id", "threat_actors", ["mitre_group_id"])

    # ------------------------------------------------------------------ campaigns
    op.create_table(
        "campaigns",
        sa.Column("campaign_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column(
            "actor_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("threat_actors.actor_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("first_observed", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_observed", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("target_sectors", ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'::text[]")),
        # `tactic_chain` is the ordered tactic label list this campaign
        # is known to execute. The chain matcher uses Jaccard ≥ 0.7
        # against an observed chain's tactics to attribute it here.
        sa.Column("tactic_chain", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_campaigns_actor_id", "campaigns", ["actor_id"])

    # Wire campaigns onto chains so the /cases page can show attribution.
    # Nullable + ON DELETE SET NULL — losing a campaign row never invalidates
    # the chain history.
    op.add_column(
        "attack_chains",
        sa.Column(
            "campaign_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("campaigns.campaign_id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_attack_chains_campaign_id", "attack_chains", ["campaign_id"])

    # ------------------------------------------------------------------ indicators
    op.create_table(
        "intel_indicators",
        sa.Column("indicator_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("indicator", sa.Text, nullable=False),
        sa.Column("indicator_type", sa.Text, nullable=False),
        sa.Column("confidence", sa.SmallInteger, nullable=False, server_default=sa.text("50")),
        sa.Column("tlp", sa.Text, nullable=False, server_default=sa.text("'clear'")),
        sa.Column(
            "source_feed_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("intel_feeds.feed_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_label", sa.Text, nullable=False, server_default=sa.text("'manual'")),
        sa.Column("first_seen", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("last_seen", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        # Internal observation timestamps — only set when STRIX has seen
        # this indicator in its own telemetry. NULL means "we know about
        # it from a feed but haven't observed it on the wire."
        sa.Column("first_seen_internal", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_seen_internal", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("internal_hit_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("valid_from", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("valid_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("tags", ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("indicator", "indicator_type", "source_label", name="uq_intel_indicator_source"),
    )
    op.create_check_constraint(
        "ck_intel_indicators_type", "intel_indicators",
        f"indicator_type IN {_INDICATOR_TYPES!r}",
    )
    op.create_check_constraint(
        "ck_intel_indicators_tlp", "intel_indicators", f"tlp IN {_TLP!r}",
    )
    op.create_check_constraint(
        "ck_intel_indicators_confidence", "intel_indicators",
        "confidence BETWEEN 0 AND 100",
    )
    op.create_index(
        "ix_intel_indicators_indicator", "intel_indicators",
        ["indicator", "indicator_type"],
    )
    op.create_index("ix_intel_indicators_tags", "intel_indicators", ["tags"], postgresql_using="gin")
    op.create_index(
        "ix_intel_indicators_internal_hit",
        "intel_indicators",
        [sa.text("last_seen_internal DESC NULLS LAST")],
    )

    # ------------------------------------------------------------------ relationships (pivot graph)
    op.create_table(
        "intel_relationships",
        sa.Column("rel_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("from_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("from_type", sa.Text, nullable=False),
        sa.Column("to_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("to_type", sa.Text, nullable=False),
        sa.Column("rel", sa.Text, nullable=False),
        sa.Column("confidence", sa.SmallInteger, nullable=False, server_default=sa.text("70")),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("from_id", "from_type", "to_id", "to_type", "rel",
                            name="uq_intel_rel_edge"),
    )
    op.create_check_constraint(
        "ck_intel_rel_kind", "intel_relationships", f"rel IN {_REL_KINDS!r}",
    )
    op.create_check_constraint(
        "ck_intel_rel_from_type", "intel_relationships",
        f"from_type IN {_ENTITY_TYPES!r}",
    )
    op.create_check_constraint(
        "ck_intel_rel_to_type", "intel_relationships",
        f"to_type IN {_ENTITY_TYPES!r}",
    )
    op.create_check_constraint(
        "ck_intel_rel_confidence", "intel_relationships",
        "confidence BETWEEN 0 AND 100",
    )
    op.create_index("ix_intel_rel_from", "intel_relationships", ["from_id", "from_type"])
    op.create_index("ix_intel_rel_to", "intel_relationships", ["to_id", "to_type"])

    # ------------------------------------------------------------------ reports
    op.create_table(
        "intel_reports",
        sa.Column("report_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body_md", sa.Text, nullable=False),
        sa.Column("tlp", sa.Text, nullable=False, server_default=sa.text("'amber'")),
        sa.Column(
            "author_user_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("linked_objects", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("tags", ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_check_constraint(
        "ck_intel_reports_tlp", "intel_reports", f"tlp IN {_TLP!r}",
    )
    op.create_index("ix_intel_reports_published_at", "intel_reports",
                    [sa.text("published_at DESC NULLS LAST")])


def downgrade() -> None:
    op.drop_index("ix_intel_reports_published_at", table_name="intel_reports")
    op.drop_table("intel_reports")

    op.drop_index("ix_intel_rel_to", table_name="intel_relationships")
    op.drop_index("ix_intel_rel_from", table_name="intel_relationships")
    op.drop_table("intel_relationships")

    op.drop_index("ix_intel_indicators_internal_hit", table_name="intel_indicators")
    op.drop_index("ix_intel_indicators_tags", table_name="intel_indicators")
    op.drop_index("ix_intel_indicators_indicator", table_name="intel_indicators")
    op.drop_table("intel_indicators")

    op.drop_index("ix_attack_chains_campaign_id", table_name="attack_chains")
    op.drop_column("attack_chains", "campaign_id")

    op.drop_index("ix_campaigns_actor_id", table_name="campaigns")
    op.drop_table("campaigns")

    op.drop_index("ix_threat_actors_mitre_group_id", table_name="threat_actors")
    op.drop_table("threat_actors")

    op.drop_table("intel_feeds")
