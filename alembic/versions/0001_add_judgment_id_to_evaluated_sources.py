"""add judgment_id to evaluated_sources

Revision ID: 0001_add_judgment_id
Revises:
Create Date: 2026-06-10

Adds judgment_id (nullable FK → judgments.id) to evaluated_sources and backfills
existing rows by matching each source to the judgment created in the same analysis
run (nearest-in-time judgment for the same claim_id within a 30-second tolerance
window). Append-only: only the new column is mutated; no rows are deleted.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta

import sqlalchemy as sa
from alembic import op

revision = "0001_add_judgment_id"
down_revision = None
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)

_TOLERANCE_SECONDS = 30


def _parse_dt(val) -> datetime | None:
    """Parse a datetime value that may arrive as a Python datetime or a SQLite string."""
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


def upgrade() -> None:
    connection = op.get_bind()

    # Check whether the table exists (it may not on a fresh database that hasn't
    # been initialised by Base.metadata.create_all() yet).
    inspector = sa.inspect(connection)
    if "evaluated_sources" not in inspector.get_table_names():
        logger.info("Backfill skipped: evaluated_sources table does not exist yet (fresh database).")
        print("[migration 0001] evaluated_sources table not found — skipping (create_all will add the column).")
        return

    # Skip if the column already exists (idempotent).
    existing_cols = {c["name"] for c in inspector.get_columns("evaluated_sources")}
    if "judgment_id" in existing_cols:
        logger.info("Column judgment_id already exists — skipping add_column.")
        print("[migration 0001] judgment_id column already present — skipping.")
        return

    # ── 1. Add column ─────────────────────────────────────────────────────────
    # SQLite batch_alter_table requires named constraints; use a plain column here
    # and let SQLAlchemy's ORM enforce the FK relationship at the application level.
    with op.batch_alter_table("evaluated_sources") as batch_op:
        batch_op.add_column(
            sa.Column("judgment_id", sa.String(36), nullable=True)
        )

    # ── 2. Backfill ───────────────────────────────────────────────────────────
    connection = op.get_bind()

    source_rows = connection.execute(
        sa.text(
            "SELECT id, claim_id, fetched_at FROM evaluated_sources "
            "WHERE judgment_id IS NULL ORDER BY claim_id, fetched_at"
        )
    ).fetchall()

    if not source_rows:
        logger.info("Backfill: no evaluated_sources rows need backfilling.")
        print("[migration 0001] Backfill: 0 rows to process.")
        return

    judgment_rows = connection.execute(
        sa.text(
            "SELECT id, claim_id, created_at FROM judgments ORDER BY claim_id, created_at"
        )
    ).fetchall()

    # Group judgments by claim_id → sorted list of (id, datetime)
    judgments_by_claim: dict[str, list[tuple[str, datetime]]] = defaultdict(list)
    for j_id, j_claim_id, j_created_at_raw in judgment_rows:
        j_dt = _parse_dt(j_created_at_raw)
        if j_dt is not None and j_claim_id:
            judgments_by_claim[j_claim_id].append((j_id, j_dt))

    # Ensure each claim's list is sorted by created_at ascending
    for cid in judgments_by_claim:
        judgments_by_claim[cid].sort(key=lambda x: x[1])

    tolerance = timedelta(seconds=_TOLERANCE_SECONDS)
    backfilled = 0
    left_null = 0
    updates: list[dict] = []

    for s_id, s_claim_id, s_fetched_at_raw in source_rows:
        if not s_claim_id or s_claim_id not in judgments_by_claim:
            left_null += 1
            continue

        s_dt = _parse_dt(s_fetched_at_raw)
        if s_dt is None:
            left_null += 1
            continue

        claim_judgments = judgments_by_claim[s_claim_id]

        # Primary strategy: latest judgment whose created_at ≤ source.fetched_at + tolerance.
        # This covers both normal order (judgment slightly after source) and the edge case
        # where the source timestamp is fractionally later than the judgment timestamp.
        upper_bound = s_dt + tolerance
        candidates = [(j_id, j_dt) for j_id, j_dt in claim_judgments if j_dt <= upper_bound]

        if candidates:
            best_id = max(candidates, key=lambda x: x[1])[0]
        else:
            # All judgments were created more than tolerance after the source.
            # Fallback: assign to the nearest judgment by absolute time difference.
            best_id = min(
                claim_judgments,
                key=lambda x: abs((x[1] - s_dt).total_seconds()),
            )[0]

        updates.append({"jid": best_id, "sid": s_id})
        backfilled += 1

    if updates:
        connection.execute(
            sa.text("UPDATE evaluated_sources SET judgment_id = :jid WHERE id = :sid"),
            updates,
        )

    msg = f"[migration 0001] Backfill complete: {backfilled} rows assigned judgment_id; {left_null} rows left NULL."
    logger.info(msg)
    print(msg)


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if "evaluated_sources" not in inspector.get_table_names():
        return
    existing_cols = {c["name"] for c in inspector.get_columns("evaluated_sources")}
    if "judgment_id" not in existing_cols:
        return
    with op.batch_alter_table("evaluated_sources") as batch_op:
        batch_op.drop_column("judgment_id")
