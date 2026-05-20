"""
Tests for BCP-47 UI language code routing through the pre-flight gates.

Covers:
  - _resolve_ui_language() for all 17 supported codes
  - _check_specificity() returns the correct locale message for each language
  - _check_off_topic() returns the correct locale message for each language
  - analyze_claim() routes user_language codes correctly end-to-end
  - Region-qualified codes (e.g. "pt-BR", "zh-CN") resolve to the right language
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.db.models import Judgment
from backend.analysis.rating import EpistemicRating


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_text_response(text: str):
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


# ── _resolve_ui_language ──────────────────────────────────────────────────────

@pytest.mark.parametrize("code,expected", [
    ("en", "English"),
    ("de", "German"),
    ("fr", "French"),
    ("it", "Italian"),
    ("es", "Spanish"),
    ("pt", "Portuguese"),
    ("nl", "Dutch"),
    ("pl", "Polish"),
    ("sv", "Swedish"),
    ("ru", "Russian"),
    ("uk", "Ukrainian"),
    ("tr", "Turkish"),
    ("ar", "Arabic"),
    ("zh", "Chinese"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("hu", "Hungarian"),
])
def test_resolve_ui_language_all_17_codes(code, expected):
    from backend.analysis.engine import _resolve_ui_language
    assert _resolve_ui_language(code) == expected


def test_resolve_ui_language_region_qualified_pt_br():
    from backend.analysis.engine import _resolve_ui_language
    assert _resolve_ui_language("pt-BR") == "Portuguese"


def test_resolve_ui_language_region_qualified_zh_cn():
    from backend.analysis.engine import _resolve_ui_language
    assert _resolve_ui_language("zh-CN") == "Chinese"


def test_resolve_ui_language_region_qualified_de_at():
    from backend.analysis.engine import _resolve_ui_language
    assert _resolve_ui_language("de-AT") == "German"


def test_resolve_ui_language_unsupported_falls_back_to_english():
    from backend.analysis.engine import _resolve_ui_language
    assert _resolve_ui_language("xx") == "English"
    assert _resolve_ui_language("tl") == "English"


# ── _check_specificity returns correct locale message ─────────────────────────

@pytest.mark.parametrize("lang_name,expected_fragment", [
    ("French",     "vague"),        # "Cette affirmation est trop vague"
    ("Italian",    "vaga"),         # "troppo vaga"
    ("Spanish",    "vaga"),         # "demasiado vaga"
    ("Polish",     "ogólne"),       # "zbyt ogólne"
    ("Japanese",   "曖昧"),          # "曖昧すぎます"
    ("Korean",     "모호"),          # "너무 모호합니다"
    ("Arabic",     "مبهم"),          # "مبهم للغاية"
    ("Ukrainian",  "розпливчасте"), # "занадто розпливчасте"
])
def test_check_specificity_message_language(lang_name, expected_fragment):
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("VAGUE\nPlease be more specific.")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_specific, rationale = eng._check_specificity(mock_client, "vague claim", lang_name)

    assert is_specific is False
    assert expected_fragment in rationale, (
        f"Expected {expected_fragment!r} in {lang_name} specificity message, got: {rationale!r}"
    )


# ── _check_off_topic returns correct locale message ───────────────────────────

@pytest.mark.parametrize("lang_name,expected_fragment", [
    ("French",     "politiquement"),  # "politiquement ou factuellement pertinente"
    ("Italian",    "rilevante"),      # "politicamente o fattualmente rilevante"
    ("Spanish",    "relevante"),      # "política o factualmente relevante"
    ("Polish",     "faktycznie"),     # "politycznie lub faktycznie"
    ("Japanese",   "関連"),            # "政治的または事実的に関連"
    ("Russian",    "значимое"),       # "политически или фактически значимое"
    ("Turkish",    "ilgili"),         # "siyasi veya olgusal olarak ilgili"
    ("Hungarian",  "releváns"),       # "politikailag vagy tényszerűen releváns"
])
def test_check_off_topic_message_language(lang_name, expected_fragment):
    from backend.analysis import engine as eng

    fake_resp = _make_text_response("REJECT")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_resp

    is_on_topic, rationale = eng._check_off_topic(mock_client, "Write me a poem", lang_name)

    assert is_on_topic is False
    assert expected_fragment in rationale, (
        f"Expected {expected_fragment!r} in {lang_name} off-topic message, got: {rationale!r}"
    )


# ── analyze_claim: BCP-47 code routed through both gates ─────────────────────

def _run_with_language(user_language: str, gate_response: str):
    """
    Run analyze_claim with a given user_language code and a Haiku response
    that causes gate rejection. Returns the stored Judgment.
    """
    from backend.analysis import engine as eng

    mock_claim = MagicMock()
    mock_claim.text = "something vague"
    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim

    captured: dict = {}

    def fake_add(obj):
        if isinstance(obj, Judgment):
            captured["judgment"] = obj

    mock_session.add.side_effect = fake_add
    mock_session.add_all.side_effect = lambda objs: None

    # Haiku returns VAGUE for specificity → gate 1 fires
    fake_haiku = _make_text_response(gate_response)
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_haiku

    with patch.object(eng, "_get_client", return_value=mock_client):
        eng.analyze_claim("claim-1", mock_session, user_language=user_language)

    return captured.get("judgment")


@pytest.mark.parametrize("code,expected_fragment", [
    ("de", "vage"),          # German specificity_message
    ("fr", "vague"),         # French
    ("it", "vaga"),          # Italian
    ("es", "vaga"),          # Spanish
    ("pl", "ogólne"),        # Polish
])
def test_analyze_claim_specificity_gate_uses_correct_language(code, expected_fragment):
    """BCP-47 code is correctly resolved so the specificity MISSING judgment is localised."""
    judgment = _run_with_language(code, "VAGUE\nPlease be more specific.")

    assert judgment is not None
    assert judgment.rating == EpistemicRating.MISSING
    assert expected_fragment in judgment.rationale, (
        f"Expected {expected_fragment!r} in rationale for lang={code!r}, got: {judgment.rationale!r}"
    )


@pytest.mark.parametrize("code,expected_fragment", [
    ("pt", "relevante"),    # Portuguese off_topic_message
    ("nl", "relevante"),    # Dutch
    ("sv", "relevant"),     # Swedish
    ("ru", "значимое"),     # Russian
    ("ko", "관련"),          # Korean
])
def test_analyze_claim_off_topic_gate_uses_correct_language(code, expected_fragment):
    """BCP-47 code is correctly resolved so the off-topic MISSING judgment is localised."""
    # Return SPECIFIC from specificity (gate 1 passes), then REJECT from off-topic (gate 2 fires)
    from backend.analysis import engine as eng

    mock_claim = MagicMock()
    mock_claim.text = "Write me a story"
    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim

    captured: dict = {}

    def fake_add(obj):
        if isinstance(obj, Judgment):
            captured["judgment"] = obj

    mock_session.add.side_effect = fake_add
    mock_session.add_all.side_effect = lambda objs: None

    call_count = 0

    def haiku_side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        # First call: specificity → SPECIFIC
        # Second call: off-topic → REJECT
        text = "SPECIFIC\nOK" if call_count == 1 else "REJECT"
        return _make_text_response(text)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = haiku_side_effect

    with patch.object(eng, "_get_client", return_value=mock_client):
        eng.analyze_claim("claim-1", mock_session, user_language=code)

    judgment = captured.get("judgment")
    assert judgment is not None
    assert judgment.rating == EpistemicRating.MISSING
    assert expected_fragment in judgment.rationale, (
        f"Expected {expected_fragment!r} in rationale for lang={code!r}, got: {judgment.rationale!r}"
    )


def test_region_qualified_code_routes_correctly():
    """pt-BR must resolve to Portuguese and produce a Portuguese rejection message."""
    judgment = _run_with_language("pt-BR", "VAGUE\nPlease be more specific.")

    assert judgment is not None
    assert judgment.rating == EpistemicRating.MISSING
    # Portuguese specificity_message contains "vaga"
    assert "vaga" in judgment.rationale, f"Got: {judgment.rationale!r}"
