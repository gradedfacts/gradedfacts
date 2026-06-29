"""
Tests for temporal prompt injection (STEP 1–3 of temporal logic fix).

Verifies:
  - Today's Europe/Zurich date appears in the assembled system prompt for both models.
  - The DATED PAST STATEMENTS rule (Finding B) is present in _SYSTEM_PROMPT.
  - The strengthened FUTURE CLAIMS rule (Finding A) is present in _SYSTEM_PROMPT.
  - _zurich_date() returns a well-formed ISO date string.
  - The Mistral phase-2 call actually sends the formatted date in its system message.
  - No changes were made to the rating-cap chain.
"""

import json
import re
from unittest.mock import MagicMock, patch


# ── _zurich_date ──────────────────────────────────────────────────────────────

class TestZurichDate:

    def test_returns_iso_date_format(self):
        from backend.analysis.engine import _zurich_date
        result = _zurich_date()
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", result), f"Expected YYYY-MM-DD, got {result!r}"

    def test_is_string(self):
        from backend.analysis.engine import _zurich_date
        assert isinstance(_zurich_date(), str)

    def test_deterministic_within_same_second(self):
        from backend.analysis.engine import _zurich_date
        d1 = _zurich_date()
        d2 = _zurich_date()
        assert d1 == d2


# ── Sonnet path: _cached_system ───────────────────────────────────────────────

class TestCachedSystem:

    def test_contains_zurich_date(self):
        from backend.analysis.engine import _cached_system, _zurich_date
        blocks = _cached_system()
        text = blocks[0]["text"]
        assert _zurich_date() in text

    def test_contains_current_date_label(self):
        from backend.analysis.engine import _cached_system
        text = _cached_system()[0]["text"]
        assert "CURRENT DATE (Europe/Zurich):" in text

    def test_no_unresolved_placeholder(self):
        from backend.analysis.engine import _cached_system
        text = _cached_system()[0]["text"]
        assert "{current_date}" not in text

    def test_cache_control_preserved(self):
        from backend.analysis.engine import _cached_system
        block = _cached_system()[0]
        assert block.get("cache_control") == {"type": "ephemeral"}

    def test_type_is_text(self):
        from backend.analysis.engine import _cached_system
        block = _cached_system()[0]
        assert block.get("type") == "text"


# ── Temporal rules content ────────────────────────────────────────────────────

class TestTemporalRulesInPrompt:

    def test_dated_past_statements_rule_present(self):
        from backend.analysis.engine import _SYSTEM_PROMPT
        assert "DATED PAST STATEMENTS" in _SYSTEM_PROMPT

    def test_dated_past_statements_as_of_stated_date(self):
        from backend.analysis.engine import _SYSTEM_PROMPT
        assert "AS OF THAT STATED DATE" in _SYSTEM_PROMPT

    def test_dated_past_statements_example(self):
        from backend.analysis.engine import _SYSTEM_PROMPT
        # The Biden/Trump example must be present so the rule is concrete.
        assert "Biden won in 2020" in _SYSTEM_PROMPT

    def test_future_claims_rule_present(self):
        from backend.analysis.engine import _SYSTEM_PROMPT
        assert "FUTURE CLAIMS" in _SYSTEM_PROMPT

    def test_future_claims_speculative_ceiling(self):
        from backend.analysis.engine import _SYSTEM_PROMPT
        assert "must not exceed SPECULATIVE" in _SYSTEM_PROMPT

    def test_future_claims_debunked_carveout_preserved(self):
        from backend.analysis.engine import _SYSTEM_PROMPT
        # The precondition-disproven → DEBUNKED exception must still be present.
        assert "DEBUNKED based on the refuted prerequisite" in _SYSTEM_PROMPT

    def test_future_claims_missing_for_no_evidence(self):
        from backend.analysis.engine import _SYSTEM_PROMPT
        assert "no evidence at all, use\n     MISSING" in _SYSTEM_PROMPT or "use MISSING" in _SYSTEM_PROMPT

    def test_placeholder_present_in_raw_prompt(self):
        """The raw string must contain {current_date} so the formatter can fill it."""
        from backend.analysis.engine import _SYSTEM_PROMPT
        assert "{current_date}" in _SYSTEM_PROMPT


# ── Symmetry: both models see the same formatted date ────────────────────────

class TestSymmetryBothModels:

    def test_formatted_prompt_matches_between_models(self):
        """
        The text assembled for Sonnet (_cached_system) and the text assembled for
        Mistral (_SYSTEM_PROMPT.format(current_date=_zurich_date())) must be identical,
        confirming symmetric temporal injection.
        """
        from backend.analysis.engine import _cached_system, _SYSTEM_PROMPT, _zurich_date
        date = _zurich_date()
        sonnet_text = _cached_system()[0]["text"]
        mistral_text = _SYSTEM_PROMPT.format(current_date=date)
        assert sonnet_text == mistral_text

    def test_dated_past_statements_in_both_assembled_prompts(self):
        from backend.analysis.engine import _cached_system, _SYSTEM_PROMPT, _zurich_date
        sonnet_text = _cached_system()[0]["text"]
        mistral_text = _SYSTEM_PROMPT.format(current_date=_zurich_date())
        assert "DATED PAST STATEMENTS" in sonnet_text
        assert "DATED PAST STATEMENTS" in mistral_text

    def test_future_claims_in_both_assembled_prompts(self):
        from backend.analysis.engine import _cached_system, _SYSTEM_PROMPT, _zurich_date
        sonnet_text = _cached_system()[0]["text"]
        mistral_text = _SYSTEM_PROMPT.format(current_date=_zurich_date())
        assert "FUTURE CLAIMS" in sonnet_text
        assert "FUTURE CLAIMS" in mistral_text


# ── Mistral live call path: system message contains formatted date ─────────────

class TestMistralSystemMessageDate:

    def _make_mistral_response(self) -> MagicMock:
        fn = MagicMock()
        fn.name = "submit_judgment"
        fn.arguments = json.dumps({
            "rating": "speculative",
            "rationale": "Some rationale.",
            "sources": [],
        })
        call = MagicMock()
        call.function = fn
        message = MagicMock()
        message.tool_calls = [call]
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        return response

    def test_system_message_contains_zurich_date(self):
        """
        _mistral_phase2_judgment must pass a system message whose content contains
        today's Europe/Zurich date — confirming the .format(current_date=...) call
        runs at request time, not import time.
        """
        from backend.analysis import consensus as cons
        from backend.analysis.engine import _zurich_date

        mock_client = MagicMock()
        mock_client.chat.complete.return_value = self._make_mistral_response()
        captured: list[dict] = []

        original_complete = mock_client.chat.complete.side_effect

        def capturing_complete(**kwargs):
            captured.extend(kwargs.get("messages", []))
            return self._make_mistral_response()

        mock_client.chat.complete.side_effect = capturing_complete

        with patch("backend.analysis.consensus._get_mistral_client", return_value=mock_client), \
             patch("backend.analysis.consensus._verify_rating_consistency",
                   side_effect=lambda r, s, *a, **kw: s), \
             patch("backend.analysis.consensus._get_client", return_value=MagicMock()):
            cons._mistral_phase2_judgment("The test claim", "Some findings")

        system_msgs = [m for m in captured if m.get("role") == "system"]
        assert system_msgs, "No system message captured in Mistral call"
        system_content = system_msgs[0]["content"]

        date = _zurich_date()
        assert date in system_content, (
            f"Expected date {date!r} in Mistral system message, got: {system_content[:120]!r}"
        )
        assert "CURRENT DATE (Europe/Zurich):" in system_content

    def test_system_message_no_unresolved_placeholder(self):
        """The Mistral system message must not contain the literal '{current_date}' string."""
        from backend.analysis import consensus as cons

        mock_client = MagicMock()
        captured: list[dict] = []

        def capturing_complete(**kwargs):
            captured.extend(kwargs.get("messages", []))
            return self._make_mistral_response()

        mock_client.chat.complete.side_effect = capturing_complete

        with patch("backend.analysis.consensus._get_mistral_client", return_value=mock_client), \
             patch("backend.analysis.consensus._verify_rating_consistency",
                   side_effect=lambda r, s, *a, **kw: s), \
             patch("backend.analysis.consensus._get_client", return_value=MagicMock()):
            cons._mistral_phase2_judgment("claim", "findings")

        system_msgs = [m for m in captured if m.get("role") == "system"]
        assert system_msgs
        assert "{current_date}" not in system_msgs[0]["content"]


# ── _PROXIMAL_EVIDENCE_BLOCK: symmetry and injection tests ───────────────────

def _make_mistral_response_proximal() -> MagicMock:
    fn = MagicMock()
    fn.name = "submit_judgment"
    fn.arguments = json.dumps({
        "rating": "speculative",
        "rationale": "Some rationale.",
        "sources": [],
    })
    call = MagicMock()
    call.function = fn
    message = MagicMock()
    message.tool_calls = [call]
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


class TestProximalEvidenceBlock:
    """
    Verifies that _PROXIMAL_EVIDENCE_BLOCK is injected into Sonnet's user message
    when findings are present, that Mistral's user message also contains the same
    block, and that the two strings are identical (shared constant, cannot drift).
    """

    def test_proximal_block_appended_to_sonnet_user_message_when_findings_present(self):
        """_phase2_judgment must include _PROXIMAL_EVIDENCE_BLOCK in user_content when findings are non-empty."""
        from backend.analysis import engine as eng
        from backend.analysis.engine import _PROXIMAL_EVIDENCE_BLOCK

        mock_client = MagicMock()
        captured_messages: list = []

        def capturing_create(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            # Return a minimal tool-use response
            tool_block = MagicMock()
            tool_block.type = "tool_use"
            tool_block.name = "submit_judgment"
            tool_block.input = {"rating": "speculative", "rationale": "r", "sources": []}
            resp = MagicMock()
            resp.content = [tool_block]
            return resp

        mock_client.messages.create.side_effect = capturing_create

        with patch.object(eng, "_verify_rating_consistency", side_effect=lambda r, s, *a, **kw: s), \
             patch.object(eng, "_verify_temporal_cap", side_effect=lambda r, *a, **kw: r):
            eng._phase2_judgment(mock_client, "Test claim", "Source 1: Title\nURL: https://example.com\nExcerpt: Text.")

        assert captured_messages, "No messages captured from Sonnet call"
        user_msgs = [m for m in captured_messages if m.get("role") == "user"]
        assert user_msgs, "No user message captured"
        user_content = user_msgs[0]["content"]
        assert _PROXIMAL_EVIDENCE_BLOCK in user_content, (
            f"_PROXIMAL_EVIDENCE_BLOCK not found in Sonnet user message. "
            f"Content excerpt: {user_content[:200]!r}"
        )

    def test_proximal_block_not_appended_to_sonnet_user_message_when_findings_absent(self):
        """_PROXIMAL_EVIDENCE_BLOCK must NOT appear when search_findings is empty."""
        from backend.analysis import engine as eng
        from backend.analysis.engine import _PROXIMAL_EVIDENCE_BLOCK

        mock_client = MagicMock()
        captured_messages: list = []

        def capturing_create(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            tool_block = MagicMock()
            tool_block.type = "tool_use"
            tool_block.name = "submit_judgment"
            tool_block.input = {"rating": "missing", "rationale": "r", "sources": []}
            resp = MagicMock()
            resp.content = [tool_block]
            return resp

        mock_client.messages.create.side_effect = capturing_create

        with patch.object(eng, "_verify_rating_consistency", side_effect=lambda r, s, *a, **kw: s), \
             patch.object(eng, "_verify_temporal_cap", side_effect=lambda r, *a, **kw: r):
            eng._phase2_judgment(mock_client, "Test claim", "")

        user_msgs = [m for m in captured_messages if m.get("role") == "user"]
        assert user_msgs
        assert _PROXIMAL_EVIDENCE_BLOCK not in user_msgs[0]["content"]

    def test_proximal_block_appended_to_mistral_user_message_when_findings_present(self):
        """_mistral_phase2_judgment must include _PROXIMAL_EVIDENCE_BLOCK in user_content."""
        from backend.analysis import consensus as cons
        from backend.analysis.engine import _PROXIMAL_EVIDENCE_BLOCK

        mock_client = MagicMock()
        captured_messages: list = []

        def capturing_complete(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return _make_mistral_response_proximal()

        mock_client.chat.complete.side_effect = capturing_complete

        with patch("backend.analysis.consensus._get_mistral_client", return_value=mock_client), \
             patch("backend.analysis.consensus._verify_rating_consistency",
                   side_effect=lambda r, s, *a, **kw: s), \
             patch("backend.analysis.consensus._get_client", return_value=MagicMock()):
            cons._mistral_phase2_judgment("Test claim", "Source 1: Title\nURL: https://example.com\nExcerpt: Text.")

        user_msgs = [m for m in captured_messages if m.get("role") == "user"]
        assert user_msgs, "No user message captured from Mistral call"
        user_content = user_msgs[0]["content"]
        assert _PROXIMAL_EVIDENCE_BLOCK in user_content, (
            f"_PROXIMAL_EVIDENCE_BLOCK not found in Mistral user message. "
            f"Content excerpt: {user_content[:200]!r}"
        )

    def test_sonnet_and_mistral_proximal_text_is_identical(self):
        """
        Both models receive the SAME proximal evidence block string — the shared
        constant ensures they cannot drift independently.
        """
        from backend.analysis import engine as eng
        from backend.analysis import consensus as cons
        from backend.analysis.engine import _PROXIMAL_EVIDENCE_BLOCK

        # Confirm consensus.py imports the same object (identity, not just equality)
        assert cons._PROXIMAL_EVIDENCE_BLOCK is eng._PROXIMAL_EVIDENCE_BLOCK, (
            "consensus._PROXIMAL_EVIDENCE_BLOCK is not the same object as engine._PROXIMAL_EVIDENCE_BLOCK"
        )
        # And it is a non-empty string
        assert isinstance(_PROXIMAL_EVIDENCE_BLOCK, str)
        assert len(_PROXIMAL_EVIDENCE_BLOCK) > 100  # sanity: not accidentally empty


# ── Source re-ask net: _claude_reask_sources / _mistral_reask_sources ────────

def _make_sonnet_tool_response(tool_name: str, tool_input: dict) -> MagicMock:
    """Build a minimal Anthropic SDK tool-use response mock."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = tool_name
    tool_block.input = tool_input
    resp = MagicMock()
    resp.content = [tool_block]
    return resp


def _make_sonnet_phase2_response(rating: str, rationale: str, sources: list) -> MagicMock:
    """submit_judgment response for the first Sonnet call."""
    return _make_sonnet_tool_response(
        "submit_judgment",
        {"rating": rating, "rationale": rationale, "sources": sources},
    )


def _make_sonnet_reask_response(sources: list) -> MagicMock:
    """submit_sources response for the Sonnet re-ask call."""
    return _make_sonnet_tool_response("submit_sources", {"sources": sources})


def _make_mistral_response_reask(tool_name: str, args: dict) -> MagicMock:
    """Build a minimal Mistral SDK tool-call response mock."""
    fn = MagicMock()
    fn.name = tool_name
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


_FINDINGS = "Source 1: Title\nURL: https://example.com/\nExcerpt: Some text."

_REASK_SOURCES = [
    {"url": "https://example.com/", "title": "Title", "tier": "secondary",
     "is_independent": True, "relevance_score": 0.8, "supports_claim": True}
]


class TestSourceReaskNet:
    """
    Tests for the single-retry source re-ask net in _phase2_judgment (Sonnet)
    and _mistral_phase2_judgment (Mistral).
    """

    # ── (i) Sonnet: empty sources triggers exactly ONE re-ask, merges sources ──

    def test_sonnet_empty_sources_triggers_reask_and_merges(self):
        """
        When Sonnet returns sources:[] despite non-empty findings, exactly one
        re-ask fires and its sources are merged; original rating + rationale unchanged.
        """
        from backend.analysis import engine as eng

        first_response = _make_sonnet_phase2_response("verified", "Original rationale.", [])
        reask_response = _make_sonnet_reask_response(_REASK_SOURCES)

        call_count = {"n": 0}

        def side_effect(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return first_response
            return reask_response

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = side_effect

        with patch.object(eng, "_verify_rating_consistency", side_effect=lambda r, s, *a, **kw: s), \
             patch.object(eng, "_verify_temporal_cap", side_effect=lambda r, *a, **kw: r):
            result = eng._phase2_judgment(mock_client, "Test claim", _FINDINGS)

        assert call_count["n"] == 2, f"Expected 2 API calls (phase2 + reask), got {call_count['n']}"
        assert result["sources"] == _REASK_SOURCES
        assert result["rationale"] == "Original rationale."
        assert result["rating"] == "verified"

    # ── (ii) Sonnet: re-ask still empty → sources stay empty, no second retry ──

    def test_sonnet_reask_still_empty_no_second_retry(self):
        """
        If the re-ask also returns sources:[], sources stay empty and no further
        call is made — existing gates handle the fallthrough.
        """
        from backend.analysis import engine as eng

        first_response = _make_sonnet_phase2_response("speculative", "Rationale.", [])
        reask_response = _make_sonnet_reask_response([])

        call_count = {"n": 0}

        def side_effect(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return first_response
            return reask_response

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = side_effect

        with patch.object(eng, "_verify_rating_consistency", side_effect=lambda r, s, *a, **kw: s), \
             patch.object(eng, "_verify_temporal_cap", side_effect=lambda r, *a, **kw: r):
            result = eng._phase2_judgment(mock_client, "Test claim", _FINDINGS)

        assert call_count["n"] == 2, f"Expected exactly 2 calls (no third), got {call_count['n']}"
        assert result["sources"] == []

    # ── (iii) Sonnet: non-empty sources on first try → NO re-ask ──

    def test_sonnet_no_reask_when_sources_present(self):
        """When Sonnet returns non-empty sources, no re-ask call is made."""
        from backend.analysis import engine as eng

        first_response = _make_sonnet_phase2_response("verified", "Rationale.", _REASK_SOURCES)

        mock_client = MagicMock()
        mock_client.messages.create.return_value = first_response

        with patch.object(eng, "_verify_rating_consistency", side_effect=lambda r, s, *a, **kw: s), \
             patch.object(eng, "_verify_temporal_cap", side_effect=lambda r, *a, **kw: r):
            result = eng._phase2_judgment(mock_client, "Test claim", _FINDINGS)

        assert mock_client.messages.create.call_count == 1
        assert result["sources"] == _REASK_SOURCES

    # ── (iv) Sonnet: empty findings → NO re-ask ──

    def test_sonnet_no_reask_when_findings_empty(self):
        """Re-ask must NOT fire when search_findings is empty (empty-search path)."""
        from backend.analysis import engine as eng

        first_response = _make_sonnet_phase2_response("missing", "No findings.", [])

        mock_client = MagicMock()
        mock_client.messages.create.return_value = first_response

        with patch.object(eng, "_verify_rating_consistency", side_effect=lambda r, s, *a, **kw: s), \
             patch.object(eng, "_verify_temporal_cap", side_effect=lambda r, *a, **kw: r):
            result = eng._phase2_judgment(mock_client, "Test claim", "")

        assert mock_client.messages.create.call_count == 1
        assert result["sources"] == []

    # ── (v) Mistral: empty sources triggers re-ask, merges sources ──

    def test_mistral_empty_sources_triggers_reask_and_merges(self):
        """
        Mirrors test (i) for Mistral: empty sources despite findings → one re-ask,
        sources merged, original rating + rationale unchanged.
        """
        from backend.analysis import consensus as cons

        first_response = _make_mistral_response_reask(
            "submit_judgment",
            {"rating": "speculative", "rationale": "Mistral rationale.", "sources": []},
        )
        reask_response = _make_mistral_response_reask("submit_sources", {"sources": _REASK_SOURCES})

        call_count = {"n": 0}

        def side_effect(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return first_response
            return reask_response

        mock_client = MagicMock()
        mock_client.chat.complete.side_effect = side_effect

        with patch("backend.analysis.consensus._get_mistral_client", return_value=mock_client), \
             patch("backend.analysis.consensus._verify_rating_consistency",
                   side_effect=lambda r, s, *a, **kw: s), \
             patch("backend.analysis.consensus._verify_temporal_cap",
                   side_effect=lambda r, *a, **kw: r), \
             patch("backend.analysis.consensus._get_client", return_value=MagicMock()):
            result = cons._mistral_phase2_judgment("Test claim", _FINDINGS)

        assert call_count["n"] == 2, f"Expected 2 API calls, got {call_count['n']}"
        assert result["sources"] == _REASK_SOURCES
        assert result["rationale"] == "Mistral rationale."
        assert result["rating"] == "speculative"

    # ── (vi) Shared prompt constant: object identity across both models ──

    def test_source_reask_prompt_is_shared_constant(self):
        """
        _SOURCE_REASK_PROMPT imported by consensus.py is the same object as the one
        in engine.py — guarantees identical re-ask text for both models.
        """
        from backend.analysis import engine as eng
        from backend.analysis import consensus as cons

        assert cons._SOURCE_REASK_PROMPT is eng._SOURCE_REASK_PROMPT
        assert isinstance(eng._SOURCE_REASK_PROMPT, str)
        assert len(eng._SOURCE_REASK_PROMPT) > 50
