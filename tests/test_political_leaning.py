"""
Tests for political_leaning classification in the judgment pipeline.

Covers:
  - Clearly LEFT-framed claims → "left"
  - Clearly RIGHT-framed claims → "right"
  - Scientific consensus claims → "none"
  - Raw economic statistics → "none"
  - Neutral claim about a left-wing politician → "none"
  - Neutral claim about a right-wing politician → "none"
  - Ambiguous claims that could cut either way → "none"
  - Parsing failure / invalid value → defaults to "none"
  - political_leaning is stored on the Judgment object
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.analysis.rating import EpistemicRating
from backend.db.models import Judgment


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_analyze_with_leaning(claim_text: str, political_leaning_value: str):
    """
    Run analyze_claim() with a mocked _phase2_judgment that returns the given
    political_leaning value. Returns the captured Judgment object.
    """
    from backend.analysis import engine as eng

    judgment_data = {
        "rationale": "Test rationale.",
        "sources": [],
        "rating": "speculative",
        "political_leaning": political_leaning_value,
    }

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

    with patch.object(eng, "_check_specificity", return_value=(True, "")), \
         patch.object(eng, "_check_off_topic", return_value=(True, "")), \
         patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt."), \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data), \
         patch.object(eng, "_get_client", return_value=MagicMock()):
        eng.analyze_claim("claim-1", mock_session)

    return captured["judgment"]


# ── 1. Clearly LEFT framing ───────────────────────────────────────────────────

def test_clearly_left_framing_stored_as_left():
    claim = "Trickle-down economics has devastated the working class and only enriched the wealthy"
    judgment = _run_analyze_with_leaning(claim, "left")
    assert judgment.political_leaning == "left"


# ── 2. Clearly RIGHT framing ──────────────────────────────────────────────────

def test_clearly_right_framing_stored_as_right():
    claim = "Open-border immigration policies are destroying national security and cultural identity"
    judgment = _run_analyze_with_leaning(claim, "right")
    assert judgment.political_leaning == "right"


# ── 3. Scientific consensus claim → none ─────────────────────────────────────

def test_scientific_consensus_claim_stored_as_none():
    claim = "Global average temperatures have risen 1.1°C since pre-industrial times"
    judgment = _run_analyze_with_leaning(claim, "none")
    assert judgment.political_leaning == "none"


# ── 4. Raw economic statistic → none ─────────────────────────────────────────

def test_raw_economic_statistic_stored_as_none():
    claim = "US GDP grew 2.3% in the fourth quarter of 2023"
    judgment = _run_analyze_with_leaning(claim, "none")
    assert judgment.political_leaning == "none"


# ── 5. Neutral claim about a left-wing politician → none ─────────────────────

def test_neutral_claim_about_left_wing_politician_stored_as_none():
    claim = "Bernie Sanders voted against the 2017 Tax Cuts and Jobs Act"
    judgment = _run_analyze_with_leaning(claim, "none")
    assert judgment.political_leaning == "none"


# ── 6. Neutral claim about a right-wing politician → none ────────────────────

def test_neutral_claim_about_right_wing_politician_stored_as_none():
    claim = "Donald Trump increased the national debt by $7.8 trillion during his first term"
    judgment = _run_analyze_with_leaning(claim, "none")
    assert judgment.political_leaning == "none"


# ── 7. Ambiguous claim (could be either side) → none ─────────────────────────

def test_ambiguous_claim_stored_as_none():
    claim = "Government spending has increased significantly over the last decade"
    judgment = _run_analyze_with_leaning(claim, "none")
    assert judgment.political_leaning == "none"


# ── 8. Parsing failure / invalid value → defaults to none ────────────────────

def test_invalid_political_leaning_value_defaults_to_none():
    claim = "Some claim"
    judgment = _run_analyze_with_leaning(claim, "INVALID_VALUE")
    assert judgment.political_leaning == "none"


def test_missing_political_leaning_key_defaults_to_none():
    """If the model omits political_leaning entirely, the field must be 'none'."""
    from backend.analysis import engine as eng

    judgment_data = {
        "rationale": "Test rationale.",
        "sources": [],
        "rating": "speculative",
        # political_leaning intentionally absent
    }

    mock_claim = MagicMock()
    mock_claim.text = "Some claim without leaning"
    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim

    captured: dict = {}

    def fake_add(obj):
        if isinstance(obj, Judgment):
            captured["judgment"] = obj

    mock_session.add.side_effect = fake_add
    mock_session.add_all.side_effect = lambda objs: None

    with patch.object(eng, "_check_specificity", return_value=(True, "")), \
         patch.object(eng, "_check_off_topic", return_value=(True, "")), \
         patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt."), \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data), \
         patch.object(eng, "_get_client", return_value=MagicMock()):
        eng.analyze_claim("claim-1", mock_session)

    assert captured["judgment"].political_leaning == "none"


# ── Symmetry: _SYSTEM_PROMPT contains the classification rules ────────────────

def test_system_prompt_contains_political_leaning_section():
    from backend.analysis.engine import _SYSTEM_PROMPT

    assert "POLITICAL_LEANING" in _SYSTEM_PROMPT
    assert "symmetry" in _SYSTEM_PROMPT.lower()
    assert '"none"' in _SYSTEM_PROMPT or "'none'" in _SYSTEM_PROMPT


def test_system_prompt_requires_none_as_default():
    from backend.analysis.engine import _SYSTEM_PROMPT

    assert "DEFAULT" in _SYSTEM_PROMPT or "default" in _SYSTEM_PROMPT
    assert "uncertain" in _SYSTEM_PROMPT.lower()


# ── _JUDGMENT_TOOL schema includes political_leaning ─────────────────────────

def test_judgment_tool_schema_includes_political_leaning():
    from backend.analysis.engine import _JUDGMENT_TOOL

    props = _JUDGMENT_TOOL["input_schema"]["properties"]
    assert "political_leaning" in props
    assert props["political_leaning"]["type"] == "string"
    assert set(props["political_leaning"]["enum"]) == {"left", "right", "none"}


def test_judgment_tool_requires_political_leaning():
    from backend.analysis.engine import _JUDGMENT_TOOL

    assert "political_leaning" in _JUDGMENT_TOOL["input_schema"]["required"]
