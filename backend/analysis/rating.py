from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EpistemicRating(str, Enum):
    VERIFIED = "verified"
    SPECULATIVE = "speculative"
    DEBUNKED = "debunked"
    MISSING = "missing"

    @property
    def color(self) -> str:
        return {
            EpistemicRating.VERIFIED: "green",
            EpistemicRating.SPECULATIVE: "yellow",
            EpistemicRating.DEBUNKED: "red",
            EpistemicRating.MISSING: "gray",
        }[self]

    @property
    def label(self) -> str:
        return self.value.capitalize()


class SourceTier(str, Enum):
    PRIMARY = "primary"      # Original data, official documents, direct statements
    SECONDARY = "secondary"  # Reporting that cites primary sources with attribution
    TERTIARY = "tertiary"    # Aggregations, summaries, opinion without independent verification


# Minimum number of distinct sources before any verdict other than MISSING can be issued.
MIN_EVIDENCE_SOURCES = 2


@dataclass(frozen=True)
class EvidenceSummary:
    """Aggregated source tiers passed to derive_rating."""
    verifying_tiers: list[SourceTier] = field(default_factory=list)
    debunking_tiers: list[SourceTier] = field(default_factory=list)


def derive_rating(evidence: EvidenceSummary) -> EpistemicRating:
    """
    Map an EvidenceSummary to an EpistemicRating.

    Rules applied in priority order:
      1. Fewer than MIN_EVIDENCE_SOURCES total sources → MISSING.
      2. Any primary or secondary debunking source → DEBUNKED.
      3. At least one primary verifying source → VERIFIED.
      4. Only secondary or tertiary verifying sources → SPECULATIVE (capped).
      5. No verifying sources at all → MISSING.
    """
    total = len(evidence.verifying_tiers) + len(evidence.debunking_tiers)
    if total < MIN_EVIDENCE_SOURCES:
        return EpistemicRating.MISSING

    strong_debunk = {SourceTier.PRIMARY, SourceTier.SECONDARY}
    if any(t in strong_debunk for t in evidence.debunking_tiers):
        return EpistemicRating.DEBUNKED

    if not evidence.verifying_tiers:
        return EpistemicRating.MISSING

    if any(t is SourceTier.PRIMARY for t in evidence.verifying_tiers):
        return EpistemicRating.VERIFIED

    return EpistemicRating.SPECULATIVE
