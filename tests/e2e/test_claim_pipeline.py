"""
E2E tests for the GradedFacts claim analysis pipeline.

Tests 1–3 require a running server with valid API keys (ANTHROPIC_API_KEY,
BRAVE_API_KEY).  Test 4 (disagreement display) mocks all network responses at
the Playwright layer so it runs without API keys.

Timeouts
--------
Real analyses involve two LLM calls and a web search and typically take
30–90 seconds.  RESULT_TIMEOUT is set to 120 s to absorb slow API responses.
"""

import pytest
from playwright.sync_api import Page, Route, Request, expect

# Real claim for the happy-path test — specific, verifiable, and stable.
_CLAIM_VERIFIABLE = "The Swiss Federal Council has 7 members"
_CLAIM_VAGUE = "politicians lie"
_CLAIM_TOO_SHORT = "a"

# Long timeout covers two LLM calls + web search + HTMX polling interval.
_RESULT_TIMEOUT_MS = 120_000

# Fake claim_id used in the disagreement mock.
_MOCK_CLAIM_ID = "mock-disagree-0001"

# Pre-crafted HTML returned by the mock for the poll endpoint.
# Includes [Claude Analysis] and [Mistral Analysis] labels so the test can
# assert them regardless of the real template implementation.
_MOCK_RESULT_HTML = f"""\
<div id="result">
  <div class="card" style="margin-bottom:1.25rem">
    <div class="board-header">
      <span class="rating-badge speculative">
        <span class="rating-dot"></span>speculative
      </span>
      <span class="board-verdict">Claim is speculative</span>
    </div>
    <p class="board-rationale">
      Claude and Mistral disagree on this claim.
      Rating defaults to Speculative when models conflict.
    </p>
  </div>
  <div class="result-columns">
    <div class="card"><p class="panel-heading">Sources (0)</p></div>
    <div class="card"><p class="panel-heading">Symmetry check</p></div>
  </div>
  <div class="card" style="margin-top:1.25rem">
    <p class="panel-heading">Judgment history (1)</p>
    <ol class="judgment-list">
      <li class="judgment-entry">
        <details open>
          <summary class="judgment-summary">
            <span class="rating-badge speculative">
              <span class="rating-dot"></span>speculative
            </span>
            <span class="judgment-current-tag">current</span>
          </summary>
          <div class="judgment-body">
            <p class="judgment-rationale">
              Claude and Mistral disagree; defaulting to Speculative per consensus rules.
            </p>
            <p class="judgment-analyst">
              [Claude Analysis]: claude-sonnet-4-6 &middot;
              [Mistral Analysis]: mistral-small-latest
            </p>
          </div>
        </details>
      </li>
    </ol>
  </div>
</div>
"""

# Analyzing partial that HTMX will render while polling — uses the mock claim_id.
_MOCK_ANALYZING_HTML = f"""\
<div id="result"
     hx-get="/ui/claims/{_MOCK_CLAIM_ID}/poll"
     hx-trigger="every 2s"
     hx-swap="outerHTML">
  <div class="loading-section">
    <div class="loading-row">
      <div class="spinner"></div>
      <span>Searching sources…</span>
    </div>
    <p class="loading-note">Analysis typically takes 1–2 minutes.</p>
  </div>
</div>
"""


@pytest.mark.e2e
class TestClaimPipeline:
    """End-to-end tests for the claim submission and result display pipeline."""

    def test_happy_path_verified_rating(self, page: Page) -> None:
        """
        Submit a specific, stable, verifiable claim and expect a VERIFIED badge.

        Requires: running server + ANTHROPIC_API_KEY + BRAVE_API_KEY.
        """
        page.goto("/")

        page.locator("textarea[name='text']").fill(_CLAIM_VERIFIABLE)
        page.locator("button[type='submit']").click()

        verified_badge = page.locator(".rating-badge.verified")
        expect(verified_badge).to_be_visible(timeout=_RESULT_TIMEOUT_MS)

    def test_vague_claim_returns_missing(self, page: Page) -> None:
        """
        Submit a content-free vague claim and expect a MISSING badge.

        The specificity pre-flight gate rejects purely generalised claims
        without triggering a full LLM analysis — so this is faster than
        test_happy_path_verified_rating but still requires a running server.

        Requires: running server + ANTHROPIC_API_KEY (specificity gate only).
        """
        page.goto("/")

        page.locator("textarea[name='text']").fill(_CLAIM_VAGUE)
        page.locator("button[type='submit']").click()

        missing_badge = page.locator(".rating-badge.missing")
        expect(missing_badge).to_be_visible(timeout=_RESULT_TIMEOUT_MS)

    def test_short_claim_returns_error(self, page: Page) -> None:
        """
        Submit a claim below the 10-character minimum and expect a 400 error.

        Does NOT require API keys — the length check fires before any LLM call.
        Requires: running server only.
        """
        page.goto("/")

        page.locator("textarea[name='text']").fill(_CLAIM_TOO_SHORT)
        page.locator("button[type='submit']").click()

        error_text = page.locator("text=Please enter at least 10 characters.")
        expect(error_text).to_be_visible(timeout=5_000)

    def test_disagreement_shows_speculative_and_model_labels(
        self, page: Page
    ) -> None:
        """
        When primary and secondary models disagree the UI shows SPECULATIVE
        and identifies both [Claude Analysis] and [Mistral Analysis].

        Network responses are mocked at the Playwright layer so this test
        runs without a server or API keys.
        """

        def handle_analyze(route: Route, request: Request) -> None:
            """Return the analyzing partial referencing the mock claim_id."""
            route.fulfill(
                status=200,
                content_type="text/html",
                body=_MOCK_ANALYZING_HTML,
            )

        def handle_poll(route: Route, request: Request) -> None:
            """Return the pre-crafted disagreement result immediately."""
            route.fulfill(
                status=200,
                content_type="text/html",
                body=_MOCK_RESULT_HTML,
            )

        page.route("**/ui/analyze/consensus", handle_analyze)
        page.route(f"**/ui/claims/{_MOCK_CLAIM_ID}/poll", handle_poll)

        page.goto("/")
        page.locator("textarea[name='text']").fill(
            "Will GDP growth exceed 3 percent next year?"
        )
        page.locator("button[type='submit']").click()

        speculative_badge = page.locator(".rating-badge.speculative")
        expect(speculative_badge).to_be_visible(timeout=10_000)

        expect(page.locator("text=[Claude Analysis]")).to_be_visible(timeout=5_000)
        expect(page.locator("text=[Mistral Analysis]")).to_be_visible(timeout=5_000)
