"""Auto-extract IOCs (IPs, hashes) from observed alert text.

Runs per verdict batch in the verdicts writer. Every IP / SHA256 found
in `full_log` is upserted into `intel_indicators` with:

  - source_label = 'internal_observation'
  - confidence   = 70  (we *saw* it; that's stronger than a feed claim
                       but weaker than analyst-curated intel)
  - tlp          = 'amber'  (internal telemetry; not for public sharing)
  - first_seen_internal / last_seen_internal / internal_hit_count++

This is the bidirectional flow that distinguishes a CTI platform from
an IOC lookup tool: STRIX *produces* intel from its own telemetry, not
just consumes it.

Filtering
---------
We aggressively skip obviously-useless indicators so the table doesn't
fill with noise:

  - 0.0.0.0, 127.0.0.0/8 (loopback)
  - 169.254.0.0/16 (link-local)
  - 255.255.255.255 (broadcast)
  - 224.0.0.0/4 (multicast)

Private RFC1918 ranges are KEPT — in the lab they're the actual
attacker-victim addresses (172.20.0.x); in prod a SOC analyst still
wants to see "we observed lateral movement from 10.0.0.7 → 10.0.0.42".
Whoever feels this is too noisy can add a configurable filter later.

SHA256 hashes are 64 hex chars — high enough entropy that false
positives are rare in real text. MD5 (32) and SHA1 (40) collide with
short hex strings (UUIDs, signing nonces) often enough to skip for
v1.
"""

from __future__ import annotations

import re
from datetime import datetime
from ipaddress import IPv4Address, ip_address
from typing import Iterable
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_IPV4_RE = re.compile(
    r"\b(?:25[0-5]|2[0-4]\d|[01]?\d?\d)"
    r"(?:\.(?:25[0-5]|2[0-4]\d|[01]?\d?\d)){3}\b"
)

# auditd encodes argv / proctitle / exe paths as hex strings that
# routinely happen to be exactly 64 chars and would match a naive
# SHA256 regex. Anchor the negative lookbehind to the known auditd
# field names so we don't pick up "curl\x00-fsS\x00…" as malware.
_SHA256_RE = re.compile(
    r"(?<!proctitle=)(?<![a-z]\d=)(?<![a-z]\d\d=)"
    r"\b[a-fA-F0-9]{64}\b"
)

# Even after the lookbehind, auditd records sometimes wrap long
# arguments across multiple a<n>= fields. A real SHA256 hash is mostly
# uniformly distributed; a hex-encoded ASCII string is dominated by
# byte values in 20-7F, so common-character ratio diverges. Cheap
# heuristic: reject if the hex contains too many printable-ASCII
# byte values (`30-7e` in hex pairs), or if it's all lowercase/all
# uppercase (real hashes are typically lowercase but the bigger tell
# is character diversity).
_SHA256_PRINTABLE_RATIO_LIMIT = 0.7


# Sources we never store as indicators — pure infrastructure noise.
_IP_SKIP_NETS = (
    ("0.0.0.0", "0.0.0.0"),
    ("127.0.0.0", "127.255.255.255"),
    ("169.254.0.0", "169.254.255.255"),
    ("224.0.0.0", "239.255.255.255"),  # multicast
    ("255.255.255.255", "255.255.255.255"),
)


def _ipv4_is_meaningful(ip_str: str) -> bool:
    try:
        ip = IPv4Address(ip_str)
    except ValueError:
        return False
    for lo, hi in _IP_SKIP_NETS:
        if IPv4Address(lo) <= ip <= IPv4Address(hi):
            return False
    return True


def _looks_like_sha256(hex_str: str) -> bool:
    """Reject hex strings that are obviously hex-encoded ASCII text.

    A real SHA256 has near-uniform byte distribution. Hex-encoded text
    is dominated by printable-ASCII bytes (0x20-0x7E). If more than
    ~70% of the decoded bytes are printable, this is almost certainly
    text, not a hash.
    """
    try:
        decoded = bytes.fromhex(hex_str)
    except ValueError:
        return False
    if len(decoded) != 32:
        return False
    printable = sum(1 for b in decoded if 0x20 <= b <= 0x7E)
    return (printable / len(decoded)) < _SHA256_PRINTABLE_RATIO_LIMIT


def extract_indicators(full_log: str | None) -> set[tuple[str, str]]:
    """Return a set of (indicator, indicator_type) pairs found in `full_log`.

    Deduplicated by value: if `1.2.3.4` appears five times in one alert,
    it shows up once here (the writer handles hit counting via the
    UPSERT's `internal_hit_count = … + 1` clause).
    """
    if not full_log:
        return set()
    out: set[tuple[str, str]] = set()
    for m in _IPV4_RE.findall(full_log):
        if _ipv4_is_meaningful(m):
            out.add((m, "ip"))
    for m in _SHA256_RE.findall(full_log):
        if _looks_like_sha256(m):
            out.add((m.lower(), "hash"))
    return out


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
        :indicator_id, :indicator, :indicator_type, 70, 'amber',
        NULL, 'internal_observation',
        :observed_at, :observed_at,
        :observed_at, :observed_at, :hit_count,
        :observed_at, NULL,
        ARRAY['internal','auto-extracted']::text[], '{}'::jsonb, NOW()
    )
    ON CONFLICT (indicator, indicator_type, source_label) DO UPDATE SET
        last_seen          = GREATEST(intel_indicators.last_seen, EXCLUDED.last_seen),
        last_seen_internal = GREATEST(
            COALESCE(intel_indicators.last_seen_internal, EXCLUDED.last_seen_internal),
            EXCLUDED.last_seen_internal
        ),
        first_seen_internal = LEAST(
            COALESCE(intel_indicators.first_seen_internal, EXCLUDED.first_seen_internal),
            EXCLUDED.first_seen_internal
        ),
        internal_hit_count = intel_indicators.internal_hit_count + EXCLUDED.internal_hit_count;
    """
)


async def write_observations(
    session: AsyncSession,
    observations: Iterable[tuple[str, str, datetime, int]],
) -> int:
    """Bulk-upsert observed indicators.

    `observations` is an iterable of (indicator, indicator_type,
    observed_at, hit_count) tuples — typically aggregated per-batch in
    the verdicts writer so one DB hit covers multiple alerts that
    referenced the same IOC.

    Returns the count of rows touched (insert OR update). Best-effort:
    failures are logged by the caller, not raised, since IOC extraction
    must never block the verdicts flush.
    """
    n = 0
    for indicator, indicator_type, observed_at, hit_count in observations:
        await session.execute(
            _INDICATOR_UPSERT,
            {
                "indicator_id": uuid4(),
                "indicator": indicator,
                "indicator_type": indicator_type,
                "observed_at": observed_at,
                "hit_count": int(hit_count),
            },
        )
        n += 1
    return n


__all__ = [
    "extract_indicators",
    "write_observations",
]
