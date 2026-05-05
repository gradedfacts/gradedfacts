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

from backend.sources.classifier import is_wikipedia
from backend.sources.independence_registry import apply_independence_override
from backend.sources.registries import apply_registry_override

_GENERIC_AFFILIATION_NOTE = (
    "Source is not editorially independent; specific affiliation not documented."
)


def evaluate_source(src: dict) -> dict:
    """
    Apply all quality checks to a single source dict from Claude's judgment.

    Returns a new dict (or the same object if no changes are needed).
    """
    # Step 1: apply regional registry overrides (known sources get curated metadata)
    src = apply_registry_override(src)

    # Step 1b: Hard rule — Wikipedia/Wikimedia is always Tertiary, overriding any
    # registry entry or model assignment.
    if is_wikipedia(src.get("url", "")) and src.get("tier") != "tertiary":
        src = dict(src)
        src["tier"] = "tertiary"

    # Step 2: apply compromised-institution registry (can further downgrade independence)
    src = apply_independence_override(src)

    # Step 3: guarantee non-independent sources carry an explanation
    if not src.get("is_independent", True) and not src.get("affiliation_note"):
        src = dict(src)
        src["affiliation_note"] = _GENERIC_AFFILIATION_NOTE

    # Step 4: clamp relevance_score to valid range
    raw_score = float(src.get("relevance_score", 0.5))
    clamped = max(0.0, min(1.0, raw_score))
    if clamped != raw_score:
        src = dict(src)
        src["relevance_score"] = clamped

    return src
