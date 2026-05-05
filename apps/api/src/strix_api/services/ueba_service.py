"""User-risk (UEBA) aggregator (Phase 9).

The original plan envisioned reading USER nodes from `gnn_graph_snapshots`,
but the snapshot writer (workers/inference.py:_persist_snapshot) emits
alert-keyed nodes (`{alertId, risk}`) without a `kind` discriminator. So
this service falls back to the data we DO have: regex-extract user-like
tokens from `Alert.full_log`, group within the window, and rank.

Risk score formula (documented inline so the front-end caption can refer):
    score = sigmoid( w_a * log(1+alert_count)
                  + w_c * (max_ckc / 7)
                  + w_h * log(1+hosts_touched) ) - 0.5
    with weights tuned so a typical "noisy admin" lands ~0.2 and a
    multi-host high-CKC user lands ~0.85.

When the GNN snapshot starts carrying USER nodes, switch the source —
the response shape (`source` field) advertises the provenance to the UI.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.schemas.ueba import UserChainRef, UserRiskItem, UserRiskResponse
from strix_api.repositories.models import Alert


# Audit / sshd patterns. Highest-confidence first.
#   uid=1000(srsysadmin)        -> srsysadmin
#   euid=0(root)                -> root
#   user=alice (auth.log)       -> alice
#   USER=postgres               -> postgres
#   for invalid user backup     -> backup
_USER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:e?uid|auid)=\d+\(([A-Za-z][A-Za-z0-9_-]{0,31})\)"),
    re.compile(r"\buser=([A-Za-z][A-Za-z0-9_-]{0,31})\b"),
    re.compile(r"\bUSER=([A-Za-z][A-Za-z0-9_-]{0,31})\b"),
    re.compile(r"\bfor (?:invalid )?user ([A-Za-z][A-Za-z0-9_-]{0,31})\b"),
    # sshd: "Accepted password for alice from ..." / "Failed password for alice from ..."
    re.compile(r"\b(?:Accepted|Failed) (?:password|publickey) for ([A-Za-z][A-Za-z0-9_-]{0,31}) from\b"),
)

# Numeric-UID fallback. On the lab boxes Wazuh's auditd decoder emits
# `uid=0 auid=0 …` *without* the `(root)` parenthetical that user-name
# resolution would require. The negative lookahead prevents double-matching
# when the parenthetical IS present (the pattern above handles those).
_NUMERIC_UID_PATTERN = re.compile(r"\b(?:auid|euid|uid)=(\d{1,7})(?!\()")

# Resolution map for the "auditd without name resolution" case. Restricted
# to UIDs whose conventional names are stable across Debian/RHEL/Alpine —
# we don't try to fingerprint the OS. Unknown UIDs fall through (we
# *don't* synthesise `uid:1234` strings — too noisy and it conflicts with
# the dashboard's "real users" framing).
_KNOWN_UIDS: dict[str, str] = {
    "0": "root",
    "1": "daemon",
    "2": "bin",
    "33": "www-data",
    "65534": "nobody",
    # First non-system UIDs on Debian/Ubuntu/Kali. Caldera victim images
    # ship with `1000` as the default agent user and `1001` as a frequent
    # secondary in red-team scenarios.
    "1000": "user",
    "1001": "user2",
}

# Generic / system accounts to suppress unless they're alone.
_SYSTEM_USERS: frozenset[str] = frozenset(
    {"none", "unknown", "(none)", "wazuh", "filebeat", "systemd", "messagebus"}
)


def _extract_users(full_log: str | None) -> list[str]:
    if not full_log:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for pat in _USER_PATTERNS:
        for m in pat.finditer(full_log):
            u = m.group(1)
            if not u or u.lower() in _SYSTEM_USERS:
                continue
            if u not in seen:
                seen.add(u)
                out.append(u)
    # Numeric-UID fallback for auditd without name resolution. Run only when
    # the higher-confidence patterns came back empty (preferred): if a name
    # was already extracted we trust that over a numeric mapping. Otherwise
    # the same alert can credit both `root` and `0` as separate users.
    if not out:
        for m in _NUMERIC_UID_PATTERN.finditer(full_log):
            uid = m.group(1)
            name = _KNOWN_UIDS.get(uid)
            if not name:
                continue
            if name in seen or name in _SYSTEM_USERS:
                continue
            seen.add(name)
            out.append(name)
    return out


def _iso(dt: Any) -> str:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat(timespec="microseconds")
    return str(dt)


def _risk_score(alert_count: int, max_ckc: int, hosts_touched: int) -> float:
    # See module docstring for derivation.
    w_a, w_c, w_h = 0.6, 1.4, 0.5
    z = (
        w_a * math.log1p(alert_count)
        + w_c * (max(0, min(7, max_ckc)) / 7.0)
        + w_h * math.log1p(hosts_touched)
    )
    sig = 1.0 / (1.0 + math.exp(-(z - 1.5)))  # offset so noisy admin ~0.2
    return round(max(0.0, min(1.0, sig)), 3)


class UebaService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def top_users(
        self,
        *,
        since: datetime | None = None,
        limit: int = 20,
    ) -> UserRiskResponse:
        now = datetime.now(UTC)
        window_end = now
        window_start = since or (now - timedelta(hours=24))

        # Pull alert rows in window. Bound the scan with a generous cap;
        # at lab scale this is a few thousand rows. We avoid pushing the
        # regex into SQL — it'd be a sequential scan anyway.
        stmt = (
            select(
                Alert.alert_id,
                Alert.host_id,
                Alert.chain_id,
                Alert.full_log,
                Alert.ckc_stage,
                Alert.occurred_at,
            )
            .where(Alert.occurred_at >= window_start)
            .where(Alert.full_log.isnot(None))
            .order_by(desc(Alert.occurred_at))
            .limit(20_000)
        )
        rows = (await self._s.execute(stmt)).all()

        # user → aggregate
        agg: dict[str, dict[str, Any]] = {}
        for r in rows:
            users = _extract_users(r.full_log)
            if not users:
                continue
            for u in users:
                a = agg.setdefault(
                    u,
                    {
                        "alert_count": 0,
                        "hosts": set[UUID](),
                        "chains": {},  # chain_id -> max_ckc seen
                        "max_ckc": 0,
                        "last_seen": None,
                    },
                )
                a["alert_count"] += 1
                if r.host_id is not None:
                    a["hosts"].add(r.host_id)
                if r.chain_id is not None:
                    prev = a["chains"].get(r.chain_id, 0)
                    a["chains"][r.chain_id] = max(prev, int(r.ckc_stage or 0))
                a["max_ckc"] = max(a["max_ckc"], int(r.ckc_stage or 0))
                if a["last_seen"] is None or (r.occurred_at and r.occurred_at > a["last_seen"]):
                    a["last_seen"] = r.occurred_at

        items: list[UserRiskItem] = []
        for u, a in agg.items():
            score = _risk_score(
                alert_count=int(a["alert_count"]),
                max_ckc=int(a["max_ckc"]),
                hosts_touched=len(a["hosts"]),
            )
            top_chains = sorted(
                a["chains"].items(), key=lambda kv: -kv[1]
            )[:3]
            items.append(
                UserRiskItem(
                    user=u,
                    risk_score=score,
                    alert_count=int(a["alert_count"]),
                    hosts_touched=len(a["hosts"]),
                    chain_count=len(a["chains"]),
                    max_ckc_stage=int(a["max_ckc"]),
                    last_seen=_iso(a["last_seen"]) if a["last_seen"] else None,
                    top_chains=[
                        UserChainRef(chain_id=cid, max_ckc_stage=int(mc))
                        for cid, mc in top_chains
                    ],
                )
            )

        items.sort(key=lambda it: (-it.risk_score, -it.alert_count, it.user))
        items = items[:limit]

        return UserRiskResponse(
            items=items,
            window_start=_iso(window_start),
            window_end=_iso(window_end),
            source="alerts.full_log",
        )
