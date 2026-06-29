"""Tests for _verify_rating_consistency, threshold-cap, and temporal gate in engine.py."""
import pytest
from unittest.mock import MagicMock, patch, call

from backend.analysis.engine import (
    _verify_rating_consistency,
    _call_haiku_rating_check,
    _verify_temporal_cap,
    _call_haiku_temporal_check,
)


def _make_haiku_response(word: str) -> MagicMock:
    """Build a minimal mock Anthropic response returning a single word."""
    block = MagicMock()
    block.text = word
    resp = MagicMock()
    resp.content = [block]
    return resp


def _make_client(side_effects) -> MagicMock:
    """Return a mock client whose messages.create returns side_effects in order."""
    client = MagicMock()
    if isinstance(side_effects, list):
        client.messages.create.side_effect = [_make_haiku_response(w) for w in side_effects]
    else:
        client.messages.create.return_value = _make_haiku_response(side_effects)
    return client


# ── 1. Confirming rationale with negation mentions stays as structured ─────────

def test_confirming_rationale_with_negation_mentions_stays_verified():
    """
    A rationale that confirms the claim is supported even though it mentions critics
    or negations must NOT be flipped. Haiku returns 'verified' → no override.
    """
    rationale = (
        "The claim is well supported by multiple independent primary sources. "
        "While some critics dispute the figure, the underlying data confirms the assertion. "
        "Opposition groups call the claim false, but the official records are clear."
    )
    client = _make_client("verified")
    result = _verify_rating_consistency(
        rationale, "verified", client, claim_text="Test claim"
    )
    assert result == "verified"
    client.messages.create.assert_called_once()


def test_verified_rationale_with_debunked_mentions_stays_verified():
    """
    Rationale concludes verified even though it contains the word 'false'. Haiku
    correctly reads the conclusion and returns 'verified' → structured rating kept.
    """
    rationale = (
        "Multiple government databases and independent audits confirm the statistic. "
        "Claims that this number is false originate from unverified sources."
    )
    client = _make_client("verified")
    result = _verify_rating_consistency(
        rationale, "verified", client, claim_text="Test claim"
    )
    assert result == "verified"


# ── 2. Clear mismatch still overrides ─────────────────────────────────────────

def test_clear_speculative_mismatch_overrides():
    """
    When Haiku reads the rationale as 'speculative' but structured says 'verified',
    the gate must override to speculative (non-opposite-polarity mismatch).
    """
    rationale = "Evidence is suggestive but not conclusive; further research is needed."
    client = _make_client("speculative")
    result = _verify_rating_consistency(
        rationale, "verified", client, claim_text="Test claim"
    )
    assert result == "speculative"
    client.messages.create.assert_called_once()


def test_clear_missing_mismatch_overrides():
    """
    Haiku reads 'missing' but structured says 'speculative' → override to missing.
    """
    rationale = "No evidence was found for or against this claim."
    client = _make_client("missing")
    result = _verify_rating_consistency(
        rationale, "speculative", client, claim_text="Test claim"
    )
    assert result == "missing"


# ── 3. UNCLEAR keeps the structured rating ────────────────────────────────────

def test_unclear_response_keeps_structured_rating():
    """
    When Haiku returns UNCLEAR the function must keep the structured rating unchanged.
    """
    rationale = "The situation is complicated and evidence points in multiple directions."
    client = _make_client("unclear")
    result = _verify_rating_consistency(
        rationale, "speculative", client, claim_text="Test claim"
    )
    assert result == "speculative"
    client.messages.create.assert_called_once()


def test_unexpected_output_treated_as_unclear_keeps_structured():
    """
    Unexpected Haiku output (not one of the four valid ratings or 'unclear') is
    treated conservatively as UNCLEAR and keeps the structured rating.
    """
    rationale = "The evidence reviewed here strongly supports the assertion."
    client = _make_client("CONFIRMED")  # not a valid token
    result = _verify_rating_consistency(
        rationale, "verified", client, claim_text="Test claim"
    )
    assert result == "verified"


# ── 4. Opposite-polarity protection ───────────────────────────────────────────

def test_opposite_polarity_both_agree_overrides():
    """
    verified vs debunked: when both Haiku calls agree on 'debunked', the
    structured 'verified' must be overridden to 'debunked'.
    """
    rationale = "The claim is directly contradicted by primary source data."
    client = _make_client(["debunked", "debunked"])
    result = _verify_rating_consistency(
        rationale, "verified", client, claim_text="Test claim"
    )
    assert result == "debunked"
    assert client.messages.create.call_count == 2


def test_opposite_polarity_calls_disagree_keeps_structured():
    """
    verified vs debunked: when the two Haiku calls disagree (first='debunked',
    second='unclear'), the function must keep the structured rating and log
    RATING-GATE-CONFLICT.
    """
    rationale = "Evidence is ambiguous; some sources support while others contradict."
    client = _make_client(["debunked", "unclear"])
    result = _verify_rating_consistency(
        rationale, "verified", client, claim_text="Test claim"
    )
    assert result == "verified"
    assert client.messages.create.call_count == 2


def test_opposite_polarity_reverse_direction_both_agree_overrides():
    """
    debunked vs verified in the other direction: structured='debunked', haiku='verified'.
    Both calls agree on 'verified' → override to 'verified'.
    """
    rationale = "All evidence consistently supports this claim."
    client = _make_client(["verified", "verified"])
    result = _verify_rating_consistency(
        rationale, "debunked", client, claim_text="Test claim"
    )
    assert result == "verified"
    assert client.messages.create.call_count == 2


def test_opposite_polarity_reverse_direction_calls_disagree_keeps_structured():
    """
    structured='debunked', first call='verified', second call='speculative' →
    calls disagree → keep structured 'debunked'.
    """
    rationale = "The analysis is inconclusive."
    client = _make_client(["verified", "speculative"])
    result = _verify_rating_consistency(
        rationale, "debunked", client, claim_text="Test claim"
    )
    assert result == "debunked"
    assert client.messages.create.call_count == 2


# ── 5. Exception fallback ──────────────────────────────────────────────────────

def test_exception_keeps_structured_rating():
    """
    Any exception from the Haiku call must be caught and the structured rating returned.
    """
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("network error")
    result = _verify_rating_consistency(
        "Some rationale.", "speculative", client, claim_text="Test claim"
    )
    assert result == "speculative"


# ── 6. Agreement short-circuits at one call ───────────────────────────────────

def test_agreement_requires_only_one_call():
    """
    When Haiku agrees with structured_rating no second call should be made.
    """
    rationale = "Evidence conclusively supports the claim."
    client = _make_client("verified")
    result = _verify_rating_consistency(
        rationale, "verified", client, claim_text="Test claim"
    )
    assert result == "verified"
    client.messages.create.assert_called_once()


# ── 7. Prompt includes both claim and rationale ────────────────────────────────

def test_prompt_includes_claim_text():
    """
    The prompt sent to Haiku must contain both the claim text and the rationale.
    """
    claim = "The unemployment rate rose by 2%."
    rationale = "Official statistics from the Bureau of Labor confirm a 2.1% rise."
    client = _make_client("verified")
    _verify_rating_consistency(rationale, "verified", client, claim_text=claim)
    args, kwargs = client.messages.create.call_args
    content = kwargs.get("messages", [{}])[0].get("content", "")
    assert claim in content
    assert rationale in content


# ── 8. Threshold cap (THE RULE enforcement) ───────────────────────────────────

def _run_threshold_test(sources: list[dict], model_rating: str) -> "Judgment":
    """Run analyze_claim with a mock that bypasses the Haiku rating gate and returns the judgment."""
    from unittest.mock import MagicMock, patch
    from backend.analysis import engine as eng
    from backend.db.models import Judgment

    judgment_data = {"rationale": "test rationale", "sources": sources, "rating": model_rating}
    mock_claim = MagicMock()
    mock_claim.text = "Test claim"
    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim
    captured: dict = {}
    mock_session.add.side_effect = lambda obj: captured.update({"judgment": obj}) if isinstance(obj, Judgment) else None
    mock_session.add_all.side_effect = lambda objs: None

    # Bypass the Haiku rating-gate so only the threshold cap is under test.
    with patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt."), \
         patch.object(eng, "_verify_rating_consistency", side_effect=lambda r, s, *a, **kw: s), \
         patch.object(eng, "_get_client", return_value=MagicMock()), \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data):
        eng.analyze_claim("claim-1", mock_session)
    return captured["judgment"]


def test_threshold_cap_verified_insufficient_sources_downgraded_to_speculative(caplog):
    """
    Model declares VERIFIED with only 1 independent secondary verifying source (< 2 required,
    no primary). THE RULE is not met → threshold cap must downgrade to SPECULATIVE and log
    [THRESHOLD-CAP].
    """
    import logging
    sources = [
        # 3 sources total — but only 1 is independent secondary, none are primary
        {"url": "https://reuters.com/a", "tier": "secondary", "is_independent": True,
         "relevance_score": 0.9, "supports_claim": True},
        {"url": "https://example.org/b", "tier": "secondary", "is_independent": False,
         "relevance_score": 0.9, "supports_claim": True},
        {"url": "https://wiki.org/c", "tier": "tertiary", "is_independent": True,
         "relevance_score": 0.9, "supports_claim": True},
    ]
    with caplog.at_level(logging.WARNING):
        judgment = _run_threshold_test(sources, "verified")
    from backend.analysis.rating import EpistemicRating
    assert judgment.rating == EpistemicRating.SPECULATIVE
    assert any("[THRESHOLD-CAP]" in r.message for r in caplog.records)


def test_threshold_cap_verified_two_indep_secondaries_stays_verified():
    """
    Model declares VERIFIED with 2 independent secondary verifying sources (≥3 total).
    THE RULE secondary path is satisfied → rating must NOT be downgraded.
    """
    sources = [
        {"url": "https://reuters.com/a", "tier": "secondary", "is_independent": True,
         "relevance_score": 0.9, "supports_claim": True},
        {"url": "https://apnews.com/b", "tier": "secondary", "is_independent": True,
         "relevance_score": 0.9, "supports_claim": True},
        {"url": "https://bbc.com/c", "tier": "secondary", "is_independent": True,
         "relevance_score": 0.9, "supports_claim": True},
    ]
    judgment = _run_threshold_test(sources, "verified")
    from backend.analysis.rating import EpistemicRating
    assert judgment.rating == EpistemicRating.VERIFIED


def test_threshold_cap_never_upgrades_speculative():
    """
    The threshold cap must never upgrade a lower rating. A model-declared SPECULATIVE
    backed by 3 independent secondaries (which would satisfy THE RULE) must stay SPECULATIVE.
    """
    sources = [
        {"url": "https://reuters.com/a", "tier": "secondary", "is_independent": True,
         "relevance_score": 0.9, "supports_claim": True},
        {"url": "https://apnews.com/b", "tier": "secondary", "is_independent": True,
         "relevance_score": 0.9, "supports_claim": True},
        {"url": "https://bbc.com/c", "tier": "secondary", "is_independent": True,
         "relevance_score": 0.9, "supports_claim": True},
    ]
    judgment = _run_threshold_test(sources, "speculative")
    from backend.analysis.rating import EpistemicRating
    assert judgment.rating == EpistemicRating.SPECULATIVE


# ── 9. No-upgrade rule in rating gate ────────────────────────────────────────

def test_gate_no_upgrade_speculative_to_verified(caplog):
    """
    Haiku reads 'verified' but structured is 'speculative'. Strength order: verified > speculative.
    Gate must keep 'speculative' and log [RATING-GATE-NOUPGRADE].
    """
    import logging
    rationale = "All available evidence strongly supports this assertion across multiple sources."
    client = _make_client("verified")
    with caplog.at_level(logging.WARNING):
        result = _verify_rating_consistency(rationale, "speculative", client, claim_text="Test claim")
    assert result == "speculative"
    assert any("[RATING-GATE-NOUPGRADE]" in r.message for r in caplog.records)


def test_gate_no_upgrade_missing_to_speculative(caplog):
    """
    Haiku reads 'speculative' but structured is 'missing'. Upgrade not allowed.
    Gate must keep 'missing' and log [RATING-GATE-NOUPGRADE].
    """
    import logging
    rationale = "Some evidence exists but it is uncertain and limited."
    client = _make_client("speculative")
    with caplog.at_level(logging.WARNING):
        result = _verify_rating_consistency(rationale, "missing", client, claim_text="Test claim")
    assert result == "missing"
    assert any("[RATING-GATE-NOUPGRADE]" in r.message for r in caplog.records)


def test_gate_no_upgrade_missing_to_verified(caplog):
    """
    Haiku reads 'verified' but structured is 'missing'. Upgrade not allowed.
    Gate must keep 'missing' and log [RATING-GATE-NOUPGRADE].
    """
    import logging
    rationale = "Multiple strong sources confirm the claim conclusively."
    client = _make_client("verified")
    with caplog.at_level(logging.WARNING):
        result = _verify_rating_consistency(rationale, "missing", client, claim_text="Test claim")
    assert result == "missing"
    assert any("[RATING-GATE-NOUPGRADE]" in r.message for r in caplog.records)


def test_gate_debunked_from_missing_allowed():
    """
    Haiku reads 'debunked' but structured is 'missing'. Debunked is polarity, not strength —
    no-upgrade rule does NOT apply. Gate should override to 'debunked' (non-opposite pair,
    so a single Haiku call suffices).
    """
    rationale = "Counter-evidence directly contradicts the claim."
    client = _make_client("debunked")
    result = _verify_rating_consistency(rationale, "missing", client, claim_text="Test claim")
    assert result == "debunked"
    client.messages.create.assert_called_once()


# ── Temporal gate (_verify_temporal_cap / _call_haiku_temporal_check) ─────────

def _make_temporal_client(token: str) -> MagicMock:
    """Return a mock client whose messages.create returns a single-word temporal token."""
    block = MagicMock()
    block.text = token
    resp = MagicMock()
    resp.content = [block]
    client = MagicMock()
    client.messages.create.return_value = resp
    return client


def test_temporal_future_verified_capped_to_speculative():
    """FUTURE + verified → speculative (the core cap)."""
    client = _make_temporal_client("FUTURE")
    result = _verify_temporal_cap("verified", "Democrats will win the 2026 midterms.", client)
    assert result == "speculative"
    client.messages.create.assert_called_once()


def test_temporal_future_debunked_unchanged():
    """FUTURE + debunked → debunked (carve-out: refuted prerequisite stays DEBUNKED)."""
    client = _make_temporal_client("FUTURE")
    result = _verify_temporal_cap("debunked", "A person who died in 1945 will return in 2030.", client)
    assert result == "debunked"


def test_temporal_future_missing_unchanged():
    """FUTURE + missing → missing (gate only acts on verified)."""
    client = _make_temporal_client("FUTURE")
    result = _verify_temporal_cap("missing", "The next election will be held tomorrow.", client)
    assert result == "missing"


def test_temporal_future_speculative_unchanged():
    """FUTURE + speculative → speculative (gate never upgrades, only caps verified)."""
    client = _make_temporal_client("FUTURE")
    result = _verify_temporal_cap("speculative", "It will probably rain next week.", client)
    assert result == "speculative"


def test_temporal_past_or_current_verified_unchanged():
    """
    PAST_OR_CURRENT + verified → verified.
    Covers the dated-past AfD case: classification already happened as of current date,
    even if status later changed. Gate must NOT cap this.
    """
    client = _make_temporal_client("PAST_OR_CURRENT")
    result = _verify_temporal_cap(
        "verified",
        "The AfD was classified as right-extremist in 2025.",
        client,
    )
    assert result == "verified"


def test_temporal_unclear_verified_unchanged():
    """UNCLEAR + verified → verified (fail-safe: no cap on ambiguous temporal classification)."""
    client = _make_temporal_client("UNCLEAR")
    result = _verify_temporal_cap("verified", "Some ambiguous claim.", client)
    assert result == "verified"


def test_temporal_exception_verified_unchanged():
    """Exception in Haiku call → verified unchanged (fail-safe, non-destructive)."""
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("network error")
    result = _verify_temporal_cap("verified", "Some claim.", client)
    assert result == "verified"


def test_temporal_unexpected_token_treated_as_unclear():
    """Any unrecognised Haiku token is normalised to 'unclear' → rating unchanged."""
    client = _make_temporal_client("CONFIRMED_FUTURE")  # not a valid token
    result = _verify_temporal_cap("verified", "Some claim.", client)
    assert result == "verified"


def test_call_haiku_temporal_check_returns_future():
    """_call_haiku_temporal_check parses 'FUTURE' correctly."""
    client = _make_temporal_client("FUTURE")
    result = _call_haiku_temporal_check(client, "Democrats will win 2026 midterms.", "2026-06-29")
    assert result == "future"


def test_call_haiku_temporal_check_returns_past_or_current():
    """_call_haiku_temporal_check parses 'PAST_OR_CURRENT' correctly."""
    client = _make_temporal_client("PAST_OR_CURRENT")
    result = _call_haiku_temporal_check(client, "The AfD was classified in 2025.", "2026-06-29")
    assert result == "past_or_current"


def test_call_haiku_temporal_check_exception_returns_unclear():
    """Exception in the API call returns 'unclear' (try/except in the helper itself)."""
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("timeout")
    result = _call_haiku_temporal_check(client, "Some claim.", "2026-06-29")
    assert result == "unclear"


def test_temporal_prompt_contains_current_date_and_worked_examples(caplog):
    """
    Regression guard: the prompt sent to Haiku must contain the current_date and
    the three worked examples (future election, AfD dated-past, NATO ongoing-state).
    """
    from backend.analysis.engine import _TEMPORAL_CHECK_PROMPT
    prompt = _TEMPORAL_CHECK_PROMPT.format(current_date="2026-06-29", claim_text="test")
    assert "2026-06-29" in prompt
    assert "2026 US midterm" in prompt or "2026 midterm" in prompt or "midterm" in prompt
    assert "AfD" in prompt
    assert "NATO" in prompt
    assert "PAST_OR_CURRENT" in prompt
    assert "FUTURE" in prompt
    assert "UNCLEAR" in prompt
