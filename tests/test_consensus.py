"""
Tests for backend/analysis/consensus.py

Covers:
  - _resolve_consensus: all agreement/disagreement/no-secondary cases
  - _mistral_phase2_judgment: tool-call parsing, error paths
  - analyze_claim_with_consensus: full integration (mocked I/O)
    — models agree
    — models disagree (consensus downgrades to SPECULATIVE)
    — Mistral Phase 2 raises (Claude-only fallback)
    — MISTRAL_API_KEY absent (Claude-only fallback)
    — claim not found
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.analysis.rating import EpistemicRating


# ── _resolve_consensus ────────────────────────────────────────────────────────

class TestResolveConsensus:
    from backend.analysis.consensus import _resolve_consensus  # type: ignore[attr-defined]

    def setup_method(self):
        from backend.analysis.consensus import _resolve_consensus
        self._fn = _resolve_consensus

    def test_both_agree_verified(self):
        rating, agree = self._fn(EpistemicRating.VERIFIED, EpistemicRating.VERIFIED)
        assert rating == EpistemicRating.VERIFIED
        assert agree is True

    def test_both_agree_debunked(self):
        rating, agree = self._fn(EpistemicRating.DEBUNKED, EpistemicRating.DEBUNKED)
        assert rating == EpistemicRating.DEBUNKED
        assert agree is True

    def test_both_agree_speculative(self):
        rating, agree = self._fn(EpistemicRating.SPECULATIVE, EpistemicRating.SPECULATIVE)
        assert rating == EpistemicRating.SPECULATIVE
        assert agree is True

    def test_both_agree_missing(self):
        rating, agree = self._fn(EpistemicRating.MISSING, EpistemicRating.MISSING)
        assert rating == EpistemicRating.MISSING
        assert agree is True

    def test_disagree_downgrades_to_speculative(self):
        rating, agree = self._fn(EpistemicRating.VERIFIED, EpistemicRating.DEBUNKED)
        assert rating == EpistemicRating.SPECULATIVE
        assert agree is False

    def test_disagree_verified_vs_missing(self):
        rating, agree = self._fn(EpistemicRating.VERIFIED, EpistemicRating.MISSING)
        assert rating == EpistemicRating.SPECULATIVE
        assert agree is False

    def test_disagree_debunked_vs_speculative(self):
        rating, agree = self._fn(EpistemicRating.DEBUNKED, EpistemicRating.SPECULATIVE)
        assert rating == EpistemicRating.SPECULATIVE
        assert agree is False

    def test_no_secondary_passes_through_claude_rating(self):
        for r in EpistemicRating:
            rating, agree = self._fn(r, None)
            assert rating == r
            assert agree is None

    def test_debunked_plus_missing_resolves_to_debunked(self):
        rating, agree = self._fn(EpistemicRating.DEBUNKED, EpistemicRating.MISSING)
        assert rating == EpistemicRating.DEBUNKED
        assert agree is False

    def test_missing_plus_debunked_resolves_to_debunked(self):
        rating, agree = self._fn(EpistemicRating.MISSING, EpistemicRating.DEBUNKED)
        assert rating == EpistemicRating.DEBUNKED
        assert agree is False

    def test_verified_plus_missing_resolves_to_speculative(self):
        rating, agree = self._fn(EpistemicRating.VERIFIED, EpistemicRating.MISSING)
        assert rating == EpistemicRating.SPECULATIVE
        assert agree is False

    def test_missing_plus_verified_resolves_to_speculative(self):
        rating, agree = self._fn(EpistemicRating.MISSING, EpistemicRating.VERIFIED)
        assert rating == EpistemicRating.SPECULATIVE
        assert agree is False

    def test_disagree_result_is_never_verified_without_source_quality(self):
        # Without source quality advantage (defaults), disagreement never yields VERIFIED
        ratings = list(EpistemicRating)
        for r1 in ratings:
            for r2 in ratings:
                if r1 != r2:
                    result, flag = self._fn(r1, r2)
                    assert result != EpistemicRating.VERIFIED
                    assert flag is False

    def test_disagree_claude_primary_wins(self):
        rating, agree = self._fn(
            EpistemicRating.VERIFIED, EpistemicRating.DEBUNKED,
            claude_source_quality=(1, 0),
        )
        assert rating == EpistemicRating.VERIFIED
        assert agree is False

    def test_disagree_mistral_primary_wins(self):
        rating, agree = self._fn(
            EpistemicRating.DEBUNKED, EpistemicRating.VERIFIED,
            mistral_source_quality=(1, 0),
        )
        assert rating == EpistemicRating.VERIFIED
        assert agree is False

    def test_disagree_equal_quality_falls_back_to_speculative(self):
        # Equal quality (1 primary each) → no tiebreaker winner → SPECULATIVE
        rating, agree = self._fn(
            EpistemicRating.VERIFIED, EpistemicRating.DEBUNKED,
            claude_source_quality=(1, 0),
            mistral_source_quality=(1, 0),
        )
        assert rating == EpistemicRating.SPECULATIVE
        assert agree is False

    def test_disagree_debunked_missing_source_quality_does_not_override(self):
        # DEBUNKED+MISSING is resolved before source quality check
        rating, agree = self._fn(
            EpistemicRating.DEBUNKED, EpistemicRating.MISSING,
            mistral_source_quality=(1, 0),
        )
        assert rating == EpistemicRating.DEBUNKED
        assert agree is False

    def test_debunked_verified_claude_primary_yields_debunked(self):
        # Claude=DEBUNKED with Primary/Independent beats Mistral=VERIFIED (Mistral has no primary)
        rating, agree = self._fn(
            EpistemicRating.DEBUNKED, EpistemicRating.VERIFIED,
            claude_source_quality=(1, 0),
        )
        assert rating == EpistemicRating.DEBUNKED
        assert agree is False

    def test_debunked_verified_claude_primary_beats_both_primary(self):
        # Claude=DEBUNKED + Primary/Independent wins even when Mistral also has primary sources.
        # Counter-evidence from the primary pipeline prevails over supporting evidence.
        rating, agree = self._fn(
            EpistemicRating.DEBUNKED, EpistemicRating.VERIFIED,
            claude_source_quality=(1, 0),
            mistral_source_quality=(1, 0),
        )
        assert rating == EpistemicRating.DEBUNKED
        assert agree is False

    def test_tiebreak_more_primary_wins(self):
        # Claude has 2 primary/independent, Mistral has 1 — Claude's rating wins
        rating, agree = self._fn(
            EpistemicRating.DEBUNKED, EpistemicRating.SPECULATIVE,
            claude_source_quality=(2, 0),
            mistral_source_quality=(1, 0),
        )
        assert rating == EpistemicRating.DEBUNKED
        assert agree is False

    def test_tiebreak_secondary_decides_when_primary_tied(self):
        # Equal primary (1 each); Claude has more secondary — Claude wins
        rating, agree = self._fn(
            EpistemicRating.DEBUNKED, EpistemicRating.SPECULATIVE,
            claude_source_quality=(1, 2),
            mistral_source_quality=(1, 0),
        )
        assert rating == EpistemicRating.DEBUNKED
        assert agree is False

    def test_tiebreak_no_primary_secondary_decides(self):
        # Neither has primary; Claude has secondary sources — Claude wins
        rating, agree = self._fn(
            EpistemicRating.DEBUNKED, EpistemicRating.SPECULATIVE,
            claude_source_quality=(0, 2),
            mistral_source_quality=(0, 0),
        )
        assert rating == EpistemicRating.DEBUNKED
        assert agree is False

    def test_real_conflicts_downgrade_to_speculative(self):
        # Pairs that are genuine conflicts (not DEBUNKED+MISSING) → SPECULATIVE
        real_conflicts = [
            (EpistemicRating.VERIFIED, EpistemicRating.DEBUNKED),
            (EpistemicRating.DEBUNKED, EpistemicRating.VERIFIED),
            (EpistemicRating.VERIFIED, EpistemicRating.SPECULATIVE),
            (EpistemicRating.SPECULATIVE, EpistemicRating.VERIFIED),
            (EpistemicRating.DEBUNKED, EpistemicRating.SPECULATIVE),
            (EpistemicRating.SPECULATIVE, EpistemicRating.DEBUNKED),
            (EpistemicRating.SPECULATIVE, EpistemicRating.MISSING),
            (EpistemicRating.MISSING, EpistemicRating.SPECULATIVE),
        ]
        for r1, r2 in real_conflicts:
            result, flag = self._fn(r1, r2)
            assert result == EpistemicRating.SPECULATIVE, f"Expected SPECULATIVE for {r1}+{r2}, got {result}"
            assert flag is False


# ── _mistral_phase2_judgment ──────────────────────────────────────────────────

class TestMistralPhase2:

    def _make_tool_response(self, args: dict) -> MagicMock:
        """Build a mock Mistral chat.complete() response with a single tool call."""
        fn = MagicMock()
        fn.name = "submit_judgment"
        fn.arguments = json.dumps(args)

        call = MagicMock()
        call.function = fn

        message = MagicMock()
        message.tool_calls = [call]

        choice = MagicMock()
        choice.message = message

        response = MagicMock()
        response.choices = [choice]
        return response

    def test_parses_tool_call_correctly(self):
        from backend.analysis.consensus import _mistral_phase2_judgment

        payload = {
            "rating": "verified",
            "rationale": "Evidence found.",
            "sources": [],
        }
        mock_response = self._make_tool_response(payload)
        mock_client = MagicMock()
        mock_client.chat.complete.return_value = mock_response

        with patch("backend.analysis.consensus._get_mistral_client", return_value=mock_client):
            result = _mistral_phase2_judgment("Some claim", "Some findings")

        assert result["rating"] == "verified"
        assert result["rationale"] == "Evidence found."

    def test_parses_dict_arguments_directly(self):
        """Some SDK versions return arguments as a dict rather than a JSON string."""
        from backend.analysis.consensus import _mistral_phase2_judgment

        payload = {"rating": "missing", "rationale": "No sources.", "sources": []}

        fn = MagicMock()
        fn.name = "submit_judgment"
        fn.arguments = payload  # already a dict

        call = MagicMock()
        call.function = fn

        message = MagicMock()
        message.tool_calls = [call]

        choice = MagicMock()
        choice.message = message

        response = MagicMock()
        response.choices = [choice]

        mock_client = MagicMock()
        mock_client.chat.complete.return_value = response

        with patch("backend.analysis.consensus._get_mistral_client", return_value=mock_client):
            result = _mistral_phase2_judgment("Some claim", "")

        assert result["rating"] == "missing"

    def test_raises_when_no_tool_calls(self):
        from backend.analysis.consensus import _mistral_phase2_judgment

        message = MagicMock()
        message.tool_calls = []

        choice = MagicMock()
        choice.message = message

        response = MagicMock()
        response.choices = [choice]

        mock_client = MagicMock()
        mock_client.chat.complete.return_value = response

        with patch("backend.analysis.consensus._get_mistral_client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="did not return any tool calls"):
                _mistral_phase2_judgment("claim", "findings")

    def test_raises_when_wrong_tool_name(self):
        from backend.analysis.consensus import _mistral_phase2_judgment

        fn = MagicMock()
        fn.name = "some_other_tool"
        fn.arguments = "{}"

        call = MagicMock()
        call.function = fn

        message = MagicMock()
        message.tool_calls = [call]

        choice = MagicMock()
        choice.message = message

        response = MagicMock()
        response.choices = [choice]

        mock_client = MagicMock()
        mock_client.chat.complete.return_value = response

        with patch("backend.analysis.consensus._get_mistral_client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="unexpected tool"):
                _mistral_phase2_judgment("claim", "findings")


# ── _verify_rating_consistency ────────────────────────────────────────────────

class TestVerifyRatingConsistency:

    def setup_method(self):
        from backend.analysis.engine import _verify_rating_consistency
        self._fn = _verify_rating_consistency

    def test_agreement_returns_structured_rating_unchanged(self):
        """Haiku agrees with structured rating → return it unchanged."""
        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "VERIFIED"
        mock_client.messages.create.return_value.content = [mock_block]

        result = self._fn("The evidence clearly supports the claim.", "verified", mock_client)
        assert result == "verified"

    def test_override_when_haiku_disagrees(self):
        """Haiku returns different rating → override structured rating."""
        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "DEBUNKED"
        mock_client.messages.create.return_value.content = [mock_block]

        result = self._fn("The claim is false according to all sources.", "speculative", mock_client)
        assert result == "debunked"

    def test_haiku_failure_keeps_original_rating(self):
        """Haiku call raises → keep structured rating unchanged."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("API error")

        result = self._fn("Some rationale text.", "speculative", mock_client)
        assert result == "speculative"


_THREE_INDEPENDENT_PRIMARIES = [
    {
        "url": f"https://www.bls.gov/data/consensus-{i}",
        "tier": "primary",
        "is_independent": True,
        "relevance_score": 0.9,
        "supports_claim": True,
    }
    for i in range(3)
]


def _make_mock_session(claim_text: str = "Test claim"):
    mock_claim = MagicMock()
    mock_claim.text = claim_text

    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim
    return mock_session


def _run_consensus(
    claude_judgment: dict,
    mistral_judgment: dict | None,
    *,
    mistral_raises: Exception | None = None,
    mistral_key: str = "fake-key",
    brave_key: str = "",
    claim_text: str = "Test claim",
):
    """
    Run analyze_claim_with_consensus with fully mocked I/O.
    Returns (judgment, evaluated_sources) captured from session.add() / session.add_all().
    """
    from backend.analysis import consensus as cons
    from backend.db.models import EvaluatedSource, Judgment

    mock_session = _make_mock_session(claim_text)
    captured: dict = {"sources": []}

    def fake_add(obj):
        if isinstance(obj, Judgment):
            captured["judgment"] = obj

    def fake_add_all(objs):
        captured["sources"].extend(o for o in objs if isinstance(o, EvaluatedSource))

    mock_session.add.side_effect = fake_add
    mock_session.add_all.side_effect = fake_add_all

    with patch.object(cons, "_check_specificity", return_value=(True, "")), \
         patch.object(cons, "_phase1_search", return_value="search findings"), \
         patch.object(cons, "_phase2_judgment", return_value=claude_judgment), \
         patch.object(cons, "_get_client", return_value=MagicMock()), \
         patch("backend.analysis.consensus.settings") as mock_settings:

        mock_settings.mistral_api_key = mistral_key
        mock_settings.brave_api_key = brave_key
        mock_settings.searxng_url = ""

        if mistral_raises is not None:
            patch_target = patch.object(cons, "_mistral_phase2_judgment", side_effect=mistral_raises)
        elif mistral_judgment is not None:
            patch_target = patch.object(cons, "_mistral_phase2_judgment", return_value=mistral_judgment)
        else:
            patch_target = patch.object(cons, "_mistral_phase2_judgment", return_value={})

        with patch_target:
            cons.analyze_claim_with_consensus("claim-1", mock_session)

    return captured.get("judgment"), captured["sources"]


# ── analyze_claim_with_consensus — integration tests ─────────────────────────

class TestAnalyzeClaimWithConsensus:

    def test_models_agree_stores_correct_consensus_fields(self):
        claude_j = {"rationale": "Claude says verified.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral agrees.", "sources": [], "rating": "verified"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert j.rating == EpistemicRating.VERIFIED
        assert j.consensus_rating == EpistemicRating.VERIFIED
        assert j.models_agree is True
        assert j.analyst == "claude-sonnet-4-6"
        assert j.analyst_secondary == "mistral-large-2512"

    def test_models_agree_rationale_is_claude_rationale(self):
        claude_j = {"rationale": "Claude rationale.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral rationale.", "sources": [], "rating": "verified"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert j.rationale == "Claude rationale."

    def test_models_disagree_source_quality_advantage_wins(self):
        """Claude has Primary/Independent sources; Mistral has none — Claude's rating wins."""
        claude_j = {"rationale": "Claude says verified.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral says debunked.", "sources": [], "rating": "debunked"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert j.rating == EpistemicRating.VERIFIED
        assert j.consensus_rating == EpistemicRating.VERIFIED
        assert j.models_agree is False

    def test_models_disagree_no_source_advantage_is_speculative(self):
        """Neither model has Primary/Independent sources — disagreement falls back to SPECULATIVE."""
        claude_j = {"rationale": "Claude says verified.", "sources": [], "rating": "verified"}
        mistral_j = {"rationale": "Mistral says debunked.", "sources": [], "rating": "debunked"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert j.rating == EpistemicRating.SPECULATIVE
        assert j.consensus_rating == EpistemicRating.SPECULATIVE
        assert j.models_agree is False

    def test_models_disagree_rationale_includes_both_verdicts(self):
        claude_j = {"rationale": "Claude says verified.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral says debunked.", "sources": [], "rating": "debunked"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert "VERIFIED" in j.rationale
        assert "DEBUNKED" in j.rationale
        assert "[RESOLUTION:consensus.source_quality_claude]" in j.rationale

    def test_models_disagree_rationale_speculative_note_when_no_advantage(self):
        claude_j = {"rationale": "Claude says verified.", "sources": [], "rating": "verified"}
        mistral_j = {"rationale": "Mistral says debunked.", "sources": [], "rating": "debunked"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert "[RESOLUTION:consensus.disagreement]" in j.rationale

    def test_mistral_phase2_raises_falls_back_to_claude(self):
        claude_j = {"rationale": "Claude only.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}

        j, _ = _run_consensus(claude_j, None, mistral_raises=RuntimeError("API timeout"))

        assert j.rating == EpistemicRating.VERIFIED
        assert j.models_agree is None
        assert j.analyst_secondary is None
        assert j.consensus_rating == EpistemicRating.VERIFIED

    def test_no_mistral_key_falls_back_to_claude(self):
        claude_j = {"rationale": "Claude only.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "speculative"}

        j, _ = _run_consensus(claude_j, None, mistral_key="")

        assert j.rating == EpistemicRating.SPECULATIVE
        assert j.models_agree is None
        assert j.analyst_secondary is None

    def test_mistral_invalid_rating_treated_as_unavailable(self):
        """If Mistral returns an unrecognised rating string, Mistral's verdict is ignored."""
        claude_j = {"rationale": "Claude says verified.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Weird.", "sources": [], "rating": "not-a-real-rating"}

        j, _ = _run_consensus(claude_j, mistral_j)

        # Mistral rating was invalid → mistral_rating=None → pass-through
        assert j.rating == EpistemicRating.VERIFIED
        assert j.models_agree is None

    def test_vague_claim_returns_missing_without_secondary(self):
        from backend.analysis import consensus as cons
        from backend.db.models import Judgment

        mock_session = _make_mock_session()
        captured: dict = {}

        def fake_add(obj):
            if isinstance(obj, Judgment):
                captured["judgment"] = obj

        mock_session.add.side_effect = fake_add
        mock_session.add_all.side_effect = lambda objs: None

        with patch.object(cons, "_check_specificity", return_value=(False, "Too vague.")), \
             patch.object(cons, "_get_client", return_value=MagicMock()), \
             patch("backend.analysis.consensus.settings") as mock_settings:
            mock_settings.mistral_api_key = "fake-key"
            mock_settings.brave_api_key = ""
            cons.analyze_claim_with_consensus("claim-1", mock_session)

        j = captured["judgment"]
        assert j.rating == EpistemicRating.MISSING
        assert j.analyst_secondary is None
        assert j.models_agree is None

    def test_claim_not_found_raises_value_error(self):
        from backend.analysis import consensus as cons

        mock_session = MagicMock()
        mock_session.get.return_value = None

        with patch.object(cons, "_get_client", return_value=MagicMock()), \
             patch("backend.analysis.consensus.settings") as mock_settings:
            mock_settings.mistral_api_key = "fake-key"
            mock_settings.brave_api_key = ""
            with pytest.raises(ValueError, match="not found"):
                cons.analyze_claim_with_consensus("nonexistent", mock_session)

    def test_models_agree_no_sources_returns_missing(self):
        """Both agree on MISSING when no sources are available."""
        claude_j = {"rationale": "No evidence.", "sources": [], "rating": "missing"}
        mistral_j = {"rationale": "No evidence.", "sources": [], "rating": "missing"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert j.rating == EpistemicRating.MISSING
        assert j.models_agree is True

    def test_mistral_secondary_field_absent_on_fallback(self):
        """analyst_secondary must be null when Mistral was not used."""
        claude_j = {"rationale": "Claude.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}

        j, _ = _run_consensus(claude_j, None, mistral_key="")

        assert j.analyst_secondary is None

    def test_mistral_secondary_field_set_when_mistral_ran(self):
        claude_j = {"rationale": "Claude.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral.", "sources": [], "rating": "verified"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert j.analyst_secondary == "mistral-large-2512"

    def test_evaluated_sources_persisted_when_claude_hard_rule_fires(self):
        """
        EvaluatedSource objects must be added to the session even when the Claude
        Hard Rule downgrades the rating from VERIFIED to SPECULATIVE (no independent
        qualifying source present).
        """
        from backend.db.models import EvaluatedSource

        # Claude claims VERIFIED but provides only a tertiary, non-qualifying source
        # so the Hard Rule will fire and downgrade to SPECULATIVE.
        non_qualifying_source = {
            "url": "https://example.com/tertiary",
            "title": "Tertiary Source",
            "tier": "tertiary",
            "is_independent": True,
            "relevance_score": 0.8,
            "supports_claim": True,
        }
        claude_j = {
            "rationale": "Claude says verified.",
            "sources": [non_qualifying_source],
            "rating": "verified",
        }
        mistral_j = {"rationale": "Mistral agrees.", "sources": [], "rating": "verified"}

        j, sources = _run_consensus(claude_j, mistral_j)

        # Hard Rule should have downgraded the rating
        assert j.rating == EpistemicRating.SPECULATIVE
        # Sources must still be persisted despite the downgrade
        assert len(sources) == 1
        assert all(isinstance(s, EvaluatedSource) for s in sources)
        assert sources[0].url == "https://example.com/tertiary"

    def test_evaluated_sources_persisted_when_consensus_hard_rule_fires(self):
        """
        EvaluatedSource objects must be added to the session even when the consensus
        Hard Rule downgrades the consensus rating from VERIFIED to SPECULATIVE.
        Both models agree on VERIFIED but Claude has no independent qualifying source,
        so the consensus Hard Rule fires.
        """
        from backend.db.models import EvaluatedSource

        # Both models say VERIFIED, but Claude's source is tertiary (non-qualifying),
        # which means claude_has_qualifying=False and the consensus Hard Rule fires.
        non_qualifying_source = {
            "url": "https://wiki.example.com/page",
            "title": "Wikipedia Page",
            "tier": "tertiary",
            "is_independent": True,
            "relevance_score": 0.75,
            "supports_claim": True,
        }
        claude_j = {
            "rationale": "Claude says verified.",
            "sources": [non_qualifying_source],
            "rating": "verified",
        }
        mistral_j = {"rationale": "Mistral agrees.", "sources": [], "rating": "verified"}

        j, sources = _run_consensus(claude_j, mistral_j)

        # Consensus Hard Rule should have downgraded to SPECULATIVE
        assert j.rating == EpistemicRating.SPECULATIVE
        assert j.consensus_rating == EpistemicRating.SPECULATIVE
        # Sources must be persisted in all cases
        assert len(sources) == 1
        assert isinstance(sources[0], EvaluatedSource)
        assert sources[0].url == "https://wiki.example.com/page"

    # ── Regression: Quellen(0) on disagreement path ───────────────────────────

    def test_sources_persisted_when_claude_speculative_mistral_debunked(self):
        """
        Regression: EvaluatedSource objects must be saved even when Claude=SPECULATIVE
        and Mistral=DEBUNKED disagree and consensus is downgraded to SPECULATIVE.
        The Quellen(0) bug arose because session.add_all() was gated on consensus
        resolution; moving it before _resolve_consensus() fixes the path.
        """
        from backend.db.models import EvaluatedSource

        source = {
            "url": "https://example.com/source-1",
            "title": "Source 1",
            "tier": "tertiary",
            "is_independent": True,
            "relevance_score": 0.8,
            "supports_claim": True,
        }
        claude_j = {"rationale": "Claude speculative.", "sources": [source], "rating": "speculative"}
        mistral_j = {"rationale": "Mistral debunked.", "sources": [], "rating": "debunked"}

        j, sources = _run_consensus(claude_j, mistral_j)

        assert j.rating == EpistemicRating.SPECULATIVE
        assert j.consensus_rating == EpistemicRating.SPECULATIVE
        assert len(sources) > 0
        assert all(isinstance(s, EvaluatedSource) for s in sources)

    def test_sources_persisted_when_claude_verified_mistral_speculative(self):
        """
        Regression: EvaluatedSource objects must be saved even when Claude=VERIFIED
        and Mistral=SPECULATIVE disagree and consensus resolves to SPECULATIVE.
        Claude has no qualifying primary source so the hard quality gate also fires.
        """
        from backend.db.models import EvaluatedSource

        source = {
            "url": "https://example.com/source-2",
            "title": "Source 2",
            "tier": "tertiary",
            "is_independent": True,
            "relevance_score": 0.8,
            "supports_claim": True,
        }
        claude_j = {"rationale": "Claude verified.", "sources": [source], "rating": "verified"}
        mistral_j = {"rationale": "Mistral speculative.", "sources": [], "rating": "speculative"}

        j, sources = _run_consensus(claude_j, mistral_j)

        assert j.rating == EpistemicRating.SPECULATIVE
        assert j.consensus_rating == EpistemicRating.SPECULATIVE
        assert len(sources) > 0
        assert all(isinstance(s, EvaluatedSource) for s in sources)

    def test_sources_persisted_when_both_debunked_normal_case(self):
        """
        Regression (normal case): EvaluatedSource objects must be saved when both
        models agree on DEBUNKED. Verifies no regression on the agreement path.
        """
        from backend.db.models import EvaluatedSource

        claude_j = {
            "rationale": "Claude debunked.",
            "sources": _THREE_INDEPENDENT_PRIMARIES,
            "rating": "debunked",
        }
        mistral_j = {"rationale": "Mistral debunked.", "sources": [], "rating": "debunked"}

        j, sources = _run_consensus(claude_j, mistral_j)

        assert j.rating == EpistemicRating.DEBUNKED
        assert j.consensus_rating == EpistemicRating.DEBUNKED
        assert j.models_agree is True
        assert len(sources) > 0
        assert all(isinstance(s, EvaluatedSource) for s in sources)


# ── _mistral_phase1_brave_search ──────────────────────────────────────────────

def _make_brave_http_mock(results: list[dict]) -> MagicMock:
    """Return a mock httpx.Client context manager that yields the given results."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"web": {"results": results}}

    mock_http = MagicMock()
    mock_http.__enter__ = MagicMock(return_value=mock_http)
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.get.return_value = mock_response
    return mock_http


class TestBraveSearch:

    def test_returns_formatted_findings_for_valid_response(self):
        from backend.sources.search import search_claim

        results = [
            {"title": "Article A", "url": "https://a.example/1", "description": "Excerpt A."},
            {"title": "Article B", "url": "https://b.example/2", "description": "Excerpt B."},
        ]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "test-brave-key"
            s.searxng_url = ""
            output = search_claim("test claim")

        assert "Article A" in output
        assert "https://a.example/1" in output
        assert "Excerpt A." in output
        assert "Article B" in output
        assert "https://b.example/2" in output

    def test_numbers_each_source(self):
        from backend.sources.search import search_claim

        results = [
            {"title": f"Title {i}", "url": f"https://x.example/{i}", "description": f"Desc {i}."}
            for i in range(3)
        ]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            output = search_claim("claim")

        assert "Source 1:" in output
        assert "Source 2:" in output
        assert "Source 3:" in output

    def test_returns_empty_string_when_key_absent(self):
        """No HTTP call is made and "" is returned immediately when key is not configured."""
        from backend.sources.search import search_claim

        with patch("backend.sources.search.httpx.Client") as mock_client_cls, \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = ""
            s.searxng_url = ""
            result = search_claim("claim")

        assert result == ""
        mock_client_cls.assert_not_called()

    def test_returns_empty_string_when_results_empty(self):
        """Empty result list → "" (not an exception)."""
        from backend.sources.search import search_claim

        mock_http = _make_brave_http_mock([])

        with patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            result = search_claim("claim")

        assert result == ""

    def test_returns_empty_string_on_http_error(self):
        """HTTP error is caught and "" is returned so Mistral still runs."""
        from backend.sources.search import search_claim
        import httpx

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403", request=MagicMock(), response=MagicMock()
        )

        with patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            result = search_claim("claim")

        assert result == ""

    def test_returns_empty_string_on_connection_error(self):
        """Network-level failures are also caught and return ""."""
        from backend.sources.search import search_claim
        import httpx

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.side_effect = httpx.ConnectError("connection refused")

        with patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            result = search_claim("claim")

        assert result == ""

    def test_sends_claim_as_query_param(self):
        from backend.sources.search import _query_brave

        results = [{"title": "T", "url": "https://t.example/", "description": "D"}]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "my-key"
            _query_brave("Joe Biden said X")

        call_kwargs = mock_http.get.call_args
        assert call_kwargs.kwargs["params"]["q"] == "Joe Biden said X"

    def test_sends_api_key_header(self):
        from backend.sources.search import _query_brave

        results = [{"title": "T", "url": "https://t.example/", "description": "D"}]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "my-secret"
            _query_brave("claim text")

        call_kwargs = mock_http.get.call_args
        assert call_kwargs.kwargs["headers"]["X-Subscription-Token"] == "my-secret"


# ── Brave integration in analyze_claim_with_consensus ─────────────────────────

class TestBraveIntegration:

    def test_mistral_receives_brave_findings_when_brave_available(self):
        """When BRAVE_API_KEY is set and Brave succeeds, Mistral Phase 2 gets Brave findings."""
        from backend.analysis import consensus as cons

        claude_j = {"rationale": "Claude.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral.", "sources": [], "rating": "verified"}

        mock_session = _make_mock_session()
        mock_session.add.side_effect = lambda obj: None
        mock_session.add_all.side_effect = lambda objs: None

        captured_findings: list[str] = []

        def fake_mistral_p2(claim_text, findings, lang_instruction=""):
            captured_findings.append(findings)
            return mistral_j

        with patch.object(cons, "_check_specificity", return_value=(True, "")), \
             patch.object(cons, "_phase1_search", return_value="claude findings"), \
             patch.object(cons, "_phase2_judgment", return_value=claude_j), \
             patch.object(cons, "_get_client", return_value=MagicMock()), \
             patch.object(cons, "search_claim", return_value="brave findings"), \
             patch.object(cons, "_mistral_phase2_judgment", side_effect=fake_mistral_p2), \
             patch("backend.analysis.consensus.settings") as mock_settings:
            mock_settings.mistral_api_key = "fake-mistral-key"
            mock_settings.brave_api_key = "fake-brave-key"
            cons.analyze_claim_with_consensus("claim-1", mock_session)

        assert captured_findings == ["brave findings"]

    def test_brave_findings_are_independent_of_claude_findings(self):
        """Mistral receives Brave findings even when Claude's findings are different."""
        from backend.analysis import consensus as cons

        claude_j = {"rationale": "Claude.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral.", "sources": [], "rating": "verified"}

        mock_session = _make_mock_session()
        mock_session.add.side_effect = lambda obj: None
        mock_session.add_all.side_effect = lambda objs: None

        captured_claude: list[str] = []
        captured_mistral: list[str] = []

        def fake_claude_p2(client, claim_text, findings, lang_instruction=""):
            captured_claude.append(findings)
            return claude_j

        def fake_mistral_p2(claim_text, findings, lang_instruction=""):
            captured_mistral.append(findings)
            return mistral_j

        with patch.object(cons, "_check_specificity", return_value=(True, "")), \
             patch.object(cons, "_phase1_search", return_value="claude-only findings"), \
             patch.object(cons, "_phase2_judgment", side_effect=fake_claude_p2), \
             patch.object(cons, "_get_client", return_value=MagicMock()), \
             patch.object(cons, "search_claim", return_value="brave-only findings"), \
             patch.object(cons, "_mistral_phase2_judgment", side_effect=fake_mistral_p2), \
             patch("backend.analysis.consensus.settings") as mock_settings:
            mock_settings.mistral_api_key = "fake-mistral-key"
            mock_settings.brave_api_key = "fake-brave-key"
            cons.analyze_claim_with_consensus("claim-1", mock_session)

        assert captured_claude == ["claude-only findings"]
        assert captured_mistral == ["brave-only findings"]

    def test_mistral_receives_empty_string_when_brave_unavailable(self):
        """When BRAVE_API_KEY is absent, Mistral Phase 2 receives "" — not Claude's findings."""
        from backend.analysis import consensus as cons

        claude_j = {"rationale": "Claude.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral.", "sources": [], "rating": "verified"}

        mock_session = _make_mock_session()
        mock_session.add.side_effect = lambda obj: None
        mock_session.add_all.side_effect = lambda objs: None

        captured_findings: list[str] = []

        def fake_mistral_p2(claim_text, findings, lang_instruction=""):
            captured_findings.append(findings)
            return mistral_j

        with patch.object(cons, "_check_specificity", return_value=(True, "")), \
             patch.object(cons, "_phase1_search", return_value="claude findings"), \
             patch.object(cons, "_phase2_judgment", return_value=claude_j), \
             patch.object(cons, "_get_client", return_value=MagicMock()), \
             patch.object(cons, "search_claim", return_value=""), \
             patch.object(cons, "_mistral_phase2_judgment", side_effect=fake_mistral_p2), \
             patch("backend.analysis.consensus.settings") as mock_settings:
            mock_settings.mistral_api_key = "fake-mistral-key"
            mock_settings.brave_api_key = ""
            cons.analyze_claim_with_consensus("claim-1", mock_session)

        assert captured_findings == [""]

    def test_mistral_receives_empty_string_when_brave_fails(self):
        """When Brave is configured but the request fails, Mistral gets "" — not Claude's findings."""
        from backend.analysis import consensus as cons

        claude_j = {"rationale": "Claude.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral.", "sources": [], "rating": "verified"}

        mock_session = _make_mock_session()
        mock_session.add.side_effect = lambda obj: None
        mock_session.add_all.side_effect = lambda objs: None

        captured_findings: list[str] = []

        def fake_mistral_p2(claim_text, findings, lang_instruction=""):
            captured_findings.append(findings)
            return mistral_j

        with patch.object(cons, "_check_specificity", return_value=(True, "")), \
             patch.object(cons, "_phase1_search", return_value="claude findings"), \
             patch.object(cons, "_phase2_judgment", return_value=claude_j), \
             patch.object(cons, "_get_client", return_value=MagicMock()), \
             patch.object(cons, "search_claim", return_value=""), \
             patch.object(cons, "_mistral_phase2_judgment", side_effect=fake_mistral_p2), \
             patch("backend.analysis.consensus.settings") as mock_settings:
            mock_settings.mistral_api_key = "fake-mistral-key"
            mock_settings.brave_api_key = "fake-brave-key"
            cons.analyze_claim_with_consensus("claim-1", mock_session)

        assert captured_findings == [""]

    def test_consensus_result_correct_regardless_of_brave_availability(self):
        """Consensus rating is correct whether Mistral received Brave findings or ""."""
        claude_j = {"rationale": "Claude verified.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral verified.", "sources": [], "rating": "verified"}

        j, _ = _run_consensus(claude_j, mistral_j)  # brave_key="" by default

        assert j.models_agree is True
        assert j.consensus_rating == EpistemicRating.VERIFIED


# ── SearXNG helpers: _query_searxng ──────────────────────────────────────────

def _make_searxng_http_mock(results: list[dict]):
    """Return a mock httpx.Client whose GET response contains the given SearXNG results."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"results": results}

    mock_http = MagicMock()
    mock_http.__enter__ = MagicMock(return_value=mock_http)
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.get.return_value = mock_response
    return mock_http


class TestQuerySearxng:

    def test_returns_normalised_results(self):
        from backend.sources.search import _query_searxng

        raw = [
            {"title": "SearX Result 1", "url": "https://sx.example/1", "content": "SearXNG content 1."},
            {"title": "SearX Result 2", "url": "https://sx.example/2", "content": "SearXNG content 2."},
        ]
        mock_http = _make_searxng_http_mock(raw)

        with patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.searxng_url = "https://searx.example.com"
            results = _query_searxng("test claim")

        assert len(results) == 2
        assert results[0]["title"] == "SearX Result 1"
        assert results[0]["url"] == "https://sx.example/1"
        assert results[0]["description"] == "SearXNG content 1."

    def test_returns_empty_list_when_url_not_configured(self):
        from backend.sources.search import _query_searxng

        with patch("backend.sources.search.httpx.Client") as mock_client_cls, \
             patch("backend.sources.search.settings") as s:
            s.searxng_url = ""
            result = _query_searxng("claim")

        assert result == []
        mock_client_cls.assert_not_called()

    def test_returns_empty_list_on_http_error(self):
        import httpx as _httpx
        from backend.sources.search import _query_searxng

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.return_value.raise_for_status.side_effect = _httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )

        with patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.searxng_url = "https://searx.example.com"
            result = _query_searxng("claim")

        assert result == []

    def test_returns_empty_list_on_connection_error(self):
        import httpx as _httpx
        from backend.sources.search import _query_searxng

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.side_effect = _httpx.ConnectError("refused")

        with patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.searxng_url = "https://searx.example.com"
            result = _query_searxng("claim")

        assert result == []

    def test_sends_correct_query_params(self):
        from backend.sources.search import _query_searxng

        mock_http = _make_searxng_http_mock([
            {"title": "T", "url": "https://t.example/", "content": "C"}
        ])

        with patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.searxng_url = "https://searx.example.com"
            _query_searxng("specific claim text")

        call_kwargs = mock_http.get.call_args
        assert call_kwargs.kwargs["params"]["q"] == "specific claim text"
        assert call_kwargs.kwargs["params"]["format"] == "json"
        assert call_kwargs.kwargs["params"]["categories"] == "general"

    def test_strips_trailing_slash_from_url(self):
        from backend.sources.search import _query_searxng

        mock_http = _make_searxng_http_mock([])

        with patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.searxng_url = "https://searx.example.com/"
            _query_searxng("claim")

        called_url = mock_http.get.call_args.args[0]
        assert called_url == "https://searx.example.com/search"


class TestSearxngInMistralPhase1:

    def test_searxng_results_included_when_configured(self):
        """When SEARXNG_URL is set and Brave is absent, SearXNG results are returned."""
        from backend.sources.search import search_claim

        raw = [{"title": "SX Title", "url": "https://sx.example/1", "content": "SX content."}]
        mock_http = _make_searxng_http_mock(raw)

        with patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = ""
            s.searxng_url = "https://searx.example.com"
            output = search_claim("test claim")

        assert "SX Title" in output
        assert "https://sx.example/1" in output
        assert "SX content." in output

    def test_deduplicates_by_url_when_both_sources_return_same_url(self):
        """URLs present in both Brave and SearXNG results appear only once."""
        from backend.sources.search import search_claim

        shared_url = "https://shared.example/article"
        brave_results = [
            {"title": "Brave Version", "url": shared_url, "description": "Brave excerpt."},
        ]

        with patch("backend.sources.search._query_brave", return_value=brave_results), \
             patch("backend.sources.search._query_searxng", return_value=[
                 {"title": "SearXNG Version", "url": shared_url, "description": "SearXNG excerpt."},
                 {"title": "SearXNG Unique", "url": "https://unique.example/", "description": "Unique."},
             ]), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "brave-key"
            s.searxng_url = "https://searx.example.com"
            output = search_claim("claim")

        # shared URL appears exactly once
        assert output.count(shared_url) == 1
        # unique SearXNG URL is also present
        assert "https://unique.example/" in output

    def test_merges_brave_and_searxng_results(self):
        """When both sources are configured, results from both are present."""
        from backend.sources.search import search_claim

        brave_results = [
            {"title": "Brave Article", "url": "https://brave.example/1", "description": "Brave desc."},
        ]
        searxng_results = [
            {"title": "SearXNG Article", "url": "https://searxng.example/1", "description": "SearX desc."},
        ]

        with patch("backend.sources.search._query_brave", return_value=brave_results), \
             patch("backend.sources.search._query_searxng", return_value=searxng_results), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "brave-key"
            s.searxng_url = "https://searx.example.com"
            output = search_claim("claim")

        assert "Brave Article" in output
        assert "https://brave.example/1" in output
        assert "SearXNG Article" in output
        assert "https://searxng.example/1" in output

    def test_returns_empty_string_when_both_unconfigured(self):
        """No HTTP call when neither Brave key nor SearXNG URL is set."""
        from backend.sources.search import search_claim

        with patch("backend.sources.search.httpx.Client") as mock_client_cls, \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = ""
            s.searxng_url = ""
            result = search_claim("claim")

        assert result == ""
        mock_client_cls.assert_not_called()

    def test_searxng_failure_still_returns_brave_results(self):
        """If SearXNG fails, Brave results are still returned (graceful degradation)."""
        from backend.sources.search import search_claim

        brave_results = [
            {"title": "Brave OK", "url": "https://brave.example/1", "description": "Brave desc."},
        ]

        with patch("backend.sources.search._query_brave", return_value=brave_results), \
             patch("backend.sources.search._query_searxng", return_value=[]), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "brave-key"
            s.searxng_url = "https://searx.example.com"
            output = search_claim("claim")

        assert "Brave OK" in output

    def test_brave_failure_still_returns_searxng_results(self):
        """If Brave fails, SearXNG results are still returned (graceful degradation)."""
        from backend.sources.search import search_claim

        searxng_results = [
            {"title": "SearX OK", "url": "https://searxng.example/1", "description": "SearX desc."},
        ]

        with patch("backend.sources.search._query_brave", return_value=[]), \
             patch("backend.sources.search._query_searxng", return_value=searxng_results), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "brave-key"
            s.searxng_url = "https://searx.example.com"
            output = search_claim("claim")

        assert "SearX OK" in output


# ── _phase1_search delegation (engine.py) ────────────────────────────────────

class TestPhase1Search:

    def test_delegates_to_search_claim(self):
        """_phase1_search must call search_claim with the claim text and return its result."""
        from backend.analysis import engine as eng

        with patch("backend.analysis.engine.search_claim", return_value="mocked findings") as mock_sc:
            result = eng._phase1_search("test claim")

        mock_sc.assert_called_once_with("test claim")
        assert result == "mocked findings"

    def test_returns_empty_when_search_claim_returns_empty(self):
        """_phase1_search propagates "" from search_claim (no search configured)."""
        from backend.analysis import engine as eng

        with patch("backend.analysis.engine.search_claim", return_value="") as mock_sc:
            result = eng._phase1_search("some claim")

        mock_sc.assert_called_once_with("some claim")
        assert result == ""
