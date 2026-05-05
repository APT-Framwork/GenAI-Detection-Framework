"""Shared MITRE catalog loader for the ATT&CK Coverage Matrix.

Used by:
  * `services/mitre_service.py`  — the matrix aggregation query.
  * `adapters/wazuh_adapter.py`  — normalises Wazuh's `<mitre><technique>`
    values at ingest, so technique *names* the ruleset emits ("Process
    Discovery") get translated to ATT&CK *IDs* ("T1057") that downstream
    consumers (matrix, RL frame, hunt facets) can join on.

Why this exists: at least one Wazuh ruleset on the lab profile emits the
human-readable technique name in the `<mitre><technique>` field instead of
the ATT&CK ID. Persisting that name verbatim breaks every catalog-keyed
join — the matrix shows a column of zeroes while the DB is full of
detections, because the SQL `GROUP BY technique` produces names like
"Web Protocols" that never match the catalog's `T1071`.

The catalogue itself ships as `data/mitre_catalog.json` and is the source
of truth for both technique IDs *and* names — so we build the name → ID
index directly from it without needing a separate dictionary.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "mitre_catalog.json"


@lru_cache(maxsize=1)
def catalog_data() -> dict[str, Any]:
    """Raw catalog (loaded once and shared)."""
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def name_to_id() -> dict[str, str]:
    """Lower-cased technique name (or alias) → canonical ATT&CK ID.

    Built from the same catalog the matrix joins on, so any technique
    present in a column header gets a name → ID entry. Two name entries
    from different tactics map to the same ID (techniques can belong to
    multiple tactics) — that's fine, the value is identical.

    Each technique entry may also declare an ``aliases`` list of strings.
    These are useful for sub-technique names that Wazuh emits in place of
    the parent (e.g. ``"Web Protocols"`` is the sub-technique name for
    ``T1071.001`` whose parent is ``T1071`` "Application Layer Protocol").
    Aliases resolve to the parent ID; the matrix's `_parent` rollup then
    leaves them where they are.
    """
    out: dict[str, str] = {}
    for tactic in catalog_data().get("tactics", []):
        for tech in tactic.get("techniques", []):
            tid = tech.get("id")
            tname = tech.get("name")
            if not isinstance(tid, str):
                continue
            if isinstance(tname, str):
                out[tname.lower().strip()] = tid
            for alias in tech.get("aliases", []) or []:
                if isinstance(alias, str):
                    out[alias.lower().strip()] = tid
    return out


def normalise_technique(value: str) -> str:
    """Translate a Wazuh-emitted technique value to its canonical ID.

    * Pass-through when already an ID-shape (`T` followed by digits, with
      optional `.subtechnique`). The matrix rolls up sub-techniques to
      parents itself, so we keep the full string here.
    * Lookup by lower-cased name when the value is human-readable.
    * Pass-through unchanged otherwise — drift will be reported by the
      matrix's `other_unmatched_ids` so an operator notices.
    """
    if not value:
        return value
    s = value.strip()
    # Cheap shape check: T-prefix + digit. Sub-technique form `T1078.004` is
    # also accepted and handled downstream.
    if len(s) >= 2 and (s[0] in "Tt") and s[1:2].isdigit():
        return s if s[0] == "T" else "T" + s[1:]
    return name_to_id().get(s.lower(), s)


__all__ = ["catalog_data", "name_to_id", "normalise_technique"]
