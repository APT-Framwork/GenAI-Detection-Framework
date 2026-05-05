"""Convert compromised_assets_view from MATERIALIZED VIEW → plain VIEW.

Background: migration 0002 created `compromised_assets_view` as a
MATERIALIZED VIEW with a comment promising "Refreshed periodically by a
small trigger or by Phase-8 cron." Neither was ever wired — there's no
`REFRESH MATERIALIZED VIEW` call anywhere in the codebase, so the view
contains exactly the rows that existed at migration time (i.e. zero) and
no detection from any subsequent sim run is visible to the threat-intel
dashboard's Compromised Assets panel.

Fix: convert it to a plain VIEW. The underlying SELECT is a per-host
GROUP BY of `detections` plus a correlated MAX over `dqn_actions` — at
the lab's scale (low-thousands of rows) the read is microseconds, and
"always fresh" is materially better than "30s stale + extra moving
parts." The schema as seen by the reader (CompromisedAssetsRepo) is
unchanged.

The unique index on the MV (`ix_compromised_assets_host_id`) is dropped
along with the MV — plain VIEWs in Postgres can't be indexed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_VIEW_BODY = """
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
GROUP BY d.host_id
""".strip()


def upgrade() -> None:
    # Drop the MV (and its unique index — plain VIEWs can't carry indexes).
    op.execute("DROP MATERIALIZED VIEW IF EXISTS compromised_assets_view")
    op.execute(f"CREATE VIEW compromised_assets_view AS {_VIEW_BODY}")


def downgrade() -> None:
    # Recreate the original MV + index so we end up exactly where 0002 left us.
    op.execute("DROP VIEW IF EXISTS compromised_assets_view")
    op.execute(f"CREATE MATERIALIZED VIEW compromised_assets_view AS {_VIEW_BODY}")
    op.create_index(
        "ix_compromised_assets_host_id",
        "compromised_assets_view",
        ["host_id"],
        unique=True,
    )
