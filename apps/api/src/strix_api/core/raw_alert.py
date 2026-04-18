"""Normalised view of a single Wazuh alert (pure-domain, no Wazuh import).

This is the contract between `adapters/wazuh_adapter.py` and the feature
engineer. It materialises only the fields §5.10 + the feature_selection
notebook reference — everything else stays in `extra` for debugging without
feeding into model inputs.

MITRE tactics/techniques are extracted and CKC-mapped HERE (they drive the
alerts table + live-feed display) but are NEVER fed to the ML models — they
are leaky at training time and the notebook's feature engineer explicitly
drops them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuleInfo(BaseModel):
    """Rule metadata. `level` and `description` and MITRE fields are kept here
    for downstream display / live-feed, NEVER fed to the 55-dim feature vector.
    """

    model_config = ConfigDict(frozen=True)

    rule_id: str | None = None
    firedtimes: int | None = None
    level: int | None = None
    description: str | None = None
    mitre_tactics: list[str] = Field(default_factory=list)
    mitre_techniques: list[str] = Field(default_factory=list)


class AgentInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_id: str
    name: str | None = None
    ip: str | None = None


class DataInfo(BaseModel):
    """Contents of `_source.data`."""

    model_config = ConfigDict(frozen=True)

    command: str | None = None
    srcip: str | None = None
    srcport: str | None = None
    srcuser: str | None = None
    dstuser: str | None = None


class SyscheckInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str | None = None
    event: str | None = None
    md5_after: str | None = None
    sha256_after: str | None = None
    changed_attributes: str | None = None


class RawAlert(BaseModel):
    """Canonical in-memory representation of one alert.

    - Populated by `WazuhAlertAdapter.parse()`.
    - Consumed by `core/feature_engineer.py` to produce the 23 individual
      features + the two SecBERT input texts (command / full_log).
    """

    model_config = ConfigDict(frozen=True)

    # Identifiers
    alert_id: str
    occurred_at: datetime

    # Ingest metadata
    decoder_name: str | None = None
    location: str | None = None
    full_log: str | None = None

    # Structured sections
    agent: AgentInfo
    rule: RuleInfo = Field(default_factory=RuleInfo)
    data: DataInfo = Field(default_factory=DataInfo)
    syscheck: SyscheckInfo = Field(default_factory=SyscheckInfo)

    # Anything else from the JSON — not fed to models, kept for debugging
    extra: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AgentInfo",
    "DataInfo",
    "RawAlert",
    "RuleInfo",
    "SyscheckInfo",
]
