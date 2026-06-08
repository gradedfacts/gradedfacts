"""
Source quality evaluator.

Post-processes raw source dicts from Claude's judgment tool call:
  1. Applies regional registry overrides — known sources get curated tier,
     independence, country, and region metadata (overrides Claude's judgment).
  2. Applies the compromised-institution registry — active politically compromised
     institutions get is_independent=False, relevance_score capped, and a
     canonical affiliation_note (overrides whatever Claude or the registry returned).
  3. Ensures every non-independent source carries an affiliation_note.
  4. Clamps relevance_score to [0.0, 1.0].

The evaluator never mutates input dicts — it returns new ones.
"""

from __future__ import annotations

import fcntl
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from backend.sources.classifier import is_wikipedia
from backend.sources.independence_registry import apply_independence_override
from backend.sources.registries import apply_registry_override, lookup_source_all_registries

logger = logging.getLogger(__name__)

_NEW_SOURCES_PATH = Path(__file__).parent / "registries" / "new_sources_to_review.json"
_NEW_SOURCES_LOCK = _NEW_SOURCES_PATH.with_suffix(".lock")


def _track_unregistered_source(domain: str, url: str) -> None:
    """Append or update domain in new_sources_to_review.json with file locking."""
    try:
        with _NEW_SOURCES_LOCK.open("a+") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            try:
                if _NEW_SOURCES_PATH.exists():
                    with _NEW_SOURCES_PATH.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                else:
                    data = {"sources_to_review": []}

                sources = data.setdefault("sources_to_review", [])
                now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

                for entry in sources:
                    if entry.get("domain") == domain:
                        entry["appearance_count"] = entry.get("appearance_count", 1) + 1
                        entry["last_seen"] = now
                        break
                else:
                    sources.append({
                        "domain": domain,
                        "first_seen": now,
                        "appearance_count": 1,
                        "example_url": url,
                        "last_seen": now,
                    })

                with _NEW_SOURCES_PATH.open("w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            finally:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)
    except Exception:
        logger.debug("_track_unregistered_source: skipped for %s", domain, exc_info=True)


def extract_domain(url: str) -> str:
    """
    Return the root domain of a URL, stripping www. and subdomains.

    Examples:
        https://www.reuters.com/article  → reuters.com
        https://stats.cbs.nl/data        → cbs.nl
        https://data.cbs.nl/data         → cbs.nl

    Takes the last two hostname labels, which covers most TLDs (.com, .nl, .de …).
    Returns "" for unparseable or non-HTTP URLs.
    """
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return ""
    parts = host.lower().split(".")
    if len(parts) < 2:
        return host
    return ".".join(parts[-2:])

_GENERIC_AFFILIATION_NOTE = (
    "Source is not editorially independent; specific affiliation not documented."
)


def evaluate_source(src: dict) -> dict:
    """
    Apply all quality checks to a single source dict from Claude's judgment.

    Returns a new dict (or the same object if no changes are needed).
    """
    url = src.get("url", "")
    _is_unregistered = bool(url) and lookup_source_all_registries(url) is None

    # Step 1: apply regional registry overrides (known sources get curated metadata)
    src = apply_registry_override(src)

    # Step 1b: Hard rule — Wikipedia/Wikimedia is always Tertiary, overriding any
    # registry entry or model assignment.
    if is_wikipedia(src.get("url", "")) and src.get("tier") != "tertiary":
        src = dict(src)
        src["tier"] = "tertiary"

    # Step 1c: track unregistered domains and flag them for UI display.
    if _is_unregistered and not is_wikipedia(url):
        domain = extract_domain(url)
        if domain:
            _track_unregistered_source(domain, url)
        src = dict(src)
        src["is_unverified"] = True

    # Step 2: apply compromised-institution registry (can further downgrade independence)
    src = apply_independence_override(src)

    # Step 3: guarantee non-independent sources carry an explanation
    _indep = src.get("is_independent", True)
    _is_not_independent = _indep is False or _indep == "not_independent"
    if _is_not_independent and not src.get("affiliation_note"):
        src = dict(src)
        src["affiliation_note"] = _GENERIC_AFFILIATION_NOTE

    # Step 4: clamp relevance_score to valid range
    raw_score = float(src.get("relevance_score", 0.5))
    clamped = max(0.0, min(1.0, raw_score))
    if clamped != raw_score:
        src = dict(src)
        src["relevance_score"] = clamped

    return src
