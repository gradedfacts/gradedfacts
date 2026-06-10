"""repair duplicate active judgments

Revision ID: 0002_repair_duplicate_active
Revises: 0001_add_judgment_id
Create Date: 2026-06-10

For each claim_id that has more than one active judgment, keep only the judgment
with the latest created_at as active and set is_active=False on all others.
Logs and prints the number of rows deactivated. Dialect-neutral: all datetime
comparisons are done Python-side, same pattern as migration 0001.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0002_repair_duplicate_active"
down_revision = "0001_add_judgment_id"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def _parse_dt(val) -> datetime | None:
    """Parse a datetime that may arrive as a Python datetime or a SQLite ISO string."""
    if isinstance(val, datetime):
        return val.replace(tzinfo=None) if val.tzinfo else val
    if isinstance(val, str):
        val = val.replace("+00:00", "").replace("Z", "")
        for fmt in (
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
        ):
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                continue
    return None


def _repair_duplicate_active_judgments(connection) -> tuple[int, int]:
    """Deactivate extra active judgments, keeping only the newest per claim.

    Returns (claims_affected, rows_deactivated).
    """
    rows = connection.execute(
        sa.text(
            "SELECT id, claim_id, created_at FROM judgments WHERE is_active = true"
        )
    ).fetchall()

    # Group active judgments by claim_id
    by_claim: dict[str, list[tuple[str, datetime]]] = defaultdict(list)
    for j_id, j_claim_id, j_created_at_raw in rows:
        j_dt = _parse_dt(j_created_at_raw)
        if j_dt is not None and j_claim_id:
            by_claim[j_claim_id].append((j_id, j_dt))

    to_deactivate: list[str] = []
    for claim_id, entries in by_claim.items():
        if len(entries) <= 1:
            continue
        # Sort descending by created_at; keep the first (newest), deactivate the rest
        entries.sort(key=lambda x: x[1], reverse=True)
        for j_id, _ in entries[1:]:
            to_deactivate.append(j_id)

    if to_deactivate:
        connection.execute(
            sa.text("UPDATE judgments SET is_active = false WHERE id = :jid"),
            [{"jid": jid} for jid in to_deactivate],
        )

    claims_affected = len([c for c, e in by_claim.items() if len(e) > 1])
    return claims_affected, len(to_deactivate)


def upgrade() -> None:
    connection = op.get_bind()

    inspector = sa.inspect(connection)
    if "judgments" not in inspector.get_table_names():
        logger.info("[migration 0002] judgments table not found — skipping (fresh database).")
        print("[migration 0002] judgments table not found — skipping.")
        return

    claims_affected, rows_deactivated = _repair_duplicate_active_judgments(connection)
    msg = (
        f"[migration 0002] Repair complete: {rows_deactivated} duplicate active judgment(s) "
        f"deactivated across {claims_affected} claim(s)."
    )
    logger.info(msg)
    print(msg)


def downgrade() -> None:
    # Repair is not reversible (we cannot know which rows were active before the repair).
    pass
