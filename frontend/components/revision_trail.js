/**
 * RevisionTrail component.
 *
 * Renders the full ordered history of Judgments for a Claim as a
 * collapsible timeline, from the original verdict to the most recent.
 *
 * Each entry shows:
 *   - Timestamp of the judgment
 *   - Rating at that time (color-coded badge)
 *   - Analyst ID (human or Claude model version)
 *   - Rationale summary
 *   - Triggering evidence for revisions (what new fact changed the verdict)
 *   - Diff toggle: what changed between this and the previous judgment
 *
 * The most recent judgment is expanded by default; older ones are collapsed.
 * No judgment is ever hidden — the full audit trail is always accessible.
 *
 * Props:
 *   revisions  {Revision[]}  Ordered revision chain for the current claim.
 */
