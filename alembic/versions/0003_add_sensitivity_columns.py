"""add registry-sensitivity columns

Revision ID: 0003_add_sensitivity_columns
Revises: 0002_repair_duplicate_active
Create Date: 2026-06-18

Adds three nullable columns required for offline registry-sensitivity
recomputation.  All columns are nullable with no default — NULL means
"written before this migration; excluded from the sensitivity set."

  evaluated_sources.supports_claim  BOOLEAN   — verifying vs. debunking polarity
  judgments.claude_rating            VARCHAR   — Claude's post-cap per-model rating
  judgments.mistral_rating           VARCHAR   — Mistral's post-cap per-model rating
                                                 (NULL also for single-engine runs)

Append-only: no existing column is modified, no row data is changed.
op.batch_alter_table is used so the same migration runs on both
SQLite (local dev) and PostgreSQL (production).
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0003_add_sensitivity_columns"
down_revision = "0002_repair_duplicate_active"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # ── evaluated_sources.supports_claim ─────────────────────────────────────
    if "evaluated_sources" in inspector.get_table_names():
        existing = {c["name"] for c in inspector.get_columns("evaluated_sources")}
        if "supports_claim" not in existing:
            with op.batch_alter_table("evaluated_sources") as batch_op:
                batch_op.add_column(
                    sa.Column("supports_claim", sa.Boolean(), nullable=True)
                )
            logger.info("[migration 0003] added evaluated_sources.supports_claim")
            print("[migration 0003] added evaluated_sources.supports_claim")
        else:
            logger.info("[migration 0003] evaluated_sources.supports_claim already exists — skipping")
            print("[migration 0003] evaluated_sources.supports_claim already exists — skipping")
    else:
        logger.info("[migration 0003] evaluated_sources table not found — skipping (fresh database)")
        print("[migration 0003] evaluated_sources table not found — skipping")

    # ── judgments.claude_rating / mistral_rating ──────────────────────────────
    if "judgments" in inspector.get_table_names():
        existing = {c["name"] for c in inspector.get_columns("judgments")}
        cols_to_add = []
        if "claude_rating" not in existing:
            cols_to_add.append(("claude_rating", sa.String(11)))
        if "mistral_rating" not in existing:
            cols_to_add.append(("mistral_rating", sa.String(11)))

        if cols_to_add:
            with op.batch_alter_table("judgments") as batch_op:
                for col_name, col_type in cols_to_add:
                    batch_op.add_column(sa.Column(col_name, col_type, nullable=True))
                    logger.info("[migration 0003] added judgments.%s", col_name)
                    print(f"[migration 0003] added judgments.{col_name}")
        else:
            logger.info("[migration 0003] judgments rating columns already exist — skipping")
            print("[migration 0003] judgments rating columns already exist — skipping")
    else:
        logger.info("[migration 0003] judgments table not found — skipping (fresh database)")
        print("[migration 0003] judgments table not found — skipping")


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if "evaluated_sources" in inspector.get_table_names():
        existing = {c["name"] for c in inspector.get_columns("evaluated_sources")}
        if "supports_claim" in existing:
            with op.batch_alter_table("evaluated_sources") as batch_op:
                batch_op.drop_column("supports_claim")
            logger.info("[migration 0003] dropped evaluated_sources.supports_claim")

    if "judgments" in inspector.get_table_names():
        existing = {c["name"] for c in inspector.get_columns("judgments")}
        with op.batch_alter_table("judgments") as batch_op:
            for col in ("claude_rating", "mistral_rating"):
                if col in existing:
                    batch_op.drop_column(col)
                    logger.info("[migration 0003] dropped judgments.%s", col)
