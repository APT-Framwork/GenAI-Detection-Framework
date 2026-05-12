"""Seed the intel_feeds registry with two no-auth abuse.ch feeds.

Picked specifically because they're free, public, well-maintained, and
return real attacker IOCs — making "STRIX ingests external threat
intel feeds" a true statement out of the box.

  - URLhaus       — recent malicious URLs + payload SHA-256 + host IPs
                    https://urlhaus.abuse.ch/api/
  - FeodoTracker  — botnet C2 IPs (Emotet, Dridex, TrickBot, …)
                    https://feodotracker.abuse.ch/downloads/

Both publish a "recent" JSON endpoint that's safe to poll at 30-min
cadence (per their robots.txt + community policy). The intel_feeds_worker
reads `url`, `kind`, `pull_interval_s`, `default_confidence`, and
`default_tlp` from these rows at boot — change them via PG, no code
deploy needed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FEEDS = [
    {
        "name": "URLhaus (abuse.ch)",
        "kind": "abuse_ch",
        "url": "https://urlhaus.abuse.ch/downloads/json_online/",
        "pull_interval_s": 1800,
        "default_confidence": 75,
        "default_tlp": "clear",
    },
    {
        "name": "FeodoTracker C2 (abuse.ch)",
        "kind": "abuse_ch",
        "url": "https://feodotracker.abuse.ch/downloads/ipblocklist.json",
        "pull_interval_s": 1800,
        "default_confidence": 80,
        "default_tlp": "clear",
    },
]


def _esc(s: str) -> str:
    return s.replace("'", "''")


def upgrade() -> None:
    for f in _FEEDS:
        op.execute(
            f"""
            INSERT INTO intel_feeds (
                feed_id, name, kind, url, enabled,
                pull_interval_s, default_confidence, default_tlp,
                last_indicator_count, created_at
            ) VALUES (
                uuid_generate_v4(),
                '{_esc(f["name"])}',
                '{_esc(f["kind"])}',
                '{_esc(f["url"])}',
                true,
                {int(f["pull_interval_s"])},
                {int(f["default_confidence"])},
                '{_esc(f["default_tlp"])}',
                0,
                NOW()
            )
            ON CONFLICT (name) DO NOTHING;
            """
        )


def downgrade() -> None:
    names = ",".join(f"'{_esc(f['name'])}'" for f in _FEEDS)
    op.execute(f"DELETE FROM intel_feeds WHERE name IN ({names});")
