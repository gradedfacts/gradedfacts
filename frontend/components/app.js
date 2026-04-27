/**
 * Application root.
 *
 * Bootstraps the SPA, initializes the API client, and mounts all top-level
 * components into #app. Owns global application state (current claim,
 * active judgment, loading/error flags) and passes it down via props or
 * a lightweight store.
 *
 * Component tree:
 *   App
 *   ├── ClaimInput       (components/claim_input.js)
 *   ├── PuzzleBoard      (components/puzzle_board.js)
 *   ├── SourcePanel      (components/source_panel.js)
 *   ├── RevisionTrail    (components/revision_trail.js)
 *   └── SymmetryReport   (components/symmetry_report.js)
 */
