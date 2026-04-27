/**
 * SourcePanel component.
 *
 * Lists all EvaluatedSources attached to the current judgment.
 * Each entry displays:
 *   - Source URL (clickable, opens in new tab)
 *   - Tier badge: Primary / Secondary / Tertiary
 *   - Independence flag: Independent / Affiliated (with affiliation note)
 *   - Relevance score (0–100)
 *   - Short excerpt from the source text relevant to the claim
 *
 * Sources are sorted by tier (Primary first) then by relevance score descending.
 * Anonymous sources are visually flagged with a warning and display the
 * recorded justification for their inclusion.
 *
 * Props:
 *   sources  {EvaluatedSource[]}  Evaluated sources from the active judgment.
 */
