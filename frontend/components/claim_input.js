/**
 * ClaimInput component.
 *
 * Form that accepts a raw political claim from the user and submits it
 * for analysis. Handles input validation, submission state, and error display.
 *
 * Behavior:
 *   - Text area with a 2000-character limit (claims must be specific enough
 *     to be verifiable; vague inputs are rejected with a hint).
 *   - Optional URL field: user may provide a source link they want checked
 *     as part of the analysis.
 *   - On submit: POST to /api/claims, then poll /api/claims/:id/judgment
 *     until the analysis pipeline completes and a Judgment is available.
 *   - Displays a progress indicator during analysis with stage labels
 *     (Fetching sources → Evaluating → Rating → Symmetry check).
 *
 * Emits:
 *   judgment-ready  {Judgment}  When the analysis pipeline returns a result.
 */
