"""Tests for _verify_rating_consistency in backend/analysis/engine.py."""
import pytest
from unittest.mock import MagicMock, patch, call

from backend.analysis.engine import _verify_rating_consistency, _call_haiku_rating_check


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
