"""Shared search layer: Brave Search API + SearXNG, used by both Claude and Mistral pipelines."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor

import anthropic
import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_TRANSLATION_MODEL = "claude-haiku-4-5-20251001"

_TRANSLATE_PROMPT = (
    "Translate the following claim to English. "
    "If it is already in English, return it exactly unchanged. "
    "Return only the translated text — no preamble, no explanation, no quotes."
)


def _translate_to_english(claim_text: str) -> str | None:
    """
    Translate claim_text to English using Claude Haiku (temperature=0, deterministic).
    Returns the translated string, or None on any failure or empty response.
    Never raises — callers fall back to original-only search on None.
    """
    if not settings.anthropic_api_key:
        return None
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=_TRANSLATION_MODEL,
            max_tokens=256,
            temperature=0,
            messages=[{
                "role": "user",
                "content": f"{_TRANSLATE_PROMPT}\n\nClaim: {claim_text}",
            }],
        )
        text = next(
            (b.text for b in resp.content if hasattr(b, "text") and b.text),
            "",
        ).strip()
        return text if text else None
    except Exception as exc:
        logger.warning("Translation to English failed (%s); using original query only.", exc)
        return None


def _query_brave(claim_text: str) -> list[dict]:
    """Query Brave Web Search; returns raw result dicts. Returns [] on any failure."""
    if not settings.brave_api_key:
        return []
    try:
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": settings.brave_api_key,
        }
        params = {"q": claim_text, "count": 10}
        logger.info("Brave Search query: %r", claim_text)
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(_BRAVE_SEARCH_URL, headers=headers, params=params)
            resp.raise_for_status()
        logger.info("Brave Search HTTP status: %d", resp.status_code)
        results = resp.json().get("web", {}).get("results", [])
        logger.info("Brave Search results returned: %d", len(results))
        logger.warning("[DEBUG sources] brave_urls=%d", len(results))
        return results
    except Exception as exc:
        logger.warning("Brave Search failed (%s); skipping Brave results.", exc)
        return []


def _query_searxng(claim_text: str) -> list[dict]:
    """
    Query SearXNG REST API; returns normalised result dicts. Returns [] on any failure.
    Each dict has keys: title, url, description (matching Brave's field names).
    """
    if not settings.searxng_url:
        return []
    try:
        base = settings.searxng_url.rstrip("/")
        params = {"q": claim_text, "format": "json", "categories": "general"}
        logger.info("SearXNG query: %r", claim_text)
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{base}/search", params=params)
            resp.raise_for_status()
        results = resp.json().get("results", [])
        logger.info("SearXNG results returned: %d", len(results))
        logger.warning("[DEBUG sources] searxng_urls=%d", len(results))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("content", ""),
            }
            for r in results
        ]
    except Exception as exc:
        logger.warning("SearXNG search failed (%s); skipping SearXNG results.", exc)
        return []


def search_claim(claim_text: str) -> str:
    """
    Query Brave and/or SearXNG for the original claim and, when non-English, its English
    translation — all in parallel.  Results are merged and deduplicated by URL.

    Merge order: original-claim Brave → original-claim SearXNG → English Brave → English
    SearXNG.  First occurrence of a URL wins, so original-language results are not displaced.

    Returns a formatted plain-text findings string ("Source N: title\\nURL: ...\\nExcerpt: ...")
    for use as model context, or "" when no source is configured or returns results.
    Never raises.
    """
    logger.info(
        "search_claim called, brave key present: %s, searxng configured: %s",
        bool(settings.brave_api_key), bool(settings.searxng_url),
    )
    logger.info("BRAVE_API_KEY present: %s", bool(os.getenv("BRAVE_API_KEY")))

    has_brave = bool(settings.brave_api_key)
    has_searxng = bool(settings.searxng_url)
    if not has_brave and not has_searxng:
        return ""

    # Attempt English translation for multilang coverage.
    translation = _translate_to_english(claim_text)
    if translation is not None and translation.strip().lower() != claim_text.strip().lower():
        en_query: str | None = translation
    else:
        en_query = None

    max_workers = 4 if en_query else 2
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        orig_brave_f = executor.submit(_query_brave, claim_text)
        orig_searxng_f = executor.submit(_query_searxng, claim_text)
        if en_query:
            en_brave_f = executor.submit(_query_brave, en_query)
            en_searxng_f = executor.submit(_query_searxng, en_query)

        orig_brave = orig_brave_f.result()
        orig_searxng = orig_searxng_f.result()
        if en_query:
            en_brave = en_brave_f.result()
            en_searxng = en_searxng_f.result()
        else:
            en_brave = []
            en_searxng = []

    # Merge: original Brave → original SearXNG → English Brave → English SearXNG.
    # First URL occurrence wins; original-language results keep priority.
    seen_urls: set[str] = set()
    merged: list[dict] = []
    for r in orig_brave + orig_searxng + en_brave + en_searxng:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged.append(r)

    merged = merged[:30]

    # Audit line — visible in uvicorn.log for every search_claim invocation.
    if translation is None:
        en_log = "skipped(translation-failed)"
    elif en_query is None:
        en_log = "skipped(same)"
    else:
        en_log = str(len(en_brave) + len(en_searxng))
    logger.warning(
        "[SEARCH-MULTILANG] original_lang_query=%d english_query=%s merged=%d",
        len(orig_brave) + len(orig_searxng),
        en_log,
        len(merged),
    )

    if not merged:
        return ""

    lines = []
    for i, r in enumerate(merged, 1):
        title = r.get("title", "")
        url = r.get("url", "")
        description = r.get("description", "")
        lines.append(f"Source {i}: {title}\nURL: {url}\nExcerpt: {description}")

    return "\n\n".join(lines)
