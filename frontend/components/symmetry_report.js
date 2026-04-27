/**
 * SymmetryReport component.
 *
 * Sidebar that displays the SymmetryReport attached to the active Judgment,
 * confirming that the Symmetry Principle has been upheld.
 *
 * Displays:
 *   - List of comparable claims analyzed for other political actors /
 *     parties / ideologies using the same method.
 *   - Link to each comparable judgment for direct cross-reference.
 *   - A green "Symmetry confirmed" banner when equivalents exist, or an
 *     amber "Pending symmetry check" notice when no comparable analysis
 *     has been run yet (the current judgment is not blocked, but the gap
 *     is surfaced transparently).
 *
 * Props:
 *   report  {SymmetryReport}  The symmetry report from the active judgment.
 */
