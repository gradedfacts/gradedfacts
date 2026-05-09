import logging

import anthropic

try:
    from langdetect import detect as _ld_detect, DetectorFactory as _LDFactory
    _LDFactory.seed = 0  # make detection deterministic across runs
    _LANGDETECT_AVAILABLE = True
except ImportError:
    _LANGDETECT_AVAILABLE = False

from backend.analysis.rating import EpistemicRating, EvidenceSummary, SourceTier, derive_rating
from backend.config import settings
from backend.db.models import Claim, EvaluatedSource, Judgment
from backend.sources.evaluator import evaluate_source, extract_domain

logger = logging.getLogger(__name__)

# ── Language detection ────────────────────────────────────────────────────────

_LANG_NAMES: dict[str, str] = {
    "af": "Afrikaans", "ar": "Arabic", "bg": "Bulgarian", "ca": "Catalan",
    "cs": "Czech", "cy": "Welsh", "da": "Danish", "de": "German",
    "el": "Greek", "en": "English", "es": "Spanish", "et": "Estonian",
    "fa": "Persian", "fi": "Finnish", "fr": "French", "gl": "Galician",
    "gu": "Gujarati", "he": "Hebrew", "hi": "Hindi", "hr": "Croatian",
    "hu": "Hungarian", "id": "Indonesian", "it": "Italian", "ja": "Japanese",
    "kn": "Kannada", "ko": "Korean", "lt": "Lithuanian", "lv": "Latvian",
    "mk": "Macedonian", "ml": "Malayalam", "mr": "Marathi", "ne": "Nepali",
    "nl": "Dutch", "no": "Norwegian", "pa": "Punjabi", "pl": "Polish",
    "pt": "Portuguese", "ro": "Romanian", "ru": "Russian", "sk": "Slovak",
    "sl": "Slovenian", "so": "Somali", "sq": "Albanian", "sv": "Swedish",
    "sw": "Swahili", "ta": "Tamil", "te": "Telugu", "th": "Thai",
    "tl": "Filipino", "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu",
    "vi": "Vietnamese", "zh-cn": "Chinese", "zh-tw": "Chinese (Traditional)",
    "zh": "Chinese",
}


def _detect_language(claim_text: str) -> str:
    """Detect the natural language of the claim. Falls back to 'English' on any error."""
    if not _LANGDETECT_AVAILABLE:
        return "English"
    try:
        code = _ld_detect(claim_text)
        return _LANG_NAMES.get(code, "English")
    except Exception:
        return "English"


def _build_lang_instruction(lang_name: str) -> str:
    """Return a per-request language instruction string, or '' for English claims."""
    if lang_name == "English":
        return ""
    return (
        f"IMPORTANT: Respond in the same language as the claim. "
        f"The claim is in {lang_name}. "
        f"Write your entire analysis, rationale, and all text in {lang_name}."
    )


# ── Source thresholds ─────────────────────────────────────────────────────────

# Hard cap on sources collected per claim.
MAX_SOURCES = 8

# Sources below this relevance score are stored but excluded from rating derivation.
MIN_RELEVANCE_SCORE = 0.6

# ── Prompt (cached on first use, TTL 5 min) ───────────────────────────────────

_SYSTEM_PROMPT = """\
You are the epistemic analysis engine for GradedFacts, a politically neutral \
fact-checking tool founded in Switzerland. Your only goal is accurate, evidence-based \
judgment — not advocacy for any political side.

EPISTEMIC RATINGS:
  VERIFIED    — factually correct; backed by ≥3 relevant sources including ≥1 primary
  SPECULATIVE — plausible but not conclusively provable with current evidence
  DEBUNKED    — factually false; primary or secondary counter-evidence documented
  MISSING     — insufficient evidence; fewer than 2 sources with relevance ≥0.6 found

SOURCE TIERS:
  primary   — original data, official documents, government records, peer-reviewed studies
  secondary — journalism that cites primary sources with full attribution
  tertiary  — aggregations, opinion, or summaries without independent verification

SOURCE INDEPENDENCE:
  A source is NOT independent if it has documented ties to political parties, PACs,
  governments with a stake in the outcome, or ideologically funded organisations.

  CRITICAL — Official ≠ Independent:
  A government agency, law enforcement body, or official institution is NOT automatically
  independent.  If the institution's leadership has documented political dependency —
  appointed on loyalty criteria, subject to political interference, or operating under
  a government with a direct stake in the outcome — mark is_independent=False and
  populate affiliation_note with the specific concern.  Tier (primary/secondary/tertiary)
  reflects document type; independence reflects editorial and institutional integrity.
  These are separate dimensions.

  Examples of official-but-not-independent sources:
    - FBI press releases while under a director appointed on loyalty criteria
    - DOJ statements from an AG confirmed after pledging personal loyalty
    - State media outlets (RT, CGTN, TRT, MTVA) regardless of their official status
    - Official government statements from authoritarian regimes on claims about themselves

HARD RULES — never violate:
  1. Your own unverified analysis counts as zero sources.
  2. Only sources with relevance_score ≥0.6 count toward rating thresholds.
  3. VERIFIED requires ≥3 relevant sources; DEBUNKED requires ≥2.
  4. Return at most 8 sources total. Prioritise primary and independent sources.
  5. Only tertiary sources → rating is capped at SPECULATIVE, never VERIFIED.
  6. Apply identical scrutiny regardless of political direction (symmetry).
  7. "We don't know" (MISSING) is a valid and important answer.
  8. Future predictions and forecasts — language such as "will", "would", "by [year]",
     "is projected to", or similar — can NEVER be rated DEBUNKED unless the predicted
     event was already supposed to have occurred and demonstrably did not. A claim about
     what will happen is inherently untestable until the deadline passes. When evidence
     is mixed or contested, default to SPECULATIVE regardless of how many current
     studies contradict the prediction.
  9. Official ≠ Independent. Evaluate institutional independence separately from
     document tier. A non-independent primary source cannot substitute for an
     independent one when assessing trustworthiness.
 10. Absence of evidence is not evidence of absence. A claim that "X secretly did Y"
     cannot be DEBUNKED merely because no evidence of X doing Y was found. To rate
     DEBUNKED, there must be direct, affirmative counter-evidence that falsifies the
     specific mechanism alleged (e.g. a documented funding trail proving different
     actors, a verified alibi, an authoritative record contradicting the assertion).
     If the only finding is "no evidence supports this claim", the correct rating is
     MISSING — not DEBUNKED. Reserve DEBUNKED for claims where evidence actively
     contradicts the assertion, not merely fails to confirm it.
 11. Wikipedia (wikipedia.org, wikimedia.org) is always classified as Tertiary —
     no exceptions, regardless of the quality of the specific article. Wikipedia
     is a crowd-edited aggregation of secondary and tertiary material; it is not
     a primary or secondary source. Wikipedia can point to primary sources: those
     primary sources count and should be cited directly. Wikipedia itself does not.\
"""

# ── Tool definitions ──────────────────────────────────────────────────────────

_WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

_JUDGMENT_TOOL = {
    "name": "submit_judgment",
    "description": (
        "Submit your structured epistemic judgment after evaluating the evidence. "
        "Call this tool exactly once."
    ),
    "input_schema": {
        "type": "object",
        "required": ["rationale", "sources", "rating"],
        "properties": {
            "rating": {
                "type": "string",
                "enum": ["verified", "speculative", "debunked", "missing"],
                "description": (
                    "Your explicit epistemic rating. This always takes precedence over "
                    "the algorithmic rating derived from source tiers. Use MISSING when "
                    "evidence is absent rather than contradictory — even if some sources "
                    "nominally debunk the claim, absence of affirmative counter-evidence "
                    "means MISSING, not DEBUNKED."
                ),
            },
            "rationale": {
                "type": "string",
                "description": (
                    "Explanation of the judgment. Cite specific findings. "
                    "Acknowledge uncertainty explicitly when present."
                ),
            },
            "sources": {
                "type": "array",
                "description": "Every source you consulted, including ones that debunk the claim.",
                "items": {
                    "type": "object",
                    "required": ["url", "tier", "is_independent", "relevance_score", "supports_claim"],
                    "properties": {
                        "url": {"type": "string"},
                        "title": {"type": "string"},
                        "tier": {
                            "type": "string",
                            "enum": ["primary", "secondary", "tertiary"],
                        },
                        "is_independent": {"type": "boolean"},
                        "affiliation_note": {
                            "type": "string",
                            "description": "Required when is_independent is false.",
                        },
                        "relevance_score": {
                            "type": "number",
                            "description": "0.0–1.0: how directly this source addresses the claim.",
                        },
                        "excerpt": {
                            "type": "string",
                            "description": "Key passage from the source that informed your evaluation.",
                        },
                        "supports_claim": {
                            "type": "boolean",
                            "description": "True if this source verifies the claim; false if it debunks it.",
                        },
                    },
                },
            },
        },
    },
}

# Model used for the cheap pre-flight specificity gate (no web search, no tools).
_SPECIFICITY_MODEL = "claude-haiku-4-5-20251001"

# ── Client (lazy, checked at call time) ──────────────────────────────────────

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def _cached_system() -> list[dict]:
    return [{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]


# ── Pipeline phases ───────────────────────────────────────────────────────────

_SPECIFICITY_PROMPT = """\
You are a fact-checking specificity gate. Decide whether a claim is specific \
enough to fact-check meaningfully.

A claim is SPECIFIC (and must pass) if ANY of the following are true:
- It names a real public figure (politician, official, executive, celebrity, etc.)
- It names a real historical or current event (JFK assassination, 9/11, a named war, \
a named policy, a named scandal, etc.)
- It names a specific organisation, institution, law, document, or place
- The alleged actor is vague ("the Deep State", "the CIA", "elites") but the event \
or subject is a named real-world thing — pass it; full analysis will evaluate the evidence

A claim is VAGUE (and must be rejected) only if it is entirely content-free:
- No named person, event, organisation, or concrete action whatsoever
- Pure generalisations: "politicians lie", "the government is bad", \
"something fishy happened", "they are hiding the truth"

When in doubt, mark SPECIFIC — it is better to analyse a borderline claim \
than to silently reject a historically significant one.

Respond with exactly two lines:
Line 1: SPECIFIC or VAGUE
Line 2: If VAGUE, one sentence explaining what specific information (who, what, \
when, which documents or actions) would make the claim analyzable. \
If SPECIFIC, write OK.\
"""


def _check_specificity(client: anthropic.Anthropic, claim_text: str) -> tuple[bool, str]:
    """
    Fast pre-flight gate using a cheap model.

    Returns (is_specific, rationale).
    - is_specific=True  → proceed to full analysis; rationale is empty.
    - is_specific=False → claim is too vague; rationale is a human-readable
                          MISSING explanation ready to store on the Judgment.
    """
    try:
        resp = client.messages.create(
            model=_SPECIFICITY_MODEL,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": f"{_SPECIFICITY_PROMPT}\n\nClaim: {claim_text}",
            }],
        )
        text = next(
            (b.text for b in resp.content if hasattr(b, "text") and b.text),
            "",
        ).strip()
    except Exception as exc:
        logger.warning("Specificity check failed (%s); treating claim as specific.", exc)
        return True, ""

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    verdict = lines[0].upper() if lines else "SPECIFIC"

    if verdict != "VAGUE":
        return True, ""

    guidance = lines[1] if len(lines) > 1 else "Please provide a more specific claim."
    rationale = (
        "This claim is too vague to fact-check meaningfully. "
        f"{guidance} "
        "Please refine the claim with specific names, dates, actions, or "
        "allegations and resubmit."
    )
    return False, rationale


def _phase1_search(client: anthropic.Anthropic, claim_text: str) -> str:
    """
    Ask Claude to search for 2-3 sources. Returns the full text of its findings.
    Falls back silently to an empty string if web search is unavailable.
    """
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=_cached_system(),
            tools=[_WEB_SEARCH_TOOL],
            messages=[{
                "role": "user",
                "content": (
                    f"Search for evidence about this claim and summarise what you find, "
                    f"including the URLs of the sources:\n\n{claim_text}"
                ),
            }],
        )
        return "\n".join(
            block.text for block in resp.content if hasattr(block, "text") and block.text
        ).strip()
    except anthropic.PermissionDeniedError:
        logger.warning("Web search not available on this API key; skipping phase 1.")
        return ""
    except Exception as exc:
        logger.warning("Phase 1 web search failed (%s); proceeding without results.", exc)
        return ""


def _phase2_judgment(client: anthropic.Anthropic, claim_text: str, search_findings: str, lang_instruction: str = "") -> dict:
    """
    Force Claude to emit a submit_judgment tool call with structured source evaluations.
    Raises RuntimeError if the model does not return the expected tool call.
    """
    user_content = f"Claim to evaluate:\n{claim_text}"
    if search_findings:
        user_content += f"\n\nResearch findings from web search:\n{search_findings}"
    else:
        user_content += (
            "\n\nNo live web search results available. "
            "Evaluate based on your training knowledge. "
            "Include every source you reference in the sources array — use the canonical homepage URL "
            "(e.g. https://bls.gov) when you do not have a direct article URL. "
            "Only return an empty sources array if you genuinely cannot name any source for this claim."
        )
    if lang_instruction:
        user_content += f"\n\n{lang_instruction}"

    # temperature=0 makes the rating deterministic: the same claim and the same
    # evidence must always produce the same rating, source tiers, and rationale.
    # Phase 1 intentionally omits this so query variation can surface different sources.
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        temperature=0,
        system=_cached_system(),
        tools=[_JUDGMENT_TOOL],
        tool_choice={"type": "tool", "name": "submit_judgment"},
        messages=[{"role": "user", "content": user_content}],
    )

    tool_block = next(
        (b for b in resp.content if b.type == "tool_use" and b.name == "submit_judgment"),
        None,
    )
    if tool_block is None:
        raise RuntimeError("Model did not return a submit_judgment tool call.")

    return tool_block.input


# ── Public entry point ────────────────────────────────────────────────────────

def analyze_claim(claim_id: str, session, analyst: str = "claude-sonnet-4-6", user_language: str | None = None) -> Judgment:
    """
    Run the full epistemic analysis pipeline for a claim.

    All DB writes are deferred until the pipeline completes successfully.
    If anything raises before session.commit(), nothing is stored and the
    claim remains with active_judgment=null.
    """
    from sqlalchemy.orm import Session  # local import avoids top-level cycle risk

    claim = session.get(Claim, claim_id)
    if claim is None:
        raise ValueError(f"Claim {claim_id} not found")

    client = _get_client()

    # Pre-flight: reject claims that are too vague to fact-check meaningfully.
    is_specific, vague_rationale = _check_specificity(client, claim.text)
    if not is_specific:
        judgment = Judgment(
            claim_id=claim_id,
            rating=EpistemicRating.MISSING,
            rationale=vague_rationale,
            analyst=analyst,
            is_active=True,
        )
        session.add(judgment)
        session.commit()
        session.refresh(judgment)
        return judgment

    # Resolve claim language: use caller-supplied UI language if provided, otherwise detect.
    if user_language:
        lang_name = _LANG_NAMES.get(user_language, "English")
    else:
        lang_name = _detect_language(claim.text)
    lang_instruction = _build_lang_instruction(lang_name)
    if lang_instruction:
        logger.debug("Claim language: %s.", lang_name)

    # Phase 1: gather evidence via web search (best-effort)
    search_findings = _phase1_search(client, claim.text)

    # Phase 2: structured judgment (forced tool call)
    data = _phase2_judgment(client, claim.text, search_findings, lang_instruction)

    # Apply independence registry + quality checks before rating derivation.
    # This overrides Claude's own is_independent assessment for known compromised
    # institutions and caps their relevance_score at COMPROMISED_SCORE_CAP.
    sources_data: list[dict] = [
        evaluate_source(src)
        for src in data.get("sources", [])[:MAX_SOURCES]
    ]
    # Domain deduplication: multiple sources from the same root domain count as one
    # for threshold purposes. All sources remain in sources_data for UI display.
    seen_domains: set[str] = set()
    verifying_tiers: list[SourceTier] = []
    debunking_tiers: list[SourceTier] = []

    for src in sources_data:
        if float(src.get("relevance_score", 0.0)) < MIN_RELEVANCE_SCORE:
            continue
        domain = extract_domain(src.get("url", ""))
        if domain:
            if domain in seen_domains:
                continue
            seen_domains.add(domain)
        try:
            tier = SourceTier(src["tier"])
        except ValueError:
            tier = SourceTier.TERTIARY
        # Non-independent primary sources are treated as secondary for rating purposes:
        # a captured official institution cannot substitute for an independent primary
        # source when establishing VERIFIED.
        if not src.get("is_independent", True) and tier is SourceTier.PRIMARY:
            tier = SourceTier.SECONDARY
        (verifying_tiers if src.get("supports_claim", True) else debunking_tiers).append(tier)

    derived_rating = derive_rating(EvidenceSummary(
        verifying_tiers=verifying_tiers,
        debunking_tiers=debunking_tiers,
    ))

    # Model's explicit rating always takes precedence; derive_rating() is fallback only.
    model_rating_str = data.get("rating")
    if model_rating_str:
        try:
            rating = EpistemicRating(model_rating_str)
        except ValueError:
            logger.warning(
                "Model returned unknown rating %r for claim %s; using derived rating %s.",
                model_rating_str, claim_id, derived_rating,
            )
            rating = derived_rating
    else:
        rating = derived_rating

    # Atomic write: sources + judgment committed together
    no_url = sum(1 for s in sources_data if not s.get("url"))
    if no_url:
        logger.warning(
            "claim %s: %d source(s) have no URL and will use title as fallback", claim_id, no_url
        )
    evaluated_sources = [
        EvaluatedSource(
            claim_id=claim_id,
            url=src.get("url") or src.get("title") or "",
            tier=SourceTier(src.get("tier", "tertiary")),
            is_independent=bool(src.get("is_independent", True)),
            affiliation_note=src.get("affiliation_note"),
            relevance_score=max(0.0, min(1.0, float(src.get("relevance_score") or 0.5))),
            excerpt=src.get("excerpt"),
        )
        for src in sources_data
        if src.get("url") or src.get("title")
    ]

    judgment = Judgment(
        claim_id=claim_id,
        rating=rating,
        rationale=data["rationale"],
        analyst=analyst,
        is_active=True,
    )

    session.add_all(evaluated_sources)
    session.add(judgment)
    session.commit()
    session.refresh(judgment)

    return judgment
