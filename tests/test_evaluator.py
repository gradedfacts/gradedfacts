"""
Tests for backend/sources/evaluator.py.

Covers: evaluate_source() — independence override, affiliation_note enforcement,
and relevance_score clamping.
"""

from backend.sources.evaluator import evaluate_source
from backend.sources.independence_registry import COMPROMISED_SCORE_CAP


class TestEvaluateSource:
    _independent_source = {
        "url": "https://www.reuters.com/article/example",
        "tier": "secondary",
        "is_independent": True,
        "relevance_score": 0.85,
        "supports_claim": True,
    }

    # ── Independence registry override ────────────────────────────────────────

    def test_fbi_source_is_marked_not_independent(self):
        src = {
            "url": "https://www.fbi.gov/news/press-releases/statement",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        }
        result = evaluate_source(src)
        assert result["is_independent"] is False

    def test_fbi_source_relevance_capped(self):
        src = {
            "url": "https://www.fbi.gov/news/press-releases/statement",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.95,
            "supports_claim": True,
        }
        result = evaluate_source(src)
        assert result["relevance_score"] == COMPROMISED_SCORE_CAP

    def test_fbi_source_affiliation_note_populated(self):
        src = {
            "url": "https://www.fbi.gov/news/press-releases/statement",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        }
        result = evaluate_source(src)
        assert result.get("affiliation_note")

    # ── Generic non-independent fallback ──────────────────────────────────────

    def test_non_independent_without_affiliation_note_gets_generic_note(self):
        src = {
            "url": "https://some-partisan-outlet.example/article",
            "tier": "secondary",
            "is_independent": False,
            "relevance_score": 0.7,
            "supports_claim": True,
        }
        result = evaluate_source(src)
        assert result.get("affiliation_note")

    def test_non_independent_with_existing_affiliation_note_preserved(self):
        src = {
            "url": "https://some-partisan-outlet.example/article",
            "tier": "secondary",
            "is_independent": False,
            "affiliation_note": "Known partisan funding source",
            "relevance_score": 0.7,
            "supports_claim": True,
        }
        result = evaluate_source(src)
        assert result["affiliation_note"] == "Known partisan funding source"

    # ── Relevance score clamping ───────────────────────────────────────────────

    def test_relevance_score_above_1_clamped_to_1(self):
        src = {**self._independent_source, "relevance_score": 1.5}
        result = evaluate_source(src)
        assert result["relevance_score"] == 1.0

    def test_relevance_score_below_0_clamped_to_0(self):
        src = {**self._independent_source, "relevance_score": -0.2}
        result = evaluate_source(src)
        assert result["relevance_score"] == 0.0

    def test_valid_relevance_score_unchanged(self):
        src = {**self._independent_source, "relevance_score": 0.75}
        result = evaluate_source(src)
        assert result["relevance_score"] == 0.75

    # ── Non-mutation guarantee ────────────────────────────────────────────────

    def test_does_not_mutate_input_dict(self):
        src = {
            "url": "https://www.fbi.gov/press",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.95,
            "supports_claim": True,
        }
        original_is_independent = src["is_independent"]
        original_score = src["relevance_score"]
        _ = evaluate_source(src)
        assert src["is_independent"] == original_is_independent
        assert src["relevance_score"] == original_score

    # ── Independent source pass-through ───────────────────────────────────────

    def test_independent_source_returned_with_unchanged_fields(self):
        result = evaluate_source(self._independent_source)
        assert result["is_independent"] is True
        assert result["relevance_score"] == 0.85
        assert result.get("affiliation_note") is None
