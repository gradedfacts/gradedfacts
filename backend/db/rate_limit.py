import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.config import settings
from backend.db.models import RateLimit

DAILY_LIMIT = 3
FOLLOWUP_DAILY_LIMIT = 1


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()


def _hash_ip_followup(ip: str) -> str:
    # Prefix before hashing so the 64-char output never collides with _hash_ip.
    return hashlib.sha256(f"followup:{ip}".encode()).hexdigest()


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def check_and_increment(ip: str, session: Session, *, enabled: bool | None = None) -> bool:
    """Return True if the request is within the daily limit.

    Pass enabled=True/False in tests to avoid depending on the env flag.
    """
    if enabled is None:
        enabled = settings.rate_limit_enabled
    if not enabled:
        return True

    ip_hash = _hash_ip(ip)
    today = _today_utc()

    row = session.get(RateLimit, (ip_hash, today))
    if row is None:
        session.add(RateLimit(ip_hash=ip_hash, date=today, count=1))
        session.commit()
        return True

    if row.count >= DAILY_LIMIT:
        return False

    row.count += 1
    session.commit()
    return True


def check_followup_rate_limit(ip: str, session: Session, *, enabled: bool | None = None) -> bool:
    """Return True if the follow-up request is within the daily follow-up limit.

    Uses a separate counter from check_and_increment — exhausting one does not
    affect the other. Pass enabled=True/False in tests to skip the env flag.
    """
    if enabled is None:
        enabled = settings.rate_limit_enabled
    if not enabled:
        return True

    ip_hash = _hash_ip_followup(ip)
    today = _today_utc()

    row = session.get(RateLimit, (ip_hash, today))
    if row is None:
        session.add(RateLimit(ip_hash=ip_hash, date=today, count=1))
        session.commit()
        return True

    if row.count >= FOLLOWUP_DAILY_LIMIT:
        return False

    row.count += 1
    session.commit()
    return True
