"""CTI auto-attribution: chain → campaign via tactic-chain Jaccard.

When a chain closes (or accumulates enough activity), compare the set
of tactics observed on its alerts against each known campaign's
`tactic_chain`. The campaign with the highest Jaccard similarity above
`ATTRIBUTION_THRESHOLD` wins.

Design notes
------------
- **Set Jaccard, not ordered LCS.** The simulator's APT chains are
  ordered, but observed chains are non-monotonic (the Transformer was
  trained on stage cycling). Ordering would penalise real behaviour.
  A campaign whose tactics overlap heavily with what we saw is the
  meaningful signal; ordering can come later as a tie-break.

- **Confidence is the Jaccard percentage**, stored on the relationship
  row so the pivot graph can render it. We only write
  `attack_chains.campaign_id` for the winning campaign; we record the
  losing candidates as lower-confidence edges in `intel_relationships`
  so an analyst can see "this chain looks 60% like APT28 too".

- **Never overwrite**. If `campaign_id` is already set, attribution is
  a no-op. An operator who manually re-attributed a chain stays in
  control. (We re-attribute open chains as more telemetry arrives by
  only setting it once the threshold is crossed; subsequent batches
  see a non-NULL value and skip.)

- **Cheap to run per-batch**. The campaign catalogue is small (4-ish
  rows). We cache `_campaigns` for the lifetime of a service instance;
  invalidating is fine via process restart since campaigns are seeded
  at migration time, not at runtime (yet).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.repositories.models import (
    Alert,
    AttackChain,
    Campaign,
)


# Threshold for the winning Jaccard score (0.0 - 1.0).
#
# Lab chains tend to be narrow (1-3 distinct MITRE tactics each)
# against 5-6-tactic campaign templates, so Jaccard naturally lands
# in the 0.10-0.30 range. 0.15 lets demo chains attribute while still
# requiring meaningful overlap. Tune higher (0.4-0.6) for production
# environments where chains accumulate full kill-chain coverage.
ATTRIBUTION_THRESHOLD: float = 0.15

# Below this score we still record an edge in intel_relationships (so
# the pivot graph and the /cases drill-down can show "candidate"
# attributions), but we don't set the chain's campaign_id.
CANDIDATE_THRESHOLD: float = 0.08


@dataclass(frozen=True)
class CampaignCandidate:
    campaign_id: UUID
    name: str
    tactics: frozenset[str]


class AttributionService:
    """Per-batch chain → campaign matcher."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._campaigns: list[CampaignCandidate] | None = None

    async def _load_campaigns(self) -> list[CampaignCandidate]:
        if self._campaigns is not None:
            return self._campaigns
        rows = (
            await self._s.execute(
                select(Campaign.campaign_id, Campaign.name, Campaign.tactic_chain)
            )
        ).all()
        self._campaigns = [
            CampaignCandidate(
                campaign_id=cid,
                name=name,
                tactics=frozenset(_normalise_tactic(t) for t in (chain or [])),
            )
            for cid, name, chain in rows
        ]
        return self._campaigns

    async def attribute_chain(self, chain_id: UUID) -> UUID | None:
        """Idempotent. Returns the winning campaign_id, or None.

        - No-op if chain already has campaign_id set.
        - No-op if there are no campaigns in the catalogue.
        - No-op if observed tactic set is empty (chain has no MITRE-tagged alerts yet).
        - Writes the winning attribution to attack_chains.campaign_id.
        - Records all above-CANDIDATE_THRESHOLD scores as edges in
          intel_relationships with rel='attributed-to', confidence=score*100.
        """
        chain = await self._s.get(AttackChain, chain_id)
        if chain is None or chain.campaign_id is not None:
            return None

        observed = await self._observed_tactics(chain_id)
        if not observed:
            return None

        campaigns = await self._load_campaigns()
        if not campaigns:
            return None

        scored: list[tuple[CampaignCandidate, float]] = []
        for c in campaigns:
            if not c.tactics:
                continue
            score = _jaccard(observed, c.tactics)
            if score >= CANDIDATE_THRESHOLD:
                scored.append((c, score))

        if not scored:
            return None

        scored.sort(key=lambda x: x[1], reverse=True)
        winner, top_score = scored[0]

        # Record all candidates (winner + runners-up) as edges. The
        # pivot graph will render these with weight = confidence.
        # Raw SQL keeps this service free of one more ORM model;
        # ON CONFLICT mirrors the unique constraint from mig 0012.
        for cand, sc in scored:
            await self._s.execute(
                _RELATIONSHIPS_INSERT,
                {
                    "rel_id": uuid4(),
                    "from_id": chain_id,
                    "from_type": "chain",
                    "to_id": cand.campaign_id,
                    "to_type": "campaign",
                    "rel": "attributed-to",
                    "confidence": int(round(sc * 100)),
                    "description": (
                        f"Auto-attribution: Jaccard={sc:.2f} on tactic set "
                        f"(observed={sorted(observed)}, campaign={cand.name})"
                    ),
                },
            )

        if top_score >= ATTRIBUTION_THRESHOLD:
            # set_only_if_unset — protect operator overrides.
            result = await self._s.execute(
                update(AttackChain)
                .where(AttackChain.chain_id == chain_id)
                .where(AttackChain.campaign_id.is_(None))
                .values(campaign_id=winner.campaign_id)
            )
            # Only write audit entry if we actually set the column —
            # rowcount=0 means another concurrent batch beat us to it.
            if (result.rowcount or 0) > 0:
                await self._s.execute(
                    text(
                        """
                        INSERT INTO case_audit_log
                          (audit_id, chain_id, user_id, from_status, to_status, note, at)
                        VALUES
                          (:aid, :cid, NULL, NULL, :ts, :note, NOW())
                        """
                    ),
                    {
                        "aid": uuid4(),
                        "cid": chain_id,
                        "ts": f"attribution:{winner.name}",
                        "note": f"Jaccard={top_score:.2f}",
                    },
                )
            return winner.campaign_id
        return None

    async def _observed_tactics(self, chain_id: UUID) -> frozenset[str]:
        """Distinct tactic labels (normalised) from this chain's alerts."""
        rows = (
            await self._s.execute(
                select(Alert.mitre_tactics).where(Alert.chain_id == chain_id)
            )
        ).all()
        out: set[str] = set()
        for (arr,) in rows:
            if not arr:
                continue
            for t in arr:
                norm = _normalise_tactic(t)
                if norm:
                    out.add(norm)
        return frozenset(out)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _normalise_tactic(value: str) -> str:
    """Tactic labels arrive in mixed case ("Defense Evasion", "defense-evasion").

    Normalise to lowercase + collapse separators so Jaccard sees the
    same identity regardless of the source's formatting.
    """
    if not value:
        return ""
    return (
        value.strip()
        .lower()
        .replace("-", " ")
        .replace("_", " ")
        # Collapse double spaces
        .replace("  ", " ")
    )


# Compiled raw INSERT used for the per-batch edge writes. Keeps the
# service free of importing the IntelRelationship ORM model (which
# would be one more table to maintain mirrors for).
_RELATIONSHIPS_INSERT = text(
    """
    INSERT INTO intel_relationships (
        rel_id, from_id, from_type, to_id, to_type, rel,
        confidence, description, created_at
    ) VALUES (
        :rel_id, :from_id, :from_type, :to_id, :to_type, :rel,
        :confidence, :description, NOW()
    )
    ON CONFLICT (from_id, from_type, to_id, to_type, rel) DO UPDATE
       SET confidence  = EXCLUDED.confidence,
           description = EXCLUDED.description;
    """
)


__all__ = [
    "ATTRIBUTION_THRESHOLD",
    "CANDIDATE_THRESHOLD",
    "AttributionService",
]
