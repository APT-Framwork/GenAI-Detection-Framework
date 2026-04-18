"""Cyber Kill Chain stages.

Integer values match the **training-time label encoding** verified in
`TP2_MLA_TE.ipynb` cell 8 — `BENIGN=0`, attack stages 1..7. Same numbering
is used by `docs/mitre_to_ckc.json`. The Transformer outputs 8 logits in
this exact order; the DQN's `current_ckc_stage` slot in the 13-d state
vector likewise expects 0=BENIGN.
"""

from __future__ import annotations

from enum import IntEnum


class CkcStage(IntEnum):
    BENIGN = 0
    RECONNAISSANCE = 1
    WEAPONIZATION = 2
    DELIVERY = 3
    EXPLOITATION = 4
    INSTALLATION = 5
    COMMAND_AND_CONTROL = 6
    ACTIONS_ON_OBJECTIVES = 7
