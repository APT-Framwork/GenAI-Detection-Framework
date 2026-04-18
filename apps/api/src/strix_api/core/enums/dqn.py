"""DQN action space.

Integer values match the training env's Discrete(5); names are the wire
labels (§6.1). `requires_approval` reflects the §6.2 semantics table —
ISOLATE_HOST and BLOCK_USER_IP are advisory-only in 1.0 per §12 Q3.
"""

from __future__ import annotations

from enum import IntEnum


class DqnAction(IntEnum):
    MONITOR = 0
    LOW_ALERT = 1
    ESCALATE = 2
    ISOLATE_HOST = 3
    BLOCK_USER_IP = 4

    @property
    def is_intervention(self) -> bool:
        """Actions ≥ ESCALATE close an attack chain (§5.4)."""
        return self.value >= DqnAction.ESCALATE.value

    @property
    def requires_approval(self) -> bool:
        """True when `AUTO_RESPONSE_ENABLED=false`, which is 1.0 default (§12 Q3)."""
        return self in (DqnAction.ISOLATE_HOST, DqnAction.BLOCK_USER_IP)
