"""
ConsensusEngine — runs Claude (primary) and Mistral (secondary) in parallel for
cross-validation. The two pipelines are fully independent: each model uses its own
search infrastructure and neither shares findings with the other.

Pipeline:
  1. Specificity gate        — Claude Haiku (fast pre-flight, same as engine.py)
  2. Phase 1 (Claude)        — Claude Sonnet web search → findings for Claude Phase 2
  3. Phase 2 parallel:
       Claude  — uses Claude's own Phase 1 findings
       Mistral — calls Brave Search independently; receives "" if BRAVE_API_KEY is
                 absent or the Brave request fails (no cross-contamination with
                 Claude's findings)
  4. Consensus resolution    — agree → that rating; disagree → SPECULATIVE

Mistral is optional: if MISTRAL_API_KEY is absent or Mistral's Phase 2 fails,
the function falls back gracefully to the Claude-only result (models_agree=None).
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass

import httpx
from mistralai.client import Mistral

from backend.analysis.engine import (
    MAX_SOURCES,
    MIN_RELEVANCE_SCORE,
    _JUDGMENT_TOOL,
    _SYSTEM_PROMPT,
    _build_lang_instruction,
    _check_specificity,
    _detect_language,
    _get_client,
    _phase1_search,
    _phase2_judgment,
)
from backend.analysis.rating import EpistemicRating, EvidenceSummary, SourceTier, derive_rating
from backend.config import settings
from backend.db.models import Claim, EvaluatedSource, Judgment
from backend.sources.evaluator import evaluate_source, extract_domain

logger = logging.getLogger(__name__)

_MISTRAL_MODEL = "mistral-large-latest"
_CLAUDE_MODEL = "claude-sonnet-4-6"
_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

# ── Mistral tool definition (Mistral uses OpenAI-compatible function format) ──

_MISTRAL_JUDGMENT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_judgment",
        "description": _JUDGMENT_TOOL["description"],
        "parameters": _JUDGMENT_TOOL["input_schema"],
    },
}

# ── Mistral client (lazy singleton) ──────────────────────────────────────────

_mistral_client: Mistral | None = None


def _get_mistral_client() -> Mistral:
    global _mistral_client
    if not settings.mistral_api_key:
        raise RuntimeError("MISTRAL_API_KEY is not configured")
    if _mistral_client is None:
        _mistral_client = Mistral(api_key=settings.mistral_api_key)
    return _mistral_client


# ── Mistral Phase 2 ───────────────────────────────────────────────────────────

def _mistral_phase2_judgment(claim_text: str, search_findings: str, lang_instruction: str = "") -> dict:
    """
    Force Mistral to emit a submit_judgment tool call.
    Returns the parsed tool input dict (same schema as Claude's Phase 2).
    Raises RuntimeError if the model does not return the expected tool call.
    """
    client = _get_mistral_client()

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

    response = client.chat.complete(
        model=_MISTRAL_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        tools=[_MISTRAL_JUDGMENT_TOOL],
        tool_choice="any",
    )

    choice = response.choices[0]
    tool_calls = choice.message.tool_calls
    if not tool_calls:
        raise RuntimeError("Mistral did not return any tool calls.")

    call = tool_calls[0]
    if call.function.name != "submit_judgment":
        raise RuntimeError(
            f"Mistral returned unexpected tool '{call.function.name}'; expected 'submit_judgment'."
        )

    args = call.function.arguments
    if isinstance(args, str):
        args = json.loads(args)
    return args


# ── Brave Search Phase 1 for Mistral ─────────────────────────────────────────

def _mistral_phase1_brave_search(claim_text: str) -> str:
    """
    Query Brave Web Search API and return formatted findings for Mistral's Phase 2.

    Returns an empty string (never raises) when:
      - BRAVE_API_KEY is not configured
      - The HTTP request fails for any reason
      - The response contains no results
    This keeps Mistral's pipeline fully independent of Claude's: an empty string
    is passed to _mistral_phase2_judgment, which handles the no-context case.
    """
    if not settings.brave_api_key:
        return ""
    try:
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": settings.brave_api_key,
        }
        params = {"q": claim_text, "count": 10}

        with httpx.Client(timeout=30.0) as client:
            resp = client.get(_BRAVE_SEARCH_URL, headers=headers, params=params)
            resp.raise_for_status()

        results = resp.json().get("web", {}).get("results", [])
        if not results:
            return ""

        lines = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            url = r.get("url", "")
            description = r.get("description", "")
            lines.append(f"Source {i}: {title}\nURL: {url}\nExcerpt: {description}")

        return "\n\n".join(lines)
    except Exception as exc:
        logger.warning("Brave Search failed (%s); Mistral will proceed without web context.", exc)
        return ""


def _mistral_search_and_judge(claim_text: str, lang_instruction: str = "") -> dict:
    """
    Mistral's independent Phase 1+2: fetch Brave findings then run Phase 2 judgment.
    Runs inside the Phase 2 ThreadPoolExecutor alongside Claude's thread.
    Brave findings may be "" if Brave is unavailable; _mistral_phase2_judgment
    handles that case with a knowledge-only fallback message.
    """
    brave_findings = _mistral_phase1_brave_search(claim_text)
    return _mistral_phase2_judgment(claim_text, brave_findings, lang_instruction)


# ── Consensus resolution ──────────────────────────────────────────────────────

def _has_primary_independent(sources: list[dict]) -> bool:
    """Return True if any source is Primary tier, independent, and meets minimum relevance."""
    return any(
        src.get("tier") == "primary"
        and bool(src.get("is_independent", True))
        and float(src.get("relevance_score", 0.0)) >= MIN_RELEVANCE_SCORE
        for src in sources
    )


def _resolve_consensus(
    claude_rating: EpistemicRating,
    mistral_rating: EpistemicRating | None,
    *,
    claude_has_primary_independent: bool = False,
    mistral_has_primary_independent: bool = False,
) -> tuple[EpistemicRating, bool | None]:
    """
    Returns (consensus_rating, models_agree).

    Resolution order (first match wins):
      1. mistral_rating is None           → pass through Claude's rating; models_agree=None.
      2. Both identical                   → that shared rating; models_agree=True.
      3. DEBUNKED + MISSING (either order)→ DEBUNKED (stronger signal wins); models_agree=False.
      4. Source quality tiebreaker        → model with ≥1 Primary/Independent source wins
                                            when the other has zero; models_agree=False.
      5. All other conflicts              → SPECULATIVE (conservative floor); models_agree=False.
    """
    if mistral_rating is None:
        return claude_rating, None
    if claude_rating == mistral_rating:
        return claude_rating, True

    pair = {claude_rating, mistral_rating}
    if pair == {EpistemicRating.DEBUNKED, EpistemicRating.MISSING}:
        return EpistemicRating.DEBUNKED, False

    # Source quality tiebreaker: clear advantage → that model's rating wins.
    if claude_has_primary_independent and not mistral_has_primary_independent:
        return claude_rating, False
    if mistral_has_primary_independent and not claude_has_primary_independent:
        return mistral_rating, False

    return EpistemicRating.SPECULATIVE, False


# ── Source processing (shared logic, same rules as engine.py) ─────────────────

def _process_sources(
    sources_raw: list[dict],
) -> tuple[list[dict], EpistemicRating]:
    """
    Apply evaluate_source(), filter by relevance, downgrade non-independent primaries,
    and derive an algorithmic rating from the resulting tiers.

    Domain deduplication: multiple sources from the same root domain count as one
    for threshold purposes (e.g. three CBS articles = one unique source). All sources
    remain in the returned list for UI display.
    """
    non_dict = sum(1 for s in sources_raw[:MAX_SOURCES] if not isinstance(s, dict))
    if non_dict:
        logger.warning("_process_sources: dropping %d non-dict items from sources_raw", non_dict)
    sources_data = [evaluate_source(src) for src in sources_raw[:MAX_SOURCES] if isinstance(src, dict)]
    logger.debug("_process_sources: %d raw → %d evaluated", len(sources_raw), len(sources_data))

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
        except (KeyError, ValueError):
            tier = SourceTier.TERTIARY
        if not src.get("is_independent", True) and tier is SourceTier.PRIMARY:
            tier = SourceTier.SECONDARY
        (verifying_tiers if src.get("supports_claim", True) else debunking_tiers).append(tier)

    derived = derive_rating(EvidenceSummary(
        verifying_tiers=verifying_tiers,
        debunking_tiers=debunking_tiers,
    ))
    return sources_data, derived


def _rating_from_data(data: dict, derived: EpistemicRating, claim_id: str) -> EpistemicRating:
    """Resolve model-explicit rating with fallback to derived, matching engine.py logic."""
    raw = data.get("rating")
    if not raw:
        return derived
    try:
        return EpistemicRating(raw)
    except ValueError:
        logger.warning(
            "Model returned unknown rating %r for claim %s; using derived rating %s.",
            raw, claim_id, derived,
        )
        return derived


# ── Public entry point ────────────────────────────────────────────────────────

@dataclass
class ConsensusResult:
    """Intermediate result before DB write; useful for callers that don't need persistence."""
    claude_rating: EpistemicRating
    claude_rationale: str
    mistral_rating: EpistemicRating | None
    mistral_rationale: str | None
    consensus_rating: EpistemicRating
    models_agree: bool | None


def analyze_claim_with_consensus(claim_id: str, session, user_language: str | None = None) -> Judgment:
    """
    Full consensus pipeline: Claude (Phase 1 + Phase 2) + Mistral (Brave Phase 1 + Phase 2).

    All DB writes are deferred until the pipeline completes successfully — the same
    atomicity guarantee as engine.analyze_claim().

    Falls back to Claude-only (models_agree=None) when:
      - MISTRAL_API_KEY is not configured
      - Mistral's Phase 2 raises any exception

    Mistral's Phase 1 falls back to Claude's findings when:
      - BRAVE_API_KEY is not configured
      - The Brave Search request fails
    """
    claim = session.get(Claim, claim_id)
    if claim is None:
        raise ValueError(f"Claim {claim_id} not found")

    claude_client = _get_client()

    # ── Pre-flight specificity gate ───────────────────────────────────────────
    is_specific, vague_rationale = _check_specificity(claude_client, claim.text)
    if not is_specific:
        judgment = Judgment(
            claim_id=claim_id,
            rating=EpistemicRating.MISSING,
            rationale=vague_rationale,
            analyst=_CLAUDE_MODEL,
            is_active=True,
        )
        session.add(judgment)
        session.commit()
        session.refresh(judgment)
        return judgment

    # Resolve claim language: use caller-supplied UI language if provided, otherwise detect.
    if user_language:
        from backend.analysis.engine import _LANG_NAMES
        lang_name = _LANG_NAMES.get(user_language, "English")
    else:
        lang_name = _detect_language(claim.text)
    lang_instruction = _build_lang_instruction(lang_name)
    if lang_instruction:
        logger.debug("Claim language: %s.", lang_name)

    # ── Phase 1: web search (Claude only — Mistral has no built-in search) ────
    search_findings = _phase1_search(claude_client, claim.text)

    # ── Phase 2: parallel judgment ────────────────────────────────────────────
    mistral_available = bool(settings.mistral_api_key)

    claude_data: dict
    mistral_data: dict | None = None

    if mistral_available:
        # Do NOT use `with ThreadPoolExecutor(...) as executor` here.
        # The context manager calls shutdown(wait=True) on exit, which blocks until
        # every submitted thread finishes.  If the Mistral thread hangs (no HTTP
        # timeout on the SDK call), the background task would block forever and the
        # poll endpoint would never find a completed judgment.
        # shutdown(wait=False) lets the Mistral thread run to natural completion
        # without blocking the main pipeline.
        executor = ThreadPoolExecutor(max_workers=2)
        try:
            claude_future = executor.submit(
                _phase2_judgment, claude_client, claim.text, search_findings, lang_instruction
            )
            # _mistral_search_and_judge runs its own independent Brave Search Phase 1
            # then Mistral Phase 2 — no shared state with Claude's thread.
            mistral_future = executor.submit(
                _mistral_search_and_judge, claim.text, lang_instruction
            )
            claude_data = claude_future.result()
            try:
                mistral_data = mistral_future.result(timeout=45)
            except FuturesTimeoutError:
                logger.warning(
                    "Mistral Phase 2 timed out for claim %s; proceeding with Claude-only result.",
                    claim_id,
                )
            except Exception as exc:
                logger.warning(
                    "Mistral Phase 2 failed for claim %s (%s); proceeding without consensus.",
                    claim_id, exc,
                )
        finally:
            executor.shutdown(wait=False)
    else:
        logger.info("MISTRAL_API_KEY not set; running single-engine (Claude-only) analysis.")
        claude_data = _phase2_judgment(claude_client, claim.text, search_findings, lang_instruction)

    # ── Process Claude's sources and derive its rating ────────────────────────
    claude_sources, claude_derived = _process_sources(claude_data.get("sources", []))
    claude_rating = _rating_from_data(claude_data, claude_derived, claim_id)
    claude_has_primary = _has_primary_independent(claude_sources)

    # ── Extract Mistral's explicit rating and assess source quality ───────────
    mistral_rating: EpistemicRating | None = None
    mistral_rationale: str | None = None
    mistral_has_primary = False
    if mistral_data is not None:
        mistral_rationale = mistral_data.get("rationale", "")
        raw_mistral_rating = mistral_data.get("rating")
        if raw_mistral_rating:
            try:
                mistral_rating = EpistemicRating(raw_mistral_rating)
            except ValueError:
                logger.warning(
                    "Mistral returned unknown rating %r for claim %s; ignoring Mistral verdict.",
                    raw_mistral_rating, claim_id,
                )
        mistral_sources_eval = [
            evaluate_source(s) for s in mistral_data.get("sources", [])[:MAX_SOURCES]
            if isinstance(s, dict)
        ]
        mistral_has_primary = _has_primary_independent(mistral_sources_eval)

    # ── Consensus resolution ──────────────────────────────────────────────────
    consensus_rating, models_agree = _resolve_consensus(
        claude_rating, mistral_rating,
        claude_has_primary_independent=claude_has_primary,
        mistral_has_primary_independent=mistral_has_primary,
    )

    # Build a combined rationale that surfaces both verdicts when models disagree
    if models_agree is False:
        pair = {claude_rating, mistral_rating}
        if pair == {EpistemicRating.DEBUNKED, EpistemicRating.MISSING}:
            resolution_note = "Models disagreed. DEBUNKED signal prevails over MISSING."
        elif (
            claude_has_primary and not mistral_has_primary
            and consensus_rating == claude_rating
        ) or (
            mistral_has_primary and not claude_has_primary
            and consensus_rating == mistral_rating
        ):
            winner = "Claude" if consensus_rating == claude_rating else "Mistral"
            resolution_note = (
                f"Models disagreed. Resolved by source quality — "
                f"{winner}'s rating applied (Primary/Independent sources present)."
            )
        else:
            resolution_note = "Models disagreed. Consensus downgraded to SPECULATIVE."
        rationale = (
            f"[Claude: {claude_rating.value.upper()}] {claude_data['rationale']}\n\n"
            f"[Mistral: {mistral_rating.value.upper()}] {mistral_rationale}\n\n"  # type: ignore[union-attr]
            f"{resolution_note}"
        )
    else:
        rationale = claude_data["rationale"]

    # ── Atomic write: sources + consensus judgment ────────────────────────────
    no_url = sum(1 for s in claude_sources if not s.get("url"))
    if no_url:
        logger.warning(
            "claim %s: %d source(s) have no URL and will use title as fallback", claim_id, no_url
        )
    logger.debug("claim %s: storing %d evaluated sources", claim_id, len(claude_sources))
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
        for src in claude_sources
        if src.get("url") or src.get("title")
    ]

    judgment = Judgment(
        claim_id=claim_id,
        rating=consensus_rating,
        rationale=rationale,
        analyst=_CLAUDE_MODEL,
        analyst_secondary=_MISTRAL_MODEL if mistral_data is not None else None,
        consensus_rating=consensus_rating,
        models_agree=models_agree,
        is_active=True,
    )

    session.add_all(evaluated_sources)
    session.add(judgment)
    session.commit()
    session.refresh(judgment)

    return judgment
