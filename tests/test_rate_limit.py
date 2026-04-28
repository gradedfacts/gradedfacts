import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.models import Base, RateLimit
from backend.db.rate_limit import DAILY_LIMIT, _hash_ip, _today_utc, check_and_increment


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session() as s:
        yield s


# ── Core counting behaviour ───────────────────────────────────────────────────

def test_first_request_allowed(session):
    assert check_and_increment("1.2.3.4", session, enabled=True) is True


def test_requests_up_to_limit_all_allowed(session):
    for _ in range(DAILY_LIMIT):
        assert check_and_increment("1.2.3.4", session, enabled=True) is True


def test_request_over_limit_blocked(session):
    for _ in range(DAILY_LIMIT):
        check_and_increment("1.2.3.4", session, enabled=True)
    assert check_and_increment("1.2.3.4", session, enabled=True) is False


def test_count_persists_across_calls(session):
    check_and_increment("1.2.3.4", session, enabled=True)
    check_and_increment("1.2.3.4", session, enabled=True)
    today = _today_utc()
    row = session.get(RateLimit, (_hash_ip("1.2.3.4"), today))
    assert row is not None
    assert row.count == 2


def test_different_ips_are_independent(session):
    for _ in range(DAILY_LIMIT):
        check_and_increment("1.2.3.4", session, enabled=True)
    # A different IP must not be affected by the first IP's count
    assert check_and_increment("5.6.7.8", session, enabled=True) is True


# ── Privacy: raw IP is never stored ──────────────────────────────────────────

def test_raw_ip_not_stored(session):
    check_and_increment("192.168.1.100", session, enabled=True)
    row = session.query(RateLimit).first()
    assert row is not None
    assert "192.168.1.100" not in row.ip_hash


def test_ip_hash_is_sha256_hex(session):
    import hashlib
    ip = "10.0.0.1"
    check_and_increment(ip, session, enabled=True)
    expected = hashlib.sha256(ip.encode()).hexdigest()
    today = _today_utc()
    row = session.get(RateLimit, (expected, today))
    assert row is not None


# ── Flag disabled: always passes ─────────────────────────────────────────────

def test_disabled_flag_allows_beyond_limit(session):
    for _ in range(DAILY_LIMIT + 10):
        assert check_and_increment("1.2.3.4", session, enabled=False) is True


def test_disabled_flag_writes_no_rows(session):
    check_and_increment("1.2.3.4", session, enabled=False)
    assert session.query(RateLimit).count() == 0
