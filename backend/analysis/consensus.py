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
    _get_registry_version,
    _phase1_search,
    _phase2_judgment,
    _verify_rating_consistency,
)
from sqlalchemy import func, select as _sa_select

from backend.analysis.rating import EpistemicRating, EvidenceSummary, SourceTier, derive_rating
from backend.analysis.engine import independence_bool, independence_label
from backend.config import settings
from backend.db.models import Claim, EvaluatedSource, Judgment
from backend.sources.evaluator import evaluate_source, extract_domain
from backend.sources.search import search_claim

logger = logging.getLogger(__name__)

_MISTRAL_MODEL = "mistral-large-2512"
_CLAUDE_MODEL = "claude-sonnet-4-6"

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
    user_content += (
        "\n\nEVIDENCE: Research findings from Brave Search and SearXNG are provided above. "
        "Base your judgment exclusively on these findings. Prioritize Primary sources, then Secondary. "
        "Only cite sources that appear in the provided findings — never invent or recall sources from memory.\n\n"
        "Rating guidance: If the provided findings include ≥3 independent Primary or Secondary sources "
        "that consistently confirm the claim, rate VERIFIED. Secondary sources citing primary sources are "
        "sufficient — do not downgrade to SPECULATIVE merely because a primary document is not directly "
        "listed. Rate DEBUNKED only when counter-evidence is clear and direct; rate MISSING when evidence "
        "is genuinely absent or contradictory."
    )
    user_content += (
        "\n\nCRITICAL NUMERICAL THRESHOLD RULE:\n"
        "'Over X' means ANY number greater than X. Period.\n"
        "- 'Over 80 million' + actual = 81.7 million → VERIFIED. Not DEBUNKED. Not SPECULATIVE.\n"
        "- NEVER interpret 'over X' as 'significantly over X' or 'clearly over X'\n"
        "- NEVER DEBUNK a threshold claim when the actual number satisfies the threshold\n"
        "- This rule overrides all other considerations"
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
    logger.warning(
        "Mistral raw response — rating: %r | rationale: %.500s",
        args.get("rating"),
        args.get("rationale", ""),
    )
    final_rating = _verify_rating_consistency(
        args.get("rationale", ""), args.get("rating", "").lower()
    )
    return {**args, "rating": final_rating}


def _mistral_search_and_judge(claim_text: str, lang_instruction: str = "") -> dict:
    """
    Mistral's independent Phase 1+2: fetch search findings then run Phase 2 judgment.
    Runs inside the Phase 2 ThreadPoolExecutor alongside Claude's thread.
    Search findings may be "" if neither Brave nor SearXNG is configured;
    _mistral_phase2_judgment handles that case with a knowledge-only fallback message.
    """
    logger.info("_mistral_search_and_judge called")
    search_findings = search_claim(claim_text)
    return _mistral_phase2_judgment(claim_text, search_findings, lang_instruction)


# ── Consensus resolution ──────────────────────────────────────────────────────

def _has_primary_independent(sources: list[dict]) -> bool:
    """Return True if any source is Primary tier, independent, and meets minimum relevance."""
    return any(
        src.get("tier") == "primary"
        and independence_bool(src.get("is_independent", True))
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
      1. mistral_rating is None                → pass through Claude's rating; models_agree=None.
      2. Both identical                         → that shared rating; models_agree=True.
      3. DEBUNKED + MISSING (either order)      → DEBUNKED (stronger signal wins); models_agree=False.
      4. DEBUNKED + VERIFIED, Claude has P/I    → DEBUNKED (counter-evidence with primary sources
                                                   prevails over supporting evidence); models_agree=False.
      5. Source quality tiebreaker              → model with ≥1 Primary/Independent source wins
                                                   when the other has zero; models_agree=False.
      6. All other conflicts                    → SPECULATIVE (conservative floor); models_agree=False.
    """
    if mistral_rating is None:
        return claude_rating, None
    if claude_rating == mistral_rating:
        return claude_rating, True

    pair = {claude_rating, mistral_rating}
    if pair == {EpistemicRating.DEBUNKED, EpistemicRating.MISSING}:
        return EpistemicRating.DEBUNKED, False

    # Counter-evidence with primary/independent sources beats supporting evidence.
    # Claude is the primary pipeline: its DEBUNKED + primary/independent wins over Mistral's VERIFIED.
    if (
        pair == {EpistemicRating.DEBUNKED, EpistemicRating.VERIFIED}
        and claude_rating == EpistemicRating.DEBUNKED
        and claude_has_primary_independent
    ):
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
) -> tuple[list[dict], EpistemicRating, bool]:
    """
    Apply evaluate_source(), filter by relevance, downgrade non-independent primaries,
    and derive an algorithmic rating from the resulting tiers.

    Domain deduplication: multiple sources from the same root domain count as one
    for threshold purposes (e.g. three CBS articles = one unique source). All sources
    remain in the returned list for UI display.

    Returns (sources_data, derived_rating, has_independent_qualifying_source).
    The third value is True when at least one independent primary or secondary source
    meets the relevance threshold — required for VERIFIED and DEBUNKED.
    """
    if sources_raw is None:
        sources_raw = []
    if isinstance(sources_raw, str):
        # Guard: model occasionally returns sources as a JSON-encoded string instead
        # of a parsed array, which would cause character-level iteration below.
        try:
            sources_raw = json.loads(sources_raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning("_process_sources: could not parse sources JSON string; treating as empty.")
            sources_raw = []

    coerced: list[dict] = []
    for s in sources_raw[:MAX_SOURCES]:
        if isinstance(s, dict):
            coerced.append(s)
        elif isinstance(s, str) and s.strip():
            logger.warning("_process_sources: coercing string URL %r to minimal source dict", s)
            coerced.append({
                "url": s, "title": s, "tier": "secondary",
                "is_independent": True, "relevance_score": 0.6,
            })
        else:
            logger.warning("_process_sources: dropping unrecognised source item %r", s)
    sources_data = [ev for ev in (evaluate_source(src) for src in coerced) if ev is not None]
    logger.debug("_process_sources: %d raw → %d evaluated", len(sources_raw), len(sources_data))

    seen_domains: set[str] = set()
    verifying_tiers: list[SourceTier] = []
    debunking_tiers: list[SourceTier] = []
    has_independent_qualifying = False

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
        is_indep = independence_bool(src.get("is_independent", True))
        if not is_indep and tier is SourceTier.PRIMARY:
            tier = SourceTier.SECONDARY
        if is_indep and tier in (SourceTier.PRIMARY, SourceTier.SECONDARY):
            has_independent_qualifying = True
        (verifying_tiers if src.get("supports_claim", True) else debunking_tiers).append(tier)

    derived = derive_rating(EvidenceSummary(
        verifying_tiers=verifying_tiers,
        debunking_tiers=debunking_tiers,
        has_independent_qualifying_source=has_independent_qualifying,
    ))
    return sources_data, derived, has_independent_qualifying


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

    # Resolve claim language first — gates need lang_name for localized messages.
    from backend.analysis.engine import _resolve_ui_language, _check_off_topic
    if user_language:
        lang_name = _resolve_ui_language(user_language)
    else:
        lang_name = _detect_language(claim.text)

    # ── Pre-flight specificity gate ───────────────────────────────────────────
    is_specific, vague_rationale = _check_specificity(claude_client, claim.text, lang_name)
    if not is_specific:
        judgment = Judgment(
            claim_id=claim_id,
            rating=EpistemicRating.MISSING,
            rationale=vague_rationale,
            analyst=_CLAUDE_MODEL,
            is_active=True,
            model_claude=_CLAUDE_MODEL,
            registry_version=_get_registry_version(),
            prompt_version="1.0",
        )
        session.add(judgment)
        session.commit()
        session.refresh(judgment)
        return judgment

    # ── Pre-flight off-topic gate ─────────────────────────────────────────────
    is_on_topic, off_topic_rationale = _check_off_topic(claude_client, claim.text, lang_name)
    if not is_on_topic:
        judgment = Judgment(
            claim_id=claim_id,
            rating=EpistemicRating.MISSING,
            rationale=off_topic_rationale,
            analyst=_CLAUDE_MODEL,
            is_active=True,
            model_claude=_CLAUDE_MODEL,
            registry_version=_get_registry_version(),
            prompt_version="1.0",
        )
        session.add(judgment)
        session.commit()
        session.refresh(judgment)
        return judgment
    lang_instruction = _build_lang_instruction(lang_name)
    if lang_instruction:
        logger.debug("Claim language: %s.", lang_name)

    # ── Phase 1: web search ────────────────────────────────────────────────────
    search_findings = _phase1_search(claim.text)

    # ── Phase 2: parallel judgment ────────────────────────────────────────────
    mistral_available = bool(settings.mistral_api_key)
    logger.info("mistral_available: %s", mistral_available)

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
    claude_sources, claude_derived, claude_has_qualifying = _process_sources(claude_data.get("sources") or [])

    # Persist EvaluatedSource objects IMMEDIATELY after _process_sources() returns —
    # before _rating_from_data(), before the Claude Hard Rule, before the consensus
    # Hard Rule, before any other logic that could raise and skip session.commit().
    no_url = sum(1 for s in claude_sources if not s.get("url"))
    if no_url:
        logger.warning(
            "claim %s: %d source(s) have no URL and will use title as fallback", claim_id, no_url
        )
    evaluated_sources = [
        EvaluatedSource(
            claim_id=claim_id,
            url=src.get("url") or src.get("title") or "",
            tier=SourceTier(src.get("tier", "tertiary")),
            is_independent=independence_bool(src.get("is_independent", True)),
            independence_label=independence_label(src.get("is_independent", True)),
            affiliation_note=src.get("affiliation_note"),
            relevance_score=max(0.0, min(1.0, float(src.get("relevance_score") or 0.5))),
            excerpt=src.get("excerpt"),
        )
        for src in claude_sources
        if src.get("url") or src.get("title")
    ]
    logger.warning("[DEBUG sources] claim_id=%s claude_sources_staged=%d", claim_id, len(evaluated_sources))

    claude_rating = _rating_from_data(claude_data, claude_derived, claim_id)

    # Hard quality gate — cannot be overridden by model judgment.
    if not claude_has_qualifying and claude_rating in (EpistemicRating.VERIFIED, EpistemicRating.DEBUNKED):
        logger.warning(
            "claim %s: hard quality gate (Claude) — no independent qualifying source; "
            "rating %s overridden to SPECULATIVE.",
            claim_id, claude_rating,
        )
        claude_rating = EpistemicRating.SPECULATIVE
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
            ev
            for ev in (
                evaluate_source(s) for s in mistral_data.get("sources", [])[:MAX_SOURCES]
                if isinstance(s, dict)
            )
            if ev is not None
        ]
        mistral_has_primary = _has_primary_independent(mistral_sources_eval)
        # Persist Mistral's sources alongside Claude's, deduped by URL.
        _seen_urls: set[str] = {es.url for es in evaluated_sources}
        _mistral_extra: list[EvaluatedSource] = []
        for _src in mistral_sources_eval:
            _url = _src.get("url") or _src.get("title") or ""
            if not _url or _url in _seen_urls:
                continue
            _seen_urls.add(_url)
            _mistral_extra.append(EvaluatedSource(
                claim_id=claim_id,
                url=_url,
                tier=SourceTier(_src.get("tier", "tertiary")),
                is_independent=independence_bool(_src.get("is_independent", True)),
                independence_label=independence_label(_src.get("is_independent", True)),
                affiliation_note=_src.get("affiliation_note"),
                relevance_score=max(0.0, min(1.0, float(_src.get("relevance_score") or 0.5))),
                excerpt=_src.get("excerpt"),
            ))
        evaluated_sources.extend(_mistral_extra)
        logger.warning(
            "[DEBUG sources] claim_id=%s Mistral sources: raw=%d evaluated=%d added=%d (deduped, total now=%d)",
            claim_id,
            len(mistral_data.get("sources", [])),
            len(mistral_sources_eval),
            len(_mistral_extra),
            len(evaluated_sources),
        )

    logger.warning(
        "claim %s: staging %d EvaluatedSource object(s) with session.add_all() "
        "[consensus.py — Claude + Mistral combined, before consensus resolution]",
        claim_id, len(evaluated_sources),
    )
    session.add_all(evaluated_sources)

    # ── Consensus resolution ─────────────────────────────────────────────────
    consensus_rating, models_agree = _resolve_consensus(
        claude_rating, mistral_rating,
        claude_has_primary_independent=claude_has_primary,
        mistral_has_primary_independent=mistral_has_primary,
    )

    # Hard quality gate on consensus — applied after resolution so neither model
    # nor the consensus logic can produce VERIFIED/DEBUNKED without an independent source.
    if not claude_has_qualifying and consensus_rating in (EpistemicRating.VERIFIED, EpistemicRating.DEBUNKED):
        logger.warning(
            "claim %s: hard quality gate (consensus) — no independent qualifying source; "
            "consensus rating %s overridden to SPECULATIVE.",
            claim_id, consensus_rating,
        )
        consensus_rating = EpistemicRating.SPECULATIVE

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

    # ── Write consensus judgment ──────────────────────────────────────────────
    # (EvaluatedSource objects were already added to the session above, before
    # the Hard Rules — they are committed together with the judgment below.)

    # Use the winning model's political_leaning, mirroring the rating resolution:
    # - Mistral absent or both agreed → Claude's leaning (primary)
    # - Mistral won via source-quality tiebreaker → Mistral's leaning
    # - SPECULATIVE fallback (no clear winner) → Claude's leaning (default)
    _VALID_LEANINGS = {"left", "right", "none"}
    def _safe_leaning(data: dict) -> str:
        raw = data.get("political_leaning", "none") if data else "none"
        return raw if raw in _VALID_LEANINGS else "none"

    mistral_won = (
        models_agree is False
        and mistral_data is not None
        and mistral_rating is not None
        and consensus_rating == mistral_rating
        and consensus_rating != claude_rating
    )
    political_leaning = _safe_leaning(mistral_data) if mistral_won else _safe_leaning(claude_data)

    judgment = Judgment(
        claim_id=claim_id,
        rating=consensus_rating,
        rationale=rationale,
        analyst=_CLAUDE_MODEL,
        analyst_secondary=_MISTRAL_MODEL if mistral_data is not None else None,
        consensus_rating=consensus_rating,
        models_agree=models_agree,
        is_active=True,
        political_leaning=political_leaning,
        model_claude=_CLAUDE_MODEL,
        model_mistral=_MISTRAL_MODEL if mistral_data is not None else None,
        registry_version=_get_registry_version(),
        prompt_version="1.0",
    )

    logger.warning(
        "[DEBUG sources] claim_id=%s PRE-COMMIT: staged_sources=%d consensus=%s models_agree=%s",
        claim_id, len(evaluated_sources), consensus_rating, models_agree,
    )
    session.add(judgment)
    session.commit()
    _post_commit_count = session.execute(
        _sa_select(func.count()).select_from(EvaluatedSource).where(EvaluatedSource.claim_id == claim_id)
    ).scalar_one()
    logger.warning(
        "[DEBUG sources] claim_id=%s POST-COMMIT db_count=%d consensus=%s models_agree=%s",
        claim_id, _post_commit_count, consensus_rating, models_agree,
    )
    session.refresh(judgment)

    return judgment
