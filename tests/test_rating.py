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


def test_three_sources_only_secondary_tertiary_no_indep_count_returns_speculative():
    # No independent-secondary count supplied → falls through to SPECULATIVE (default count=0)
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.SECONDARY, SourceTier.SECONDARY, SourceTier.TERTIARY],
    )) == EpistemicRating.SPECULATIVE


def test_three_sources_two_indep_secondary_returns_verified():
    # THE RULE secondary path: ≥3 verifying AND ≥2 independent secondary → VERIFIED
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.SECONDARY, SourceTier.SECONDARY, SourceTier.TERTIARY],
        has_independent_qualifying_source=True,
        independent_secondary_verifying_count=2,
    )) == EpistemicRating.VERIFIED


def test_three_sources_only_one_indep_secondary_stays_speculative():
    # Only 1 independent secondary (< 2 required) and no primary → SPECULATIVE
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.SECONDARY, SourceTier.SECONDARY, SourceTier.TERTIARY],
        has_independent_qualifying_source=True,
        independent_secondary_verifying_count=1,
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


# ── Hard quality gate: no independent qualifying source ───────────────────────

def test_no_qualifying_source_caps_verified_to_speculative():
    """VERIFIED is impossible when has_independent_qualifying_source=False."""
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.PRIMARY, SourceTier.SECONDARY, SourceTier.SECONDARY],
        has_independent_qualifying_source=False,
    )) == EpistemicRating.SPECULATIVE


def test_no_qualifying_source_caps_debunked_to_speculative():
    """DEBUNKED is impossible when has_independent_qualifying_source=False."""
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.TERTIARY, SourceTier.TERTIARY],
        debunking_tiers=[SourceTier.PRIMARY],
        has_independent_qualifying_source=False,
    )) == EpistemicRating.SPECULATIVE


def test_qualifying_source_present_allows_verified():
    """VERIFIED is reachable when has_independent_qualifying_source=True (explicit)."""
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.PRIMARY, SourceTier.SECONDARY, SourceTier.SECONDARY],
        has_independent_qualifying_source=True,
    )) == EpistemicRating.VERIFIED


def test_qualifying_source_present_allows_debunked():
    """DEBUNKED is reachable when has_independent_qualifying_source=True (explicit)."""
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.TERTIARY, SourceTier.TERTIARY],
        debunking_tiers=[SourceTier.PRIMARY],
        has_independent_qualifying_source=True,
    )) == EpistemicRating.DEBUNKED


def test_missing_unaffected_by_quality_gate():
    """MISSING is not capped by the quality gate — too-few-sources still returns MISSING."""
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.PRIMARY],
        has_independent_qualifying_source=False,
    )) == EpistemicRating.MISSING


def test_speculative_unaffected_by_quality_gate():
    """SPECULATIVE outcome is unchanged by quality gate (gate only caps stronger ratings)."""
    assert derive_rating(EvidenceSummary(
        verifying_tiers=[SourceTier.SECONDARY, SourceTier.SECONDARY, SourceTier.TERTIARY],
        has_independent_qualifying_source=False,
    )) == EpistemicRating.SPECULATIVE


def test_model_cannot_override_quality_gate_to_verified():
    """
    Even when the model explicitly returns 'verified', the hard quality gate must
    override it to SPECULATIVE if no independent primary/secondary source is present.
    Uses only tertiary sources so has_independent_qualifying_source=False.
    """
    from unittest.mock import MagicMock, patch
    from backend.analysis import engine as eng
    from backend.db.models import Judgment

    sources = [
        {"url": f"https://example{i}.com/page", "tier": "tertiary",
         "is_independent": True, "relevance_score": 0.9, "supports_claim": True}
        for i in range(3)
    ]
    judgment_data = {"rationale": "test", "sources": sources, "rating": "verified"}
    mock_claim = MagicMock()
    mock_claim.text = "Test claim"
    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim
    captured: dict = {}
    mock_session.add.side_effect = lambda obj: captured.update({"judgment": obj}) if isinstance(obj, Judgment) else None
    mock_session.add_all.side_effect = lambda objs: None

    with patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt."), \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data), \
         patch.object(eng, "_get_client", return_value=MagicMock()):
        eng.analyze_claim("claim-1", mock_session)

    assert captured["judgment"].rating == EpistemicRating.SPECULATIVE


def test_model_cannot_override_quality_gate_to_debunked():
    """
    Even when the model explicitly returns 'debunked', the hard quality gate must
    override it to SPECULATIVE if no independent primary/secondary source is present.
    """
    from unittest.mock import MagicMock, patch
    from backend.analysis import engine as eng
    from backend.db.models import Judgment

    sources = [
        {"url": f"https://example{i}.com/page", "tier": "tertiary",
         "is_independent": True, "relevance_score": 0.9, "supports_claim": False}
        for i in range(3)
    ]
    judgment_data = {"rationale": "test", "sources": sources, "rating": "debunked"}
    mock_claim = MagicMock()
    mock_claim.text = "Test claim"
    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim
    captured: dict = {}
    mock_session.add.side_effect = lambda obj: captured.update({"judgment": obj}) if isinstance(obj, Judgment) else None
    mock_session.add_all.side_effect = lambda objs: None

    with patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt."), \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data), \
         patch.object(eng, "_get_client", return_value=MagicMock()):
        eng.analyze_claim("claim-1", mock_session)

    assert captured["judgment"].rating == EpistemicRating.SPECULATIVE


# ── Relevance filtering (engine responsibility, rating sees pre-filtered) ──────

def test_engine_filters_low_relevance_sources():
    """Sources with relevance_score < 0.6 must not reach rating derivation."""
    from unittest.mock import MagicMock, patch

    sources = [
        # Two high-relevance primary sources from different domains — both included
        {
            "url": "https://reuters.com/1",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        },
        {
            "url": "https://apnews.com/2",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.7,
            "supports_claim": True,
        },
        # Low-relevance source — must be excluded from rating derivation
        {
            "url": "https://lowquality.example/3",
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

    with patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt."), \
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


def test_engine_absent_supports_claim_not_counted_toward_verified():
    """Sources that omit supports_claim must NOT count as verifying (default False).

    Regression guard for the belegt-vs-diskutiert fix: three high-relevance,
    independent primary sources with supports_claim absent no longer fill
    verifying_tiers, so a model-declared VERIFIED is capped to SPECULATIVE by
    verified_threshold_met(). The storage-write default (True) is unchanged and
    tested separately in test_sensitivity_columns.py.
    """
    from unittest.mock import MagicMock, patch

    sources = [
        {
            "url": f"https://indep{i}.example/a",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            # deliberately omitting supports_claim → threshold count defaults False
        }
        for i in range(3)
    ]

    judgment_data = {"rating": "verified", "rationale": "test", "sources": sources}

    mock_claim = MagicMock()
    mock_claim.text = "Test claim"

    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim

    from backend.analysis import engine as eng
    from backend.db.models import Judgment

    with patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt."), \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data), \
         patch.object(eng, "_get_client", return_value=MagicMock()):

        captured = {}

        def fake_add(obj):
            if isinstance(obj, Judgment):
                captured["judgment"] = obj

        mock_session.add.side_effect = fake_add
        mock_session.add_all.side_effect = lambda objs: None

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

    with patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt."), \
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


# ── Independence: official ≠ independent ──────────────────────────────────────

def _run_engine_with_sources(sources: list[dict]) -> "Judgment":
    """Helper: run analyze_claim with the given source list and return the Judgment."""
    from unittest.mock import MagicMock, patch

    from backend.analysis import engine as eng
    from backend.db.models import Judgment

    judgment_data = {"rationale": "test", "sources": sources}
    mock_claim = MagicMock()
    mock_claim.text = "Test claim"
    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim

    captured: dict = {}

    def fake_add(obj):
        if isinstance(obj, Judgment):
            captured["judgment"] = obj

    mock_session.add.side_effect = fake_add
    mock_session.add_all.side_effect = lambda objs: None

    with patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt."), \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data), \
         patch.object(eng, "_get_client", return_value=MagicMock()):
        eng.analyze_claim("claim-1", mock_session)

    return captured["judgment"]


def test_compromised_primary_source_cannot_alone_enable_verified():
    """
    Three compromised primary sources (from different domains) marked independent by Claude
    must NOT produce VERIFIED — the registry override must downgrade them to secondary, and
    only secondaries cannot reach VERIFIED without an independent primary.
    """
    sources = [
        {
            "url": "https://www.fbi.gov/news/press-releases/2025/item-1",
            "tier": "primary",
            "is_independent": True,  # Will be overridden by compromised registry
            "relevance_score": 0.9,
            "supports_claim": True,
        },
        {
            "url": "https://www.justice.gov/opa/press-release/2025/item-2",
            "tier": "primary",
            "is_independent": True,  # Will be overridden by compromised registry
            "relevance_score": 0.9,
            "supports_claim": True,
        },
        {
            "url": "https://rt.com/news/item-3",
            "tier": "primary",
            "is_independent": True,  # Will be overridden by compromised registry
            "relevance_score": 0.9,
            "supports_claim": True,
        },
    ]
    judgment = _run_engine_with_sources(sources)
    # Registry must override is_independent → False and downgrade tier to secondary.
    # Three secondaries (different domains) → SPECULATIVE (no independent primary → never VERIFIED).
    assert judgment.rating == EpistemicRating.SPECULATIVE


def test_independent_primary_source_enables_verified():
    """
    Three genuine independent primary sources from different domains must still produce VERIFIED.
    Uses bls.gov, reuters.com, apnews.com — all registry-confirmed independent sources.
    """
    sources = [
        {
            "url": "https://www.bls.gov/news.release/cpi.nr0.htm",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        },
        {
            "url": "https://www.reuters.com/article/economy-1",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        },
        {
            "url": "https://apnews.com/article/economy-2",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        },
    ]
    judgment = _run_engine_with_sources(sources)
    assert judgment.rating == EpistemicRating.VERIFIED


def test_mixed_independent_and_compromised_can_reach_verified():
    """
    One independent primary + two compromised sources from different domains with total ≥3 →
    VERIFIED because there IS one independent primary.
    Uses bls.gov (registry-confirmed primary) as the independent source.
    FBI and DOJ are compromised but still count as unique domains for the threshold.
    """
    sources = [
        {
            "url": "https://www.bls.gov/news.release/cpi.nr0.htm",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        },
        {
            "url": "https://www.fbi.gov/news/press-releases/2025/item-1",
            "tier": "primary",
            "is_independent": True,  # Will be overridden by compromised registry
            "relevance_score": 0.9,
            "supports_claim": True,
        },
        {
            "url": "https://www.justice.gov/opa/press-release/2025/item-1",
            "tier": "primary",
            "is_independent": True,  # Will be overridden by compromised registry
            "relevance_score": 0.9,
            "supports_claim": True,
        },
    ]
    judgment = _run_engine_with_sources(sources)
    # BLS (independent primary) + FBI + DOJ (both downgraded to secondary) = 3 unique domains
    # 3 total relevant, has independent primary → VERIFIED
    assert judgment.rating == EpistemicRating.VERIFIED


def test_registry_override_stored_in_evaluated_source():
    """
    The EvaluatedSource records persisted to the DB must reflect the registry
    override: is_independent=False and affiliation_note set for compromised sources.
    """
    from unittest.mock import MagicMock, patch

    from backend.analysis import engine as eng
    from backend.db.models import EvaluatedSource

    sources = [
        {
            "url": "https://www.fbi.gov/news/press-releases/2025/statement",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        }
    ]
    judgment_data = {"rationale": "test", "sources": sources}
    mock_claim = MagicMock()
    mock_claim.text = "Test claim"
    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim

    stored_sources: list = []
    mock_session.add_all.side_effect = lambda objs: stored_sources.extend(objs)
    mock_session.add.side_effect = lambda obj: None

    with patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt."), \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data), \
         patch.object(eng, "_get_client", return_value=MagicMock()):
        eng.analyze_claim("claim-1", mock_session)

    evaluated = [o for o in stored_sources if isinstance(o, EvaluatedSource)]
    assert len(evaluated) == 1
    fbi_src = evaluated[0]
    assert fbi_src.is_independent is False
    assert fbi_src.affiliation_note is not None
    assert "Kash Patel" in fbi_src.affiliation_note


# ── Model-explicit rating overrides derive_rating ─────────────────────────────

def test_model_explicit_rating_takes_precedence_over_derived():
    """
    When the model includes a 'rating' field in submit_judgment, that rating is
    used even when derive_rating() would have returned something different.

    Here: source tiers would yield DEBUNKED (primary debunking source present),
    but the model explicitly concludes MISSING (no affirmative counter-evidence).
    The model's MISSING must win.
    """
    from unittest.mock import MagicMock, patch

    from backend.analysis import engine as eng
    from backend.db.models import Judgment

    sources = [
        {
            "url": "https://a.example/1",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.8,
            "supports_claim": False,  # debunking primary → derive_rating → DEBUNKED
        },
        {
            "url": "https://a.example/2",
            "tier": "secondary",
            "is_independent": True,
            "relevance_score": 0.8,
            "supports_claim": False,
        },
    ]
    judgment_data = {
        "rationale": "No affirmative counter-evidence found; absence is not falsification.",
        "sources": sources,
        "rating": "missing",  # model explicitly concludes MISSING
    }

    mock_claim = MagicMock()
    mock_claim.text = "Test claim"
    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim

    captured: dict = {}

    def fake_add(obj):
        if isinstance(obj, Judgment):
            captured["judgment"] = obj

    mock_session.add.side_effect = fake_add
    mock_session.add_all.side_effect = lambda objs: None

    with patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt."), \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data), \
         patch.object(eng, "_get_client", return_value=MagicMock()):
        eng.analyze_claim("claim-1", mock_session)

    assert captured["judgment"].rating == EpistemicRating.MISSING


def test_no_explicit_rating_falls_back_to_derive_rating():
    """
    When the model does not include a 'rating' field, derive_rating() is used as
    the fallback and must still produce the correct result.
    """
    # Three independent primary verifying sources from different domains → VERIFIED
    sources = [
        {
            "url": "https://www.bls.gov/news.release/fallback.htm",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        },
        {
            "url": "https://www.reuters.com/article/fallback",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        },
        {
            "url": "https://apnews.com/article/fallback",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        },
    ]
    # No 'rating' key in judgment_data → must fall back to derive_rating
    judgment = _run_engine_with_sources(sources)
    assert judgment.rating == EpistemicRating.VERIFIED


def test_invalid_explicit_rating_falls_back_to_derive_rating():
    """
    An unrecognised rating string must log a warning and fall back to derive_rating().
    """
    from unittest.mock import MagicMock, patch

    from backend.analysis import engine as eng
    from backend.db.models import Judgment

    sources = [
        {
            "url": "https://www.bls.gov/news.release/invalid.htm",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        },
        {
            "url": "https://www.reuters.com/article/invalid",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        },
        {
            "url": "https://apnews.com/article/invalid",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        },
    ]
    judgment_data = {
        "rationale": "test",
        "sources": sources,
        "rating": "not-a-real-rating",  # invalid → fallback
    }

    mock_claim = MagicMock()
    mock_claim.text = "Test claim"
    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim

    captured: dict = {}

    def fake_add(obj):
        if isinstance(obj, Judgment):
            captured["judgment"] = obj

    mock_session.add.side_effect = fake_add
    mock_session.add_all.side_effect = lambda objs: None

    with patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt."), \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data), \
         patch.object(eng, "_get_client", return_value=MagicMock()):
        eng.analyze_claim("claim-1", mock_session)

    # derive_rating: 3 independent primary verifying → VERIFIED
    assert captured["judgment"].rating == EpistemicRating.VERIFIED


def test_compromised_source_relevance_capped_in_db():
    """
    A compromised source with relevance_score=0.95 must be stored with
    relevance_score ≤ COMPROMISED_SCORE_CAP in the database.
    """
    from unittest.mock import MagicMock, patch

    from backend.analysis import engine as eng
    from backend.db.models import EvaluatedSource
    from backend.sources.independence_registry import COMPROMISED_SCORE_CAP

    sources = [
        {
            "url": "https://www.justice.gov/opa/press-release/2025",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.95,
            "supports_claim": True,
        }
    ]
    judgment_data = {"rationale": "test", "sources": sources}
    mock_claim = MagicMock()
    mock_claim.text = "Test claim"
    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim

    stored_sources: list = []
    mock_session.add_all.side_effect = lambda objs: stored_sources.extend(objs)
    mock_session.add.side_effect = lambda obj: None

    with patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt."), \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data), \
         patch.object(eng, "_get_client", return_value=MagicMock()):
        eng.analyze_claim("claim-1", mock_session)

    evaluated = [o for o in stored_sources if isinstance(o, EvaluatedSource)]
    assert evaluated[0].relevance_score <= COMPROMISED_SCORE_CAP
