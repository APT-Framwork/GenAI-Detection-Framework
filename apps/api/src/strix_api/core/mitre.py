"""MITRE ATT&CK → CKC stage mapping.

Loads `docs/mitre_to_ckc.json` once and provides O(1) lookups by:
  * tactic ID  ('TA0001'…)
  * tactic name ('Initial Access', 'Execution', …)
  * technique ID ('T1566', 'T1059', …)
  * technique name ('Phishing', 'Command and Scripting Interpreter', …)

Resolution rules (per JSON `phase_priority`): when a single alert lists
multiple tactics/techniques mapping to different CKC stages, take the
EARLIEST stage (smallest non-zero value) — the rationale being that
detecting at the earliest plausible stage gives the SOC the most lead time.

Returned `CkcStage`:
  - BENIGN (0)   if no MITRE info is present
  - 1..7         from the JSON mapping
  - BENIGN (0)   if a tactic/technique resolves to "Unknown" (-1) or 0

The JSON file ships in `docs/mitre_to_ckc.json` and is read at import time;
every worker holds the same singleton via `get_mitre_mapper()`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from strix_api.core.enums import CkcStage


def _resolve_default_mitre_path() -> Path:
    """Find docs/mitre_to_ckc.json across dev tree + container layouts.

    Layouts we support:
      - dev:  apps/api/src/strix_api/core/mitre.py → repo-root/docs/...
      - container: /app/src/strix_api/core/mitre.py → /app/docs/... (we COPY
        docs/ into the runtime image)
      - $STRIX_MITRE_PATH env var override (operator escape hatch)
    """
    import os
    if env := os.environ.get("STRIX_MITRE_PATH"):
        return Path(env)
    here = Path(__file__).resolve()
    # Walk up checking for a "docs/mitre_to_ckc.json" sibling.
    for parent in here.parents:
        candidate = parent / "docs" / "mitre_to_ckc.json"
        if candidate.exists():
            return candidate
    # Last-resort: assume dev tree depth (parents[5]) — preserves old behaviour.
    return here.parents[5] / "docs" / "mitre_to_ckc.json"


_DEFAULT_PATH = _resolve_default_mitre_path()


class MitreMapper:
    """Stateless after construction — mappings are read-only."""

    def __init__(
        self,
        *,
        tactic_id_to_ckc: dict[str, int],
        tactic_name_to_ckc: dict[str, int],
        technique_id_to_ckc: dict[str, int],
        technique_name_to_ckc: dict[str, int],
    ) -> None:
        # Normalise lookup keys (case-insensitive for names; IDs stay as-is).
        self._tactic_id = {k: v for k, v in tactic_id_to_ckc.items()}
        self._tactic_name = {k.lower(): v for k, v in tactic_name_to_ckc.items()}
        self._tech_id = {k: v for k, v in technique_id_to_ckc.items()}
        self._tech_name = {k.lower(): v for k, v in technique_name_to_ckc.items()}

    # ---- single-token lookups ----------------------------------------

    def tactic(self, value: str | None) -> CkcStage | None:
        if not value:
            return None
        # Try ID first, then name.
        v = self._tactic_id.get(value)
        if v is None:
            v = self._tactic_name.get(value.lower())
        return _to_enum(v)

    def technique(self, value: str | None) -> CkcStage | None:
        if not value:
            return None
        # Some Wazuh feeds emit `T1566.001` (technique.subtechnique).
        # Try the full string, then the parent technique.
        v = self._tech_id.get(value)
        if v is None and "." in value:
            v = self._tech_id.get(value.split(".", 1)[0])
        if v is None:
            v = self._tech_name.get(value.lower())
        return _to_enum(v)

    # ---- alert-level resolution --------------------------------------

    def resolve(
        self,
        *,
        tactics: Iterable[str] = (),
        techniques: Iterable[str] = (),
    ) -> CkcStage:
        """Earliest stage wins. Returns BENIGN when nothing maps."""
        candidates: list[int] = []
        for t in tactics:
            stage = self.tactic(t)
            if stage is not None and stage != CkcStage.BENIGN:
                candidates.append(int(stage))
        for t in techniques:
            stage = self.technique(t)
            if stage is not None and stage != CkcStage.BENIGN:
                candidates.append(int(stage))
        if not candidates:
            return CkcStage.BENIGN
        return CkcStage(min(candidates))


def _to_enum(v: int | None) -> CkcStage | None:
    if v is None:
        return None
    if v < 0 or v > 7:
        # JSON sentinels (-1 = "Unknown") fall back to BENIGN per resolution_rules
        return CkcStage.BENIGN
    return CkcStage(v)


@lru_cache(maxsize=1)
def get_mitre_mapper(path: str | None = None) -> MitreMapper:
    """Singleton — workers + tests share one instance."""
    p = Path(path) if path else _DEFAULT_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))

    def _ckc_int(v: object) -> int:
        if isinstance(v, int):
            return v
        if isinstance(v, dict) and "ckc" in v:
            return int(v["ckc"])
        return 0

    return MitreMapper(
        tactic_id_to_ckc={k: _ckc_int(v) for k, v in raw.get("tactic_id_to_ckc", {}).items()},
        tactic_name_to_ckc={k: _ckc_int(v) for k, v in raw.get("tactic_name_to_ckc", {}).items()},
        technique_id_to_ckc={k: _ckc_int(v) for k, v in raw.get("technique_id_to_ckc", {}).items()},
        technique_name_to_ckc={k: _ckc_int(v) for k, v in raw.get("technique_name_to_ckc", {}).items()},
    )


__all__ = ["MitreMapper", "get_mitre_mapper"]
