# GradedFacts

A politically independent fact-checking tool that helps citizens evaluate political claims against verifiable evidence. Founded in Switzerland. No funding from political parties, PACs, or politically dependent media.

## How it works

Submit a political claim. GradedFacts searches for sources, evaluates them, and returns a structured judgment using a four-status epistemic framework:

| Status | Color | Meaning |
|--------|-------|---------|
| Verified | Green | Factually correct with verifiable sources |
| Speculative | Yellow | Plausible but not conclusively provable |
| Debunked | Red | Counter-evidence actively contradicts the claim |
| Missing | Gray | Insufficient evidence to issue any judgment |

Every judgment cites its sources. Every revision is archived. Every method applied to one political side is applied identically to all others.

## Project structure

```
gradedfacts/
├── backend/
│   ├── api.py                   # FastAPI app, HTML/HTMX endpoints, background analysis tasks
│   ├── config.py                # Settings loaded from environment (pydantic-settings)
│   ├── schemas.py               # Pydantic request/response models
│   ├── analysis/
│   │   ├── engine.py            # Two-phase epistemic pipeline (web search → structured judgment)
│   │   ├── rating.py            # EpistemicRating enum and derivation logic
│   │   └── symmetry.py          # Symmetry principle enforcement across political actors
│   ├── sources/
│   │   ├── evaluator.py         # Source independence and quality scoring (entry point)
│   │   ├── independence_registry.py  # Registry of known politically compromised institutions
│   │   ├── classifier.py        # Primary / Secondary / Tertiary tier classification
│   │   ├── fetcher.py           # Web source discovery and content retrieval
│   │   └── registries/
│   │       └── us_sources.json  # Curated US source domain registry with tier + independence data
│   └── db/
│       ├── models.py            # SQLAlchemy models: Claim, EvaluatedSource, Judgment, Revision
│       ├── session.py           # DB session factory and dependency
│       ├── storage.py           # Append-only judgment storage (reads unrestricted; writes never mutate)
│       ├── revisions.py         # Revision history lifecycle and audit trail
│       └── rate_limit.py        # Per-IP request rate limiting
├── frontend/
│   ├── styles/
│   │   └── main.css             # Design tokens and all component styles
│   └── templates/
│       ├── base.html            # Shared layout: header, footer, HTMX script
│       ├── index.html           # Home page: trust block, coverage notice, claim form
│       ├── methodology.html     # /methodology: epistemic framework docs for journalists
│       └── partials/
│           ├── analyzing.html   # HTMX polling partial (loading state)
│           ├── error.html       # HTMX error partial
│           └── result.html      # HTMX result partial: judgment, sources, revision trail
├── tests/
│   ├── test_rating.py
│   ├── test_evaluator.py
│   ├── test_independence_registry.py
│   ├── test_rate_limit.py
│   └── test_us_sources_registry.py
├── deploy/
│   └── infomaniak.md            # Deployment notes for Infomaniak hosting
├── Procfile                     # web: uvicorn backend.api:app --host 0.0.0.0 --port $PORT
├── runtime.txt                  # python-3.12
├── requirements.txt
├── CLAUDE.md
└── README.md
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add ANTHROPIC_API_KEY
uvicorn backend.api:app --reload
```

## Running tests

```bash
pytest tests/
```

## Core principles

- **Symmetry** — identical analytical methods across the political spectrum, no exceptions
- **Transparency** — every decision is traceable; all sources cited; methodology is open source
- **Uncertainty** — "we don't know" (Missing) is a first-class answer, never suppressed
- **Revision** — new evidence updates verdicts; prior verdicts are archived, never deleted
- **Independence** — no political funding; full public disclosure of all funding sources

## Contributing

All contributions must pass symmetry review: if your change affects how one political actor is analysed, it must apply equally to all others. See [/methodology](https://gradedfacts.com/methodology) for the full epistemic framework.
