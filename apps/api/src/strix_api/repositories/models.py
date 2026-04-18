"""SQLAlchemy ORM mirrors of §6.2 tables.

Kept intentionally in `repositories/` so `core/` can stay free of
SQLAlchemy imports (see §3.4 dependency rule).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, REAL, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """All ORM tables inherit from here."""

    type_annotation_map = {
        dict[str, Any]: JSONB,
        list[str]: ARRAY(Text),
        list[float]: ARRAY(REAL),
    }


# ---------------------------------------------------------------- hosts


class Host(Base):
    __tablename__ = "hosts"

    host_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    agent_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    is_manager: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# ---------------------------------------------------------------- users


class User(Base):
    """Single-admin Phase 0 stub; real RBAC lands in P4-10."""

    __tablename__ = "users"

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    designation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# ---------------------------------------------------------------- attack_chains


class AttackChain(Base):
    __tablename__ = "attack_chains"

    chain_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    host_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_malicious_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    max_ckc_stage: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    max_vae_prob: Mapped[float] = mapped_column(REAL, nullable=False, default=0.0)
    intervention_action_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------- alerts (hypertable)


class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(Text, primary_key=True)
    host_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("hosts.host_id"), nullable=True
    )
    chain_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("attack_chains.chain_id"),
        nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), primary_key=True, nullable=False
    )
    decoder_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_firedtimes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mitre_tactics: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    mitre_techniques: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    ckc_stage: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    raw_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


# ---------------------------------------------------------------- detections (hypertable)


class Detection(Base):
    __tablename__ = "detections"

    alert_id: Mapped[str] = mapped_column(Text, ForeignKey("alerts.alert_id"), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), primary_key=True, nullable=False
    )
    host_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    chain_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    step_in_chain: Mapped[int] = mapped_column(Integer, nullable=False)
    ae_anomaly_score: Mapped[float | None] = mapped_column(REAL, nullable=True)
    ae_recon_error: Mapped[float | None] = mapped_column(REAL, nullable=True)
    vae_malicious_prob: Mapped[float | None] = mapped_column(REAL, nullable=True)
    vae_uncertainty: Mapped[float | None] = mapped_column(REAL, nullable=True)
    transformer_pred_ckc: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    transformer_confidence: Mapped[float | None] = mapped_column(REAL, nullable=True)
    gnn_node_risk: Mapped[float | None] = mapped_column(REAL, nullable=True)
    gnn_neighbor_risk: Mapped[float | None] = mapped_column(REAL, nullable=True)
    gnn_risk_growth: Mapped[float | None] = mapped_column(REAL, nullable=True)
    state_vector: Mapped[list[float] | None] = mapped_column(ARRAY(REAL), nullable=True)
    model_versions: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------- dqn_actions


class DqnActionRow(Base):
    __tablename__ = "dqn_actions"

    action_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    alert_id: Mapped[str] = mapped_column(Text, ForeignKey("alerts.alert_id"), nullable=False)
    chain_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    host_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    action: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    action_name: Mapped[str] = mapped_column(Text, nullable=False)
    q_values: Mapped[list[float]] = mapped_column(ARRAY(REAL), nullable=False)
    ckc_stage_at_decision: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    applied_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    applied_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    rejected_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )


# ---------------------------------------------------------------- GNN snapshots


class GnnGraphSnapshot(Base):
    __tablename__ = "gnn_graph_snapshots"

    snapshot_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    shard_id: Mapped[int] = mapped_column(Integer, nullable=False)
    taken_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), primary_key=True, nullable=False
    )
    node_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    edge_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nodes: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    edges: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


# ---------------------------------------------------------------- IOC cache


class IocLookupCache(Base):
    __tablename__ = "ioc_lookup_cache"

    indicator: Mapped[str] = mapped_column(Text, primary_key=True)
    indicator_type: Mapped[str] = mapped_column(Text, primary_key=True)
    source: Mapped[str] = mapped_column(Text, primary_key=True)
    reputation: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


# ---------------------------------------------------------------- LLM insight cache


class LlmInsightCache(Base):
    __tablename__ = "llm_insight_cache"

    payload_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    insight: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_actions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


# ---------------------------------------------------------------- file scans


class FileScan(Base):
    __tablename__ = "file_scans"

    scan_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(length=64), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    uploaded_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    vt_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    vt_scanned_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)


# ---------------------------------------------------------------- push_devices (M0-B5)


class PushDevice(Base):
    __tablename__ = "push_devices"

    device_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    expo_push_token: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    app_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "Alert",
    "AttackChain",
    "Base",
    "Detection",
    "DqnActionRow",
    "FileScan",
    "GnnGraphSnapshot",
    "Host",
    "IocLookupCache",
    "LlmInsightCache",
    "PushDevice",
    "User",
]
