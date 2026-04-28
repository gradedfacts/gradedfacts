import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend import schemas
from backend.analysis.engine import analyze_claim
from backend.db.models import Base, Claim, EvaluatedSource, Judgment
from backend.db.rate_limit import check_and_increment
from backend.db.session import SessionLocal, engine, get_session

logger = logging.getLogger(__name__)

# ── Template helpers ──────────────────────────────────────────────────────────

_ROOT = Path(__file__).parent.parent


def _domain(url: str) -> str:
    try:
        host = urlparse(url).hostname or url
        return host.removeprefix("www.")
    except Exception:
        return url


def _rating_label(rating) -> str:
    key = getattr(rating, "value", str(rating))
    return {
        "verified":    "Claim is verified",
        "speculative": "Claim is speculative",
        "debunked":    "Claim is debunked",
        "missing":     "Insufficient evidence",
    }.get(key, key)


templates = Jinja2Templates(directory=str(_ROOT / "frontend" / "templates"))
templates.env.filters["domain"] = _domain
templates.env.filters["rating_label"] = _rating_label

# ── Background analysis state ─────────────────────────────────────────────────

_LOADING_MESSAGES = [
    "Searching sources…",
    "Evaluating independence…",
    "Deriving rating…",
]

_TIER_ORDER = {"primary": 0, "secondary": 1, "tertiary": 2}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

# claim_id → (http_status_code, human_message)
_analysis_errors: dict[str, tuple[int, str]] = {}


def _sort_sources(sources: list) -> list:
    return sorted(sources, key=lambda s: (_TIER_ORDER.get(str(s.tier), 9), -s.relevance_score))


def _run_analysis(claim_id: str) -> None:
    """Background task: runs analyze_claim in its own DB session."""
    with SessionLocal() as session:
        try:
            analyze_claim(claim_id, session)
        except RuntimeError as exc:
            _analysis_errors[claim_id] = (503, str(exc))
        except Exception as exc:
            logger.error("Background analysis failed for %s: %s", claim_id, exc, exc_info=True)
            _analysis_errors[claim_id] = (500, "Analysis pipeline failed.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="GradedFacts API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.mount("/static", StaticFiles(directory=str(_ROOT / "frontend")), name="static")


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


@app.get("/claims/{claim_id}/sources", response_model=list[schemas.SourceOut])
def get_claim_sources(claim_id: str, session: Session = Depends(get_session)):
    if not session.get(Claim, claim_id):
        raise HTTPException(status_code=404, detail="Claim not found")
    rows = session.execute(
        select(EvaluatedSource)
        .where(EvaluatedSource.claim_id == claim_id)
        .order_by(EvaluatedSource.relevance_score.desc())
    ).scalars().all()
    return rows


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


# ── HTML endpoints (HTMX + Jinja2) ───────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/ui/analyze", response_class=HTMLResponse)
def ui_analyze(
    request: Request,
    background_tasks: BackgroundTasks,
    text: str = Form(""),
    session: Session = Depends(get_session),
):
    if not check_and_increment(_client_ip(request), session):
        return templates.TemplateResponse(
            request,
            "partials/error.html",
            {"code": 429, "message": "You've used your 5 free analyses today. Pro plan coming soon."},
        )
    text = text.strip()
    if len(text) < 10:
        return templates.TemplateResponse(
            request,
            "partials/error.html",
            {"code": 400, "message": "Please enter at least 10 characters."},
        )
    claim = Claim(text=text[:2000])
    session.add(claim)
    session.commit()
    session.refresh(claim)
    background_tasks.add_task(_run_analysis, claim.id)
    return templates.TemplateResponse(
        request,
        "partials/analyzing.html",
        {"claim_id": claim.id, "loading_message": _LOADING_MESSAGES[0]},
    )


@app.get("/ui/claims/{claim_id}/poll", response_class=HTMLResponse)
def ui_poll(claim_id: str, request: Request, session: Session = Depends(get_session)):
    if claim_id in _analysis_errors:
        code, message = _analysis_errors.pop(claim_id)
        return templates.TemplateResponse(
            request,
            "partials/error.html",
            {"code": code, "message": message},
        )

    claim = session.get(Claim, claim_id)
    if not claim:
        return templates.TemplateResponse(
            request,
            "partials/error.html",
            {"code": 404, "message": "Claim not found."},
        )

    active_judgment = session.execute(
        select(Judgment)
        .where(Judgment.claim_id == claim_id, Judgment.is_active.is_(True))
        .order_by(Judgment.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if not active_judgment:
        # Still running — return the loading partial so polling continues
        msg_idx = (int(time.time()) % 18) // 6
        return templates.TemplateResponse(
            request,
            "partials/analyzing.html",
            {
                "claim_id": claim_id,
                "loading_message": _LOADING_MESSAGES[msg_idx],
            },
        )

    sources = session.execute(
        select(EvaluatedSource).where(EvaluatedSource.claim_id == claim_id)
    ).scalars().all()

    judgments = session.execute(
        select(Judgment)
        .where(Judgment.claim_id == claim_id)
        .options(joinedload(Judgment.revision))
        .order_by(Judgment.created_at.desc())
    ).scalars().unique().all()

    return templates.TemplateResponse(
        request,
        "partials/result.html",
        {
            "claim_text": claim.text,
            "judgment": active_judgment,
            "sources": _sort_sources(sources),
            "judgments": list(judgments),
        },
    )
