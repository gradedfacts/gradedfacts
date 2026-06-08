import html
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, inspect, text
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend import schemas
from backend.analysis.consensus import analyze_claim_with_consensus
from backend.analysis.engine import analyze_claim, _get_client, independence_bool, independence_label
from backend.sources.evaluator import extract_domain
from backend.sources.registries import lookup_source_all_registries
from backend.db.models import Base, Claim, EvaluatedSource, Judgment
from backend.db.rate_limit import check_and_increment, check_followup_rate_limit
from backend.db.session import SessionLocal, engine, get_session
from backend.db.storage import find_canonical_claim, merge_into_canonical

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


_BADGE_RE = re.compile(r'\[([A-Za-z]+): ([A-Z]+)\]')

# Translated display labels for rating words inside [Model: RATING] badges.
# Loaded from locale JSON files (rating.* keys, first character capitalised).
# CSS classes always use the English lowercase value; only the visible label is translated.
def _load_rating_translations() -> dict[str, dict[str, str]]:
    import json as _json
    locales_dir = _ROOT / "frontend" / "locales"
    translations: dict[str, dict[str, str]] = {}
    for lang_dir in sorted(locales_dir.iterdir()):
        lang = lang_dir.name
        if lang == "en":
            continue
        translation_file = lang_dir / "translation.json"
        if not translation_file.exists():
            continue
        try:
            data = _json.loads(translation_file.read_text(encoding="utf-8"))
            rating = data.get("rating", {})
            if rating:
                translations[lang] = {k: v[0].upper() + v[1:] for k, v in rating.items() if v}
        except Exception:
            logger.warning("Failed to load rating translations for locale %s", lang)
    return translations

_RATING_TRANSLATIONS: dict[str, dict[str, str]] = _load_rating_translations()


def _render_model_badges(text: str, lang: str = "en") -> str:
    """Replace [Model: RATING] tags with styled rating-badge spans. Returns safe HTML.

    Rating words are translated to `lang` when a translation is available;
    CSS classes always use the English lowercase value so styling is unaffected.
    """
    escaped = html.escape(text)
    translations = _RATING_TRANSLATIONS.get(lang, {})

    def _badge(m: re.Match) -> str:
        model = m.group(1)
        rating_upper = m.group(2)
        rating_lower = rating_upper.lower()
        label = translations.get(rating_lower, rating_upper)
        return (
            f'<span class="rating-badge {rating_lower}" style="vertical-align:middle;margin-right:0.35em">'
            f'<span class="rating-dot"></span>'
            f'{model}: {label}'
            f'</span>'
        )

    result = _BADGE_RE.sub(_badge, escaped)
    result = result.replace('\n\n', '<br><br>').replace('\n', '<br>')
    return result


templates = Jinja2Templates(directory=str(_ROOT / "frontend" / "templates"))
templates.env.filters["domain"] = _domain
templates.env.filters["rating_label"] = _rating_label
templates.env.filters["render_model_badges"] = _render_model_badges

# ── Background analysis state ─────────────────────────────────────────────────

_LOADING_MESSAGES = [
    {"key": "analyzing.searching",  "text": "Searching sources…"},
    {"key": "analyzing.evaluating", "text": "Evaluating independence…"},
    {"key": "analyzing.deriving",   "text": "Deriving rating…"},
]

_TIER_ORDER = {"primary": 0, "secondary": 1, "tertiary": 2}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

# claim_id → (http_status_code, human_message)
_analysis_errors: dict[str, tuple[int, str]] = {}

# temp_claim_id → canonical_claim_id, set after dedup completes so ui_poll can resolve
_claim_redirects: dict[str, str] = {}


_SOURCE_PASSTHROUGH = (
    "id", "claim_id", "url", "relevance_score", "excerpt",
    "full_text_snapshot", "anonymous", "anonymity_justification", "fetched_at",
)


def _apply_live_registry(source) -> object:
    """Return a render-time view of source with tier/independence from the current registry.

    The DB is append-only, so rows written before a registry update may carry stale
    tier or independence values.  When the domain is found in registry.json, override
    those fields so the UI always reflects the current curated classification.
    Returns the original object unchanged when the domain is not in the registry.
    """
    import types
    from backend.analysis.rating import SourceTier

    entry = lookup_source_all_registries(source.url)
    if entry is None:
        return source

    live_indep = independence_bool(entry["is_independent"])

    ns = types.SimpleNamespace()
    for attr in _SOURCE_PASSTHROUGH:
        setattr(ns, attr, getattr(source, attr, None))
    ns.tier = SourceTier(entry["tier"])
    ns.is_independent = live_indep
    ns.independence_label = independence_label(entry["is_independent"])
    ns.affiliation_note = entry.get("affiliation_note") if not live_indep else None
    # A registered domain is by definition verified.
    ns.is_unverified = False
    return ns


def _sort_sources(sources: list) -> list:
    return sorted(sources, key=lambda s: (_TIER_ORDER.get(str(s.tier), 9), -s.relevance_score))


def _group_sources_by_domain(sources: list) -> list[dict]:
    """Group a sorted source list by root domain, preserving sort order."""
    seen: dict[str, list] = {}
    order: list[str] = []
    for source in sources:
        dom = extract_domain(source.url) or source.url
        if dom not in seen:
            seen[dom] = []
            order.append(dom)
        seen[dom].append(source)
    return [
        {"domain": dom, "sources": seen[dom], "is_multi": len(seen[dom]) > 1}
        for dom in order
    ]


def _deduplicate_after_analysis(claim_id: str, session) -> str | None:
    """After a completed analysis, merge into the canonical Claim if an identical one exists.

    Returns the canonical claim_id if a duplicate was found (and temp claim deleted), else None.
    The full analysis always runs first; this is storage-level dedup only.
    """
    claim = session.get(Claim, claim_id)
    if claim is None:
        return None
    canonical = find_canonical_claim(session, claim.text, exclude_id=claim_id)
    if canonical is None:
        return None
    merge_into_canonical(session, temp_id=claim_id, canonical_id=canonical.id)
    logger.info("Dedup: merged temp claim %s → canonical %s", claim_id, canonical.id)
    return canonical.id


def _run_analysis(claim_id: str, user_language: str | None = None) -> None:
    """Background task: runs analyze_claim then deduplicates at the storage level."""
    with SessionLocal() as session:
        try:
            analyze_claim(claim_id, session, user_language=user_language)
        except RuntimeError as exc:
            _analysis_errors[claim_id] = (503, str(exc))
            return
        except Exception as exc:
            logger.error("Background analysis failed for %s: %s", claim_id, exc, exc_info=True)
            _analysis_errors[claim_id] = (500, "Analysis pipeline failed.")
            return
        canonical_id = _deduplicate_after_analysis(claim_id, session)
        if canonical_id:
            _claim_redirects[claim_id] = canonical_id


def _run_consensus_analysis(claim_id: str, user_language: str | None = None) -> None:
    """Background task: runs analyze_claim_with_consensus then deduplicates at the storage level."""
    with SessionLocal() as session:
        try:
            analyze_claim_with_consensus(claim_id, session, user_language=user_language)
        except RuntimeError as exc:
            _analysis_errors[claim_id] = (503, str(exc))
            return
        except Exception as exc:
            logger.error("Background consensus analysis failed for %s: %s", claim_id, exc, exc_info=True)
            _analysis_errors[claim_id] = (500, "Analysis pipeline failed.")
            return
        canonical_id = _deduplicate_after_analysis(claim_id, session)
        if canonical_id:
            _claim_redirects[claim_id] = canonical_id


_JUDGMENT_ADDCOLS = [
    ("analyst_secondary", "VARCHAR(128)"),
    ("consensus_rating",  "VARCHAR(11)"),
    ("models_agree",      "BOOLEAN"),
    ("model_claude",      "VARCHAR(64)"),
    ("model_mistral",     "VARCHAR(64)"),
    ("registry_version",  "VARCHAR(40)"),
    ("prompt_version",    "VARCHAR(16)"),
]

_CLAIM_ADDCOLS = [
    ("political_leaning", "VARCHAR(10)"),
]

_EVALUATED_SOURCE_ADDCOLS = [
    ("independence_label", "VARCHAR(20)"),
]


def _migrate_evaluated_sources() -> None:
    """Add columns introduced after initial schema creation to the evaluated_sources table."""
    with engine.connect() as conn:
        existing = {col["name"] for col in inspect(engine).get_columns("evaluated_sources")}
        for col, col_type in _EVALUATED_SOURCE_ADDCOLS:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE evaluated_sources ADD COLUMN {col} {col_type}"))
                logger.info("DB migration: added evaluated_sources.%s", col)
        conn.commit()


def _migrate_judgments() -> None:
    """Add columns introduced by the ConsensusEngine to pre-existing databases."""
    with engine.connect() as conn:
        existing = {col["name"] for col in inspect(engine).get_columns("judgments")}
        for col, col_type in _JUDGMENT_ADDCOLS:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE judgments ADD COLUMN {col} {col_type}"))
                logger.info("DB migration: added judgments.%s", col)
        conn.commit()


def _migrate_claims() -> None:
    """Add columns introduced after initial schema creation to the claims table."""
    with engine.connect() as conn:
        existing = {col["name"] for col in inspect(engine).get_columns("claims")}
        for col, col_type in _CLAIM_ADDCOLS:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE claims ADD COLUMN {col} {col_type}"))
                logger.info("DB migration: added claims.%s", col)
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_judgments()
    _migrate_claims()
    _migrate_evaluated_sources()
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
def home(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "index.html", {
        "symmetry_counts": _get_symmetry_counts(session),
    })


@app.get("/methodology", response_class=HTMLResponse)
def methodology(request: Request):
    return templates.TemplateResponse(request, "methodology.html")


@app.get("/about", response_class=HTMLResponse)
def about(request: Request):
    return templates.TemplateResponse(request, "about.html")


def _get_symmetry_counts(session: Session) -> dict[str, int]:
    """Return left/right/none judgment counts for the last 30 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    rows = session.execute(
        select(Judgment.political_leaning, func.count(Judgment.id))
        .where(Judgment.created_at >= cutoff)
        .group_by(Judgment.political_leaning)
    ).all()
    counts: dict[str, int] = {"left": 0, "right": 0, "none": 0}
    for leaning, count in rows:
        key = leaning if leaning in counts else "none"
        counts[key] += count
    return counts


@app.get("/ui/symmetry-stats")
def ui_symmetry_stats(session: Session = Depends(get_session)):
    return JSONResponse(_get_symmetry_counts(session))


@app.post("/ui/analyze", response_class=HTMLResponse)
def ui_analyze(
    request: Request,
    background_tasks: BackgroundTasks,
    text: str = Form(""),
    lang: str = Form("en"),
    session: Session = Depends(get_session),
):
    if not check_and_increment(_client_ip(request), session):
        return templates.TemplateResponse(
            request,
            "partials/error.html",
            {"code": 429, "message": "You've used your 3 free analyses today. Pro plan coming soon."},
        )
    text = text.strip()
    if len(text) < 10:
        return templates.TemplateResponse(
            request,
            "partials/error.html",
            {"code": 400, "message": "Please enter at least 10 characters."},
        )
    user_language = lang.strip()[:10] or None
    logger.debug("analyze endpoint: lang=%r  user_language=%r", lang, user_language)
    claim = Claim(text=text[:2000])
    session.add(claim)
    session.commit()
    session.refresh(claim)
    background_tasks.add_task(_run_analysis, claim.id, user_language)
    return templates.TemplateResponse(
        request,
        "partials/analyzing.html",
        {
            "claim_id": claim.id,
            "lang": lang.strip()[:10] or "en",
            "loading_message": _LOADING_MESSAGES[0]["text"],
            "loading_key": _LOADING_MESSAGES[0]["key"],
        },
    )


@app.post("/ui/analyze/consensus", response_class=HTMLResponse)
def ui_analyze_consensus(
    request: Request,
    background_tasks: BackgroundTasks,
    text: str = Form(""),
    lang: str = Form("en"),
    session: Session = Depends(get_session),
):
    logger.debug("consensus endpoint received lang=%r", lang)
    if not check_and_increment(_client_ip(request), session):
        return templates.TemplateResponse(
            request,
            "partials/error.html",
            {"code": 429, "message": "You've used your 3 free analyses today. Pro plan coming soon."},
        )
    text = text.strip()
    if len(text) < 10:
        return templates.TemplateResponse(
            request,
            "partials/error.html",
            {"code": 400, "message": "Please enter at least 10 characters."},
        )
    user_language = lang.strip()[:10] or None
    logger.debug("consensus endpoint: lang=%r  user_language=%r", lang, user_language)
    claim = Claim(text=text[:2000])
    session.add(claim)
    session.commit()
    session.refresh(claim)
    background_tasks.add_task(_run_consensus_analysis, claim.id, user_language)
    return templates.TemplateResponse(
        request,
        "partials/analyzing.html",
        {
            "claim_id": claim.id,
            "lang": lang.strip()[:10] or "en",
            "loading_message": _LOADING_MESSAGES[0]["text"],
            "loading_key": _LOADING_MESSAGES[0]["key"],
        },
    )


@app.get("/ui/claims/{claim_id}/poll", response_class=HTMLResponse)
def ui_poll(
    claim_id: str,
    request: Request,
    lang: str = Query("en"),
    session: Session = Depends(get_session),
):
    # Resolve dedup redirect: if this temp claim was merged into a canonical one,
    # use the canonical claim_id for all subsequent lookups.
    resolved_id = _claim_redirects.get(claim_id, claim_id)

    if claim_id in _analysis_errors:
        code, message = _analysis_errors.pop(claim_id)
        return templates.TemplateResponse(
            request,
            "partials/error.html",
            {"code": code, "message": message},
        )

    claim = session.get(Claim, resolved_id)
    if not claim:
        return templates.TemplateResponse(
            request,
            "partials/error.html",
            {"code": 404, "message": "Claim not found."},
        )

    active_judgment = session.execute(
        select(Judgment)
        .where(Judgment.claim_id == resolved_id, Judgment.is_active.is_(True))
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
                "loading_message": _LOADING_MESSAGES[msg_idx]["text"],
                "loading_key": _LOADING_MESSAGES[msg_idx]["key"],
                "lang": lang,
            },
        )

    sources = session.execute(
        select(EvaluatedSource).where(EvaluatedSource.claim_id == resolved_id)
    ).scalars().all()

    judgments = session.execute(
        select(Judgment)
        .where(Judgment.claim_id == resolved_id)
        .options(joinedload(Judgment.revision))
        .order_by(Judgment.created_at.desc())
    ).scalars().unique().all()

    live_sources = [_apply_live_registry(s) for s in sources]
    sorted_sources = _sort_sources(live_sources)
    return templates.TemplateResponse(
        request,
        "partials/result.html",
        {
            "claim_text": claim.text,
            "judgment": active_judgment,
            "sources": sorted_sources,
            "grouped_sources": _group_sources_by_domain(sorted_sources),
            "judgments": list(judgments),
            "lang": lang,
            "symmetry_counts": _get_symmetry_counts(session),
        },
    )


_FOLLOWUP_SYSTEM = (
    "You are a fact-checking assistant for GradedFacts, a politically independent platform. "
    "Answer the user's follow-up question about a fact-checked claim clearly and concisely. "
    "Stay grounded in the provided rating and rationale. Do not exceed three short paragraphs."
)


@app.post("/ui/followup", response_class=HTMLResponse)
def ui_followup(
    request: Request,
    claim_id: str = Form(""),
    followup_question: str = Form(""),
    lang: str = Form("en"),
    session: Session = Depends(get_session),
):
    if not check_followup_rate_limit(_client_ip(request), session):
        return HTMLResponse(
            '<p class="followup-error">You\'ve used your 1 free follow-up today.</p>'
        )

    followup_question = followup_question.strip()
    if len(followup_question) < 5:
        return HTMLResponse('<p class="followup-error">Please enter a question (at least 5 characters).</p>')

    claim = session.get(Claim, claim_id)
    if not claim:
        return HTMLResponse('<p class="followup-error">Claim not found.</p>')

    active_judgment = session.execute(
        select(Judgment)
        .where(Judgment.claim_id == claim_id, Judgment.is_active.is_(True))
        .order_by(Judgment.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not active_judgment:
        return HTMLResponse('<p class="followup-error">No judgment found for this claim.</p>')

    try:
        client = _get_client()
        sources = session.execute(
            select(EvaluatedSource).where(EvaluatedSource.claim_id == claim_id)
        ).scalars().all()

        sources_block = ""
        if sources:
            lines = ["Sources used in this analysis:"]
            for i, src in enumerate(sources, 1):
                independence = (
                    src.independence_label
                    if src.independence_label
                    else ("independent" if src.is_independent else "not_independent")
                )
                lines.append(
                    f"{i}. URL: {src.url}\n"
                    f"   Tier: {src.tier.value}\n"
                    f"   Independence: {independence}\n"
                    f"   Relevance score: {src.relevance_score:.2f}\n"
                    f"   Excerpt: {src.excerpt or '(none)'}"
                )
            sources_block = "\n\n" + "\n\n".join(lines)

        user_msg = (
            f"Claim: {claim.text}\n\n"
            f"Fact-check rating: {active_judgment.rating.value.upper()}\n\n"
            f"Rationale: {active_judgment.rationale}"
            f"{sources_block}\n\n"
            f"Follow-up question: {followup_question}"
        )
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=_FOLLOWUP_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        answer = response.content[0].text
        answer_html = html.escape(answer).replace("\n\n", "<br><br>").replace("\n", "<br>")
        return HTMLResponse(f'<p class="followup-answer-text">{answer_html}</p>')
    except Exception as exc:
        logger.error("Follow-up Claude call failed for claim %s: %s", claim_id, exc, exc_info=True)
        return HTMLResponse('<p class="followup-error">Analysis service temporarily unavailable.</p>')
