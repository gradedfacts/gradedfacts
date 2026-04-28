"""
Registry of known politically compromised institutions.

An institution is "compromised" when its leadership has documented political
dependency that undermines editorial or investigative independence — regardless
of its official legal status.  Being an official government body does NOT
imply independence.

Rule (TransparencyPuzzle epistemic framework):
  Institutional independence overrides institutional status.
  Official documents from compromised institutions get is_independent=False
  and relevance_score capped at COMPROMISED_SCORE_CAP, with an explicit
  affiliation_note.

Adding entries:
  - domain_patterns: lowercase URL substrings (matched case-insensitively)
  - compromised_since: ISO date when compromise began (informational)
  - compromised_until: ISO date if the compromise period ended, else None
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompromisedEntry:
    institution: str
    domain_patterns: tuple[str, ...]
    affiliation_note: str
    country: str
    compromised_since: str | None = None
    compromised_until: str | None = None


# Sources from compromised institutions have their relevance_score capped here.
COMPROMISED_SCORE_CAP: float = 0.75

_REGISTRY: list[CompromisedEntry] = [
    # ── United States ─────────────────────────────────────────────────────────
    CompromisedEntry(
        institution="FBI under Kash Patel",
        domain_patterns=("fbi.gov",),
        affiliation_note=(
            "FBI under Director Kash Patel (2025–): appointed by President Trump; "
            "Patel has publicly stated intent to use the FBI against perceived political "
            "enemies. Independence of official FBI statements cannot be assumed."
        ),
        country="US",
        compromised_since="2025-02-20",
    ),
    CompromisedEntry(
        institution="DOJ under Pam Bondi",
        domain_patterns=("justice.gov",),
        affiliation_note=(
            "DOJ under AG Pam Bondi (2025–): confirmed after pledging personal loyalty "
            "to President Trump; multiple career prosecutors resigned citing political "
            "interference. Official DOJ positions reflect political direction, not "
            "independent legal judgment."
        ),
        country="US",
        compromised_since="2025-01-22",
    ),
    # ── Russia ────────────────────────────────────────────────────────────────
    CompromisedEntry(
        institution="Russian state media",
        domain_patterns=("rt.com", "tass.com", "ria.ru", "iz.ru", "rg.ru", "kremlin.ru"),
        affiliation_note=(
            "Russian state outlets (RT, TASS, RIA Novosti) operate under direct Kremlin "
            "editorial control. RT has been designated a foreign agent in multiple "
            "democracies. Independence is structurally impossible."
        ),
        country="RU",
    ),
    # ── China ─────────────────────────────────────────────────────────────────
    CompromisedEntry(
        institution="Chinese state media and government portals",
        domain_patterns=(
            "xinhuanet.com",
            "xinhua.net",
            "cgtn.com",
            "chinadaily.com.cn",
            "people.com.cn",
            "gov.cn",
        ),
        affiliation_note=(
            "Chinese state outlets (Xinhua, CGTN, People's Daily) and official government "
            "portals operate under CCP editorial control. No editorial independence from "
            "the Party-State is structurally possible."
        ),
        country="CN",
    ),
    # ── Turkey ────────────────────────────────────────────────────────────────
    CompromisedEntry(
        institution="Turkish state and AKP-aligned media",
        domain_patterns=("trt.net.tr", "trtworld.com", "aa.com.tr", "anadoluajansi.com.tr"),
        affiliation_note=(
            "Turkish state outlets (TRT, Anadolu Agency) are directly controlled by the "
            "AKP-led government under President Erdoğan. RSF press freedom index ranks "
            "Turkey among the most censored environments globally."
        ),
        country="TR",
    ),
    # ── Hungary ───────────────────────────────────────────────────────────────
    CompromisedEntry(
        institution="Hungarian state and Fidesz-aligned media",
        domain_patterns=("hirado.hu", "m1.hu", "kossuth.hu", "mtva.hu"),
        affiliation_note=(
            "Hungarian public broadcaster MTVA and aligned outlets are controlled by the "
            "Fidesz-aligned KESMA media conglomerate under PM Viktor Orbán. "
            "EU Parliament has repeatedly cited rule-of-law concerns regarding media "
            "independence."
        ),
        country="HU",
    ),
    # ── Belarus ───────────────────────────────────────────────────────────────
    CompromisedEntry(
        institution="Belarusian state media",
        domain_patterns=("belta.by", "sb.by", "ont.by", "tvr.by"),
        affiliation_note=(
            "Belarusian state outlets operate under Lukashenko government control. "
            "Independent journalism has been systematically suppressed since 2020."
        ),
        country="BY",
    ),
]


def lookup(url: str) -> CompromisedEntry | None:
    """
    Return a CompromisedEntry if the URL matches a known compromised institution,
    otherwise None.  Matching is substring-based and case-insensitive.
    """
    url_lower = url.lower()
    for entry in _REGISTRY:
        if any(pattern in url_lower for pattern in entry.domain_patterns):
            return entry
    return None


def apply_independence_override(source: dict) -> dict:
    """
    Check a source dict against the registry and return a (possibly modified) copy.

    When the URL matches a compromised institution:
      - is_independent is set to False
      - relevance_score is capped at COMPROMISED_SCORE_CAP
      - affiliation_note is set to the registry entry's canonical note

    The input dict is never mutated; a new dict is always returned when changes
    are made (identity is preserved for unmatched sources).
    """
    entry = lookup(source.get("url", ""))
    if entry is None:
        return source

    updated = dict(source)
    updated["is_independent"] = False
    updated["relevance_score"] = min(
        float(source.get("relevance_score", 1.0)),
        COMPROMISED_SCORE_CAP,
    )
    updated["affiliation_note"] = entry.affiliation_note
    return updated
