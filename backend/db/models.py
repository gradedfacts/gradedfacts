from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Enum as SAEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from backend.analysis.rating import EpistemicRating, SourceTier


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(default=_now)
    # Anonymized submitter token (e.g. hashed session ID) — never stores PII
    submitter_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Political leaning of the claim as assessed: "left", "right", or "none"
    political_leaning: Mapped[str | None] = mapped_column(String(10), nullable=True)

    sources: Mapped[list[EvaluatedSource]] = relationship(back_populates="claim")
    judgments: Mapped[list[Judgment]] = relationship(
        back_populates="claim", order_by="Judgment.created_at"
    )


class EvaluatedSource(Base):
    __tablename__ = "evaluated_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[SourceTier] = mapped_column(SAEnum(SourceTier), nullable=False)
    is_independent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Three-state display label: "independent" | "neutral" | "not_independent"
    # Null for rows written before this column was added (pre-migration rows fall back
    # to deriving the label from the boolean at read time).
    independence_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Populated when is_independent is False
    affiliation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 0.0–1.0: how directly this source addresses the specific claim
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Snapshot of full text at fetch time — ensures past judgments remain reproducible
    full_text_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Required when anonymous is True; no anonymous source accepted without justification
    anonymity_justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(default=_now)

    claim: Mapped[Claim] = relationship(back_populates="sources")


class Judgment(Base):
    __tablename__ = "judgments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), nullable=False)
    rating: Mapped[EpistemicRating] = mapped_column(SAEnum(EpistemicRating), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON-encoded SymmetryReport; nullable until the symmetry check completes
    symmetry_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Human analyst ID or Claude model string, e.g. "claude-sonnet-4-6"
    analyst: Mapped[str] = mapped_column(String(128), nullable=False)
    # Secondary analyst model string (e.g. "mistral-large-latest"); null = single-engine run
    analyst_secondary: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Resolved consensus rating; null = single-engine run (no cross-validation performed)
    consensus_rating: Mapped[EpistemicRating | None] = mapped_column(
        SAEnum(EpistemicRating), nullable=True
    )
    # True when primary and secondary analysts agreed; null = no secondary analyst
    models_agree: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    # True for the current active judgment; False once superseded by a Revision
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Political framing of the claim: "left", "right", or "none". Solely for symmetry
    # measurement; never affects the rating. Null until the engine populates it.
    political_leaning: Mapped[str | None] = mapped_column(String(10), nullable=True)

    claim: Mapped[Claim] = relationship(back_populates="judgments")
    # One-to-one: a judgment is superseded by at most one revision
    revision: Mapped[Revision | None] = relationship(
        back_populates="prior_judgment",
        foreign_keys="Revision.prior_judgment_id",
        uselist=False,
    )


class Revision(Base):
    __tablename__ = "revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), nullable=False)
    prior_judgment_id: Mapped[str] = mapped_column(ForeignKey("judgments.id"), nullable=False)
    new_judgment_id: Mapped[str] = mapped_column(ForeignKey("judgments.id"), nullable=False)
    # Required: what new evidence or correction triggered this revision
    trigger_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    prior_judgment: Mapped[Judgment] = relationship(
        back_populates="revision", foreign_keys=[prior_judgment_id]
    )
    new_judgment: Mapped[Judgment] = relationship(foreign_keys=[new_judgment_id])


class RateLimit(Base):
    __tablename__ = "rate_limits"

    # SHA-256 of the client IP — raw IP is never stored
    ip_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    # ISO date string "YYYY-MM-DD" in UTC — resets at midnight UTC
    date: Mapped[str] = mapped_column(String(10), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
