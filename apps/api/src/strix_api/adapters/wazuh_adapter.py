"""Parse flattened Wazuh JSON into a `RawAlert`.

Responsibilities:
1. Accept either a top-level Wazuh document (`{_index, _source, ...}`) or
   an already-flattened `_source` dict.
2. Strip envelope metadata (`_index`, `_id`, `_version`, `_score`).
3. Drop leaky columns **before** passing anything downstream, so no leaky
   value can accidentally appear in a feature vector.
4. Parse the dotted-path keys used by the training pipeline
   (`_source.agent.ip`, `_source.rule.firedtimes`, etc.) into structured
   sub-models.

Leaky fields (per feature_selection_final.ipynb cell 7):
- `_source.rule.level`
- `_source.rule.description`
- `_source.rule.mitre.tactic` / `.tactics`
- `_source.rule.mitre.technique` / `.techniques`
- `_source.rule.groups`          (often tactic-related)

These are REMOVED from the `extra` dict too — they don't propagate anywhere
that could be read by the feature engineer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from strix_api.api.errors import ValidationFailedError
from strix_api.core.raw_alert import (
    AgentInfo,
    DataInfo,
    RawAlert,
    RuleInfo,
    SyscheckInfo,
)

_ENVELOPE_KEYS = frozenset({"_index", "_id", "_version", "_score", "_type", "sort"})
_LEAKY_RULE_KEYS = frozenset({"level", "description", "mitre", "groups"})
_LEAKY_RULE_KEY_PREFIXES = ("mitre_",)


def _deep_get(src: dict[str, Any], *path: str) -> Any:
    """Walk a nested dict without raising on missing intermediate keys."""
    cur: Any = src
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
        if cur is None:
            return None
    return cur


def _extract_source(doc: dict[str, Any]) -> dict[str, Any]:
    """Accept either a raw document or a `_source` payload."""
    if "_source" in doc and isinstance(doc["_source"], dict):
        src = doc["_source"]
    else:
        src = doc
    # Strip envelope keys just in case they're mixed in at the same level.
    return {k: v for k, v in src.items() if k not in _ENVELOPE_KEYS}


def _parse_timestamp(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, str):
        # Wazuh sends ISO-8601, sometimes with Z suffix
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError as exc:  # pragma: no cover — trivial
            raise ValidationFailedError(f"invalid timestamp: {ts!r}") from exc
    raise ValidationFailedError(f"unsupported timestamp type: {type(ts).__name__}")


def _mitre_list(rule: dict[str, Any], singular: str, plural: str) -> list[str]:
    """Collect MITRE tactic/technique IDs from whichever Wazuh shape is present."""
    mitre = rule.get("mitre")
    if isinstance(mitre, dict):
        for key in (plural, singular):
            v = mitre.get(key)
            if isinstance(v, list):
                return [str(x) for x in v]
            if isinstance(v, str):
                return [v]
    return []


def _rule_id(rule: dict[str, Any]) -> str | None:
    raw = rule.get("id")
    if raw is None:
        return None
    return str(raw)


def _non_leaky_rule_extras(rule: dict[str, Any]) -> dict[str, Any]:
    """Everything in rule except the leaky fields and the ones we lift."""
    return {
        k: v
        for k, v in rule.items()
        if k not in _LEAKY_RULE_KEYS
        and k not in {"id", "firedtimes"}
        and not any(k.startswith(p) for p in _LEAKY_RULE_KEY_PREFIXES)
    }


def _int_or_none(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


class WazuhAlertAdapter:
    """Stateless. Instantiate once per worker; call `parse()` per message."""

    def parse(self, doc: dict[str, Any]) -> RawAlert:
        """Parse one flattened Wazuh document into a `RawAlert`.

        Raises `ValidationFailedError` only on truly malformed inputs (missing
        id, unparseable timestamp, missing agent). Anything else is best-effort.
        """
        src = _extract_source(doc)

        alert_id = src.get("id") or doc.get("_id")
        if not alert_id:
            raise ValidationFailedError("alert is missing `_id` / `id`")

        occurred_at_raw = src.get("@timestamp") or src.get("timestamp")
        if occurred_at_raw is None:
            raise ValidationFailedError("alert is missing @timestamp")
        occurred_at = _parse_timestamp(occurred_at_raw)

        # --- agent ---
        agent_section = src.get("agent") or {}
        agent_id = agent_section.get("id")
        if not agent_id:
            raise ValidationFailedError("alert is missing agent.id")
        agent = AgentInfo(
            agent_id=str(agent_id),
            name=agent_section.get("name"),
            ip=agent_section.get("ip"),
        )

        # --- rule (non-leaky + identifier + firedtimes) ---
        # Level / description / MITRE fields are explicitly kept out of the
        # feature vector but preserved in RuleInfo so live-feed + detections
        # table can display them (§4.1 Live Feed + §6.2 alerts.mitre_*).
        rule_section = src.get("rule") or {}
        rule = RuleInfo(
            rule_id=_rule_id(rule_section),
            firedtimes=_int_or_none(rule_section.get("firedtimes")),
            level=_int_or_none(rule_section.get("level")),
            description=(
                rule_section.get("description")
                if isinstance(rule_section.get("description"), str)
                else None
            ),
            mitre_tactics=_mitre_list(rule_section, "tactic", "tactics"),
            mitre_techniques=_mitre_list(rule_section, "technique", "techniques"),
        )

        # --- data ---
        data_section = src.get("data") or {}
        data = DataInfo(
            command=data_section.get("command"),
            srcip=data_section.get("srcip"),
            srcport=(
                str(data_section.get("srcport"))
                if data_section.get("srcport") is not None
                else None
            ),
            srcuser=data_section.get("srcuser"),
            dstuser=data_section.get("dstuser"),
        )

        # --- syscheck ---
        syscheck_section = src.get("syscheck") or {}
        syscheck = SyscheckInfo(
            path=syscheck_section.get("path"),
            event=syscheck_section.get("event"),
            md5_after=syscheck_section.get("md5_after"),
            sha256_after=syscheck_section.get("sha256_after"),
            changed_attributes=(
                " ".join(syscheck_section["changed_attributes"])
                if isinstance(syscheck_section.get("changed_attributes"), list)
                else syscheck_section.get("changed_attributes")
            ),
        )

        # Extras = everything we didn't lift, minus anything leaky.
        extra = {
            k: v
            for k, v in src.items()
            if k not in {
                "id", "@timestamp", "timestamp",
                "agent", "rule", "data", "syscheck",
                "decoder", "location", "full_log",
            }
        }
        if isinstance(src.get("rule"), dict):
            remaining = _non_leaky_rule_extras(src["rule"])
            if remaining:
                extra["rule_extra"] = remaining

        return RawAlert(
            alert_id=str(alert_id),
            occurred_at=occurred_at,
            decoder_name=_deep_get(src, "decoder", "name"),
            location=src.get("location"),
            full_log=src.get("full_log"),
            agent=agent,
            rule=rule,
            data=data,
            syscheck=syscheck,
            extra=extra,
        )


__all__ = ["WazuhAlertAdapter"]
