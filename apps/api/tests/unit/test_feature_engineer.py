"""FeatureEngineerNoLeakage — per-alert transforms must match the notebook."""

from __future__ import annotations

import math

import numpy as np
import pytest
from tests.fixtures.sample_alerts import (
    SAMPLE_AUDITD_ALERT,
    SAMPLE_EMPTY_ALERT,
    SAMPLE_SYSCHECK_ALERT,
)

from strix_api.adapters.wazuh_adapter import WazuhAlertAdapter
from strix_api.core.feature_engineer import FeatureEngineerNoLeakage


@pytest.fixture
def engineer() -> FeatureEngineerNoLeakage:
    return FeatureEngineerNoLeakage()


@pytest.fixture
def adapter() -> WazuhAlertAdapter:
    return WazuhAlertAdapter()


def test_canonical_ordering_has_exactly_23(engineer: FeatureEngineerNoLeakage) -> None:
    assert len(engineer.INDIVIDUAL_FEATURES) == 23
    assert len(set(engineer.INDIVIDUAL_FEATURES)) == 23  # no dupes


def test_feature_dict_covers_all_canonical_columns(
    engineer: FeatureEngineerNoLeakage, adapter: WazuhAlertAdapter
) -> None:
    alert = adapter.parse(SAMPLE_AUDITD_ALERT)
    features = engineer.engineer(alert)
    assert set(features) >= set(engineer.INDIVIDUAL_FEATURES)
    # Every value is a finite float
    for k, v in features.items():
        assert isinstance(v, float), k
        assert math.isfinite(v), k


def test_to_array_shape_and_dtype(
    engineer: FeatureEngineerNoLeakage, adapter: WazuhAlertAdapter
) -> None:
    alert = adapter.parse(SAMPLE_AUDITD_ALERT)
    arr = engineer.to_array(alert)
    assert arr.shape == (23,)
    assert arr.dtype == np.float32


def test_auditd_alert_activates_expected_flags(
    engineer: FeatureEngineerNoLeakage, adapter: WazuhAlertAdapter
) -> None:
    alert = adapter.parse(SAMPLE_AUDITD_ALERT)
    f = engineer.engineer(alert)

    # decoder_auditd should be 1; other decoder one-hots zero
    assert f["decoder_auditd"] == 1.0
    assert f["decoder_web-accesslog"] == 0.0
    assert f["decoder_dpkg-decoder"] == 0.0
    assert f["decoder_syscheck_deleted"] == 0.0
    assert f["decoder_syscheck_integrity_changed"] == 0.0

    # location__var_log_audit_audit.log should be 1, the others zero
    assert f["location__var_log_audit_audit.log"] == 1.0
    assert f["location__var_log_apache2_access.log"] == 0.0
    assert f["location__var_log_auth.log"] == 0.0
    assert f["location_syscheck"] == 0.0

    # firedtimes = 3; firedtimes_log = log1p(3)
    assert f["firedtimes"] == 3.0
    assert math.isclose(f["firedtimes_log"], math.log1p(3.0))

    # srcip 10.0.0.42 is private
    assert f["srcip_is_private"] == 1.0

    # path: auditd alert has no syscheck.path → missing
    assert f["path_is_missing"] == 1.0
    assert f["path_depth"] == 0.0
    assert f["path_is_sensitive"] == 0.0
    assert f["path_is_temp"] == 0.0

    # command present and non-empty
    assert f["cmd_is_missing"] == 0.0
    assert f["cmd_length"] == float(len(alert.data.command or ""))

    # no hashes
    assert f["has_md5"] == 0.0
    assert f["has_sha256"] == 0.0

    # no syscheck events on this alert
    assert f["syscheck_added"] == 0.0
    assert f["syscheck_modified"] == 0.0
    assert f["syscheck_deleted"] == 0.0


def test_syscheck_alert_activates_integrity_flags(
    engineer: FeatureEngineerNoLeakage, adapter: WazuhAlertAdapter
) -> None:
    alert = adapter.parse(SAMPLE_SYSCHECK_ALERT)
    f = engineer.engineer(alert)

    assert f["decoder_syscheck_integrity_changed"] == 1.0
    assert f["location_syscheck"] == 1.0
    assert f["syscheck_modified"] == 1.0
    assert f["syscheck_added"] == 0.0
    assert f["syscheck_deleted"] == 0.0
    assert f["has_md5"] == 1.0
    assert f["has_sha256"] == 1.0

    # /etc/passwd is sensitive (/etc), not temp, depth=2
    assert f["path_is_missing"] == 0.0
    assert f["path_depth"] == 2.0
    assert f["path_is_sensitive"] == 1.0
    assert f["path_is_temp"] == 0.0


def test_empty_alert_produces_defensible_zeros(
    engineer: FeatureEngineerNoLeakage, adapter: WazuhAlertAdapter
) -> None:
    alert = adapter.parse(SAMPLE_EMPTY_ALERT)
    f = engineer.engineer(alert)

    # -1 for missing srcip matches the notebook's sentinel (StandardScaler
    # saw -1, not NaN, at training time — §6.3 implicit).
    assert f["srcip_is_private"] == -1.0
    assert f["cmd_is_missing"] == 1.0
    assert f["cmd_length"] == 0.0
    assert f["path_is_missing"] == 1.0
    assert f["firedtimes"] == 0.0
    assert f["firedtimes_log"] == 0.0  # log1p(0) = 0
    # All decoder / location one-hots must be 0 (decoder field missing).
    for name in engineer.INDIVIDUAL_FEATURES:
        if name.startswith(("decoder_", "location_")):
            assert f[name] == 0.0


def test_path_depth_is_clipped(
    engineer: FeatureEngineerNoLeakage, adapter: WazuhAlertAdapter
) -> None:
    doc = dict(SAMPLE_SYSCHECK_ALERT)
    src = dict(doc["_source"])
    syscheck = dict(src["syscheck"])
    syscheck["path"] = "/" + "/".join(["deep"] * 25)  # depth 25 raw
    src["syscheck"] = syscheck
    doc = {**doc, "_source": src}
    alert = adapter.parse(doc)
    f = engineer.engineer(alert)
    assert f["path_depth"] == 15.0  # clipped


def test_to_array_respects_canonical_order(
    engineer: FeatureEngineerNoLeakage, adapter: WazuhAlertAdapter
) -> None:
    """The first three columns of the canonical order are the 3 I claim."""
    alert = adapter.parse(SAMPLE_AUDITD_ALERT)
    arr = engineer.to_array(alert)

    # selected_features_top25.json positions 0, 1, 2 = decoder_auditd,
    # firedtimes, location__var_log_audit_audit.log
    assert arr[0] == 1.0  # decoder_auditd
    assert arr[1] == 3.0  # firedtimes
    assert arr[2] == 1.0  # location__var_log_audit_audit.log


def test_text_inputs_cleaning(
    engineer: FeatureEngineerNoLeakage, adapter: WazuhAlertAdapter
) -> None:
    alert = adapter.parse(SAMPLE_EMPTY_ALERT)
    cmd, log = engineer.text_inputs(alert)
    assert cmd == "[EMPTY]"
    assert log == "[EMPTY]"

    alert2 = adapter.parse(SAMPLE_AUDITD_ALERT)
    cmd2, log2 = engineer.text_inputs(alert2)
    assert "sudo" in cmd2
    assert "SYSCALL" in log2
