"""
Source quality evaluator.

Post-processes raw source dicts from Claude's judgment tool call:
  1. Applies the independence registry — compromised institutions get
     is_independent=False, relevance_score capped, and a canonical
     affiliation_note (overrides whatever Claude returned).
  2. Ensures every non-independent source carries an affiliation_note.
  3. Clamps relevance_score to [0.0, 1.0].

The evaluator never mutates input dicts — it returns new ones.
"""

from __future__ import annotations

from backend.sources.independence_registry import apply_independence_override

_GENERIC_AFFILIATION_NOTE = (
    "Source is not editorially independent; specific affiliation not documented."
)


def evaluate_source(src: dict) -> dict:
    """
    Apply all quality checks to a single source dict from Claude's judgment.

    Returns a new dict (or the same object if no changes are needed).
    """
    # Step 1: apply independence registry overrides
    src = apply_independence_override(src)

    # Step 2: guarantee non-independent sources carry an explanation
    if not src.get("is_independent", True) and not src.get("affiliation_note"):
        src = dict(src)
        src["affiliation_note"] = _GENERIC_AFFILIATION_NOTE

    # Step 3: clamp relevance_score to valid range
    raw_score = float(src.get("relevance_score", 0.5))
    clamped = max(0.0, min(1.0, raw_score))
    if clamped != raw_score:
        src = dict(src)
        src["relevance_score"] = clamped

    return src
