import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend import schemas
from backend.analysis.engine import analyze_claim
from backend.db.models import Base, Claim, Judgment
from backend.db.session import engine, get_session

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="TransparencyPuzzle API", version="0.1.0", lifespan=lifespan)


@app.post("/claims", response_model=schemas.ClaimOut, status_code=201)
def create_claim(body: schemas.ClaimCreate, session: Session = Depends(get_session)):
    claim = Claim(text=body.text, submitter_token=body.submitter_token)
    session.add(claim)
    session.commit()
    session.refresh(claim)
    return claim


@app.get("/claims/{claim_id}", response_model=schemas.ClaimDetailOut)
def get_claim(claim_id: str, session: Session = Depends(get_session)):
    claim = session.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    active_judgment = session.execute(
        select(Judgment)
        .where(Judgment.claim_id == claim_id, Judgment.is_active.is_(True))
        .order_by(Judgment.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    return schemas.ClaimDetailOut(
        id=claim.id,
        text=claim.text,
        submitted_at=claim.submitted_at,
        active_judgment=schemas.JudgmentOut.model_validate(active_judgment) if active_judgment else None,
    )


@app.get("/claims/{claim_id}/history", response_model=schemas.ClaimHistoryOut)
def get_claim_history(claim_id: str, session: Session = Depends(get_session)):
    claim = session.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    rows = session.execute(
        select(Judgment)
        .where(Judgment.claim_id == claim_id)
        .options(joinedload(Judgment.revision))
        .order_by(Judgment.created_at)
    ).scalars().unique().all()

    judgments = [
        schemas.JudgmentHistoryOut(
            id=j.id,
            rating=j.rating,
            rationale=j.rationale,
            analyst=j.analyst,
            symmetry_report=j.symmetry_report,
            created_at=j.created_at,
            is_active=j.is_active,
            superseded_by=schemas.RevisionOut.model_validate(j.revision) if j.revision else None,
        )
        for j in rows
    ]

    return schemas.ClaimHistoryOut(
        id=claim.id,
        text=claim.text,
        submitted_at=claim.submitted_at,
        judgments=judgments,
    )


@app.post("/claims/{claim_id}/analyze", response_model=schemas.JudgmentOut, status_code=201)
def analyze_claim_endpoint(claim_id: str, session: Session = Depends(get_session)):
    claim = session.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    existing = session.execute(
        select(Judgment)
        .where(Judgment.claim_id == claim_id, Judgment.is_active.is_(True))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Claim already has an active judgment")

    try:
        return analyze_claim(claim_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error("Analysis pipeline failed for claim %s: %s", claim_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Analysis pipeline failed")
