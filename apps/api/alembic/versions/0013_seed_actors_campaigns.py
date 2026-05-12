"""Seed threat_actors + campaigns from the simulator's APT_GROUPS catalogue.

The simulator already encodes four APT groups with ordered tactic chains
(see infra/simulation/scripts/run_full_simulation.py:APT_GROUPS). This
migration mirrors that catalogue into the CTI core tables so:

  - /intel/actors has real actor cards (with public-knowledge MITRE
    Group IDs + country attribution + motivation),
  - /intel/campaigns has one campaign per APT group, carrying the tactic
    chain that the matcher will Jaccard-compare against observed chains
    for auto-attribution,
  - intel_relationships links each campaign → actor with kind
    "attributed-to" so the pivot graph has its first edges.

Attribution data is from public sources (MITRE ATT&CK Groups, CISA
advisories, well-established industry reporting). No claim of novel
attribution — these are reference rows, like the MITRE catalog.

Idempotent via name-uniqueness in the target tables: ON CONFLICT
(name) DO NOTHING means re-running the migration after a partial
failure is safe.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from alembic import op


revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Public-knowledge attribution. The tactic_chain values mirror
# APT_GROUPS in run_full_simulation.py — keep these in sync if the
# simulator's catalogue changes.
_ACTORS: list[dict] = [
    {
        "name": "APT41",
        "aliases": ["Barium", "Wicked Panda", "Winnti"],
        "mitre_group_id": "G0096",
        "country": "China",
        "motivation": "espionage + financial",
        "description": (
            "Dual-mission Chinese actor. State-sponsored intrusions for "
            "espionage interleaved with financially-motivated activity "
            "(gaming industry supply chain, cryptocurrency theft). Known "
            "for fast deployment of zero-days and signed loaders."
        ),
    },
    {
        "name": "APT28",
        "aliases": ["Sofacy", "Fancy Bear", "Sednit", "Pawn Storm", "STRONTIUM"],
        "mitre_group_id": "G0007",
        "country": "Russia",
        "motivation": "espionage",
        "description": (
            "Russian military intelligence (GRU Unit 26165) cyber-espionage "
            "group. Heavy focus on NATO governments, defence contractors, "
            "election infrastructure. Toolkit: X-Agent, X-Tunnel, Zebrocy."
        ),
    },
    {
        "name": "APT29",
        "aliases": ["Cozy Bear", "The Dukes", "Nobelium", "Midnight Blizzard"],
        "mitre_group_id": "G0016",
        "country": "Russia",
        "motivation": "espionage",
        "description": (
            "Russian SVR cyber-espionage group. Known for stealth, custom "
            "malware (CozyDuke, MiniDuke, WellMess), and high-profile "
            "supply-chain operations including SUNBURST / SolarWinds."
        ),
    },
    {
        "name": "Turla",
        "aliases": ["Snake", "Uroburos", "Venomous Bear", "Waterbug"],
        "mitre_group_id": "G0010",
        "country": "Russia",
        "motivation": "espionage",
        "description": (
            "Long-running Russian-speaking actor active since at least "
            "2004. Persistence-heavy with rootkit-grade implants (Snake / "
            "Uroburos) targeting government, military, and embassies."
        ),
    },
]


# (campaign_name, actor_name, tactic_chain, description)
_CAMPAIGNS: list[dict] = [
    {
        "name": "APT41 — backdoor + rsync exfil",
        "actor_name": "APT41",
        "tactic_chain": [
            "Persistence", "Privilege Escalation", "Defense Evasion",
            "Discovery", "Collection", "Exfiltration",
        ],
        "description": (
            "Reference chain: rootkit-grade persistence followed by "
            "credential discovery, host enumeration, staged collection, "
            "and signature rsync-based exfiltration to attacker-controlled "
            "infrastructure."
        ),
    },
    {
        "name": "APT28 — Sofacy CVE → curl exfil",
        "actor_name": "APT28",
        "tactic_chain": [
            "Discovery", "Privilege Escalation", "Defense Evasion",
            "Collection", "Exfiltration",
        ],
        "description": (
            "Reference chain: post-exploitation of a known CVE, host and "
            "network discovery, privilege escalation, evasion via process "
            "masquerading, collection of target documents, exfil over "
            "HTTPS POST (curl)."
        ),
    },
    {
        "name": "APT29 — Cozy Bear stealth lateral movement",
        "actor_name": "APT29",
        "tactic_chain": [
            "Persistence", "Defense Evasion", "Lateral Movement",
            "Privilege Escalation", "Discovery",
        ],
        "description": (
            "Reference chain: low-and-slow campaign emphasising lateral "
            "movement and credential reuse, with heavy obfuscation "
            "(base64-jumble in lab simulation). Initial access (phishing) "
            "and DNS C2 are out of band for the lab."
        ),
    },
    {
        "name": "Turla — Snake persistence + credential focus",
        "actor_name": "Turla",
        "tactic_chain": [
            "Persistence", "Privilege Escalation", "Credential Access",
            "Discovery", "Collection", "Defense Evasion",
        ],
        "description": (
            "Reference chain: kernel-grade persistence, credential dumping, "
            "internal network discovery, staged collection, evasion through "
            "Snake's modular plugin chain."
        ),
    },
]


def _esc(s: str) -> str:
    return s.replace("'", "''")


def upgrade() -> None:
    # Actors. ON CONFLICT (name) DO NOTHING keeps the migration idempotent.
    for a in _ACTORS:
        aliases_array = "ARRAY[" + ",".join(f"'{_esc(x)}'" for x in a["aliases"]) + "]::text[]"
        op.execute(
            f"""
            INSERT INTO threat_actors (
                actor_id, name, aliases, mitre_group_id, country,
                motivation, description, created_at
            ) VALUES (
                uuid_generate_v4(),
                '{_esc(a["name"])}',
                {aliases_array},
                '{_esc(a["mitre_group_id"])}',
                '{_esc(a["country"])}',
                '{_esc(a["motivation"])}',
                '{_esc(a["description"])}',
                NOW()
            )
            ON CONFLICT (name) DO NOTHING;
            """
        )

    # Campaigns + actor FK + attributed-to relationship in one pass.
    for c in _CAMPAIGNS:
        chain_json = json.dumps(c["tactic_chain"])
        op.execute(
            f"""
            INSERT INTO campaigns (
                campaign_id, name, actor_id, tactic_chain,
                description, created_at
            )
            SELECT
                uuid_generate_v4(),
                '{_esc(c["name"])}',
                a.actor_id,
                '{_esc(chain_json)}'::jsonb,
                '{_esc(c["description"])}',
                NOW()
            FROM threat_actors a
            WHERE a.name = '{_esc(c["actor_name"])}'
            ON CONFLICT (name) DO NOTHING;
            """
        )
        # Edge for the pivot graph: campaign --attributed-to--> actor
        op.execute(
            f"""
            INSERT INTO intel_relationships (
                rel_id, from_id, from_type, to_id, to_type, rel,
                confidence, description, created_at
            )
            SELECT
                uuid_generate_v4(),
                c.campaign_id, 'campaign',
                a.actor_id, 'actor',
                'attributed-to',
                95,
                'Public attribution per MITRE ATT&CK Groups',
                NOW()
            FROM campaigns c
            JOIN threat_actors a ON a.actor_id = c.actor_id
            WHERE c.name = '{_esc(c["name"])}'
            ON CONFLICT (from_id, from_type, to_id, to_type, rel) DO NOTHING;
            """
        )


def downgrade() -> None:
    actor_names = ",".join(f"'{_esc(a['name'])}'" for a in _ACTORS)
    campaign_names = ",".join(f"'{_esc(c['name'])}'" for c in _CAMPAIGNS)
    # Edges first (FKs ON DELETE SET NULL cover the rest, but we want a
    # clean reverse).
    op.execute(
        f"""
        DELETE FROM intel_relationships
        WHERE rel = 'attributed-to'
          AND from_type = 'campaign'
          AND from_id IN (SELECT campaign_id FROM campaigns WHERE name IN ({campaign_names}));
        """
    )
    op.execute(f"DELETE FROM campaigns WHERE name IN ({campaign_names});")
    op.execute(f"DELETE FROM threat_actors WHERE name IN ({actor_names});")
