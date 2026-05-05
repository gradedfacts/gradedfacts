"""
E2E test configuration for GradedFacts.

Requires a running server on BASE_URL (default: http://localhost:8080).
Override the base URL with: pytest tests/e2e/ --base-url http://other-host:port

Browser: Chromium headless (default pytest-playwright setting).
"""

import pytest

# Default server address for local E2E runs.
_DEFAULT_BASE_URL = "http://localhost:8080"


@pytest.fixture(scope="session")
def base_url(pytestconfig: pytest.Config) -> str:
    """Base URL for all E2E requests. Override with --base-url."""
    return pytestconfig.getoption("base_url") or _DEFAULT_BASE_URL


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict, base_url: str) -> dict:
    """Inject base_url into every browser context so relative URLs work."""
    return {**browser_context_args, "base_url": base_url}
