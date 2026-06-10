"""
Tests for the single-active-judgment invariant.

(a) analyze_claim deactivates prior active judgment before inserting new one.
(b) merge_into_canonical leaves exactly one active judgment on canonical.
(c) Migration 0002 repair keeps only the newest active judgment per claim.
"""
import importlib.util
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.analysis.engine import _deactivate_prior_judgments
from backend.analysis.rating import EpistemicRating, SourceTier
from backend.db.models import Base, Claim, EvaluatedSource, Judgment
from backend.db.storage import merge_into_canonical


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _make_claim(session: Session, text: str = "test claim") -> Claim:
    c = Claim(text=text)
    session.add(c)
    session.flush()
    return c


def _make_judgment(session: Session, claim_id: str, is_active: bool = True) -> Judgment:
    j = Judgment(
        claim_id=claim_id,
        rating=EpistemicRating.SPECULATIVE,
        rationale="test",
        analyst="test",
        is_active=is_active,
    )
    session.add(j)
    session.flush()
    return j


# ── (a) _deactivate_prior_judgments ──────────────────────────────────────────

class TestDeactivatePriorJudgments:

    def test_deactivates_existing_active_judgment(self, session):
        claim = _make_claim(session)
        prior = _make_judgment(session, claim.id, is_active=True)
        session.commit()

        assert prior.is_active is True

        _deactivate_prior_judgments(session, claim.id)
        session.commit()

        session.expire(prior)
        assert prior.is_active is False

    def test_new_judgment_is_the_only_active_one(self, session):
        claim = _make_claim(session)
        prior = _make_judgment(session, claim.id, is_active=True)
        session.commit()

        _deactivate_prior_judgments(session, claim.id)
        new_j = Judgment(
            claim_id=claim.id,
            rating=EpistemicRating.VERIFIED,
            rationale="updated",
            analyst="test",
            is_active=True,
        )
        session.add(new_j)
        session.commit()

        active_ids = session.execute(
            select(Judgment.id).where(
                Judgment.claim_id == claim.id,
                Judgment.is_active.is_(True),
            )
        ).scalars().all()

        assert len(active_ids) == 1
        assert active_ids[0] == new_j.id

    def test_does_not_touch_other_claims(self, session):
        claim_a = _make_claim(session, "claim A")
        claim_b = _make_claim(session, "claim B")
        j_a = _make_judgment(session, claim_a.id, is_active=True)
        j_b = _make_judgment(session, claim_b.id, is_active=True)
        session.commit()

        _deactivate_prior_judgments(session, claim_a.id)
        session.commit()

        session.expire(j_b)
        assert j_b.is_active is True

    def test_no_error_when_no_prior_judgments(self, session):
        claim = _make_claim(session)
        session.commit()
        # Should not raise
        _deactivate_prior_judgments(session, claim.id)
        session.commit()


# ── (b) merge_into_canonical ──────────────────────────────────────────────────

class TestMergeIntoCanonical:

    def test_leaves_exactly_one_active_judgment_after_merge(self, session):
        canonical = _make_claim(session, "canonical claim text")
        temp = _make_claim(session, "identical claim text")

        # canonical has a prior active judgment
        prior_canonical_j = _make_judgment(session, canonical.id, is_active=True)
        # temp has the newly created judgment (from the just-completed analysis)
        new_j = _make_judgment(session, temp.id, is_active=True)
        session.commit()

        merge_into_canonical(session, temp.id, canonical.id)

        active = session.execute(
            select(Judgment).where(
                Judgment.claim_id == canonical.id,
                Judgment.is_active.is_(True),
            )
        ).scalars().all()

        assert len(active) == 1
        assert active[0].id == new_j.id

    def test_prior_canonical_judgment_is_deactivated(self, session):
        canonical = _make_claim(session, "canonical claim")
        temp = _make_claim(session, "temp claim")

        prior = _make_judgment(session, canonical.id, is_active=True)
        _make_judgment(session, temp.id, is_active=True)
        session.commit()

        prior_id = prior.id
        merge_into_canonical(session, temp.id, canonical.id)

        refreshed = session.get(Judgment, prior_id)
        assert refreshed.is_active is False

    def test_all_judgments_move_to_canonical(self, session):
        canonical = _make_claim(session, "canonical")
        temp = _make_claim(session, "temp")

        _make_judgment(session, canonical.id, is_active=True)
        temp_j = _make_judgment(session, temp.id, is_active=True)
        session.commit()

        temp_j_id = temp_j.id
        merge_into_canonical(session, temp.id, canonical.id)

        moved = session.get(Judgment, temp_j_id)
        assert moved.claim_id == canonical.id


# ── (c) Migration 0002 repair logic ──────────────────────────────────────────

def _load_migration_0002():
    path = Path(__file__).parent.parent / "alembic" / "versions" / "0002_repair_duplicate_active_judgments.py"
    spec = importlib.util.spec_from_file_location("migration_0002", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMigration0002Repair:

    @pytest.fixture()
    def conn(self):
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        with engine.connect() as c:
            yield c

    def test_keeps_newest_active_deactivates_older(self, conn):
        from datetime import datetime, timedelta

        mod = _load_migration_0002()

        base_time = datetime(2026, 1, 1, 12, 0, 0)
        claim_id = str(uuid.uuid4())

        conn.execute(
            Base.metadata.tables["claims"].insert(),
            {"id": claim_id, "text": "test", "submitted_at": base_time},
        )

        older_id = str(uuid.uuid4())
        newer_id = str(uuid.uuid4())
        conn.execute(
            Base.metadata.tables["judgments"].insert(),
            [
                {
                    "id": older_id,
                    "claim_id": claim_id,
                    "rating": "speculative",
                    "rationale": "old",
                    "analyst": "test",
                    "is_active": True,
                    "created_at": base_time,
                },
                {
                    "id": newer_id,
                    "claim_id": claim_id,
                    "rating": "verified",
                    "rationale": "new",
                    "analyst": "test",
                    "is_active": True,
                    "created_at": base_time + timedelta(hours=1),
                },
            ],
        )
        conn.commit()

        claims_affected, rows_deactivated = mod._repair_duplicate_active_judgments(conn)
        conn.commit()

        assert claims_affected == 1
        assert rows_deactivated == 1

        from sqlalchemy import text
        results = conn.execute(
            text("SELECT id, is_active FROM judgments WHERE claim_id = :cid"),
            {"cid": claim_id},
        ).fetchall()
        by_id = {r[0]: r[1] for r in results}

        assert by_id[newer_id] is True or by_id[newer_id] == 1
        assert by_id[older_id] is False or by_id[older_id] == 0

    def test_no_change_when_only_one_active(self, conn):
        from datetime import datetime

        mod = _load_migration_0002()

        claim_id = str(uuid.uuid4())
        conn.execute(
            Base.metadata.tables["claims"].insert(),
            {"id": claim_id, "text": "single", "submitted_at": datetime.utcnow()},
        )
        j_id = str(uuid.uuid4())
        conn.execute(
            Base.metadata.tables["judgments"].insert(),
            {
                "id": j_id,
                "claim_id": claim_id,
                "rating": "speculative",
                "rationale": "r",
                "analyst": "test",
                "is_active": True,
                "created_at": datetime.utcnow(),
            },
        )
        conn.commit()

        claims_affected, rows_deactivated = mod._repair_duplicate_active_judgments(conn)
        assert claims_affected == 0
        assert rows_deactivated == 0

    def test_multiple_claims_repaired_independently(self, conn):
        from datetime import datetime, timedelta

        mod = _load_migration_0002()

        base = datetime(2026, 1, 1, 12, 0, 0)

        claims_data = []
        for i in range(3):
            cid = str(uuid.uuid4())
            claims_data.append(cid)
            conn.execute(
                Base.metadata.tables["claims"].insert(),
                {"id": cid, "text": f"claim {i}", "submitted_at": base},
            )
            # Insert 2 active judgments per claim
            for offset in range(2):
                conn.execute(
                    Base.metadata.tables["judgments"].insert(),
                    {
                        "id": str(uuid.uuid4()),
                        "claim_id": cid,
                        "rating": "speculative",
                        "rationale": "r",
                        "analyst": "test",
                        "is_active": True,
                        "created_at": base + timedelta(hours=offset),
                    },
                )
        conn.commit()

        claims_affected, rows_deactivated = mod._repair_duplicate_active_judgments(conn)
        assert claims_affected == 3
        assert rows_deactivated == 3  # 1 deactivated per claim
