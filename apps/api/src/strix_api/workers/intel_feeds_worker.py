"""Background worker that pulls subscribed CTI feeds into intel_indicators.

Reads enabled rows from `intel_feeds`, polls each at its configured
`pull_interval_s`, parses the response into (indicator, indicator_type)
tuples, and upserts them into `intel_indicators` with:

  - source_feed_id   = the feed's UUID
  - source_label     = a short slug ('urlhaus', 'feodotracker', ...)
  - confidence       = feed's default_confidence
  - tlp              = feed's default_tlp
  - first_seen / last_seen     = NOW() (when WE saw it; the feed's
                                  own observation timestamps live in
                                  the indicator payload field)
  - valid_from / valid_until   = NOW() / NOW() + 30d  (feed-supplied IOCs
                                  shouldn't live forever)

After each pull, `intel_feeds.last_pulled_at` / `last_status` /
`last_indicator_count` get stamped so the UI can show feed health.

Design notes
------------
- **Per-feed try/except.** A single broken feed must never break the
  pull loop for the others.
- **Per-pull transaction.** Either every indicator from a pull lands,
  or none do — the UI's "last_indicator_count" shouldn't lie.
- **Bounded payload size.** We cap the response at ~5 MB so a runaway
  feed can't OOM the worker. (URLhaus json_recent is ~2 MB typically.)
- **No retries inside the worker.** If a pull fails, the next interval
  retries naturally. Adding retry/backoff here would double-poll.
"""

from __future__ import annotations

import asyncio
import json
import re
import signal
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.observability import configure_logging
from strix_api.repositories.database import init_engine, session_scope
from strix_api.settings import get_settings


_USER_AGENT = "STRIX-CTI/0.1 (+https://strix.local; abuse@strix.local)"
_MAX_BYTES = 20 * 1024 * 1024  # 20 MB hard cap per pull
_HTTP_TIMEOUT_S = 30
# Loop tick — we sleep this long between scans of the feeds table.
# Each individual feed honours its own pull_interval_s via last_pulled_at.
_TICK_S = 30


# ---------------------------------------------------------------- parsers

_IPV4_RE = re.compile(
    r"^(?:25[0-5]|2[0-4]\d|[01]?\d?\d)"
    r"(?:\.(?:25[0-5]|2[0-4]\d|[01]?\d?\d)){3}$"
)


def _parse_urlhaus(payload: dict[str, Any]) -> list[tuple[str, str, dict]]:
    """URLhaus json_recent → list of (indicator, type, extra_payload).

    The response is a dict keyed by URLhaus URL ID, each value is a list
    of dicts. From each entry we emit:
      - the URL itself (type='url')
      - the host part of the URL as ip OR domain
      - the payload SHA-256 if attached (type='hash')
    """
    out: list[tuple[str, str, dict]] = []
    for _key, entries in payload.items():
        if not isinstance(entries, list):
            continue
        for e in entries:
            if not isinstance(e, dict):
                continue
            url = e.get("url")
            # json_online doesn't carry a separate `host` field — parse
            # it from the URL ourselves. json_recent has both; either
            # path works.
            host = e.get("host")
            if not host and url:
                try:
                    parsed = urllib.parse.urlparse(url)
                    host = (parsed.hostname or "").strip()
                except Exception:  # noqa: BLE001
                    host = ""
            tags = e.get("tags") or []
            threat = e.get("threat") or ""
            payload_meta = {
                "tags": tags if isinstance(tags, list) else [tags],
                "threat": threat,
                "date_added": e.get("date_added") or e.get("dateadded"),
                "reporter": e.get("reporter"),
                "url_status": e.get("url_status"),
            }
            if url:
                out.append((url, "url", payload_meta))
            if host:
                ind_type = "ip" if _IPV4_RE.match(host) else "domain"
                out.append((host, ind_type, payload_meta))
            # URLhaus may attach multiple payloads; iterate.
            for p in e.get("payloads") or []:
                if not isinstance(p, dict):
                    continue
                sha = (p.get("response_sha256") or "").lower()
                if sha and re.fullmatch(r"[a-f0-9]{64}", sha):
                    out.append((sha, "hash", {
                        "filename": p.get("filename"),
                        "file_type": p.get("file_type"),
                        "signature": p.get("signature"),
                    }))
    return out


def _parse_feodo(payload: list[dict] | dict) -> list[tuple[str, str, dict]]:
    """FeodoTracker ipblocklist → list of (ip, 'ip', extra_payload).

    The endpoint returns a JSON array of IP entries with malware family,
    first-seen, last-online, port, etc.
    """
    out: list[tuple[str, str, dict]] = []
    rows = payload if isinstance(payload, list) else payload.get("ip_addresses", [])
    for e in rows:
        if not isinstance(e, dict):
            continue
        ip = e.get("ip_address") or e.get("ip")
        if not ip or not _IPV4_RE.match(ip):
            continue
        out.append((
            ip,
            "ip",
            {
                "malware": e.get("malware") or e.get("malware_alias"),
                "port": e.get("port"),
                "first_seen": e.get("first_seen"),
                "last_online": e.get("last_online"),
                "confidence_level": e.get("confidence_level"),
            },
        ))
    return out


# Dispatch table keyed by URL fragment so we can support multiple
# abuse.ch feeds under the same `kind='abuse_ch'`.
_URL_PARSERS: list[tuple[str, str]] = [
    ("urlhaus.abuse.ch", "urlhaus"),
    ("feodotracker.abuse.ch", "feodotracker"),
]


def _parser_slug_for(url: str) -> str | None:
    for needle, slug in _URL_PARSERS:
        if needle in url:
            return slug
    return None


# ---------------------------------------------------------------- HTTP

def _pull(url: str) -> Any:
    """Sync HTTP GET with size cap. Returns parsed JSON or raises."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:
        raw = resp.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            raise RuntimeError(f"response too large (>{_MAX_BYTES} bytes)")
    return json.loads(raw.decode("utf-8", errors="replace"))


# ---------------------------------------------------------------- upsert

_INDICATOR_UPSERT = text(
    """
    INSERT INTO intel_indicators (
        indicator_id, indicator, indicator_type, confidence, tlp,
        source_feed_id, source_label,
        first_seen, last_seen,
        first_seen_internal, last_seen_internal, internal_hit_count,
        valid_from, valid_until,
        tags, payload, created_at
    ) VALUES (
        :indicator_id, :indicator, :indicator_type, :confidence, :tlp,
        :source_feed_id, :source_label,
        NOW(), NOW(),
        NULL, NULL, 0,
        NOW(), NOW() + INTERVAL '30 days',
        :tags, :payload, NOW()
    )
    ON CONFLICT (indicator, indicator_type, source_label) DO UPDATE SET
        last_seen   = NOW(),
        valid_until = NOW() + INTERVAL '30 days',
        confidence  = GREATEST(intel_indicators.confidence, EXCLUDED.confidence),
        payload     = EXCLUDED.payload;
    """
)


async def _upsert_indicators(
    session: AsyncSession,
    *,
    feed_id: UUID,
    source_label: str,
    confidence: int,
    tlp: str,
    items: list[tuple[str, str, dict]],
) -> int:
    if not items:
        return 0
    # Dedupe within this pull so a single CSV row appearing twice doesn't
    # spam the same upsert.
    seen: set[tuple[str, str]] = set()
    n = 0
    for indicator, indicator_type, meta in items:
        key = (indicator, indicator_type)
        if key in seen:
            continue
        seen.add(key)
        tags = ["feed", source_label]
        if isinstance(meta.get("tags"), list):
            tags.extend(str(t) for t in meta["tags"] if t)
        await session.execute(
            _INDICATOR_UPSERT,
            {
                "indicator_id": uuid4(),
                "indicator": indicator,
                "indicator_type": indicator_type,
                "confidence": confidence,
                "tlp": tlp,
                "source_feed_id": feed_id,
                "source_label": source_label,
                "tags": tags,
                "payload": json.dumps(meta),
            },
        )
        n += 1
    return n


# ---------------------------------------------------------------- worker

class IntelFeedsWorker:
    def __init__(self, log: structlog.stdlib.BoundLogger) -> None:
        self._log = log
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        self._log.info("intel_feeds_worker_started", tick_s=_TICK_S)
        while not self._stop.is_set():
            try:
                await self._scan_once()
            except Exception as exc:  # noqa: BLE001
                self._log.error("intel_feeds_scan_failed", exc_info=exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=_TICK_S)
            except asyncio.TimeoutError:
                pass
        self._log.info("intel_feeds_worker_stopped")

    async def _scan_once(self) -> None:
        """One pass over the feeds table; pull anything overdue."""
        async with session_scope() as session:
            rows = (await session.execute(text(
                """
                SELECT feed_id, name, url, kind, default_confidence,
                       default_tlp, last_pulled_at, pull_interval_s
                FROM intel_feeds
                WHERE enabled = true
                """
            ))).mappings().all()
        now = datetime.now(UTC)
        for r in rows:
            last = r["last_pulled_at"]
            interval = int(r["pull_interval_s"] or 1800)
            if last is not None and (now - last) < timedelta(seconds=interval):
                continue
            await self._pull_one(
                feed_id=r["feed_id"],
                name=r["name"],
                url=r["url"],
                confidence=int(r["default_confidence"] or 60),
                tlp=str(r["default_tlp"] or "clear"),
            )

    async def _pull_one(
        self,
        *,
        feed_id: UUID,
        name: str,
        url: str,
        confidence: int,
        tlp: str,
    ) -> None:
        slug = _parser_slug_for(url)
        log = self._log.bind(feed_id=str(feed_id), name=name, url=url)
        if slug is None:
            log.warning("intel_feed_no_parser")
            await self._stamp_status(feed_id, status="error: no parser", count=0)
            return

        try:
            payload = await asyncio.to_thread(_pull, url)
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, OSError) as e:
            log.warning("intel_feed_pull_failed", error=str(e))
            await self._stamp_status(feed_id, status=f"error: {str(e)[:80]}", count=0)
            return

        if slug == "urlhaus":
            items = _parse_urlhaus(payload)
        elif slug == "feodotracker":
            items = _parse_feodo(payload)
        else:
            items = []

        try:
            async with session_scope() as session:
                n = await _upsert_indicators(
                    session,
                    feed_id=feed_id,
                    source_label=slug,
                    confidence=confidence,
                    tlp=tlp,
                    items=items,
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            log.error("intel_feed_upsert_failed", exc_info=exc)
            await self._stamp_status(feed_id, status=f"error: upsert {str(exc)[:60]}", count=0)
            return

        log.info("intel_feed_pull_ok", indicators=n)
        await self._stamp_status(feed_id, status="ok", count=n)

    async def _stamp_status(self, feed_id: UUID, *, status: str, count: int) -> None:
        try:
            async with session_scope() as session:
                await session.execute(
                    text(
                        """
                        UPDATE intel_feeds
                           SET last_pulled_at        = NOW(),
                               last_status          = :status,
                               last_indicator_count = :count
                         WHERE feed_id = :feed_id
                        """
                    ),
                    {"status": status, "count": count, "feed_id": feed_id},
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            self._log.warning("intel_feed_stamp_failed", feed_id=str(feed_id), exc_info=exc)


# ---------------------------------------------------------------- entrypoint

async def _amain() -> None:
    settings = get_settings()
    configure_logging(
        service_name="strix-intel-feeds",
        level=settings.observability.log_level,
        json_output=settings.observability.log_json,
    )
    log = structlog.get_logger().bind(service="strix-intel-feeds")
    init_engine(settings)

    worker = IntelFeedsWorker(log)
    loop = asyncio.get_running_loop()
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            loop.add_signal_handler(sig, worker.request_stop)
    await worker.run()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
