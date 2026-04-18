"""Per-alert port of `FeatureEngineerNoLeakage` (feature_selection_final.ipynb cell 7).

The notebook processes a DataFrame of alerts in one call. At inference we
process one alert at a time. This module keeps the per-alert transforms
that produce the **23 individual features** in the canonical Top-25 schema:

  selected_features_top25.json → all_selected_columns[0:23]

SecBERT embeddings (+ PCA) for command and full_log are NOT computed here —
they need the SecBERT model and the two fitted PCAs, which live in
`adapters/preprocessing_pipeline.py` (per §3.4 layer rules).
"""

from __future__ import annotations

import ipaddress
import math
from collections.abc import Mapping
from typing import Final

import numpy as np

from strix_api.core.raw_alert import RawAlert

# ---------------------------------------------------------------- tables

#: Paths considered sensitive (matches the notebook's `sensitive_dirs`).
_SENSITIVE_DIRS: Final[tuple[str, ...]] = (
    "/etc",
    "/var/log",
    "/home",
    "/root",
    "/bin",
    "/sbin",
    "/usr/bin",
    "/tmp",
    "/var/www",
)

#: Paths considered temp-like (matches `/tmp` and `/temp` heuristic).
_TEMP_DIRS: Final[tuple[str, ...]] = ("/tmp", "/temp")

#: Canonical 23 individual features in the Top-25 ordering
#: (selected_features_top25.json → all_selected_columns[0:23]).
_INDIVIDUAL_FEATURES_ORDER: Final[tuple[str, ...]] = (
    "decoder_auditd",
    "firedtimes",
    "location__var_log_audit_audit.log",
    "srcip_is_private",
    "decoder_web-accesslog",
    "location__var_log_apache2_access.log",
    "firedtimes_log",
    "path_is_missing",
    "has_md5",
    "cmd_length",
    "has_sha256",
    "syscheck_added",
    "cmd_is_missing",
    "decoder_dpkg-decoder",
    "syscheck_deleted",
    "path_depth",
    "syscheck_modified",
    "location__var_log_auth.log",
    "decoder_syscheck_deleted",
    "path_is_sensitive",
    "decoder_syscheck_integrity_changed",
    "location_syscheck",
    "path_is_temp",
)

#: Decoder values that appear in the Top-25 ordering (as decoder_* one-hots).
_DECODER_VALUES: Final[tuple[str, ...]] = (
    "auditd",
    "web-accesslog",
    "dpkg-decoder",
    "syscheck_deleted",
    "syscheck_integrity_changed",
)

#: Location one-hot column_name → original raw value. The column-name format
#: `location_<normalised>` is reproduced from the notebook:
#:   col_name = f'location_{str(loc)[:30].replace("/","_").replace(" ","_")}'
_LOCATION_VALUES: Final[dict[str, str]] = {
    "location__var_log_audit_audit.log": "/var/log/audit/audit.log",
    "location__var_log_apache2_access.log": "/var/log/apache2/access.log",
    "location__var_log_auth.log": "/var/log/auth.log",
    "location_syscheck": "syscheck",
}

#: Strings that count as "missing" for string-valued Wazuh fields.
_MISSING_SENTINELS: Final[frozenset[str]] = frozenset({"", "none", "None", "null"})


# ---------------------------------------------------------------- helpers


def _is_private_ip(ip: str | None) -> int:
    """Returns 1 (private), 0 (public), or -1 (missing / unparseable).

    Matches the notebook's `_is_private_ip` exactly — preserving the `-1`
    sentinel is important because the training-time StandardScaler saw it
    as a numeric value, not as NaN.
    """
    if ip is None or ip.strip() in _MISSING_SENTINELS:
        return -1
    try:
        return 1 if ipaddress.ip_address(ip.strip()).is_private else 0
    except (ValueError, TypeError):
        return -1


def _path_features(path: str | None) -> tuple[int, int, int, int, int]:
    """Returns (is_missing, depth_clipped, is_sensitive, is_temp, is_hidden_unused).

    Depth is clipped to 15 (matches notebook's `min(depth, 15)`).
    Only the 4 fields needed by the Top-25 schema are returned to the caller
    below; `is_hidden` is computed for compatibility with a future full-119
    path back but unused in the 55-col output.
    """
    if not path:
        return 1, 0, 0, 0, 0
    depth = min(path.count("/"), 15)
    is_sensitive = int(any(d in path for d in _SENSITIVE_DIRS))
    is_temp = int(any(d in path for d in _TEMP_DIRS))
    is_hidden = int("/." in path)  # not in Top-25 but computed for symmetry
    return 0, depth, is_sensitive, is_temp, is_hidden


def _cmd_length_and_missing(cmd: str | None) -> tuple[int, int]:
    if cmd is None or cmd.strip() == "":
        return 0, 1
    return len(cmd), 0


def _syscheck_event_flags(event: str | None) -> tuple[int, int, int]:
    """Returns (added, modified, deleted) substring flags."""
    if not event:
        return 0, 0, 0
    e = event.lower()
    return (
        int("added" in e),
        int("modified" in e),
        int("deleted" in e),
    )


def _has_hash(h: str | None) -> int:
    return 1 if h and h.strip() else 0


# ---------------------------------------------------------------- engineer


class FeatureEngineerNoLeakage:
    """Per-alert, stateless. One instance can serve every worker thread.

    Public API:
      * `engineer(alert)` → dict[str, float] keyed by feature name.
      * `to_array(alert)` → np.ndarray shape (23,) dtype float32, in the
        canonical Top-25 ordering (for direct consumption by the
        preprocessing pipeline that will concat with SecBERT PCAs to 55-dim).
    """

    INDIVIDUAL_FEATURES: Final[tuple[str, ...]] = _INDIVIDUAL_FEATURES_ORDER
    DECODER_VALUES: Final[tuple[str, ...]] = _DECODER_VALUES
    LOCATION_VALUES: Final[dict[str, str]] = _LOCATION_VALUES

    def engineer(self, alert: RawAlert) -> dict[str, float]:
        """Extract the 23 individual features as a name→value dict."""
        # Firedtimes (float)
        firedtimes = float(alert.rule.firedtimes or 0)
        firedtimes_log = math.log1p(firedtimes)

        # IP
        srcip_is_private = _is_private_ip(alert.data.srcip)

        # Path
        path_is_missing, path_depth, path_is_sensitive, path_is_temp, _ = _path_features(
            alert.syscheck.path
        )

        # Command
        cmd_length, cmd_is_missing = _cmd_length_and_missing(alert.data.command)

        # Hash presence
        has_md5 = _has_hash(alert.syscheck.md5_after)
        has_sha256 = _has_hash(alert.syscheck.sha256_after)

        # Syscheck event substring flags
        syscheck_added, syscheck_modified, syscheck_deleted = _syscheck_event_flags(
            alert.syscheck.event
        )

        # Decoder one-hots (top-5 decoder values from training vocabulary)
        decoder = alert.decoder_name or ""
        decoder_flags = {f"decoder_{v}": float(decoder == v) for v in _DECODER_VALUES}

        # Location one-hots (top-4 location values from training vocabulary)
        location = alert.location or ""
        location_flags = {
            col_name: float(location == raw) for col_name, raw in _LOCATION_VALUES.items()
        }

        features: dict[str, float] = {
            "firedtimes": firedtimes,
            "firedtimes_log": firedtimes_log,
            "srcip_is_private": float(srcip_is_private),
            "path_is_missing": float(path_is_missing),
            "path_depth": float(path_depth),
            "path_is_sensitive": float(path_is_sensitive),
            "path_is_temp": float(path_is_temp),
            "cmd_length": float(cmd_length),
            "cmd_is_missing": float(cmd_is_missing),
            "has_md5": float(has_md5),
            "has_sha256": float(has_sha256),
            "syscheck_added": float(syscheck_added),
            "syscheck_modified": float(syscheck_modified),
            "syscheck_deleted": float(syscheck_deleted),
            **decoder_flags,
            **location_flags,
        }

        # Guard: every canonical feature must be present.
        missing = [n for n in _INDIVIDUAL_FEATURES_ORDER if n not in features]
        if missing:  # pragma: no cover — defensive; table is static
            raise RuntimeError(f"feature engineer produced incomplete dict: {missing}")
        return features

    def to_array(self, alert_or_features: RawAlert | Mapping[str, float]) -> np.ndarray:
        """Shape (23,), dtype float32, in canonical Top-25 order."""
        if isinstance(alert_or_features, RawAlert):
            features = self.engineer(alert_or_features)
        else:
            features = alert_or_features
        return np.array(
            [features[name] for name in _INDIVIDUAL_FEATURES_ORDER],
            dtype=np.float32,
        )

    @staticmethod
    def text_inputs(alert: RawAlert) -> tuple[str, str]:
        """Return (command_text, full_log_text) for SecBERT embedding.

        Matches the notebook's cleaning: empty/None becomes `[EMPTY]`,
        long strings truncated to 2000 chars (tokenizer further truncates
        to 128 tokens).
        """

        def _clean(s: str | None) -> str:
            if not s or not s.strip():
                return "[EMPTY]"
            return s[:2000]

        return _clean(alert.data.command), _clean(alert.full_log)


__all__ = ["FeatureEngineerNoLeakage"]
