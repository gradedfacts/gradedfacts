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


# Minimum relevant sources before any verdict other than MISSING can be issued.
MIN_EVIDENCE_SOURCES = 2

# Minimum relevant sources required to reach VERIFIED (stricter than any-verdict threshold).
MIN_VERIFIED_SOURCES = 3


@dataclass(frozen=True)
class EvidenceSummary:
    """Aggregated source tiers passed to derive_rating."""
    verifying_tiers: list[SourceTier] = field(default_factory=list)
    debunking_tiers: list[SourceTier] = field(default_factory=list)
    # Hard quality gate: True when at least one qualifying source passes
    # (tier PRIMARY and is_independent=True) OR (tier SECONDARY and is_independent=True).
    # Defaults to True for backward compatibility; engines must set it explicitly.
    has_independent_qualifying_source: bool = True


def derive_rating(evidence: EvidenceSummary) -> EpistemicRating:
    """
    Map an EvidenceSummary to an EpistemicRating.

    Only sources that pass the relevance filter (>= MIN_RELEVANCE_SCORE) in the
    analysis engine are included in the EvidenceSummary; this function sees only
    the already-filtered tiers.

    Rules applied in priority order:
      1. Fewer than MIN_EVIDENCE_SOURCES relevant sources → MISSING.
      2. Hard quality gate: no independent primary/secondary source present
         → VERIFIED and DEBUNKED are impossible; cap at SPECULATIVE.
      3. Any primary or secondary debunking source → DEBUNKED.
      4. No verifying sources → MISSING.
      5. Fewer than MIN_VERIFIED_SOURCES relevant sources → SPECULATIVE
         (primary source present but threshold not met).
      6. At least one primary verifying source → VERIFIED.
      7. Only secondary or tertiary verifying sources → SPECULATIVE (capped).
    """
    total = len(evidence.verifying_tiers) + len(evidence.debunking_tiers)
    if total < MIN_EVIDENCE_SOURCES:
        return EpistemicRating.MISSING

    _qualifying = evidence.has_independent_qualifying_source

    strong_debunk = {SourceTier.PRIMARY, SourceTier.SECONDARY}
    if any(t in strong_debunk for t in evidence.debunking_tiers):
        return EpistemicRating.DEBUNKED if _qualifying else EpistemicRating.SPECULATIVE

    if not evidence.verifying_tiers:
        return EpistemicRating.MISSING

    if total < MIN_VERIFIED_SOURCES:
        return EpistemicRating.SPECULATIVE

    if any(t is SourceTier.PRIMARY for t in evidence.verifying_tiers):
        return EpistemicRating.VERIFIED if _qualifying else EpistemicRating.SPECULATIVE

    return EpistemicRating.SPECULATIVE
