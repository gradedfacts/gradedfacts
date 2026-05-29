"""
Tests for the /ui/followup endpoint source-context fix.

Verifies that the user message passed to Claude includes the complete
sources list (URL, tier, independence, relevance, excerpt) so that
follow-up questions about specific sources are answered correctly.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.analysis.rating import EpistemicRating, SourceTier
from backend.db.models import Base, Claim, EvaluatedSource, Judgment
from backend.db.session import get_session


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_session():
    _engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(_engine)
    Session = sessionmaker(bind=_engine, autoflush=False)
    with Session() as s:
        yield s


def _make_claude_response(text: str):
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def _seed(session, *, sources: list[dict]) -> tuple[str, str]:
    """Insert a Claim, its EvaluatedSources, and an active Judgment. Returns (claim_id, judgment_id)."""
    claim = Claim(
        id="claim-1",
        text="GDP grew by more than 2% last year.",
    )
    session.add(claim)

    for s in sources:
        session.add(EvaluatedSource(
            claim_id="claim-1",
            url=s["url"],
            tier=s.get("tier", SourceTier.SECONDARY),
            is_independent=s.get("is_independent", True),
            independence_label=s.get("independence_label", "independent"),
            relevance_score=s.get("relevance_score", 0.9),
            excerpt=s.get("excerpt"),
        ))

    judgment = Judgment(
        id="judgment-1",
        claim_id="claim-1",
        rating=EpistemicRating.VERIFIED,
        rationale="GDP growth confirmed by official statistics.",
        analyst="claude-sonnet-4-6",
        is_active=True,
    )
    session.add(judgment)
    session.commit()
    return "claim-1", "judgment-1"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _captured_user_msg(session, sources: list[dict], question: str) -> str:
    """
    Call the follow-up endpoint and return the `content` of the user message
    that was passed to the Claude client.
    """
    from backend.api import app

    _seed(session, sources=sources)

    with patch("backend.api._get_client") as mock_get_client, \
         patch("backend.api.check_followup_rate_limit", return_value=True):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_claude_response("Answer here.")
        mock_get_client.return_value = mock_client

        def _override():
            yield session

        app.dependency_overrides[get_session] = _override
        try:
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/ui/followup",
                data={"claim_id": "claim-1", "followup_question": question, "lang": "en"},
            )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 200
    call_kwargs = mock_client.messages.create.call_args
    messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs["messages"]
    # messages is a list; the user turn is role=="user"
    user_turn = next(m for m in messages if m["role"] == "user")
    return user_turn["content"]


# ── Test 1: source IS in the list → URL appears in context ───────────────────

def test_followup_includes_source_that_is_present(db_session):
    sources = [
        {
            "url": "https://www.destatis.de/gdp-2023",
            "tier": SourceTier.PRIMARY,
            "is_independent": True,
            "independence_label": "independent",
            "relevance_score": 0.95,
            "excerpt": "Real GDP growth was 2.3% in 2023.",
        }
    ]
    user_msg = _captured_user_msg(
        db_session, sources, "Was destatis.de used as a source?"
    )

    assert "destatis.de/gdp-2023" in user_msg, (
        "URL of the source must appear in the context passed to Claude"
    )
    assert "primary" in user_msg.lower(), "Tier must be present"
    assert "independent" in user_msg.lower(), "Independence status must be present"
    assert "0.95" in user_msg, "Relevance score must be present"
    assert "Real GDP growth was 2.3%" in user_msg, "Excerpt must be present"


# ── Test 2: source NOT in the list → only listed URLs appear ─────────────────

def test_followup_context_does_not_invent_absent_source(db_session):
    sources = [
        {
            "url": "https://www.bls.gov/gdp-stats",
            "tier": SourceTier.PRIMARY,
            "is_independent": True,
            "independence_label": "independent",
            "relevance_score": 0.88,
            "excerpt": "GDP data from BLS.",
        }
    ]
    user_msg = _captured_user_msg(
        db_session, sources, "Was a news agency used as a source?"
    )

    # The sources block must list bls.gov but must not invent reuters.com
    assert "bls.gov" in user_msg, "The actual source URL must be present"
    # Confirm the sources section (everything before the follow-up line) has no phantom URL
    sources_section = user_msg.split("Follow-up question:")[0]
    assert "reuters.com" not in sources_section, (
        "A URL absent from the DB must not appear in the sources context"
    )


# ── Test 3: all four context fields are present ───────────────────────────────

def test_followup_context_contains_all_required_fields(db_session):
    sources = [
        {
            "url": "https://eurostat.ec.europa.eu/data/gdp",
            "tier": SourceTier.SECONDARY,
            "is_independent": False,
            "independence_label": "neutral",
            "relevance_score": 0.75,
            "excerpt": "Eurostat reports 2.1% growth.",
        }
    ]
    user_msg = _captured_user_msg(
        db_session, sources, "What does the Eurostat source say?"
    )

    # 1. Original claim
    assert "GDP grew by more than 2% last year" in user_msg
    # 2. Rating
    assert "VERIFIED" in user_msg
    # 3. Rationale
    assert "GDP growth confirmed by official statistics" in user_msg
    # 4. Source metadata
    assert "eurostat.ec.europa.eu" in user_msg
    assert "secondary" in user_msg.lower()
    assert "neutral" in user_msg.lower()
    assert "0.75" in user_msg
    assert "Eurostat reports 2.1% growth" in user_msg
