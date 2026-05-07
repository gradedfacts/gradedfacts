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

    def test_disagree_result_is_never_verified(self):
        # All disagreeing pairs must not produce VERIFIED
        ratings = list(EpistemicRating)
        for r1 in ratings:
            for r2 in ratings:
                if r1 != r2:
                    result, flag = self._fn(r1, r2)
                    assert result != EpistemicRating.VERIFIED
                    assert flag is False

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


# ── analyze_claim_with_consensus — helpers ────────────────────────────────────

_THREE_INDEPENDENT_PRIMARIES = [
    {
        "url": f"https://www.reuters.com/article/consensus-{i}",
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
    Returns the Judgment captured by session.add().

    brave_key defaults to "" so Brave Search is bypassed and _mistral_phase2_judgment
    (which is mocked here) receives Claude's findings — matching pre-Brave behaviour.
    Pass a non-empty brave_key to exercise the Brave code path, but then also mock
    _mistral_phase1_brave_search at the call site.
    """
    from backend.analysis import consensus as cons
    from backend.db.models import Judgment

    mock_session = _make_mock_session(claim_text)
    captured: dict = {}

    def fake_add(obj):
        if isinstance(obj, Judgment):
            captured["judgment"] = obj

    mock_session.add.side_effect = fake_add
    mock_session.add_all.side_effect = lambda objs: None

    with patch.object(cons, "_check_specificity", return_value=(True, "")), \
         patch.object(cons, "_phase1_search", return_value="search findings"), \
         patch.object(cons, "_phase2_judgment", return_value=claude_judgment), \
         patch.object(cons, "_get_client", return_value=MagicMock()), \
         patch("backend.analysis.consensus.settings") as mock_settings:

        mock_settings.mistral_api_key = mistral_key
        mock_settings.brave_api_key = brave_key

        if mistral_raises is not None:
            patch_target = patch.object(cons, "_mistral_phase2_judgment", side_effect=mistral_raises)
        elif mistral_judgment is not None:
            patch_target = patch.object(cons, "_mistral_phase2_judgment", return_value=mistral_judgment)
        else:
            patch_target = patch.object(cons, "_mistral_phase2_judgment", return_value={})

        with patch_target:
            cons.analyze_claim_with_consensus("claim-1", mock_session)

    return captured.get("judgment")


# ── analyze_claim_with_consensus — integration tests ─────────────────────────

class TestAnalyzeClaimWithConsensus:

    def test_models_agree_stores_correct_consensus_fields(self):
        claude_j = {"rationale": "Claude says verified.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral agrees.", "sources": [], "rating": "verified"}

        j = _run_consensus(claude_j, mistral_j)

        assert j.rating == EpistemicRating.VERIFIED
        assert j.consensus_rating == EpistemicRating.VERIFIED
        assert j.models_agree is True
        assert j.analyst == "claude-sonnet-4-6"
        assert j.analyst_secondary == "mistral-large-latest"

    def test_models_agree_rationale_is_claude_rationale(self):
        claude_j = {"rationale": "Claude rationale.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral rationale.", "sources": [], "rating": "verified"}

        j = _run_consensus(claude_j, mistral_j)

        assert j.rationale == "Claude rationale."

    def test_models_disagree_consensus_is_speculative(self):
        claude_j = {"rationale": "Claude says verified.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral says debunked.", "sources": [], "rating": "debunked"}

        j = _run_consensus(claude_j, mistral_j)

        assert j.rating == EpistemicRating.SPECULATIVE
        assert j.consensus_rating == EpistemicRating.SPECULATIVE
        assert j.models_agree is False

    def test_models_disagree_rationale_includes_both_verdicts(self):
        claude_j = {"rationale": "Claude says verified.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral says debunked.", "sources": [], "rating": "debunked"}

        j = _run_consensus(claude_j, mistral_j)

        assert "VERIFIED" in j.rationale
        assert "DEBUNKED" in j.rationale
        assert "Consensus downgraded to SPECULATIVE" in j.rationale

    def test_mistral_phase2_raises_falls_back_to_claude(self):
        claude_j = {"rationale": "Claude only.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}

        j = _run_consensus(claude_j, None, mistral_raises=RuntimeError("API timeout"))

        assert j.rating == EpistemicRating.VERIFIED
        assert j.models_agree is None
        assert j.analyst_secondary is None
        assert j.consensus_rating == EpistemicRating.VERIFIED

    def test_no_mistral_key_falls_back_to_claude(self):
        claude_j = {"rationale": "Claude only.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "speculative"}

        j = _run_consensus(claude_j, None, mistral_key="")

        assert j.rating == EpistemicRating.SPECULATIVE
        assert j.models_agree is None
        assert j.analyst_secondary is None

    def test_mistral_invalid_rating_treated_as_unavailable(self):
        """If Mistral returns an unrecognised rating string, Mistral's verdict is ignored."""
        claude_j = {"rationale": "Claude says verified.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Weird.", "sources": [], "rating": "not-a-real-rating"}

        j = _run_consensus(claude_j, mistral_j)

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

        j = _run_consensus(claude_j, mistral_j)

        assert j.rating == EpistemicRating.MISSING
        assert j.models_agree is True

    def test_mistral_secondary_field_absent_on_fallback(self):
        """analyst_secondary must be null when Mistral was not used."""
        claude_j = {"rationale": "Claude.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}

        j = _run_consensus(claude_j, None, mistral_key="")

        assert j.analyst_secondary is None

    def test_mistral_secondary_field_set_when_mistral_ran(self):
        claude_j = {"rationale": "Claude.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral.", "sources": [], "rating": "verified"}

        j = _run_consensus(claude_j, mistral_j)

        assert j.analyst_secondary == "mistral-large-latest"


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
        from backend.analysis.consensus import _mistral_phase1_brave_search

        results = [
            {"title": "Article A", "url": "https://a.example/1", "description": "Excerpt A."},
            {"title": "Article B", "url": "https://b.example/2", "description": "Excerpt B."},
        ]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "test-brave-key"
            output = _mistral_phase1_brave_search("test claim")

        assert "Article A" in output
        assert "https://a.example/1" in output
        assert "Excerpt A." in output
        assert "Article B" in output
        assert "https://b.example/2" in output

    def test_numbers_each_source(self):
        from backend.analysis.consensus import _mistral_phase1_brave_search

        results = [
            {"title": f"Title {i}", "url": f"https://x.example/{i}", "description": f"Desc {i}."}
            for i in range(3)
        ]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "key"
            output = _mistral_phase1_brave_search("claim")

        assert "Source 1:" in output
        assert "Source 2:" in output
        assert "Source 3:" in output

    def test_returns_empty_string_when_key_absent(self):
        """No HTTP call is made and "" is returned immediately when key is not configured."""
        from backend.analysis.consensus import _mistral_phase1_brave_search

        with patch("backend.analysis.consensus.httpx.Client") as mock_client_cls, \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = ""
            result = _mistral_phase1_brave_search("claim")

        assert result == ""
        mock_client_cls.assert_not_called()

    def test_returns_empty_string_when_results_empty(self):
        """Empty result list → "" (not an exception)."""
        from backend.analysis.consensus import _mistral_phase1_brave_search

        mock_http = _make_brave_http_mock([])

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "key"
            result = _mistral_phase1_brave_search("claim")

        assert result == ""

    def test_returns_empty_string_on_http_error(self):
        """HTTP error is caught and "" is returned so Mistral still runs."""
        from backend.analysis.consensus import _mistral_phase1_brave_search
        import httpx

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403", request=MagicMock(), response=MagicMock()
        )

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "key"
            result = _mistral_phase1_brave_search("claim")

        assert result == ""

    def test_returns_empty_string_on_connection_error(self):
        """Network-level failures are also caught and return ""."""
        from backend.analysis.consensus import _mistral_phase1_brave_search
        import httpx

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.side_effect = httpx.ConnectError("connection refused")

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "key"
            result = _mistral_phase1_brave_search("claim")

        assert result == ""

    def test_sends_claim_as_query_param(self):
        from backend.analysis.consensus import _mistral_phase1_brave_search

        results = [{"title": "T", "url": "https://t.example/", "description": "D"}]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "my-key"
            _mistral_phase1_brave_search("Joe Biden said X")

        call_kwargs = mock_http.get.call_args
        assert call_kwargs.kwargs["params"]["q"] == "Joe Biden said X"

    def test_sends_api_key_header(self):
        from backend.analysis.consensus import _mistral_phase1_brave_search

        results = [{"title": "T", "url": "https://t.example/", "description": "D"}]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "my-secret"
            _mistral_phase1_brave_search("claim text")

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
             patch.object(cons, "_mistral_phase1_brave_search", return_value="brave findings"), \
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
             patch.object(cons, "_mistral_phase1_brave_search", return_value="brave-only findings"), \
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

        # Mock _mistral_phase1_brave_search to return "" (what it does on any failure)
        with patch.object(cons, "_check_specificity", return_value=(True, "")), \
             patch.object(cons, "_phase1_search", return_value="claude findings"), \
             patch.object(cons, "_phase2_judgment", return_value=claude_j), \
             patch.object(cons, "_get_client", return_value=MagicMock()), \
             patch.object(cons, "_mistral_phase1_brave_search", return_value=""), \
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

        j = _run_consensus(claude_j, mistral_j)  # brave_key="" by default

        assert j.models_agree is True
        assert j.consensus_rating == EpistemicRating.VERIFIED
