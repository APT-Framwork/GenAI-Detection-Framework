"""Seed starter IOC rows so /threat-intel has a populated table on first load.

The page reads `ioc_lookup_cache` for the IOC results table. Until a
juror types a search, the table is empty — even though the XON +
VirusTotal adapters work fine. This migration seeds five representative
rows covering the indicator types the UI renders (sha256, ip, email,
domain) and the reputation buckets (malicious, suspicious, clean,
breached) so the table is interesting from page-load.

Rows are real samples that a SOC analyst would recognise:

  - EICAR test SHA-256 → virustotal, malicious
  - test@example.com   → xon, clean
  - leaked@yahoo.com   → xon, breached (synthetic counts payload)
  - 8.8.8.8            → virustotal, clean (Google DNS)
  - 185.220.101.1      → virustotal, suspicious (Tor exit node range)

All rows get `expires_at = NOW() + 100 years` so the cache TTL doesn't
sweep them. Idempotent: ON CONFLICT (indicator, indicator_type, source)
DO NOTHING since the composite PK is what the cache upserts on. A live
adapter call later overwrites our seeded payload — that's intentional;
the seed is a fallback, not authoritative truth.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (indicator, indicator_type, source, reputation, payload_json)
# Schema constraints (migration 0001):
#   indicator_type ∈ {ip, email, domain, hash}
#   reputation     ∈ {malicious, suspicious, clean, unknown}
# XON's "breached" maps to `malicious` per threat_intel_service.py.
_STARTER_IOCS: list[tuple[str, str, str, str, str]] = [
    (
        "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f",
        "hash", "virustotal", "malicious",
        '{"counts": {"malicious": 64, "suspicious": 0, "harmless": 0, "undetected": 8}, "engines": {}}',
    ),
    (
        "test@example.com",
        "email", "xon", "clean",
        '{"breachCount": 0, "breaches": []}',
    ),
    (
        "leaked@yahoo.com",
        "email", "xon", "malicious",
        '{"breachCount": 3, "breaches": ["Yahoo (2014)", "LinkedIn (2012)", "MyFitnessPal (2018)"]}',
    ),
    (
        "8.8.8.8",
        "ip", "virustotal", "clean",
        '{"counts": {"malicious": 0, "suspicious": 0, "harmless": 76, "undetected": 18}, "engines": {}}',
    ),
    (
        "185.220.101.1",
        "ip", "virustotal", "suspicious",
        '{"counts": {"malicious": 4, "suspicious": 12, "harmless": 50, "undetected": 28}, "engines": {}}',
    ),
]


def upgrade() -> None:
    for indicator, itype, source, reputation, payload in _STARTER_IOCS:
        op.execute(
            f"""
            INSERT INTO ioc_lookup_cache (
                indicator, indicator_type, source, reputation,
                payload, checked_at, expires_at
            )
            VALUES (
                '{indicator.replace("'", "''")}',
                '{itype}', '{source}', '{reputation}',
                '{payload.replace("'", "''")}'::jsonb,
                NOW(), NOW() + INTERVAL '100 years'
            )
            ON CONFLICT (indicator, indicator_type, source) DO NOTHING;
            """
        )


def downgrade() -> None:
    for indicator, itype, source, _rep, _pl in _STARTER_IOCS:
        op.execute(
            f"DELETE FROM ioc_lookup_cache WHERE "
            f"indicator = '{indicator.replace(chr(39), chr(39)*2)}' "
            f"AND indicator_type = '{itype}' AND source = '{source}';"
        )
