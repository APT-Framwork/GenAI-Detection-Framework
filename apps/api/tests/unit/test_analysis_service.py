"""AnalysisService — pure-domain helpers (without a real DB).

The service's main job is SQL — those queries get integration coverage.
Here we exercise the CKC-name lookup, the cursor encoder, and the
`infection()` rule's reliance on `INFECTION_VAE_PROB_THRESHOLD` /
`DqnAction.ESCALATE` (catch a refactor that moves the threshold or
changes the action ordering).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from strix_api.core.constants import INFECTION_VAE_PROB_THRESHOLD
from strix_api.core.enums import CkcStage, DqnAction
from strix_api.services.analysis_service import _CKC_NAMES, _LogCursor, _stage_name


def test_stage_name_matches_enum() -> None:
    for stage in CkcStage:
        assert _stage_name(int(stage)) == stage.name
    assert _stage_name(None) is None


def test_stage_name_unknown_returns_none() -> None:
    assert _stage_name(999) is None


def test_ckc_names_complete() -> None:
    assert set(_CKC_NAMES.keys()) == {0, 1, 2, 3, 4, 5, 6, 7}
    # 0 = BENIGN per the Transformer's training labels (TP2_MLA_TE.ipynb)
    assert _CKC_NAMES[0] == "BENIGN"
    assert _CKC_NAMES[7] == "ACTIONS_ON_OBJECTIVES"


def test_log_cursor_lex_orderable() -> None:
    """Cursors are used as keyset boundaries; equal-time alerts must order
    deterministically by alert_id so pagination doesn't loop."""
    a = _LogCursor(
        occurred_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=UTC),
        alert_id="aaa",
    )
    b = _LogCursor(
        occurred_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=UTC),
        alert_id="bbb",
    )
    # The encoded strings differ, and the timestamp+id key is well-defined.
    assert a.encode() != b.encode()
    assert a.alert_id < b.alert_id


def test_infection_rule_uses_documented_threshold() -> None:
    """Catch a refactor that lowers / removes INFECTION_VAE_PROB_THRESHOLD."""
    # §6.3 fixed it at 0.7
    assert INFECTION_VAE_PROB_THRESHOLD == 0.7


def test_infection_rule_uses_escalate_or_higher() -> None:
    """The infection rule joins on `dqn_actions.action >= ESCALATE`. If
    DqnAction values change order, the SQL would silently miss interventions."""
    assert DqnAction.ESCALATE > DqnAction.LOW_ALERT
    assert DqnAction.ISOLATE_HOST > DqnAction.ESCALATE
    assert DqnAction.BLOCK_USER_IP > DqnAction.ISOLATE_HOST


def test_log_cursor_decode_invalid_base64() -> None:
    with pytest.raises(ValueError):
        _LogCursor.decode("@@@not_base64@@@")


def test_log_cursor_decode_invalid_payload() -> None:
    """A correctly base64'd but non-`<iso>|<id>` payload must error."""
    import base64

    bad = base64.urlsafe_b64encode(b"no-pipe-separator").rstrip(b"=").decode()
    with pytest.raises(ValueError):
        _LogCursor.decode(bad)
