import pytest

from backend.analysis.rating import (
    EpistemicRating,
    EvidenceSummary,
    SourceTier,
    derive_rating,
)


# ── MISSING ───────────────────────────────────────────────────────────────────

def test_no_sources_returns_missing():
    assert derive_rating(EvidenceSummary()) == EpistemicRating.MISSING


def test_single_source_returns_missing():
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.PRIMARY],
    )) == EpistemicRating.MISSING


def test_no_verifying_sources_returns_missing():
    # Two tertiary debunking sources don't trigger DEBUNKED (tertiary only),
    # and there are no verifying sources → MISSING.
    assert derive_rating(EvidenceSummary(
        debunking_tiers=[SourceTier.TERTIARY, SourceTier.TERTIARY],
    )) == EpistemicRating.MISSING


# ── DEBUNKED ──────────────────────────────────────────────────────────────────

def test_primary_debunking_source_returns_debunked():
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.TERTIARY, SourceTier.TERTIARY],
        debunking_tiers=[SourceTier.PRIMARY],
    )) == EpistemicRating.DEBUNKED


def test_secondary_debunking_source_returns_debunked():
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.TERTIARY, SourceTier.TERTIARY],
        debunking_tiers=[SourceTier.SECONDARY],
    )) == EpistemicRating.DEBUNKED


# ── SPECULATIVE ───────────────────────────────────────────────────────────────

def test_two_primary_sources_returns_speculative_not_verified():
    # MIN_VERIFIED_SOURCES=3; 2 relevant sources → SPECULATIVE even with primary
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.PRIMARY, SourceTier.PRIMARY],
    )) == EpistemicRating.SPECULATIVE


def test_three_sources_only_secondary_tertiary_returns_speculative():
    # No primary verifying source → capped at SPECULATIVE
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.SECONDARY, SourceTier.SECONDARY, SourceTier.TERTIARY],
    )) == EpistemicRating.SPECULATIVE


def test_only_tertiary_verifying_returns_speculative():
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.TERTIARY, SourceTier.TERTIARY, SourceTier.TERTIARY],
    )) == EpistemicRating.SPECULATIVE


# ── VERIFIED ──────────────────────────────────────────────────────────────────

def test_three_sources_with_primary_returns_verified():
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.PRIMARY, SourceTier.SECONDARY, SourceTier.SECONDARY],
    )) == EpistemicRating.VERIFIED


def test_four_primary_sources_returns_verified():
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.PRIMARY] * 4,
    )) == EpistemicRating.VERIFIED


# ── Relevance filtering (engine responsibility, rating sees pre-filtered) ──────

def test_engine_filters_low_relevance_sources():
    """Sources with relevance_score < 0.6 must not reach rating derivation."""
    from unittest.mock import MagicMock, patch

    sources = [
        # Two high-relevance primary sources — should be included
        {
            "url": "https://a.example/1",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        },
        {
            "url": "https://a.example/2",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.7,
            "supports_claim": True,
        },
        # Low-relevance source — must be excluded from rating derivation
        {
            "url": "https://a.example/3",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.4,
            "supports_claim": True,
        },
    ]

    # With the low-relevance source excluded, only 2 relevant sources remain
    # → SPECULATIVE (needs 3 for VERIFIED)
    judgment_data = {"rationale": "test", "sources": sources}

    mock_claim = MagicMock()
    mock_claim.text = "Test claim"

    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim

    from backend.analysis import engine as eng

    with patch.object(eng, "_phase1_search", return_value=""), \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data), \
         patch.object(eng, "_get_client", return_value=MagicMock()):

        from backend.db.models import Judgment
        captured = {}

        def fake_add(obj):
            if isinstance(obj, Judgment):
                captured["judgment"] = obj

        def fake_add_all(objs):
            pass

        mock_session.add.side_effect = fake_add
        mock_session.add_all.side_effect = fake_add_all

        eng.analyze_claim("claim-1", mock_session)

        assert captured["judgment"].rating == EpistemicRating.SPECULATIVE


def test_engine_caps_sources_at_max():
    """analyze_claim must use at most MAX_SOURCES sources."""
    from unittest.mock import MagicMock, patch

    from backend.analysis.engine import MAX_SOURCES

    # Build MAX_SOURCES + 3 sources, all high-relevance primary verifying
    sources = [
        {
            "url": f"https://a.example/{i}",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        }
        for i in range(MAX_SOURCES + 3)
    ]

    judgment_data = {"rationale": "test", "sources": sources}

    mock_claim = MagicMock()
    mock_claim.text = "Test claim"

    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim

    from backend.analysis import engine as eng
    from backend.db.models import EvaluatedSource

    with patch.object(eng, "_phase1_search", return_value=""), \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data), \
         patch.object(eng, "_get_client", return_value=MagicMock()):

        stored_sources = []

        def fake_add_all(objs):
            stored_sources.extend(objs)

        mock_session.add.side_effect = lambda obj: None
        mock_session.add_all.side_effect = fake_add_all

        eng.analyze_claim("claim-1", mock_session)

        evaluated = [o for o in stored_sources if isinstance(o, EvaluatedSource)]
        assert len(evaluated) <= MAX_SOURCES
