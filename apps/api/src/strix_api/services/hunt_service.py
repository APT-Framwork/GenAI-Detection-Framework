"""Hunt query service — KQL/Lucene-lite parser + SQL builder (Phase 7).

Grammar:
    field:value          → field ∈ {host, user, technique, time}
    field:"value text"   → quoted value with whitespace
    free text            → coalesced into a single `text` token (ILIKE on full_log)

Parsing is **permissive**: malformed input never raises. Tokens that fail
their type check are dropped from the executable set and reported in
`parsed.errors`, so the UI can underline the offending token without losing
the rest of the query.

The grammar is documented in docs/hunt-grammar.md and mirrored in
apps/web/lib/hunt-grammar.ts. The two parsers must produce the same Token[]
shape for a given query string — keep them in sync.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, func, or_, select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.errors import NotFoundError
from strix_api.api.schemas.hunt import (
    HuntParsed,
    HuntQueryResponse,
    HuntResultItem,
    HuntSort,
    HuntToken,
    SavedQueriesResponse,
    SavedQuery,
)
from strix_api.core.enums import CkcStage
from strix_api.repositories.models import Alert, Host, HuntSavedQuery


_TOKEN_RE = re.compile(
    r"""(?P<field>host|user|technique|time)
        :
        (?:
            "(?P<qval>[^"]*)"          # quoted value
          | (?P<val>[^\s"]+)           # bare value
        )""",
    re.VERBOSE | re.IGNORECASE,
)

# `time:` accepts: 1h | 30m | 24h | 7d | iso-date.
_DURATION_RE = re.compile(r"^(\d+)\s*([smhd])$", re.IGNORECASE)

_CKC_NAMES: dict[int, str] = {int(s): s.name for s in CkcStage}


def _stage_name(s: int | None) -> str | None:
    if s is None:
        return None
    return _CKC_NAMES.get(int(s))


def _iso(dt: Any) -> str:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat(timespec="microseconds")
    return str(dt)


# ── Cursor (occurred_at, alert_id) — same shape as analysis service ──


@dataclass(frozen=True)
class _HuntCursor:
    occurred_at: datetime
    alert_id: str

    def encode(self) -> str:
        raw = f"{self.occurred_at.isoformat()}|{self.alert_id}".encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    @classmethod
    def decode(cls, encoded: str) -> "_HuntCursor":
        pad = "=" * (-len(encoded) % 4)
        raw = base64.urlsafe_b64decode(encoded + pad).decode()
        ts, aid = raw.split("|", 1)
        return cls(occurred_at=datetime.fromisoformat(ts), alert_id=aid)


# ── Parser ────────────────────────────────────────────────────────────


def parse_query(q: str) -> HuntParsed:
    """Parse `q` into typed tokens + non-fatal errors.

    Token order is preserved. Free-text tokens (anything that isn't a
    `field:value` match) are coalesced into a single `text` token at the end
    so the SQL builder doesn't have to OR multiple ILIKEs.
    """
    if not q or not q.strip():
        return HuntParsed(tokens=[], errors=[])

    tokens: list[HuntToken] = []
    errors: list[str] = []
    text_chunks: list[str] = []
    cursor = 0

    for m in _TOKEN_RE.finditer(q):
        # Anything between the previous match and this one is free text.
        if m.start() > cursor:
            chunk = q[cursor : m.start()].strip()
            if chunk:
                text_chunks.append(chunk)
        cursor = m.end()

        field_raw = (m.group("field") or "").lower()
        value = m.group("qval") if m.group("qval") is not None else (m.group("val") or "")
        value = value.strip()
        if not value:
            errors.append(f"empty value for `{field_raw}:`")
            continue

        if field_raw == "time":
            ok = _validate_time(value)
            if not ok:
                errors.append(f"`time:{value}` not understood (try 1h, 30m, 24h, 7d, or ISO)")
                continue

        if field_raw == "technique":
            up = value.upper()
            if not re.match(r"^T\d{4}(\.\d{3})?$", up):
                errors.append(f"`technique:{value}` doesn't look like a MITRE id (Txxxx[.yyy])")
                continue
            value = up

        tokens.append(HuntToken(field=field_raw, op="eq", value=value))  # type: ignore[arg-type]

    # Trailing free text.
    if cursor < len(q):
        tail = q[cursor:].strip()
        if tail:
            text_chunks.append(tail)

    if text_chunks:
        tokens.append(HuntToken(field="text", op="contains", value=" ".join(text_chunks)))

    return HuntParsed(tokens=tokens, errors=errors)


def _validate_time(raw: str) -> bool:
    if _DURATION_RE.match(raw):
        return True
    try:
        datetime.fromisoformat(raw)
        return True
    except Exception:  # noqa: BLE001
        return False


def _resolve_time(raw: str, now: datetime) -> datetime | None:
    m = _DURATION_RE.match(raw)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        delta = {
            "s": timedelta(seconds=n),
            "m": timedelta(minutes=n),
            "h": timedelta(hours=n),
            "d": timedelta(days=n),
        }[unit]
        return now - delta
    try:
        d = datetime.fromisoformat(raw)
        if d.tzinfo is None:
            d = d.replace(tzinfo=UTC)
        return d
    except Exception:  # noqa: BLE001
        return None


# ── Service ───────────────────────────────────────────────────────────


class HuntService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def query(
        self,
        *,
        q: str,
        limit: int = 100,
        cursor: str | None = None,
        sort: HuntSort = "ts_desc",
    ) -> HuntQueryResponse:
        parsed = parse_query(q)
        # Default time horizon: 24 h, unless a `time:` token tightens it.
        now = datetime.now(UTC)
        time_floor: datetime = now - timedelta(hours=24)

        host_terms: list[str] = []
        user_terms: list[str] = []
        technique_terms: list[str] = []
        text_terms: list[str] = []

        for t in parsed.tokens:
            if t.field == "host":
                host_terms.append(t.value)
            elif t.field == "user":
                user_terms.append(t.value)
            elif t.field == "technique":
                technique_terms.append(t.value)
            elif t.field == "time":
                resolved = _resolve_time(t.value, now)
                if resolved is not None:
                    time_floor = resolved
            elif t.field == "text":
                text_terms.append(t.value)

        # ---- base query ----
        stmt = (
            select(
                Alert.alert_id,
                Alert.occurred_at,
                Alert.chain_id,
                Alert.host_id,
                Host.agent_name,
                Alert.rule_id,
                Alert.full_log,
                Alert.ckc_stage,
                Alert.mitre_techniques,
            )
            .select_from(Alert)
            .join(Host, Host.host_id == Alert.host_id, isouter=True)
            .where(Alert.occurred_at >= time_floor)
        )

        for h in host_terms:
            stmt = stmt.where(Host.agent_name.ilike(f"%{h}%"))
        for u in user_terms:
            # raw_jsonb is `{}` today (verdicts_writer.py), so we fall back
            # to substring on full_log. Phase 7+ can switch to a JSONB path
            # once raw_jsonb starts carrying decoder fields.
            stmt = stmt.where(Alert.full_log.ilike(f"%{u}%"))
        if technique_terms:
            # `mitre_techniques @> ARRAY[...]` — needs the GIN index from 0007.
            stmt = stmt.where(Alert.mitre_techniques.op("@>")(technique_terms))
        for t in text_terms:
            stmt = stmt.where(Alert.full_log.ilike(f"%{t}%"))

        # ---- approximate total (counted under same predicates) ----
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self._s.execute(count_stmt)).scalar_one())

        # ---- cursor ----
        if cursor:
            try:
                cur = _HuntCursor.decode(cursor)
            except Exception:  # noqa: BLE001
                cur = None
            if cur is not None:
                if sort == "ts_asc":
                    stmt = stmt.where(
                        or_(
                            Alert.occurred_at > cur.occurred_at,
                            and_(
                                Alert.occurred_at == cur.occurred_at,
                                Alert.alert_id > cur.alert_id,
                            ),
                        )
                    )
                else:
                    stmt = stmt.where(
                        or_(
                            Alert.occurred_at < cur.occurred_at,
                            and_(
                                Alert.occurred_at == cur.occurred_at,
                                Alert.alert_id < cur.alert_id,
                            ),
                        )
                    )

        # ---- sort ----
        if sort == "ts_asc":
            stmt = stmt.order_by(Alert.occurred_at.asc(), Alert.alert_id.asc())
        elif sort == "ckc_desc":
            stmt = stmt.order_by(
                desc(Alert.ckc_stage),
                desc(Alert.occurred_at),
                desc(Alert.alert_id),
            )
        else:
            stmt = stmt.order_by(desc(Alert.occurred_at), desc(Alert.alert_id))

        stmt = stmt.limit(limit + 1)
        rows = (await self._s.execute(stmt)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]

        items: list[HuntResultItem] = []
        for r in rows:
            items.append(
                HuntResultItem(
                    alert_id=r.alert_id,
                    ts=_iso(r.occurred_at),
                    chain_id=r.chain_id,
                    host_id=r.host_id,
                    host_name=r.agent_name,
                    rule_id=r.rule_id,
                    description=(r.full_log or "")[:400] or None,
                    ckc_stage=r.ckc_stage,
                    ckc_stage_name=_stage_name(r.ckc_stage),
                    mitre_techniques=list(r.mitre_techniques or []),
                )
            )

        next_cursor: str | None = None
        if has_more and rows:
            tail = rows[-1]
            next_cursor = _HuntCursor(
                occurred_at=tail.occurred_at, alert_id=tail.alert_id
            ).encode()

        return HuntQueryResponse(
            parsed=parsed,
            items=items,
            total=total,
            next_cursor=next_cursor,
        )

    # ── saved queries ──

    async def list_saved(self, *, user_id: UUID) -> SavedQueriesResponse:
        stmt = (
            select(HuntSavedQuery)
            .where(HuntSavedQuery.user_id == user_id)
            .order_by(desc(HuntSavedQuery.created_at))
            .limit(100)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return SavedQueriesResponse(
            items=[
                SavedQuery(
                    saved_id=r.saved_id,
                    name=r.name,
                    q=r.q,
                    created_at=_iso(r.created_at),
                )
                for r in rows
            ]
        )

    async def save(
        self, *, user_id: UUID, name: str, q: str
    ) -> SavedQuery:
        # Upsert by (user_id, name) — saving with the same name overwrites.
        stmt = (
            select(HuntSavedQuery)
            .where(HuntSavedQuery.user_id == user_id)
            .where(HuntSavedQuery.name == name)
            .limit(1)
        )
        existing = (await self._s.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            existing.q = q
            existing.created_at = datetime.now(UTC)
            await self._s.flush()
            row = existing
        else:
            row = HuntSavedQuery(
                saved_id=uuid4(),
                user_id=user_id,
                name=name,
                q=q,
            )
            self._s.add(row)
            await self._s.flush()
        return SavedQuery(
            saved_id=row.saved_id,
            name=row.name,
            q=row.q,
            created_at=_iso(row.created_at),
        )

    async def delete(self, *, user_id: UUID, saved_id: UUID) -> None:
        row = await self._s.get(HuntSavedQuery, saved_id)
        if row is None or row.user_id != user_id:
            raise NotFoundError(f"saved query {saved_id} not found")
        await self._s.delete(row)
        await self._s.flush()
