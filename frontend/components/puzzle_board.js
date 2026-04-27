/**
 * PuzzleBoard component.
 *
 * Renders the epistemic judgment as an interactive puzzle tile grid.
 * Each tile represents one piece of evidence; its color reflects the
 * rating of that piece:
 *
 *   Green  — evidence is verified
 *   Yellow — evidence is speculative
 *   Red    — evidence is debunked
 *   Gray   — evidence is missing or awaited
 *
 * The overall judgment rating is derived from the aggregate of tiles
 * and displayed as a summary badge above the grid.
 *
 * Props:
 *   judgment  {Judgment}  The current active judgment for the claim.
 *
 * Emits:
 *   tile-click  {sourceId}  When the user clicks a tile to view its source.
 */
