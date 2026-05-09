import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.config import settings
from backend.db.models import RateLimit

DAILY_LIMIT = 3


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()


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
