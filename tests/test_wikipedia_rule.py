"""
Tests for the Wikipedia = Tertiary hard rule.

Covers:
  - classifier.is_wikipedia() domain detection
  - evaluator.evaluate_source() tier enforcement for Wikipedia URLs
  - Rule applies regardless of what Claude or the registry assigned
"""

import pytest

from backend.sources.classifier import is_wikipedia, WIKIPEDIA_DOMAINS
from backend.sources.evaluator import evaluate_source


# ── classifier.is_wikipedia() ─────────────────────────────────────────────────

class TestIsWikipedia:

    @pytest.mark.parametrize("url", [
        "https://en.wikipedia.org/wiki/Unemployment",
        "https://de.wikipedia.org/wiki/Inflation",
        "https://fr.wikipedia.org/wiki/Article",
        "https://wikipedia.org/wiki/Something",
        "https://upload.wikimedia.org/wikipedia/commons/something.jpg",
        "https://www.wikimedia.org/",
        "http://en.wikipedia.org/wiki/Topic",
    ])
    def test_wikipedia_urls_detected(self, url):
        assert is_wikipedia(url) is True, f"Expected True for {url!r}"

    @pytest.mark.parametrize("url", [
        "https://www.reuters.com/article/example",
        "https://www.nytimes.com/2024/01/01/article.html",
        "https://notwikipedia.org/article",
        "https://fakewikipedia.org/page",
        "https://en.wikipedia.org.malicious.example.com/wiki/Article",
        "",
        "not-a-url",
    ])
    def test_non_wikipedia_urls_not_detected(self, url):
        assert is_wikipedia(url) is False, f"Expected False for {url!r}"

    def test_wikipedia_domains_constant_contains_expected_entries(self):
        assert "wikipedia.org" in WIKIPEDIA_DOMAINS
        assert "wikimedia.org" in WIKIPEDIA_DOMAINS


# ── evaluator.evaluate_source() Wikipedia enforcement ─────────────────────────

class TestEvaluateSourceWikipediaRule:

    def _wikipedia_src(self, tier: str = "secondary", **kwargs) -> dict:
        return {
            "url": "https://en.wikipedia.org/wiki/Unemployment_in_the_United_States",
            "tier": tier,
            "is_independent": True,
            "relevance_score": 0.85,
            "supports_claim": True,
            **kwargs,
        }

    def test_wikipedia_primary_downgraded_to_tertiary(self):
        result = evaluate_source(self._wikipedia_src(tier="primary"))
        assert result["tier"] == "tertiary"

    def test_wikipedia_secondary_downgraded_to_tertiary(self):
        result = evaluate_source(self._wikipedia_src(tier="secondary"))
        assert result["tier"] == "tertiary"

    def test_wikipedia_already_tertiary_unchanged(self):
        result = evaluate_source(self._wikipedia_src(tier="tertiary"))
        assert result["tier"] == "tertiary"

    def test_wikipedia_wikimedia_url_also_downgraded(self):
        src = {
            "url": "https://upload.wikimedia.org/wikipedia/commons/example.png",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.7,
            "supports_claim": True,
        }
        result = evaluate_source(src)
        assert result["tier"] == "tertiary"

    def test_non_wikipedia_source_tier_unchanged(self):
        src = {
            "url": "https://www.reuters.com/article/example",
            "tier": "secondary",
            "is_independent": True,
            "relevance_score": 0.85,
            "supports_claim": True,
        }
        result = evaluate_source(src)
        assert result["tier"] == "secondary"

    def test_wikipedia_rule_does_not_mutate_input(self):
        src = self._wikipedia_src(tier="primary")
        original_tier = src["tier"]
        _ = evaluate_source(src)
        assert src["tier"] == original_tier

    def test_wikipedia_rule_preserves_other_fields(self):
        src = self._wikipedia_src(tier="secondary")
        result = evaluate_source(src)
        assert result["url"] == src["url"]
        assert result["is_independent"] == src["is_independent"]
        assert result["relevance_score"] == src["relevance_score"]
        assert result["supports_claim"] == src["supports_claim"]

    @pytest.mark.parametrize("lang_subdomain", ["en", "de", "fr", "es", "ja", "zh"])
    def test_all_language_subdomains_are_tertiary(self, lang_subdomain):
        src = {
            "url": f"https://{lang_subdomain}.wikipedia.org/wiki/Some_Article",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        }
        result = evaluate_source(src)
        assert result["tier"] == "tertiary", (
            f"Expected tertiary for {lang_subdomain}.wikipedia.org"
        )
