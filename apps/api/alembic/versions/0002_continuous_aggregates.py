"""Timescale continuous aggregates for the dashboard (P4-1).

Three CAGGs:

  ckc_stage_hourly      time_bucket('1 hour', occurred_at), ckc_stage → count(*)
                        Used by /dashboard/attack-vector.

  global_risk_minutely  time_bucket('1 minute', occurred_at) → mean VAE prob,
                        max GNN node risk, anomaly rate, growth.
                        Used by /dashboard/global-risk.

  compromised_assets_view  per-host max action + max VAE prob (rolling).
                           Materialised via continuous-agg refresh policy.

Refresh policy: every 5 min, lag 15 min. Real-time view enabled so the
dashboard sees data within a minute of arrival even before the materialised
chunk catches up.

CAGGs are NOT FK-target-compatible — we never JOIN them as parents — and
they survive `alembic downgrade` because they're created with `DROP IF
EXISTS` (no model_metadata side effects).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- ckc_stage_hourly --------------------------------------------
    op.execute(
        """
        CREATE MATERIALIZED VIEW ckc_stage_hourly
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket(INTERVAL '1 hour', occurred_at) AS bucket,
            ckc_stage,
            COUNT(*) AS alert_count
        FROM alerts
        WHERE ckc_stage IS NOT NULL
        GROUP BY bucket, ckc_stage
        WITH NO DATA;
        """
    )
    op.execute(
        """
        SELECT add_continuous_aggregate_policy('ckc_stage_hourly',
            start_offset => INTERVAL '7 days',
            end_offset   => INTERVAL '15 minutes',
            schedule_interval => INTERVAL '5 minutes');
        """
    )
    op.execute("ALTER MATERIALIZED VIEW ckc_stage_hourly SET (timescaledb.materialized_only = false)")

    # ---- global_risk_minutely ----------------------------------------
    op.execute(
        """
        CREATE MATERIALIZED VIEW global_risk_minutely
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket(INTERVAL '1 minute', occurred_at) AS bucket,
            AVG(vae_malicious_prob)::REAL          AS vae_mean_prob,
            MAX(gnn_node_risk)::REAL               AS gnn_max_node_risk,
            (COUNT(*) FILTER (WHERE ae_anomaly_score > 1.0)::REAL
             / GREATEST(COUNT(*), 1)::REAL)        AS anomaly_rate,
            COUNT(*)                               AS alert_count
        FROM detections
        GROUP BY bucket
        WITH NO DATA;
        """
    )
    op.execute(
        """
        SELECT add_continuous_aggregate_policy('global_risk_minutely',
            start_offset => INTERVAL '24 hours',
            end_offset   => INTERVAL '1 minute',
            schedule_interval => INTERVAL '1 minute');
        """
    )
    op.execute("ALTER MATERIALIZED VIEW global_risk_minutely SET (timescaledb.materialized_only = false)")

    # ---- confidence_trend_daily (model-monitoring) -------------------
    op.execute(
        """
        CREATE MATERIALIZED VIEW confidence_trend_daily
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket(INTERVAL '1 day', occurred_at) AS bucket,
            AVG(ae_anomaly_score)::REAL          AS ae_anomaly,
            AVG(vae_malicious_prob)::REAL        AS vae_prob,
            AVG(transformer_confidence)::REAL    AS transformer_confidence,
            AVG(gnn_node_risk)::REAL             AS gnn_risk
        FROM detections
        GROUP BY bucket
        WITH NO DATA;
        """
    )
    op.execute(
        """
        SELECT add_continuous_aggregate_policy('confidence_trend_daily',
            start_offset => INTERVAL '30 days',
            end_offset   => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour');
        """
    )
    op.execute("ALTER MATERIALIZED VIEW confidence_trend_daily SET (timescaledb.materialized_only = false)")

    # ---- compromised_assets_view -------------------------------------
    # Plain materialised view (not a CAGG — Timescale CAGGs require a
    # time_bucket on a hypertable; this aggregate is per-host, not per-time).
    # Refreshed periodically by a small trigger or by Phase-8 cron.
    op.execute(
        """
        CREATE MATERIALIZED VIEW compromised_assets_view AS
        SELECT
            d.host_id,
            MAX(d.vae_malicious_prob)::REAL  AS max_vae_prob,
            MAX(d.gnn_node_risk)::REAL       AS max_gnn_risk,
            MAX(d.occurred_at)               AS last_seen_at,
            COUNT(*)                         AS detection_count,
            (
                SELECT MAX(action) FROM dqn_actions a WHERE a.host_id = d.host_id
            )                                AS max_action_int
        FROM detections d
        GROUP BY d.host_id;
        """
    )
    op.create_index(
        "ix_compromised_assets_host_id",
        "compromised_assets_view",
        ["host_id"],
        unique=True,
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS compromised_assets_view")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS confidence_trend_daily CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS global_risk_minutely CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS ckc_stage_hourly CASCADE")
