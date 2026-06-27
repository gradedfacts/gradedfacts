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
