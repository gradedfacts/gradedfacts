"""Shared search layer: Brave Search API + SearXNG, used by both Claude and Mistral pipelines."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


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
    Query Brave and/or SearXNG in parallel; merge and deduplicate results by URL.

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

    with ThreadPoolExecutor(max_workers=2) as executor:
        brave_future = executor.submit(_query_brave, claim_text)
        searxng_future = executor.submit(_query_searxng, claim_text)
        brave_results = brave_future.result()
        searxng_results = searxng_future.result()

    # Merge and deduplicate by URL; Brave results take precedence for duplicates.
    seen_urls: set[str] = set()
    merged: list[dict] = []
    for r in brave_results + searxng_results:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged.append(r)

    if not merged:
        return ""

    merged = merged[:20]

    lines = []
    for i, r in enumerate(merged, 1):
        title = r.get("title", "")
        url = r.get("url", "")
        description = r.get("description", "")
        lines.append(f"Source {i}: {title}\nURL: {url}\nExcerpt: {description}")

    return "\n\n".join(lines)
