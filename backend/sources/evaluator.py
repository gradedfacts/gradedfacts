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
import re
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


# Multi-part TLDs where the registrable domain is three labels, not two.
# e.g. ris.bka.gv.at → registrable domain is bka.gv.at, not gv.at.
_MULTI_PART_TLDS: frozenset[str] = frozenset({
    "ac.at", "ac.il", "co.il", "co.nz", "co.uk", "co.za", "com.au",
    "com.tr", "edu.tr", "gov.il", "gov.tr", "gv.at", "muni.il",
    "net.tr", "org.il", "org.tr", "org.uk",
})

_VALID_HOSTNAME_RE = re.compile(r"^[a-z0-9.\-]+$")


def extract_domain(url: str) -> str | None:
    """
    Return the registrable domain of a URL, handling multi-part TLDs.

    Examples:
        https://www.reuters.com/article  → reuters.com
        https://stats.cbs.nl/data        → cbs.nl
        https://ris.bka.gv.at/doc        → bka.gv.at
        https://www.bbc.co.uk/news       → bbc.co.uk

    Returns None for empty input, unparseable URLs, or hostnames containing
    invalid characters (e.g. bare '{' from malformed LLM output).
    """
    if not url:
        return None
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return None
    if not host:
        return None
    host = host.lower()
    if not _VALID_HOSTNAME_RE.match(host):
        return None
    parts = host.split(".")
    if len(parts) < 2:
        return host  # single-label (e.g. localhost)
    two_part = ".".join(parts[-2:])
    if len(parts) >= 3 and two_part in _MULTI_PART_TLDS:
        return ".".join(parts[-3:])
    return two_part


_SOCIAL_MEDIA_BLACKLIST: frozenset[str] = frozenset({
    "x.com",
    "twitter.com",
    "facebook.com",
    "fb.com",
    "instagram.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",       # YouTube short-URL service — same platform, same exclusion rule
    "linkedin.com",
    "reddit.com",
    "bluesky.app",
    "bsky.app",
    "threads.net",
    "mastodon.social",
    "telegram.org",
    "t.me",
    "t.co",           # Twitter/X URL-shortener — same platform, same exclusion rule
    "whatsapp.com",
    "snapchat.com",
    "pinterest.com",
    "tumblr.com",
})


def is_social_media_url(url: str) -> bool:
    """Return True if the URL belongs to a blacklisted social media platform."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    host_lower = host.lower()
    if extract_domain(url) in _SOCIAL_MEDIA_BLACKLIST:
        return True
    # Catch any mastodon instance: mastodon.online, mastodon.world, etc.
    if "mastodon." in host_lower:
        return True
    return False


# Political party and individual politician websites are never independent sources.
# A politician's own website is primary-source propaganda, not independent reporting.
# This list MUST grow symmetrically across the political spectrum — no selective
# exclusion of parties or politicians from one ideological side only.
_PARTY_POLITICIAN_BLACKLIST: frozenset[str] = frozenset({
    "friedrich-merz.de",   # CDU — German federal politician
    "sp-ps.ch",            # SP Switzerland — Swiss social democratic party
    "michael-donth.de",    # CDU — German federal politician
})


def is_party_politician_url(url: str) -> bool:
    """Return True if the URL belongs to a political party or individual politician's website."""
    return extract_domain(url) in _PARTY_POLITICIAN_BLACKLIST


# User-content platforms, upload/hosting layers, and single-author self-published
# sites without editorial structure. The common property is not the absence of
# original content — a single-author site produces plenty — but the absence of any
# editorial control structure, which leaves nothing to assess for independence or
# tier. Excluded like social media.
_USER_CONTENT_BLACKLIST: frozenset[str] = frozenset({
    "vocal.media",      # user-generated content platform
    "docplayer.org",    # document upload platform (unverifiable provenance)
    "quora.com",        # user-generated Q&A platform (unverifiable provenance)
    "blogspan.net",     # open blog-hosting platform
    "michael-mannheimer.net",  # single-author blog, no editorial control structure
    "dillum.ch",        # Chronologiekritik/pseudohistory, single author, self-published, verified 2026-08-06
    "github.com",       # code hosting, arbitrary user repositories — decision recorded June 2026, never implemented
    "windows.net",      # Azure blob storage, hosting layer with no publisher — same June 2026 decision
})


def is_user_content_url(url: str) -> bool:
    """Return True if the URL belongs to a user-content or document-upload platform."""
    return extract_domain(url) in _USER_CONTENT_BLACKLIST


# Defunct, parked, and redirect-to-parking domains. These still surface in search
# results but carry no assessable content, so there is nothing to rate. They must
# NOT be registered in registry.json instead: a parked domain can be sold and
# repurposed at any time, while a registry classification would outlive the change
# and silently vouch for whatever the new owner publishes.
# Every entry carries the date the status was established — this list can go stale
# in both directions (a parked domain may be revived, a live one may lapse).
_DEFUNCT_DOMAIN_BLACKLIST: frozenset[str] = frozenset({
    "iog.hu",   # redirects to parking service domain2.hu, verified 2026-08-06
})


def is_defunct_domain_url(url: str) -> bool:
    """Return True if the URL belongs to a defunct or parked domain."""
    return extract_domain(url) in _DEFUNCT_DOMAIN_BLACKLIST


_GENERIC_AFFILIATION_NOTE = (
    "Source is not editorially independent; specific affiliation not documented."
)


def evaluate_source(src: dict) -> dict | None:
    """
    Apply all quality checks to a single source dict from Claude's judgment.

    Returns a new dict (or the same object if no changes are needed).
    Returns None when the URL is on any blacklist (social media, user content,
    party/politician, defunct/parked) — callers must filter.
    """
    url = src.get("url", "")
    if url and is_social_media_url(url):
        logger.warning("[BLACKLIST] Social media URL excluded: %s", url)
        return None
    if url and is_user_content_url(url):
        logger.warning("[BLACKLIST] User-content platform URL excluded: %s", url)
        return None
    if url and is_party_politician_url(url):
        logger.warning("[BLACKLIST] Party/politician URL excluded: %s", url)
        return None
    if url and is_defunct_domain_url(url):
        logger.warning("[BLACKLIST] Defunct/parked domain excluded: %s", url)
        return None
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
