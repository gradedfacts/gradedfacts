"""
Wire-agency registry for cascade-deduplication in source independence counting.

SYMMETRY: Every entry is added regardless of the agency's political affiliation,
country of origin, or editorial line.  New agencies are always added with the
same process applied to all others — no selective exclusion.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Registry: canonical name → tuple of common written variants.
#
# Variants must be unique across agencies (no variant may appear under two
# canonical names) so that the first-match detection is unambiguous.
# ---------------------------------------------------------------------------

# fmt: off
_AGENCIES: dict[str, tuple[str, ...]] = {
    # International wire services (independent)
    "AP":       ("Associated Press", "AP"),   # longest variant first
    "AFP":      ("AFP",),
    "Reuters":  ("Reuters",),
    # German-language wire services
    "dpa":      ("dpa",),
    "SDA":      ("SDA", "Keystone-SDA"),
    "APA":      ("APA",),                     # Österreichische Presse-Agentur
    # Other regional/national wire services
    "EFE":      ("EFE",),
    "ANSA":     ("ANSA",),
    # State-controlled wire service — listed for structural symmetry;
    # deduplication is agency-agnostic and does not treat TASS differently.
    "TASS":     ("TASS",),
}
# fmt: on


def _build_attribution_re(variants: tuple[str, ...]) -> re.Pattern[str]:
    """
    Build a regex that matches ONLY explicit attribution contexts for the
    given variant spellings.  Does NOT match a mere topic mention.

    Attribution contexts matched:
      (1) Parenthetical byline     — (dpa)  (AP)  (dpa/AFP)
      (2) Attribution keyword      — Quelle: AFP   laut Reuters   von dpa
                                     by AP   via Reuters   Source: AP
                                     laut der Nachrichtenagentur dpa
                                     berichtet die Nachrichtenagentur AP
      (3) Slash byline, left side  — "dpa/" at start or after space/pipe/paren
      (4) Slash byline, right side — "/AFP" before end/space/pipe/paren
    """
    # Sort longest variant first so "Associated Press" matches before "AP".
    alts = "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True))

    return re.compile(
        r"(?i)"
        # (1) Parenthetical: opening paren is sufficient; catches (dpa) and (dpa/AFP)
        r"\(\s*(?:" + alts + r")\b"
        r"|"
        # (2a) "Quelle: dpa"  /  "Source: Reuters"
        r"(?:quelle|source)\s*:\s*(?:" + alts + r")\b"
        r"|"
        # (2b) "laut dpa"  /  "laut der Nachrichtenagentur AFP"
        r"laut\s+(?:der\s+)?(?:nachrichtenagentur\s+)?(?:" + alts + r")\b"
        r"|"
        # (2c) "von dpa"  /  "by AP"  /  "via Reuters"
        r"(?:von|by|via)\s+(?:" + alts + r")\b"
        r"|"
        # (2d) "berichtet die Nachrichtenagentur AP"
        r"berichtet(?:\s+die)?\s+nachrichtenagentur\s+(?:" + alts + r")\b"
        r"|"
        # (3) Slash byline, left side: agency at start or preceded by space/pipe/paren
        r"(?:(?:^|(?<=[\s|(]))(?:" + alts + r")\s*/)"
        r"|"
        # (4) Slash byline, right side: agency after / and followed by boundary
        r"(?:/\s*(?:" + alts + r")(?=\s|\)|$|\|))"
    )


# Pre-compiled list of (canonical_name, pattern) pairs.
# Iteration order follows _AGENCIES insertion order; first match wins.
_AGENCY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (canonical, _build_attribution_re(variants))
    for canonical, variants in _AGENCIES.items()
]


def detect_wire_agency(title: str, excerpt: str) -> str | None:
    """
    Return the canonical wire-agency name if the source explicitly attributes
    its content to a wire agency via a byline or attribution keyword.

    Matches only clear attribution patterns (parenthetical byline, keyword
    attribution, slash byline).  Does NOT match a mere mention of the agency
    as a news topic (e.g. "Reuters published a study on ...").

    Returns None when no wire-agency attribution is found.
    """
    text = f"{title or ''} {excerpt or ''}"
    for canonical, pattern in _AGENCY_PATTERNS:
        if pattern.search(text):
            return canonical
    return None
