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
"""
