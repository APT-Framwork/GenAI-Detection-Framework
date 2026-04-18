"""WazuhAlertAdapter — parsing + leaky-field removal."""

from __future__ import annotations

import pytest
from tests.fixtures.sample_alerts import (
    SAMPLE_AUDITD_ALERT,
    SAMPLE_EMPTY_ALERT,
    SAMPLE_SYSCHECK_ALERT,
)

from strix_api.adapters.wazuh_adapter import WazuhAlertAdapter
from strix_api.api.errors import ValidationFailedError


@pytest.fixture
def adapter() -> WazuhAlertAdapter:
    return WazuhAlertAdapter()


def test_parse_auditd_alert_happy_path(adapter: WazuhAlertAdapter) -> None:
    alert = adapter.parse(SAMPLE_AUDITD_ALERT)
    assert alert.alert_id == "QKuawJEBxxxxxxxxxxxx"
    assert alert.agent.agent_id == "001"
    assert alert.agent.name == "Machine-1-New"
    assert alert.agent.ip == "10.0.0.11"
    assert alert.rule.rule_id == "80710"
    assert alert.rule.firedtimes == 3
    assert alert.rule.level == 10  # kept for display, never fed to the model
    assert alert.rule.mitre_tactics == ["TA0004"]
    assert alert.rule.mitre_techniques == ["T1548.003"]
    assert alert.decoder_name == "auditd"
    assert alert.location == "/var/log/audit/audit.log"
    assert "sudo" in (alert.data.command or "")
    assert alert.data.srcip == "10.0.0.42"
    assert alert.data.srcport == "49512"


def test_parse_syscheck_alert_with_changed_attr_list(adapter: WazuhAlertAdapter) -> None:
    alert = adapter.parse(SAMPLE_SYSCHECK_ALERT)
    # changed_attributes was a list in source; adapter flattens it to a string
    assert alert.syscheck.changed_attributes is not None
    assert "md5" in alert.syscheck.changed_attributes
    assert "sha256" in alert.syscheck.changed_attributes
    assert alert.syscheck.md5_after is not None
    assert alert.syscheck.sha256_after is not None
    assert alert.syscheck.event == "modified"


def test_parse_handles_missing_optional_sections(adapter: WazuhAlertAdapter) -> None:
    alert = adapter.parse(SAMPLE_EMPTY_ALERT)
    assert alert.agent.agent_id == "003"
    assert alert.rule.firedtimes is None
    assert alert.data.command is None
    assert alert.syscheck.path is None
    assert alert.decoder_name is None


def test_envelope_keys_are_stripped(adapter: WazuhAlertAdapter) -> None:
    alert = adapter.parse(SAMPLE_AUDITD_ALERT)
    # None of the envelope keys should leak into `extra`
    assert "_index" not in alert.extra
    assert "_id" not in alert.extra
    assert "_score" not in alert.extra


def test_leaky_rule_fields_never_appear_in_extra(adapter: WazuhAlertAdapter) -> None:
    """Constraint C4 / §5.10: description/mitre/groups must not land in `extra`.

    They're preserved in RuleInfo for live-feed display, but `extra` is the
    only place the feature engineer could look for stray fields — if a leaky
    field got in there, a future refactor could accidentally use it.
    """
    alert = adapter.parse(SAMPLE_AUDITD_ALERT)
    rule_extra = alert.extra.get("rule_extra", {})
    assert "description" not in rule_extra
    assert "mitre" not in rule_extra
    assert "groups" not in rule_extra
    assert "level" not in rule_extra


def test_accepts_flat_source_payload(adapter: WazuhAlertAdapter) -> None:
    """Some Wazuh configs emit the `_source` directly, without the envelope."""
    flat = SAMPLE_AUDITD_ALERT["_source"]
    alert = adapter.parse(flat)
    assert alert.alert_id == "QKuawJEBxxxxxxxxxxxx"
    assert alert.agent.agent_id == "001"


def test_missing_agent_raises(adapter: WazuhAlertAdapter) -> None:
    bad = {"_source": {"id": "x", "@timestamp": "2026-04-17T00:00:00Z"}}
    with pytest.raises(ValidationFailedError):
        adapter.parse(bad)


def test_missing_id_raises(adapter: WazuhAlertAdapter) -> None:
    bad = {"_source": {"@timestamp": "2026-04-17T00:00:00Z", "agent": {"id": "1"}}}
    with pytest.raises(ValidationFailedError):
        adapter.parse(bad)


def test_missing_timestamp_raises(adapter: WazuhAlertAdapter) -> None:
    bad = {"_source": {"id": "x", "agent": {"id": "1"}}}
    with pytest.raises(ValidationFailedError):
        adapter.parse(bad)


def test_handles_Z_suffix_and_mitre_singular(adapter: WazuhAlertAdapter) -> None:
    """Some Wazuh versions emit `tactic`/`technique` singular string values."""
    doc = {
        "_source": {
            "id": "z1",
            "@timestamp": "2026-04-17T00:00:00Z",
            "agent": {"id": "9"},
            "rule": {"mitre": {"tactic": "TA0001", "technique": "T1566"}},
        }
    }
    alert = adapter.parse(doc)
    assert alert.rule.mitre_tactics == ["TA0001"]
    assert alert.rule.mitre_techniques == ["T1566"]
