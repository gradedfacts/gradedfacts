from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.analysis.rating import EpistemicRating, SourceTier


class ClaimCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    submitter_token: str | None = None


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    text: str
    submitted_at: datetime


class JudgmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rating: EpistemicRating
    rationale: str
    analyst: str
    analyst_secondary: str | None = None
    consensus_rating: EpistemicRating | None = None
    models_agree: bool | None = None
    symmetry_report: str | None
    created_at: datetime
    is_active: bool


class ClaimDetailOut(BaseModel):
    id: str
    text: str
    submitted_at: datetime
    active_judgment: JudgmentOut | None


class RevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    prior_judgment_id: str
    new_judgment_id: str
    trigger_evidence: str
    created_at: datetime


class JudgmentHistoryOut(JudgmentOut):
    superseded_by: RevisionOut | None = None


class ClaimHistoryOut(BaseModel):
    id: str
    text: str
    submitted_at: datetime
    judgments: list[JudgmentHistoryOut]


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    url: str
    tier: SourceTier
    is_independent: bool
    affiliation_note: str | None
    relevance_score: float
    excerpt: str | None
    fetched_at: datetime
