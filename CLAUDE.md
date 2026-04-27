# TransparencyPuzzle

A politically independent fact-checking and analysis tool supporting democratic transparency. Founded in Switzerland. No funding from political parties, PACs, or politically dependent media.

## Mission

TransparencyPuzzle helps citizens evaluate political statements, claims, and narratives against verifiable facts — without taking sides, without ideological agenda.

## Epistemic Framework

Every analysis uses a consistent rating system:

| Status | Color | Meaning |
|--------|-------|---------|
| **Verified** | Green | Factually correct with verifiable sources |
| **Speculative** | Yellow | Plausible but not conclusively provable |
| **Debunked** | Red | Factually false, counter-evidence available |
| **Missing** | Gray | Puzzle pieces still outstanding, judgment withheld |

**No conclusion without sufficient puzzle pieces.** Incomplete evidence is always explicitly labeled as such.

## Core Principles

### Symmetry Principle
Every analysis method applied to one political side is applied identically to all others. No double standards, no exceptions.

### Transparency Principle
Every decision is traceable. Sources are always cited in full. Rating logic is publicly visible.

### Uncertainty Principle
"We don't know" is a valid and important answer. Uncertainty is never concealed or downplayed.

### Revision Principle
New facts can change existing judgments. Revisions are documented with timestamp and rationale. Older judgments are never silently overwritten — they are archived.

### Independence Principle
- No funding from political parties, PACs, or politically dependent media
- Full disclosure of every funding source
- Neither influenced by US Democrats nor Republicans (or equivalent parties in other countries)

## Tech Stack

- **Backend**: Python
- **Frontend**: Web (browser-based)
- **AI Verification**: Anthropic API (Claude) — for structured analysis and source evaluation
- **Source Checking**: Web Search — for current primary sources and cross-referencing

## Development Guidelines

### General
- No code without clear mapping to an epistemic status
- Source parsing and storage are core features, not afterthoughts
- All ratings are stored immutably; revisions create new entries, not overwrites

### Anthropic API
- Enable prompt caching for recurring analysis contexts
- Claude responses are rated "speculative" until supported by external sources
- Model selection: `claude-sonnet-4-6` as default, `claude-opus-4-7` for complex analyses

### Source Quality
Sources are classified by tier (Primary / Secondary / Tertiary) and by independence. No anonymous sources without explicit justification.

### Testing
- Symmetry tests: same analysis pipeline applied to politically opposing claims
- Regression tests for revisions: ensure new judgments correctly archive prior ones

## Project Structure (target)

```
transparencypuzzle/
├── backend/          # Python API
│   ├── analysis/     # Analysis engine (Epistemic Framework)
│   ├── sources/      # Source fetching and evaluation
│   └── db/           # Immutable judgment storage with revision history
├── frontend/         # Web UI
│   └── components/   # Puzzle visualization (Green/Yellow/Red/Gray)
└── CLAUDE.md
```
