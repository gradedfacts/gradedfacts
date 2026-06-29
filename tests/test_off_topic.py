"""
Tests for the off-topic pre-flight gate.

Covers:
  - _check_off_topic() response parsing (unit)
  - _get_off_topic_message() locale loading (unit)
  - analyze_claim() short-circuits on off-topic input (integration)
  - analyze_claim() proceeds normally for on-topic claims (integration)
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.analysis.rating import EpistemicRating
from backend.db.models import Judgment


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_text_response(text: str):
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


# ── _check_off_topic unit tests ───────────────────────────────────────────────

def test_reject_verdict_returns_false_with_message():
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("REJECT")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_on_topic, rationale = eng._check_off_topic(mock_client, "What should I cook for dinner?", "English")

    assert is_on_topic is False
    assert len(rationale) > 0
    assert "GradedFacts" in rationale


def test_pass_verdict_returns_true():
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("PASS")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_on_topic, rationale = eng._check_off_topic(mock_client, "Donald Trump signed the TCJA in 2017.", "English")

    assert is_on_topic is True
    assert rationale == ""


def test_api_exception_treated_as_on_topic():
    """Gate failures must fail open so legitimate claims are not silently dropped."""
    from backend.analysis import engine as eng

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("network error")

    is_on_topic, rationale = eng._check_off_topic(mock_client, "Some claim", "English")

    assert is_on_topic is True
    assert rationale == ""


def test_empty_response_treated_as_on_topic():
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_on_topic, _ = eng._check_off_topic(mock_client, "Some claim", "English")

    assert is_on_topic is True


def test_unexpected_response_treated_as_on_topic():
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("MAYBE")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_on_topic, _ = eng._check_off_topic(mock_client, "Something borderline", "English")

    assert is_on_topic is True


def test_off_topic_gate_uses_cheap_model():
    """The gate must use _SPECIFICITY_MODEL (Haiku), not the main analysis model."""
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("PASS")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    eng._check_off_topic(mock_client, "Some claim", "English")

    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs.get("model") == eng._SPECIFICITY_MODEL


def test_reject_returns_localized_message_for_german():
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("REJECT")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    _, rationale = eng._check_off_topic(mock_client, "Schreib mir ein Gedicht", "German")

    assert "GradedFacts" in rationale
    # German locale should contain German text
    assert any(word in rationale for word in ["prüft", "Behauptungen", "formuliere"])


def test_reject_returns_english_fallback_for_unknown_language():
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("REJECT")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    _, rationale = eng._check_off_topic(mock_client, "Write me a poem", "Klingon")

    assert "GradedFacts" in rationale
    assert "claim" in rationale.lower()


# ── _get_off_topic_message unit tests ────────────────────────────────────────

def test_get_off_topic_message_english():
    from backend.analysis.engine import _get_off_topic_message

    msg = _get_off_topic_message("English")
    assert "GradedFacts" in msg
    assert "claim" in msg.lower()


def test_get_off_topic_message_german():
    from backend.analysis.engine import _get_off_topic_message

    msg = _get_off_topic_message("German")
    assert "GradedFacts" in msg
    assert "Behauptungen" in msg


def test_get_off_topic_message_french():
    from backend.analysis.engine import _get_off_topic_message

    msg = _get_off_topic_message("French")
    assert "GradedFacts" in msg
    assert "pertinente" in msg


def test_get_off_topic_message_unknown_falls_back_to_english():
    from backend.analysis.engine import _get_off_topic_message

    msg = _get_off_topic_message("Esperanto")
    assert "GradedFacts" in msg
    assert "claim" in msg.lower()


# ── Boundary: what must always pass ──────────────────────────────────────────

@pytest.mark.parametrize("claim", [
    "Donald Trump colluded with Russia in 2016",
    "The EU imposed sanctions on Russia after the 2022 invasion",
    "Global average temperatures have risen 1.1°C since pre-industrial times",
    "The US national debt exceeded $30 trillion in 2022",
    "Is democracy declining globally?",
    # Regression: political advocacy claims with a specific factual assertion must pass.
    # The factual core ("systematic oppression") is empirically checkable even though
    # the claim also includes a normative demand ("must be abolished").
    "Die amerikanische Polizei ist ein systematisches Instrument der Unterdrückung schwarzer Menschen und muss vollständig abgeschafft werden.",
    "The EU migration policy is inhumane and must be reformed",
    "The death penalty disproportionately targets minorities and should be banned",
])
def test_political_and_factual_claims_pass(claim):
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("PASS")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_on_topic, rationale = eng._check_off_topic(mock_client, claim, "English")

    assert is_on_topic is True, f"Expected PASS for: {claim!r}"
    assert rationale == ""


def test_off_topic_prompt_contains_advocacy_guidance():
    """
    Regression guard: _OFF_TOPIC_PROMPT must explicitly instruct the model to pass
    political advocacy claims that contain a specific factual assertion.
    Without this, claims like "X is oppressive and must be abolished" are incorrectly
    classified as pure normative opinion and rejected.
    """
    from backend.analysis.engine import _OFF_TOPIC_PROMPT

    prompt_lower = _OFF_TOPIC_PROMPT.lower()
    assert "advocacy" in prompt_lower or "abolished" in prompt_lower, (
        "_OFF_TOPIC_PROMPT must contain explicit guidance that advocacy claims "
        "with a factual assertion pass (e.g. 'should be abolished', 'must be reformed')"
    )
    assert "factual assertion" in prompt_lower or "factual component" in prompt_lower, (
        "_OFF_TOPIC_PROMPT must distinguish 'pure normative opinion' "
        "(no factual assertion) from advocacy claims that DO contain one"
    )


@pytest.mark.parametrize("claim", [
    "What should I cook for dinner?",
    "Help me write a Python script",
    "Tell me a joke",
    "What is the definition of inflation?",
    "Write me a poem about the ocean",
])
def test_off_topic_requests_are_rejected(claim):
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("REJECT")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_on_topic, rationale = eng._check_off_topic(mock_client, claim, "English")

    assert is_on_topic is False, f"Expected REJECT for: {claim!r}"
    assert len(rationale) > 0


# ── analyze_claim integration tests ──────────────────────────────────────────

def _run_analyze(
    claim_text: str,
    specificity_result: tuple,
    off_topic_result: tuple,
    judgment_data: dict | None = None,
):
    from backend.analysis import engine as eng

    if judgment_data is None:
        judgment_data = {"rationale": "Evidence found.", "sources": [], "rating": "missing"}

    mock_claim = MagicMock()
    mock_claim.text = claim_text
    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim

    captured: dict = {}

    def fake_add(obj):
        if isinstance(obj, Judgment):
            captured["judgment"] = obj

    mock_session.add.side_effect = fake_add
    mock_session.add_all.side_effect = lambda objs: None

    with patch.object(eng, "_check_specificity", return_value=specificity_result), \
         patch.object(eng, "_check_off_topic", return_value=off_topic_result), \
         patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt.") as p1, \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data) as p2, \
         patch.object(eng, "_get_client", return_value=MagicMock()):
        eng.analyze_claim("claim-1", mock_session)

    return captured.get("judgment"), p1, p2


def test_off_topic_claim_returns_missing_judgment():
    msg = "GradedFacts Politics checks political and factual claims. Please formulate a concrete, verifiable claim."
    judgment, _, _ = _run_analyze(
        "Write me a poem",
        specificity_result=(True, ""),
        off_topic_result=(False, msg),
    )

    assert judgment is not None
    assert judgment.rating == EpistemicRating.MISSING
    assert "GradedFacts" in judgment.rationale


def test_off_topic_claim_does_not_call_phase1_or_phase2():
    judgment, phase1, phase2 = _run_analyze(
        "Tell me a joke",
        specificity_result=(True, ""),
        off_topic_result=(False, "Off-topic rejection."),
    )

    phase1.assert_not_called()
    phase2.assert_not_called()


def test_on_topic_claim_proceeds_past_off_topic_gate():
    # Three distinct domains so domain dedup doesn't collapse them to one source.
    sources = [
        {"url": "https://bls.gov/data/tcja", "tier": "primary",
         "is_independent": True, "relevance_score": 0.9, "supports_claim": True},
        {"url": "https://reuters.com/article/tcja", "tier": "primary",
         "is_independent": True, "relevance_score": 0.9, "supports_claim": True},
        {"url": "https://apnews.com/article/tcja", "tier": "primary",
         "is_independent": True, "relevance_score": 0.9, "supports_claim": True},
    ]
    judgment_data = {"rationale": "Well-sourced.", "sources": sources, "rating": "verified"}

    judgment, phase1, phase2 = _run_analyze(
        "Donald Trump signed the TCJA on 22 December 2017.",
        specificity_result=(True, ""),
        off_topic_result=(True, ""),
        judgment_data=judgment_data,
    )

    phase1.assert_called_once()
    phase2.assert_called_once()
    assert judgment.rating == EpistemicRating.VERIFIED


def test_off_topic_check_not_called_when_specificity_fails():
    """If the specificity gate rejects, the off-topic gate must never run."""
    from backend.analysis import engine as eng

    mock_claim = MagicMock()
    mock_claim.text = "something vague"
    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim
    mock_session.add.side_effect = lambda obj: None
    mock_session.add_all.side_effect = lambda objs: None

    with patch.object(eng, "_check_specificity", return_value=(False, "Too vague.")), \
         patch.object(eng, "_check_off_topic") as off_topic_mock, \
         patch.object(eng, "_get_client", return_value=MagicMock()):
        eng.analyze_claim("claim-1", mock_session)

    off_topic_mock.assert_not_called()
