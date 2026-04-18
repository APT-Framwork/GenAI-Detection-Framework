"""Stream message schemas (§6.5).

Every inter-worker message on Redis Streams is MessagePack-encoded and
validated by these Pydantic models. Keeping them under `core/` means
workers, adapters, and routes all share one source of truth for the wire
format without importing `redis` or `fastapi` to read a type.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from strix_api.core.constants import (
    AE_LATENT_DIM,
    DQN_ACTION_SPACE,
    FEATURE_VECTOR_DIM,
    STATE_VECTOR_DIM,
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class _StreamBase(BaseModel):
    """All wire messages use camelCase on the outside, snake_case inside."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=True,
    )


# ---------------------------------------------------------------- raw ingest


class RawAlertMessage(_StreamBase):
    """Produced by the Wazuh adapter, consumed by the normalizer.

    `raw_json` is the flattened Wazuh `_source` dict with envelope metadata
    (`_index`, `_id`, `_version`, `_score`) stripped. Leaky columns
    (`rule.level`, `rule.description`, `rule.mitre.tactics`,
    `rule.mitre.techniques`) are dropped here — before the normalizer ever
    sees them — so no leaky field can leak into feature engineering by
    accident.
    """

    alert_id: str
    ingested_at: str = Field(default_factory=_utcnow_iso)
    raw_json: dict[str, Any]


# ---------------------------------------------------------------- features


class FeatureMessage(_StreamBase):
    """Produced by the normalizer, consumed by the inference worker.

    `feature_vector` is exactly `FEATURE_VECTOR_DIM` floats in the canonical
    order defined by `selected_features_top25.json` (AE/VAE path — numeric
    SecBERT ordering). The GNN path re-permutes into alphabetical SecBERT
    ordering inside the inference worker using `gnn_metadata.pkl['features']`.

    `current_ckc_stage`, `mitre_tactics`, `mitre_techniques`, `srcuser`, `srcip`
    are lifted from the Wazuh alert at parse time so the inference worker can
    build the 13-d state vector and the GNN graph without re-parsing the raw
    JSON. None of these are fed to AE/VAE/Transformer/GNN as features —
    they're metadata for state assembly + edge construction.
    """

    alert_id: str
    agent_id: str
    host_id: UUID
    occurred_at: str
    feature_vector: list[float] = Field(
        min_length=FEATURE_VECTOR_DIM, max_length=FEATURE_VECTOR_DIM
    )
    # MITRE-resolved CKC stage (0=BENIGN, 1..7 attack stages). Used for
    # `current_ckc_stage` in the 13-d state and for the dashboard pie chart.
    current_ckc_stage: int = 0
    mitre_tactics: list[str] = Field(default_factory=list)
    mitre_techniques: list[str] = Field(default_factory=list)
    # GNN edge construction needs these — kept on the wire so the inference
    # worker doesn't need to re-parse the raw alert.
    srcuser: str | None = None
    srcip: str | None = None
    schema_version: Literal["v1"] = "v1"


# ---------------------------------------------------------------- verdicts


class VerdictMessage(_StreamBase):
    """Produced by the inference worker, consumed by the verdicts writer.

    Carries everything needed to build a detection row + DQN action row +
    update the attack_chain in a single DB transaction.
    """

    alert_id: str
    chain_id: UUID
    step_in_chain: int
    occurred_at: str

    # AE
    ae_anomaly_score: float
    ae_recon_error: float
    ae_latent: list[float] = Field(
        min_length=AE_LATENT_DIM, max_length=AE_LATENT_DIM
    )

    # VAE
    vae_malicious_prob: float
    vae_uncertainty: float

    # Transformer (CKC prediction)
    transformer_pred_ckc: int
    transformer_confidence: float

    # GNN
    gnn_node_risk: float
    gnn_neighbor_risk: float
    gnn_risk_growth: float

    # Assembled state + DQN decision
    state_vector: list[float] = Field(
        min_length=STATE_VECTOR_DIM, max_length=STATE_VECTOR_DIM
    )
    dqn_action: int = Field(ge=0, lt=DQN_ACTION_SPACE)
    dqn_action_name: str
    q_values: list[float] = Field(
        min_length=DQN_ACTION_SPACE, max_length=DQN_ACTION_SPACE
    )

    model_versions: dict[str, str]


__all__ = ["FeatureMessage", "RawAlertMessage", "VerdictMessage"]
