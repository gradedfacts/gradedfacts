"""
Tests for the registry-sensitivity schema migration write paths.

Verifies that newly created judgments persist:
  (a) supports_claim on EvaluatedSource rows
  (b) claude_rating on Judgment (EpistemicRating.value string)
  (c) mistral_rating is None on a single-engine (Claude-only) run

These tests exercise the write paths in engine.py (single-engine) and
consensus.py (consensus path) without touching the DB or making live API
calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.analysis.rating import EpistemicRating
from backend.db.models import EvaluatedSource, Judgment


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_sources(n: int = 3, *, supports: bool = True, tier: str = "primary") -> list[dict]:
    return [
        {
            "url": f"https://example-{i}.org/article",
            "title": f"Source {i}",
            "tier": tier,
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": supports,
            "excerpt": f"Excerpt {i}",
        }
        for i in range(n)
    ]


def _make_mock_session(captured: dict):
    """Return a mock session that captures Judgment and EvaluatedSource objects."""
    session = MagicMock()

    def fake_add(obj):
        if isinstance(obj, Judgment):
            captured.setdefault("judgments", []).append(obj)

    def fake_add_all(objs):
        for obj in objs:
            if isinstance(obj, EvaluatedSource):
                captured.setdefault("sources", []).append(obj)

    session.add.side_effect = fake_add
    session.add_all.side_effect = fake_add_all
    return session


# ── Single-engine path (engine.py) ───────────────────────────────────────────

class TestSingleEngineWritePath:

    def _run(self, sources: list[dict], model_rating: str = "verified") -> dict:
        from backend.analysis import engine as eng

        mock_claim = MagicMock()
        mock_claim.text = "Test claim for sensitivity columns"
        captured: dict = {}
        session = _make_mock_session(captured)
        session.get.return_value = mock_claim

        judgment_data = {
            "rationale": "Rationale text.",
            "sources": sources,
            "rating": model_rating,
            "political_leaning": "none",
        }

        with patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt."), \
             patch.object(eng, "_phase2_judgment", return_value=judgment_data), \
             patch.object(eng, "_get_client", return_value=MagicMock()), \
             patch.object(eng, "_check_specificity", return_value=(True, "")), \
             patch.object(eng, "_check_off_topic", return_value=(True, "")), \
             patch.object(eng, "_get_registry_version", return_value="abc123"), \
             patch.object(eng, "_deactivate_prior_judgments", return_value=None):
            eng.analyze_claim("claim-id-1", session)

        return captured

    def test_supports_claim_true_persisted_on_verifying_sources(self):
        """supports_claim=True from the model is written to each EvaluatedSource."""
        sources = _make_sources(3, supports=True)
        captured = self._run(sources, model_rating="verified")

        stored = captured.get("sources", [])
        assert len(stored) >= 3, f"Expected ≥3 sources, got {len(stored)}"
        for src in stored:
            assert src.supports_claim is True, (
                f"supports_claim should be True, got {src.supports_claim!r} for {src.url}"
            )

    def test_supports_claim_false_persisted_on_debunking_sources(self):
        """supports_claim=False from the model is written to each EvaluatedSource."""
        sources = _make_sources(3, supports=False, tier="secondary")
        captured = self._run(sources, model_rating="debunked")

        stored = captured.get("sources", [])
        assert len(stored) >= 3, f"Expected ≥3 sources, got {len(stored)}"
        for src in stored:
            assert src.supports_claim is False, (
                f"supports_claim should be False, got {src.supports_claim!r} for {src.url}"
            )

    def test_claude_rating_persisted_on_judgment(self):
        """claude_rating is written as an EpistemicRating.value string."""
        sources = _make_sources(3, supports=True)
        captured = self._run(sources, model_rating="verified")

        judgments = captured.get("judgments", [])
        assert judgments, "No Judgment was captured"
        j = judgments[-1]
        assert j.claude_rating is not None, "claude_rating must not be None"
        # Must be a valid EpistemicRating value string
        assert j.claude_rating in {r.value for r in EpistemicRating}, (
            f"claude_rating {j.claude_rating!r} is not a valid EpistemicRating value"
        )

    def test_mistral_rating_is_none_single_engine(self):
        """mistral_rating must be None on a single-engine (Claude-only) run."""
        sources = _make_sources(3, supports=True)
        captured = self._run(sources, model_rating="verified")

        judgments = captured.get("judgments", [])
        assert judgments, "No Judgment was captured"
        j = judgments[-1]
        assert j.mistral_rating is None, (
            f"mistral_rating must be None for single-engine run, got {j.mistral_rating!r}"
        )

    def test_claude_rating_matches_final_judgment_rating(self):
        """claude_rating must equal the final rating value on the Judgment row."""
        sources = _make_sources(2, supports=True)  # 2 sources → SPECULATIVE (< MIN_VERIFIED_SOURCES)
        captured = self._run(sources, model_rating="speculative")

        judgments = captured.get("judgments", [])
        assert judgments, "No Judgment was captured"
        j = judgments[-1]
        assert j.claude_rating == j.rating.value, (
            f"claude_rating {j.claude_rating!r} != rating.value {j.rating.value!r}"
        )

    def test_supports_claim_not_present_defaults_to_true(self):
        """When supports_claim is absent from the model output, default True is written."""
        sources = [
            {
                "url": f"https://nosupports-{i}.org/page",
                "tier": "primary",
                "is_independent": True,
                "relevance_score": 0.9,
                # deliberately omitting supports_claim
            }
            for i in range(3)
        ]
        captured = self._run(sources, model_rating="verified")

        stored = captured.get("sources", [])
        assert len(stored) >= 3
        for src in stored:
            assert src.supports_claim is True, (
                f"Default supports_claim should be True, got {src.supports_claim!r}"
            )


# ── Consensus path (consensus.py) ────────────────────────────────────────────

class TestConsensusWritePath:
    """
    Spot-checks the consensus.py write path via analyze_claim_with_consensus.
    Mistral is mocked so both the Mistral-available and Mistral-absent paths
    are covered.
    """

    _THREE_PRIMARIES = [
        {
            "url": f"https://primary-{i}.org/doc",
            "title": f"Primary {i}",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
            "excerpt": f"Evidence {i}",
        }
        for i in range(3)
    ]

    def _run_consensus(
        self,
        claude_sources: list[dict],
        mistral_sources: list[dict] | None,
        claude_model_rating: str = "verified",
        mistral_model_rating: str | None = "verified",
    ) -> dict:
        from backend.analysis import consensus as con

        mock_claim = MagicMock()
        mock_claim.text = "Consensus test claim"
        captured: dict = {}
        session = _make_mock_session(captured)
        session.get.return_value = mock_claim

        claude_data = {
            "rationale": "Claude rationale.",
            "sources": claude_sources,
            "rating": claude_model_rating,
            "political_leaning": "none",
        }

        mistral_data: dict | None = None
        if mistral_sources is not None and mistral_model_rating is not None:
            mistral_data = {
                "rationale": "Mistral rationale.",
                "sources": mistral_sources,
                "rating": mistral_model_rating,
                "political_leaning": "none",
            }

        with patch.object(con, "_check_specificity", return_value=(True, "")), \
             patch.object(con, "_check_off_topic", return_value=(True, "")), \
             patch.object(con, "_phase1_search", return_value=""), \
             patch.object(con, "_phase2_judgment", return_value=claude_data), \
             patch.object(con, "_get_client", return_value=MagicMock()), \
             patch.object(con, "_get_registry_version", return_value="abc123"), \
             patch.object(con, "_deactivate_prior_judgments", return_value=None), \
             patch.object(con, "_detect_language", return_value="English"), \
             patch.object(con, "_mistral_search_and_judge",
                          return_value=mistral_data if mistral_data is not None else {}), \
             patch("backend.analysis.consensus.settings") as mock_settings:
            mock_settings.mistral_api_key = "mock-key" if mistral_data is not None else ""
            # Bypass the ThreadPoolExecutor by making both futures resolve synchronously.
            if mistral_data is not None:
                with patch("backend.analysis.consensus.ThreadPoolExecutor") as MockExec:
                    mock_executor = MagicMock()
                    MockExec.return_value = mock_executor
                    claude_future = MagicMock()
                    claude_future.result.return_value = claude_data
                    mistral_future = MagicMock()
                    mistral_future.result.return_value = mistral_data
                    mock_executor.submit.side_effect = [claude_future, mistral_future]
                    con.analyze_claim_with_consensus("claim-id-2", session)
            else:
                con.analyze_claim_with_consensus("claim-id-2", session)

        return captured

    def test_claude_rating_persisted_consensus_agree(self):
        """claude_rating is written when both models agree (models_agree=True path)."""
        captured = self._run_consensus(
            claude_sources=self._THREE_PRIMARIES,
            mistral_sources=[],
            claude_model_rating="verified",
            mistral_model_rating="verified",
        )
        judgments = captured.get("judgments", [])
        assert judgments, "No Judgment captured"
        j = judgments[-1]
        assert j.claude_rating is not None
        assert j.claude_rating in {r.value for r in EpistemicRating}

    def test_mistral_rating_persisted_consensus_agree(self):
        """mistral_rating is written (non-None) when Mistral is present."""
        captured = self._run_consensus(
            claude_sources=self._THREE_PRIMARIES,
            mistral_sources=[],
            claude_model_rating="verified",
            mistral_model_rating="verified",
        )
        judgments = captured.get("judgments", [])
        assert judgments, "No Judgment captured"
        j = judgments[-1]
        assert j.mistral_rating is not None, "mistral_rating must be set when Mistral is present"
        assert j.mistral_rating in {r.value for r in EpistemicRating}

    def test_mistral_rating_none_when_mistral_absent(self):
        """mistral_rating is None when MISTRAL_API_KEY is absent (Claude-only fallback)."""
        captured = self._run_consensus(
            claude_sources=self._THREE_PRIMARIES,
            mistral_sources=None,
            mistral_model_rating=None,
        )
        judgments = captured.get("judgments", [])
        assert judgments, "No Judgment captured"
        j = judgments[-1]
        assert j.mistral_rating is None, (
            f"mistral_rating must be None when Mistral is absent, got {j.mistral_rating!r}"
        )

    def test_supports_claim_persisted_claude_sources_consensus(self):
        """supports_claim is written on Claude's EvaluatedSource rows in the consensus path."""
        captured = self._run_consensus(
            claude_sources=self._THREE_PRIMARIES,
            mistral_sources=[],
            claude_model_rating="verified",
            mistral_model_rating="verified",
        )
        sources = captured.get("sources", [])
        assert sources, "No EvaluatedSource objects captured"
        for src in sources:
            assert src.supports_claim is not None, (
                f"supports_claim must be set on {src.url}"
            )
