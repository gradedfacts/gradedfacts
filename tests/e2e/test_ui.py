"""
E2E tests for GradedFacts static UI elements.

All tests in this file test rendered HTML structure and navigation only —
no LLM calls, no API keys required.  A running server on localhost:8080 is
the only prerequisite.
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
class TestStaticUI:
    """Navigation, page content, and structural UI invariants."""

    def test_logo_is_clickable_and_navigates_home(self, page: Page) -> None:
        """
        The site wordmark (logo link) must navigate to / from any page.
        Verified from /methodology to confirm it works outside the homepage.
        """
        page.goto("/methodology")

        wordmark = page.locator("a.site-wordmark")
        expect(wordmark).to_be_visible()
        wordmark.click()

        expect(page).to_have_url("/")

    def test_about_page_loads_and_contains_independence_phrase(
        self, page: Page
    ) -> None:
        """/about renders and contains the key independence claim."""
        page.goto("/about")

        expect(page).to_have_title("GradedFacts")
        expect(
            page.locator("text=institutional independence takes precedence")
        ).to_be_visible()

    def test_methodology_page_loads_and_contains_hard_rules(
        self, page: Page
    ) -> None:
        """/methodology renders and contains the 'Ten Hard Rules' section."""
        page.goto("/methodology")

        expect(page).to_have_title("GradedFacts")
        expect(page.locator("text=The Ten Hard Rules")).to_be_visible()

    def test_homepage_shows_one_claim_per_check_text(self, page: Page) -> None:
        """Homepage footer of the form shows 'One claim per check' static text."""
        page.goto("/")

        expect(
            page.locator("text=One claim per check")
        ).to_be_visible()

    def test_footer_contains_hosted_in_switzerland(self, page: Page) -> None:
        """Every page footer must carry the Swiss hosting disclosure."""
        page.goto("/")

        footer = page.locator("footer.site-footer")
        expect(footer).to_be_visible()
        expect(footer.locator("text=Hosted in Switzerland")).to_be_visible()
