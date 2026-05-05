# GradedFacts E2E Tests

Browser-based end-to-end tests using [Playwright](https://playwright.dev/) and [pytest-playwright](https://playwright.dev/python/docs/pytest-plugin).

## Prerequisites

### 1 — Install Python dependencies

```bash
pip install playwright==1.59.0 pytest-playwright==0.7.2 pytest-base-url==2.1.0
```

All three are included in `requirements.txt` under the dev section.

### 2 — Install the Chromium browser

```bash
playwright install chromium
```

This downloads the Chromium binary used for headless testing (~170 MB).  
Run once per environment; not required for the unit test suite.

### 3 — Start the GradedFacts server

```bash
uvicorn backend.api:app --host 0.0.0.0 --port 8080
```

The E2E tests connect to `http://localhost:8080` by default.  
API keys (`ANTHROPIC_API_KEY`, `BRAVE_API_KEY`, `MISTRAL_API_KEY`) must be set
in `.env` for tests that trigger real analysis (see below).

---

## Running the tests

### All E2E tests (requires server + API keys for pipeline tests)

```bash
pytest tests/e2e/ -m e2e -v
```

### UI-only tests (no API keys required — server only)

```bash
pytest tests/e2e/test_ui.py -v
```

### Disagreement mock test only (no server or API keys required)

```bash
pytest tests/e2e/test_claim_pipeline.py::TestClaimPipeline::test_disagreement_shows_speculative_and_model_labels -v
```

### With a non-default server address

```bash
pytest tests/e2e/ -m e2e --base-url http://staging.example.com
```

### Headed mode (watch the browser)

```bash
pytest tests/e2e/ -m e2e --headed
```

### Slow down execution (useful for debugging)

```bash
pytest tests/e2e/ -m e2e --headed --slowmo 500
```

---

## Test inventory

### `test_ui.py` — Static UI tests (server only, no API keys)

| Test | What it checks |
|------|---------------|
| `test_logo_is_clickable_and_navigates_home` | Wordmark link navigates to `/` from any page |
| `test_about_page_loads_and_contains_independence_phrase` | `/about` renders and contains key independence claim |
| `test_methodology_page_loads_and_contains_hard_rules` | `/methodology` renders and contains "Ten Hard Rules" |
| `test_homepage_shows_one_claim_per_check_text` | Homepage shows "One claim per check" static text |
| `test_footer_contains_hosted_in_switzerland` | Footer Swiss hosting disclosure is present |

### `test_claim_pipeline.py` — Pipeline tests

| Test | Requires | What it checks |
|------|----------|----------------|
| `test_happy_path_verified_rating` | Server + API keys | Verifiable claim → VERIFIED badge |
| `test_vague_claim_returns_missing` | Server + API keys | Vague claim → MISSING badge |
| `test_short_claim_returns_error` | Server only | < 10 chars → 400 error message |
| `test_disagreement_shows_speculative_and_model_labels` | None (mocked) | Disagreement → SPECULATIVE + both model labels |

---

## Separation from unit tests

E2E tests are excluded from the normal `pytest tests/` run via `norecursedirs = e2e`
in `pytest.ini`.  All E2E tests also carry `@pytest.mark.e2e` for explicit
filtering.

```bash
# Unit tests only (default; e2e directory skipped):
pytest tests/

# E2E tests only:
pytest tests/e2e/ -m e2e

# Everything (unit + E2E, requires server + API keys):
pytest tests/ tests/e2e/
```

---

## Timeouts

Pipeline tests that trigger real LLM analysis allow up to **120 seconds** for
a result to appear (two model calls + web search + HTMX polling).  
UI-only and mock tests use a 5–10 second timeout.

---

## Do NOT run against production

These tests submit real claims to whatever server `--base-url` points to.
Always verify you are targeting a local or staging instance before running
the pipeline tests.
