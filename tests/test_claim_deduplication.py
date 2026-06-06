"""
Unit tests for claim deduplication logic in backend/db/storage.py.

Tests cover:
  - normalize_claim_text: unicode normalization, whitespace collapse, case folding
  - find_canonical_claim: match / no-match / self-exclusion
  - merge_into_canonical: reassignment of Judgments + EvaluatedSources, temp Claim deletion
"""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.db.models import Base, Claim, EvaluatedSource, Judgment
from backend.analysis.rating import EpistemicRating, SourceTier
from backend.db.storage import find_canonical_claim, merge_into_canonical, normalize_claim_text


# ── normalize_claim_text ──────────────────────────────────────────────────────

class TestNormalizeClaimText:

    def test_strips_leading_trailing_whitespace(self):
        assert normalize_claim_text("  hello  ") == "hello"

    def test_collapses_internal_whitespace(self):
        assert normalize_claim_text("hello   world") == "hello world"

    def test_lowercases(self):
        assert normalize_claim_text("Hello World") == "hello world"

    def test_nfc_normalization(self):
        # "é" as NFD (e + combining accent) vs NFC (single codepoint) must match
        nfd = "é"  # NFD: e + combining acute accent
        nfc = "\xe9"     # NFC: é
        assert normalize_claim_text(nfd) == normalize_claim_text(nfc)

    def test_tabs_and_newlines_collapsed(self):
        assert normalize_claim_text("hello\t\nworld") == "hello world"

    def test_empty_string(self):
        assert normalize_claim_text("") == ""

    def test_already_normalized(self):
        assert normalize_claim_text("the gdp grew by 3%") == "the gdp grew by 3%"

    @pytest.mark.parametrize("a,b", [
        ("The claim is true", "the claim is true"),
        ("  extra   spaces  ", "extra spaces"),
        ("Über", "über"),
    ])
    def test_pairs_normalize_to_same(self, a, b):
        assert normalize_claim_text(a) == normalize_claim_text(b)


# ── Shared in-memory DB fixture ───────────────────────────────────────────────

@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _make_claim(session: Session, text: str) -> Claim:
    c = Claim(text=text)
    session.add(c)
    session.flush()
    return c


def _make_judgment(session: Session, claim_id: str) -> Judgment:
    j = Judgment(
        claim_id=claim_id,
        rating=EpistemicRating.SPECULATIVE,
        rationale="test",
        analyst="test",
        is_active=True,
    )
    session.add(j)
    session.flush()
    return j


def _make_source(session: Session, claim_id: str) -> EvaluatedSource:
    s = EvaluatedSource(
        claim_id=claim_id,
        url="https://example.com",
        tier=SourceTier.SECONDARY,
        is_independent=True,
        relevance_score=0.8,
    )
    session.add(s)
    session.flush()
    return s


# ── find_canonical_claim ──────────────────────────────────────────────────────

class TestFindCanonicalClaim:

    def test_returns_none_when_no_match(self, session):
        _make_claim(session, "some unique claim about pandas")
        result = find_canonical_claim(session, "completely different text")
        assert result is None

    def test_finds_exact_match(self, session):
        existing = _make_claim(session, "the economy grew by 2%")
        result = find_canonical_claim(session, "the economy grew by 2%")
        assert result is not None
        assert result.id == existing.id

    def test_matches_case_insensitively(self, session):
        existing = _make_claim(session, "the economy grew by 2%")
        result = find_canonical_claim(session, "THE ECONOMY GREW BY 2%")
        assert result is not None
        assert result.id == existing.id

    def test_matches_after_whitespace_normalization(self, session):
        existing = _make_claim(session, "the economy grew by 2%")
        result = find_canonical_claim(session, "  the  economy  grew  by  2%  ")
        assert result is not None
        assert result.id == existing.id

    def test_excludes_self(self, session):
        claim = _make_claim(session, "the economy grew by 2%")
        result = find_canonical_claim(session, "the economy grew by 2%", exclude_id=claim.id)
        assert result is None

    def test_returns_earliest_when_multiple_match(self, session):
        first = _make_claim(session, "unemployment is at 4%")
        second = _make_claim(session, "unemployment is at 4%")
        result = find_canonical_claim(session, "unemployment is at 4%", exclude_id=second.id)
        assert result is not None
        assert result.id == first.id

    def test_no_match_for_similar_but_different_text(self, session):
        _make_claim(session, "gdp rose by 3%")
        result = find_canonical_claim(session, "gdp rose by 4%")
        assert result is None


# ── merge_into_canonical ──────────────────────────────────────────────────────

class TestMergeIntoCanonical:

    def test_judgment_reassigned_to_canonical(self, session):
        canonical = _make_claim(session, "original claim")
        temp = _make_claim(session, "original claim")
        judgment = _make_judgment(session, temp.id)
        session.commit()

        merge_into_canonical(session, temp_id=temp.id, canonical_id=canonical.id)

        session.expire_all()
        updated = session.get(Judgment, judgment.id)
        assert updated.claim_id == canonical.id

    def test_source_reassigned_to_canonical(self, session):
        canonical = _make_claim(session, "original claim")
        temp = _make_claim(session, "original claim")
        source = _make_source(session, temp.id)
        session.commit()

        merge_into_canonical(session, temp_id=temp.id, canonical_id=canonical.id)

        session.expire_all()
        updated = session.get(EvaluatedSource, source.id)
        assert updated.claim_id == canonical.id

    def test_temp_claim_deleted(self, session):
        canonical = _make_claim(session, "original claim")
        temp = _make_claim(session, "original claim")
        session.commit()

        merge_into_canonical(session, temp_id=temp.id, canonical_id=canonical.id)

        session.expire_all()
        assert session.get(Claim, temp.id) is None

    def test_canonical_claim_preserved(self, session):
        canonical = _make_claim(session, "original claim")
        temp = _make_claim(session, "original claim")
        session.commit()

        merge_into_canonical(session, temp_id=temp.id, canonical_id=canonical.id)

        session.expire_all()
        assert session.get(Claim, canonical.id) is not None

    def test_canonical_history_accumulates(self, session):
        canonical = _make_claim(session, "claim text")
        old_judgment = _make_judgment(session, canonical.id)
        temp = _make_claim(session, "claim text")
        new_judgment = _make_judgment(session, temp.id)
        session.commit()

        merge_into_canonical(session, temp_id=temp.id, canonical_id=canonical.id)

        session.expire_all()
        rows = session.execute(
            select(Judgment).where(Judgment.claim_id == canonical.id)
        ).scalars().all()
        ids = {j.id for j in rows}
        assert old_judgment.id in ids
        assert new_judgment.id in ids
        assert len(rows) == 2

    def test_multiple_sources_all_reassigned(self, session):
        canonical = _make_claim(session, "claim text")
        temp = _make_claim(session, "claim text")
        sources = [_make_source(session, temp.id) for _ in range(3)]
        session.commit()

        merge_into_canonical(session, temp_id=temp.id, canonical_id=canonical.id)

        session.expire_all()
        for src in sources:
            updated = session.get(EvaluatedSource, src.id)
            assert updated.claim_id == canonical.id
