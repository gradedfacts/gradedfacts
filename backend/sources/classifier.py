"""
Source tier classifier.

Determines whether a source qualifies as Primary, Secondary, or Tertiary
using domain heuristics, content analysis, and a curated domain registry.

    Primary   — Original data, official documents, direct statements,
                government records, peer-reviewed studies.
    Secondary — Reporting that cites primary sources; editorial analysis
                with full attribution.
    Tertiary  — Aggregations, summaries, opinion pieces, or sources that
                cite secondary material without independent verification.

A judgment backed only by Tertiary sources is automatically capped at
SPECULATIVE regardless of AI confidence.

HARD RULE — Wikipedia is always Tertiary:
    Any URL on wikipedia.org or wikimedia.org is classified as Tertiary
    regardless of the article's content quality. Wikipedia is a crowd-edited
    aggregation; it is not a primary or secondary source. Cite the primary
    sources that Wikipedia links to — not Wikipedia itself.
"""

from urllib.parse import urlparse

# Domains that are unconditionally classified as Tertiary.
WIKIPEDIA_DOMAINS: frozenset[str] = frozenset({"wikipedia.org", "wikimedia.org"})


def is_wikipedia(url: str) -> bool:
    """Return True if the URL belongs to Wikipedia or Wikimedia."""
    try:
        host = urlparse(url).hostname or ""
        return any(host == d or host.endswith("." + d) for d in WIKIPEDIA_DOMAINS)
    except Exception:
        return False
