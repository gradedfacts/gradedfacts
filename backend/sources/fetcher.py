"""
Web source fetcher.

Discovers and retrieves source documents relevant to a given claim.
Uses web search APIs to find candidate URLs, then fetches and extracts
the text content of each page for downstream evaluation.

Responsibilities:
    - Accept a normalized claim string and return a list of RawSource objects.
    - Execute web searches against configured search providers.
    - Download and parse HTML into clean plaintext (no scripts, ads, boilerplate).
    - Respect robots.txt and rate limits.
    - Surface fetch errors as structured warnings rather than hard failures,
      so a single unreachable URL does not abort the entire analysis.
"""
