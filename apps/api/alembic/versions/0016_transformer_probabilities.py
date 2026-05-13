"""Per-detection Transformer softmax distribution.

Adds `detections.transformer_probabilities REAL[]` so the analysis surface
can render the true per-stage CKC distribution emitted by the Transformer
instead of reconstructing a degenerate `(confidence, (1-conf)/(n-1) × 7)`
distribution from the argmax + confidence pair we used to store.

The column is nullable: rows written before this migration retain their
`(pred_ckc, confidence)` only, and the API falls back to the reconstructed
distribution for those. New verdicts persist the full 8-vector.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY


revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "detections",
        sa.Column(
            "transformer_probabilities",
            ARRAY(sa.REAL),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("detections", "transformer_probabilities")
