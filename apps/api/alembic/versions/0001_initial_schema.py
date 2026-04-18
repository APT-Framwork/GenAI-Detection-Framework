"""initial STRIX schema

Revision ID: 0001
Revises:
Create Date: 2026-04-17 00:00:00.000000

Creates the full §6.2 schema plus TimescaleDB hypertables on `alerts`,
`detections`, and `gnn_graph_snapshots`. Hypertable conversion runs
inside the same transaction as the CREATE TABLEs — if Timescale is
missing the whole migration aborts cleanly rather than leaving a
half-migrated DB.

Downgrade drops everything. No continuous aggregates yet — those land
in Phase 4 (P4-1).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Required extensions. `timescaledb` is the only one that can fail on a
    # vanilla Postgres image; guarding lets us run migrations against non-TSDB
    # in CI smoke tests if we ever want to.
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # ---- hosts --------------------------------------------------------
    op.create_table(
        "hosts",
        sa.Column("host_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", sa.Text, nullable=False, unique=True),
        sa.Column("agent_name", sa.Text, nullable=False),
        sa.Column("ip_address", INET, nullable=True),
        sa.Column(
            "is_manager", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=False),
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
    op.create_index("ix_hosts_agent_id", "hosts", ["agent_id"], unique=True)

    # ---- users --------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("user_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column(
            "role", sa.Text, nullable=False, server_default=sa.text("'admin'")
        ),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
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
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('admin', 'analyst')",
    )

    # ---- attack_chains ------------------------------------------------
    op.create_table(
        "attack_chains",
        sa.Column("chain_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("host_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("opened_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("close_reason", sa.Text, nullable=True),
        sa.Column(
            "first_malicious_at", sa.TIMESTAMP(timezone=True), nullable=False
        ),
        sa.Column(
            "max_ckc_stage",
            sa.SmallInteger,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "max_vae_prob",
            sa.REAL,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "intervention_action_id", PG_UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            "step_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "status", sa.Text, nullable=False, server_default=sa.text("'open'")
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.host_id"]),
    )
    op.create_check_constraint(
        "ck_attack_chains_status",
        "attack_chains",
        "status IN ('open', 'closed')",
    )
    op.create_check_constraint(
        "ck_attack_chains_close_reason",
        "attack_chains",
        "close_reason IS NULL OR close_reason IN "
        "('INTERVENTION', 'IDLE_TIMEOUT', 'MAX_STEPS')",
    )
    op.create_index(
        "ix_attack_chains_host_open",
        "attack_chains",
        ["host_id"],
        postgresql_where=sa.text("status = 'open'"),
    )

    # ---- alerts (hypertable) -----------------------------------------
    op.create_table(
        "alerts",
        sa.Column("alert_id", sa.Text, nullable=False),
        sa.Column("host_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("chain_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("decoder_name", sa.Text, nullable=True),
        sa.Column("location", sa.Text, nullable=True),
        sa.Column("full_log", sa.Text, nullable=True),
        sa.Column("rule_id", sa.Text, nullable=True),
        sa.Column("rule_firedtimes", sa.Integer, nullable=True),
        sa.Column(
            "mitre_tactics",
            sa.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "mitre_techniques",
            sa.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("ckc_stage", sa.SmallInteger, nullable=True),
        sa.Column("raw_jsonb", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # Composite PK because hypertable partitioning requires time col in PK
        sa.PrimaryKeyConstraint("alert_id", "occurred_at"),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.host_id"]),
        sa.ForeignKeyConstraint(["chain_id"], ["attack_chains.chain_id"]),
    )
    op.create_index("ix_alerts_occurred_at", "alerts", ["occurred_at"])
    op.create_index(
        "ix_alerts_host_occurred",
        "alerts",
        ["host_id", "occurred_at"],
    )
    op.create_index(
        "ix_alerts_chain_occurred",
        "alerts",
        ["chain_id", "occurred_at"],
        postgresql_where=sa.text("chain_id IS NOT NULL"),
    )
    op.execute(
        "SELECT create_hypertable('alerts', 'occurred_at', "
        "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE)"
    )

    # ---- detections (hypertable) -------------------------------------
    op.create_table(
        "detections",
        sa.Column("alert_id", sa.Text, nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("host_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("chain_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("step_in_chain", sa.Integer, nullable=False),
        sa.Column("ae_anomaly_score", sa.REAL, nullable=True),
        sa.Column("ae_recon_error", sa.REAL, nullable=True),
        sa.Column("vae_malicious_prob", sa.REAL, nullable=True),
        sa.Column("vae_uncertainty", sa.REAL, nullable=True),
        sa.Column("transformer_pred_ckc", sa.SmallInteger, nullable=True),
        sa.Column("transformer_confidence", sa.REAL, nullable=True),
        sa.Column("gnn_node_risk", sa.REAL, nullable=True),
        sa.Column("gnn_neighbor_risk", sa.REAL, nullable=True),
        sa.Column("gnn_risk_growth", sa.REAL, nullable=True),
        sa.Column("state_vector", sa.ARRAY(sa.REAL), nullable=True),
        sa.Column("model_versions", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("alert_id", "occurred_at"),
    )
    op.create_index(
        "ix_detections_chain_step",
        "detections",
        ["chain_id", "step_in_chain"],
    )
    op.create_index(
        "ix_detections_host_occurred",
        "detections",
        ["host_id", "occurred_at"],
    )
    op.execute(
        "SELECT create_hypertable('detections', 'occurred_at', "
        "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE)"
    )

    # ---- dqn_actions --------------------------------------------------
    op.create_table(
        "dqn_actions",
        sa.Column("action_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("alert_id", sa.Text, nullable=False),
        sa.Column("chain_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("host_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("action", sa.SmallInteger, nullable=False),
        sa.Column("action_name", sa.Text, nullable=False),
        sa.Column("q_values", sa.ARRAY(sa.REAL), nullable=False),
        sa.Column("ckc_stage_at_decision", sa.SmallInteger, nullable=False),
        sa.Column("requires_approval", sa.Boolean, nullable=False),
        sa.Column(
            "applied",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("applied_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "applied_by",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=True,
        ),
        sa.Column("rejected_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "rejected_by",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_dqn_action_range",
        "dqn_actions",
        "action BETWEEN 0 AND 4",
    )
    op.create_check_constraint(
        "ck_dqn_action_name",
        "dqn_actions",
        "action_name IN ('MONITOR', 'LOW_ALERT', 'ESCALATE', "
        "'ISOLATE_HOST', 'BLOCK_USER_IP')",
    )
    op.create_index(
        "ix_dqn_actions_chain_decided",
        "dqn_actions",
        ["chain_id", "decided_at"],
    )
    op.create_index(
        "ix_dqn_actions_host_decided",
        "dqn_actions",
        ["host_id", "decided_at"],
    )
    op.create_index(
        "ix_dqn_actions_pending",
        "dqn_actions",
        ["requires_approval", "applied"],
        postgresql_where=sa.text("requires_approval = true AND applied = false"),
    )

    # ---- gnn_graph_snapshots (hypertable) -----------------------------
    op.create_table(
        "gnn_graph_snapshots",
        sa.Column("snapshot_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("shard_id", sa.Integer, nullable=False),
        sa.Column("taken_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("node_count", sa.Integer, nullable=True),
        sa.Column("edge_count", sa.Integer, nullable=True),
        sa.Column("nodes", JSONB, nullable=True),
        sa.Column("edges", JSONB, nullable=True),
        sa.PrimaryKeyConstraint("snapshot_id", "taken_at"),
    )
    op.create_index(
        "ix_gnn_snapshots_shard_taken",
        "gnn_graph_snapshots",
        ["shard_id", "taken_at"],
    )
    op.execute(
        "SELECT create_hypertable('gnn_graph_snapshots', 'taken_at', "
        "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE)"
    )

    # ---- ioc_lookup_cache --------------------------------------------
    op.create_table(
        "ioc_lookup_cache",
        sa.Column("indicator", sa.Text, nullable=False),
        sa.Column("indicator_type", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("reputation", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("checked_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("indicator", "indicator_type", "source"),
    )
    op.create_check_constraint(
        "ck_ioc_reputation",
        "ioc_lookup_cache",
        "reputation IN ('malicious', 'suspicious', 'clean', 'unknown')",
    )
    op.create_check_constraint(
        "ck_ioc_type",
        "ioc_lookup_cache",
        "indicator_type IN ('ip', 'email', 'domain', 'hash')",
    )
    op.create_index(
        "ix_ioc_expires_at", "ioc_lookup_cache", ["expires_at"]
    )

    # ---- llm_insight_cache -------------------------------------------
    op.create_table(
        "llm_insight_cache",
        sa.Column("payload_hash", sa.Text, primary_key=True),
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("insight", sa.Text, nullable=False),
        sa.Column("recommended_actions", JSONB, nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )

    # ---- file_scans ---------------------------------------------------
    op.create_table(
        "file_scans",
        sa.Column("scan_id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("sha256", sa.String(length=64), nullable=False, unique=True),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("uploaded_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("uploaded_by", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("vt_result", JSONB, nullable=True),
        sa.Column("vt_scanned_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", sa.Text, nullable=False),
    )
    op.create_check_constraint(
        "ck_file_scan_status",
        "file_scans",
        "status IN ('queued', 'scanning', 'complete', 'error')",
    )


def downgrade() -> None:
    # Reverse order respects FK constraints.
    op.drop_table("file_scans")
    op.drop_table("llm_insight_cache")
    op.drop_table("ioc_lookup_cache")
    op.drop_table("gnn_graph_snapshots")
    op.drop_table("dqn_actions")
    op.drop_table("detections")
    op.drop_table("alerts")
    op.drop_table("attack_chains")
    op.drop_table("users")
    op.drop_table("hosts")
