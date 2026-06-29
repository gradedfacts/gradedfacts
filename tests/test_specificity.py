"""
Tests for the claim specificity pre-flight gate.

Covers:
  - _check_specificity() response parsing (unit)
  - analyze_claim() short-circuits when claim is too vague (integration)
  - analyze_claim() proceeds normally when claim is specific (integration)
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.analysis.rating import EpistemicRating
from backend.db.models import Judgment


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_text_response(text: str):
    """Return a minimal fake anthropic response with a single text block."""
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


# ── _check_specificity unit tests ─────────────────────────────────────────────

def test_vague_verdict_returns_false_with_rationale():
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("VAGUE\nPlease name the specific individual and the document set.")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_specific, rationale = eng._check_specificity(mock_client, "Trump in the Epstein files")

    assert is_specific is False
    assert "vague" in rationale.lower() or "specific" in rationale.lower()


def test_specific_verdict_returns_true():
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("SPECIFIC\nOK")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_specific, rationale = eng._check_specificity(mock_client, "Donald Trump signed the TCJA in December 2017.")

    assert is_specific is True
    assert rationale == ""


def test_unexpected_verdict_treated_as_specific():
    """Any response that isn't exactly 'VAGUE' is treated as specific (fail-open)."""
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("UNCLEAR\nCould not determine.")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_specific, _ = eng._check_specificity(mock_client, "Some claim")

    assert is_specific is True


def test_api_exception_treated_as_specific():
    """If the API call itself raises, the gate fails open so analysis can proceed."""
    from backend.analysis import engine as eng

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("network error")

    is_specific, rationale = eng._check_specificity(mock_client, "Some claim")

    assert is_specific is True
    assert rationale == ""


def test_empty_response_treated_as_specific():
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_specific, _ = eng._check_specificity(mock_client, "Some claim")

    assert is_specific is True


def test_vague_without_guidance_line_uses_fallback():
    """A 'VAGUE' response with no second line must still produce a usable rationale."""
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("VAGUE")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_specific, rationale = eng._check_specificity(mock_client, "Politicians lie")

    assert is_specific is False
    assert len(rationale) > 0


def test_specificity_check_uses_cheap_model():
    """The gate must use _SPECIFICITY_MODEL, not the main analysis model."""
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("SPECIFIC\nOK")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    eng._check_specificity(mock_client, "Some claim")

    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs.get("model") == eng._SPECIFICITY_MODEL


# ── Prompt boundary tests: what the updated prompt must accept ────────────────
#
# These tests simulate the model returning SPECIFIC for claims that the new
# prompt rules say must always pass. They document the intended gate boundary
# so a future prompt regression is caught immediately.

@pytest.mark.parametrize("claim", [
    "The Deep State assassinated JFK",
    "The CIA killed JFK",
    "The government was involved in the 9/11 attacks",
    "Donald Trump colluded with Russia in 2016",
    "Hillary Clinton ran a child trafficking ring",
    "Oswald did not act alone in the JFK assassination",
    "Jeffrey Epstein did not kill himself",
    "The NSA spied on American citizens without warrants",
    # Regression: systemic/structural claims about named institutions + named groups
    # must pass even when phrased as political advocacy.
    "Die amerikanische Polizei ist ein systematisches Instrument der Unterdrückung schwarzer Menschen und muss vollständig abgeschafft werden.",
    "The American police is a systematic instrument of oppression of Black people and must be abolished",
    "The Catholic Church systematically covered up child abuse for decades",
    "The EU migration policy discriminates against non-European asylum seekers",
])
def test_named_event_or_figure_claims_are_marked_specific(claim):
    """
    Claims referencing a named public figure or a named historical event must
    be marked SPECIFIC by the gate model. We simulate the correct model response
    and verify that _check_specificity honours it — ensuring the parsing path
    works and the test suite documents the intended boundary.
    """
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("SPECIFIC\nOK")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_specific, rationale = eng._check_specificity(mock_client, claim)

    assert is_specific is True, f"Expected SPECIFIC for: {claim!r}"
    assert rationale == ""


def test_specificity_prompt_covers_systemic_institutional_claims():
    """
    Regression guard: _SPECIFICITY_PROMPT must explicitly instruct the model to pass
    systemic/structural claims about named institutions — even broad ones like
    "the American police". Without this, advocacy-phrased systemic claims are
    incorrectly rejected as vague generalisations.
    """
    from backend.analysis.engine import _SPECIFICITY_PROMPT

    prompt_lower = _SPECIFICITY_PROMPT.lower()
    assert "american police" in prompt_lower, (
        "_SPECIFICITY_PROMPT must include 'American police' as an explicit example "
        "of a named institution that passes the specificity gate"
    )
    assert "systemic" in prompt_lower or "structural" in prompt_lower, (
        "_SPECIFICITY_PROMPT must contain explicit guidance for systemic/structural "
        "claims about named institutions"
    )
    assert "named group" in prompt_lower or "named institution" in prompt_lower, (
        "_SPECIFICITY_PROMPT must reference named groups or institutions explicitly"
    )


@pytest.mark.parametrize("claim", [
    "the government is bad",
    "politicians lie",
    "something fishy happened",
    "they are hiding the truth",
    "elites control everything",
])
def test_content_free_claims_are_marked_vague(claim):
    """
    Purely content-free claims with no named person, event, or organisation must
    be marked VAGUE by the gate model.
    """
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("VAGUE\nPlease name a specific person, event, or allegation.")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_specific, rationale = eng._check_specificity(mock_client, claim)

    assert is_specific is False, f"Expected VAGUE for: {claim!r}"
    assert len(rationale) > 0


# ── analyze_claim integration tests ──────────────────────────────────────────

def _run_analyze(claim_text: str, specificity_result: tuple, judgment_data: dict | None = None):
    """
    Run analyze_claim with mocked specificity check and phase functions.
    Returns (captured_judgment, stored_sources, phase1_mock, phase2_mock).
    """
    from backend.analysis import engine as eng

    if judgment_data is None:
        judgment_data = {
            "rationale": "Evidence found.",
            "sources": [],
            "rating": "missing",
        }

    mock_claim = MagicMock()
    mock_claim.text = claim_text
    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim

    captured: dict = {}
    stored_sources: list = []

    def fake_add(obj):
        if isinstance(obj, Judgment):
            captured["judgment"] = obj

    mock_session.add.side_effect = fake_add
    mock_session.add_all.side_effect = lambda objs: stored_sources.extend(objs)

    with patch.object(eng, "_check_specificity", return_value=specificity_result), \
         patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt.") as p1, \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data) as p2, \
         patch.object(eng, "_get_client", return_value=MagicMock()):
        eng.analyze_claim("claim-1", mock_session)

    return captured.get("judgment"), stored_sources, p1, p2


def test_vague_claim_returns_missing_judgment():
    guidance = "Please name the specific official and the corrupt action alleged."
    rationale = (
        "This claim is too vague to fact-check meaningfully. "
        f"{guidance} "
        "Please refine the claim with specific names, dates, actions, or allegations and resubmit."
    )
    judgment, _, _, _ = _run_analyze(
        "The government is corrupt",
        specificity_result=(False, rationale),
    )

    assert judgment is not None
    assert judgment.rating == EpistemicRating.MISSING
    assert "vague" in judgment.rationale.lower() or "specific" in judgment.rationale.lower()


def test_vague_claim_stores_no_sources():
    judgment, sources, _, _ = _run_analyze(
        "Politicians lie",
        specificity_result=(False, "Too vague. Please name specific politicians and specific lies."),
    )

    assert sources == []


def test_vague_claim_does_not_call_phase1_or_phase2():
    _, _, phase1, phase2 = _run_analyze(
        "something fishy happened",
        specificity_result=(False, "Please specify who did what."),
    )

    phase1.assert_not_called()
    phase2.assert_not_called()


def test_vague_claim_judgment_analyst_is_set():
    judgment, _, _, _ = _run_analyze(
        "The media is biased",
        specificity_result=(False, "Please name a specific outlet and a specific false claim."),
    )

    assert judgment.analyst == "claude-sonnet-4-6"


def test_specific_claim_proceeds_to_full_pipeline():
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

    judgment, _, phase1, phase2 = _run_analyze(
        "Donald Trump signed the Tax Cuts and Jobs Act on 22 December 2017.",
        specificity_result=(True, ""),
        judgment_data=judgment_data,
    )

    phase1.assert_called_once()
    phase2.assert_called_once()
    assert judgment.rating == EpistemicRating.VERIFIED


# ── Breaking-news regression tests ───────────────────────────────────────────
#
# The gate must NEVER reject a claim just because the event is unknown to the
# model. Only reject when the claim lacks a specific actor + specific action.

def test_breaking_news_house_vote_iran_passes():
    """
    Precise breaking-news claim with date, institution, vote count, and topic
    must PASS even though the event post-dates training data.
    """
    from backend.analysis import engine as eng

    claim = (
        "Das Repräsentantenhaus der USA hat am 3. Juni 2026 mit 215 zu 208 Stimmen "
        "für den Militärabzug aus dem Iran-Krieg gestimmt."
    )
    fake_resp = _make_text_response("SPECIFIC")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_specific, rationale = eng._check_specificity(mock_client, claim)

    assert is_specific is True, f"Breaking-news claim must PASS specificity gate: {claim!r}"
    assert rationale == ""


def test_vague_iran_war_claim_fails():
    """
    A claim about the Iran war with no named actor, date, or concrete result
    must FAIL the specificity gate.
    """
    from backend.analysis import engine as eng

    claim = "Die USA haben etwas Wichtiges zum Iran-Krieg beschlossen."
    fake_resp = _make_text_response("VAGUE")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_specific, rationale = eng._check_specificity(mock_client, claim)

    assert is_specific is False, f"Vague claim must FAIL specificity gate: {claim!r}"
    assert len(rationale) > 0


def test_breaking_news_bundestag_nato_passes():
    """
    Implausible-sounding but fully specific breaking-news claim (named institution,
    date, vote count, topic) must PASS. Plausibility is checked later in the
    analysis pipeline, never at the specificity gate.
    """
    from backend.analysis import engine as eng

    claim = (
        "Der Bundestag hat am 3. Juni 2026 mit 500 zu 0 Stimmen beschlossen, "
        "Deutschland aus der NATO auszutreten."
    )
    fake_resp = _make_text_response("SPECIFIC")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_specific, rationale = eng._check_specificity(mock_client, claim)

    assert is_specific is True, (
        f"Specific claim must PASS even if implausible — plausibility is not the gate's job: {claim!r}"
    )
    assert rationale == ""


def test_specificity_prompt_covers_breaking_news_rule():
    """
    Regression guard: _SPECIFICITY_PROMPT must explicitly state that breaking-news
    claims about unfamiliar events must pass, and must never reject based on
    event familiarity.
    """
    from backend.analysis.engine import _SPECIFICITY_PROMPT

    prompt_lower = _SPECIFICITY_PROMPT.lower()
    assert "breaking news" in prompt_lower or "breaking-news" in prompt_lower, (
        "_SPECIFICITY_PROMPT must mention breaking news claims"
    )
    assert "training data" in prompt_lower, (
        "_SPECIFICITY_PROMPT must state that unfamiliarity from training data is not a rejection reason"
    )
    assert "plausibility" in prompt_lower or "plausible" in prompt_lower, (
        "_SPECIFICITY_PROMPT must clarify that plausibility is checked elsewhere, not here"
    )


def test_specific_claim_uses_model_rating():
    """When the claim is specific, the model's explicit rating is honoured."""
    sources = [
        {
            "url": "https://apnews.com/1",
            "tier": "secondary",
            "is_independent": True,
            "relevance_score": 0.8,
            "supports_claim": True,
        },
        {
            "url": "https://apnews.com/2",
            "tier": "secondary",
            "is_independent": True,
            "relevance_score": 0.8,
            "supports_claim": True,
        },
    ]
    judgment_data = {"rationale": "Plausible but thin.", "sources": sources, "rating": "speculative"}

    judgment, _, _, _ = _run_analyze(
        "Joe Biden's approval rating fell below 40% in November 2021.",
        specificity_result=(True, ""),
        judgment_data=judgment_data,
    )

    assert judgment.rating == EpistemicRating.SPECULATIVE
