# GradedFacts

A politically independent fact-checking tool that helps citizens evaluate political claims against verifiable evidence. Founded in Switzerland. No funding from political parties, PACs, or politically dependent media.

## How it works

Submit a political claim. GradedFacts fetches sources, evaluates them, and returns a structured judgment using a four-status epistemic framework:

| Status | Color | Meaning |
|--------|-------|---------|
| Verified | Green | Factually correct with verifiable sources |
| Speculative | Yellow | Plausible but not conclusively provable |
| Debunked | Red | Factually false; counter-evidence documented |
| Missing | Gray | Insufficient evidence to issue any judgment |

Every judgment cites its sources. Every revision is archived. Every method applied to one political side is applied identically to all others.

## Project structure

```
gradedfacts/
├── backend/
│   ├── analysis/
│   │   ├── engine.py       # Epistemic analysis pipeline
│   │   ├── rating.py       # EpistemicRating enum and assignment logic
│   │   └── symmetry.py     # Symmetry principle enforcement
│   ├── sources/
│   │   ├── fetcher.py      # Web source discovery and retrieval
│   │   ├── evaluator.py    # Source independence and quality scoring
│   │   └── classifier.py   # Primary / Secondary / Tertiary classification
│   └── db/
│       ├── models.py       # Claim, EvaluatedSource, Judgment, Revision models
│       ├── storage.py      # Append-only judgment storage
│       └── revisions.py    # Revision history and audit trail
├── frontend/
│   ├── index.html
│   ├── styles/main.css
│   └── components/
│       ├── app.js              # Application root
│       ├── claim_input.js      # Claim submission form
│       ├── puzzle_board.js     # Color-coded evidence tile grid
│       ├── source_panel.js     # Source list with tier and independence badges
│       ├── revision_trail.js   # Full judgment history timeline
│       └── symmetry_report.js  # Symmetry principle confirmation sidebar
├── requirements.txt
├── README.md
└── CLAUDE.md
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add ANTHROPIC_API_KEY
uvicorn backend.main:app --reload
```

## Core principles

- **Symmetry** — identical analytical methods across the political spectrum
- **Transparency** — every decision is traceable; all sources cited
- **Uncertainty** — "we don't know" is a first-class answer
- **Revision** — new evidence updates verdicts; old verdicts are archived, never deleted
- **Independence** — full public disclosure of all funding sources

## Contributing

All contributions must pass symmetry review: if your change affects how one political actor is analyzed, it must apply equally to all others.
