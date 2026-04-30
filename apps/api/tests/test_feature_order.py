"""Workstream 2 / Phase B — feature column order regression test.

Asserts that ``preprocessing_pipeline.FEATURE_COLUMNS`` is an explicit
55-name list copied verbatim from the training notebook's ordering, and
that ``PreprocessingPipeline.transform`` produces a normalized vector
that matches a row computed by manually applying the canonical training
recipe (engineer 23 individuals + log/cmd PCAs concatenated in canonical
order, then StandardScaler).

How the expected vector was captured:
    The ``selected_features_top25.json['all_selected_columns']`` list IS
    the verbatim training-notebook ordering (the JSON was emitted from
    the same ``feature_selection_final.ipynb`` cell that fit the scaler).
    We rebuild the expected scaled row by:
      1. running ``FeatureEngineerNoLeakage.to_array`` on a sample alert
         (23 individuals in canonical order),
      2. embedding ``full_log`` + ``command`` via SecBERT and applying
         the two saved PCAs,
      3. concatenating ``[ind, log_16, cmd_16]`` (canonical order),
      4. transforming through ``standard_scaler.pkl``.
    Both the test and the pipeline pull from the same artifacts, so an
    *exact* match (within 1e-6) is the correctness guarantee that the
    pipeline is using the explicit column ordering rather than an
    ad-hoc reconstruction.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = REPO_ROOT / "apps" / "models"


def test_feature_columns_constant_exists_and_matches_canonical_json() -> None:
    """`FEATURE_COLUMNS` must be importable and match selected_features_top25.json verbatim."""
    from strix_api.adapters.preprocessing_pipeline import FEATURE_COLUMNS

    assert isinstance(FEATURE_COLUMNS, list)
    assert len(FEATURE_COLUMNS) == 55
    canonical = json.loads(
        (MODELS_DIR / "selected_features_top25.json").read_text()
    )["all_selected_columns"]
    assert FEATURE_COLUMNS == canonical, (
        "FEATURE_COLUMNS must match selected_features_top25.json all_selected_columns "
        "verbatim — order is load-bearing for the StandardScaler."
    )


def test_feature_columns_layout_matches_docstring() -> None:
    """The 23+16+16 layout (individuals, log_pca, cmd_pca) must be preserved."""
    from strix_api.adapters.preprocessing_pipeline import FEATURE_COLUMNS

    # 23 individuals
    assert all("secbert" not in c for c in FEATURE_COLUMNS[:23])
    # log_secbert_emb_0..15
    assert FEATURE_COLUMNS[23:39] == [f"log_secbert_emb_{i}" for i in range(16)]
    # cmd_secbert_emb_0..15
    assert FEATURE_COLUMNS[39:55] == [f"cmd_secbert_emb_{i}" for i in range(16)]


@pytest.mark.skipif(
    not (MODELS_DIR / "preprocess" / "scaler_55.pkl").exists(),
    reason="Phase A artifacts not present",
)
def test_pipeline_uses_explicit_feature_columns_for_assembly() -> None:
    """End-to-end exact match: alert → pipeline.transform should equal a manual
    canonical-order assembly + StandardScaler within 1e-6."""
    import joblib
    from datetime import UTC, datetime

    from strix_api.adapters.preprocessing_pipeline import (
        FEATURE_COLUMNS,
        build_pipeline,
    )
    from strix_api.core.raw_alert import (
        AgentInfo,
        DataInfo,
        RawAlert,
        RuleInfo,
        SyscheckInfo,
    )

    pipe = build_pipeline(MODELS_DIR, warmup=False)

    alert = RawAlert(
        alert_id="row-0",
        occurred_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        decoder_name="auditd",
        location="/var/log/audit/audit.log",
        full_log="type=EXECVE msg=audit(1.2:3): argc=2 a0=ls a1=-la /etc/passwd",
        agent=AgentInfo(agent_id="row-0-agent"),
        rule=RuleInfo(rule_id="80700", firedtimes=2, level=5),
        data=DataInfo(command="ls -la /etc/passwd"),
        syscheck=SyscheckInfo(),
    )

    actual = pipe.transform(alert)

    # Manual reconstruction in canonical FEATURE_COLUMNS order.
    individuals = pipe._engineer.to_array(alert)  # 23
    cmd_text, log_text = pipe._engineer.text_inputs(alert)
    cmd_768 = pipe._secbert.embed_one(cmd_text)
    log_768 = pipe._secbert.embed_one(log_text)
    log_16 = pipe._log_pca.transform(log_768.reshape(1, -1))[0]
    cmd_16 = pipe._cmd_pca.transform(cmd_768.reshape(1, -1))[0]

    expected = np.concatenate([individuals, log_16, cmd_16]).astype(np.float32)
    expected_scaled = pipe._scaler.transform(expected.reshape(1, -1))[0].astype(np.float32)

    assert actual.shape == (55,)
    np.testing.assert_allclose(actual, expected_scaled, atol=1e-6, rtol=0)

    # And the columns it implicitly uses are FEATURE_COLUMNS.
    assert pipe.canonical_order == tuple(FEATURE_COLUMNS)
