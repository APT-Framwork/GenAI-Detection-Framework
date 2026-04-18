"""Cross-cutting wire types. Imported by every tab's schema module.

Conventions from §6.1 + §13:
- snake_case Python ↔ camelCase JSON via `alias_generator=to_camel`.
- `ckcStage` = integer 0..7; `ckcStageName` = display label.
- DQN action names = UPPER_SNAKE_CASE.
- Window selectors = literal strings, same everywhere.
"""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")

WindowLiteral = Literal["15m", "1h", "24h", "7d", "all"]

Severity = Literal["critical", "high", "medium", "low", "info"]

DqnActionName = Literal[
    "MONITOR", "LOW_ALERT", "ESCALATE", "ISOLATE_HOST", "BLOCK_USER_IP"
]

# CKC names come from mitre_to_ckc.json. Kept as a display-only alias.
# Ordering matches `CkcStage` (0=BENIGN, 1..7 attack stages).
CkcStageName = Literal[
    "BENIGN",
    "RECONNAISSANCE",
    "WEAPONIZATION",
    "DELIVERY",
    "EXPLOITATION",
    "INSTALLATION",
    "COMMAND_AND_CONTROL",
    "ACTIONS_ON_OBJECTIVES",
]


class StrixBase(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class Page(StrixBase):
    cursor: str | None = None
    has_more: bool = False


class PaginatedResponse(StrixBase, Generic[T]):
    items: list[T]
    page: Page
