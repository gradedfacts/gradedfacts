"""
Tests for backend/sources/registries/us_sources.json and its loader.

Covers: schema validity, required source entries, independence symmetry,
tier consistency, and the lookup_source() helper.
"""

import json
from pathlib import Path

import pytest

REGISTRY_PATH = Path(__file__).parent.parent / "backend/sources/registries/us_sources.json"

_REQUIRED_FIELDS = {"name", "domain", "tier", "is_independent", "category", "independence_note"}
_VALID_TIERS = {"primary", "secondary", "tertiary"}
_VALID_CATEGORIES = {
    "government", "news_agency", "newspaper", "broadcaster",
    "academic", "fact_checker", "nonprofit", "social_media",
    "data_portal",  # commercial or institutional statistics aggregators (e.g. Statista)
}


@pytest.fixture(scope="module")
def registry() -> dict:
    with REGISTRY_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def sources(registry) -> list[dict]:
    return registry["sources"]


# ── Schema validity ────────────────────────────────────────────────────────────

class TestSchema:
    def test_json_is_valid(self, registry):
        assert isinstance(registry, dict)

    def test_has_meta_section(self, registry):
        assert "_meta" in registry
        assert "version" in registry["_meta"]
        assert "last_updated" in registry["_meta"]

    def test_has_sources_list(self, sources):
        assert isinstance(sources, list)

    def test_source_count_in_range(self, sources):
        assert 30 <= len(sources) <= 40, f"Expected 30–40 sources, got {len(sources)}"

    def test_all_required_fields_present(self, sources):
        for src in sources:
            missing = _REQUIRED_FIELDS - src.keys()
            assert not missing, f"{src.get('name','?')} is missing fields: {missing}"

    def test_all_tiers_are_valid(self, sources):
        for src in sources:
            assert src["tier"] in _VALID_TIERS, (
                f"{src['name']} has invalid tier: {src['tier']!r}"
            )

    def test_all_categories_are_valid(self, sources):
        for src in sources:
            assert src["category"] in _VALID_CATEGORIES, (
                f"{src['name']} has invalid category: {src['category']!r}"
            )

    def test_is_independent_has_valid_value(self, sources):
        """
        Primary/secondary sources use JSON booleans.
        Tertiary sources use "neutral" or "not_independent" (Rule 1).
        """
        _TERTIARY_VALUES = {"neutral", "not_independent"}
        for src in sources:
            val = src["is_independent"]
            if src["tier"] == "tertiary":
                assert val in _TERTIARY_VALUES, (
                    f"{src['name']}: tertiary is_independent must be 'neutral' or "
                    f"'not_independent', got {val!r}"
                )
            else:
                assert isinstance(val, bool), (
                    f"{src['name']}: primary/secondary is_independent must be a "
                    f"JSON boolean, got {type(val)}"
                )

    def test_no_duplicate_domains(self, sources):
        domains = [src["domain"] for src in sources]
        assert len(domains) == len(set(domains)), "Duplicate domains found in registry"

    def test_no_empty_independence_notes(self, sources):
        for src in sources:
            assert src["independence_note"].strip(), (
                f"{src['name']} has an empty independence_note"
            )

    def test_non_independent_sources_have_substantive_notes(self, sources):
        for src in sources:
            val = src["is_independent"]
            is_not_independent = (val is False) or (val == "not_independent")
            if is_not_independent:
                note = src["independence_note"]
                assert len(note) > 80, (
                    f"{src['name']}: independence_note for non-independent source is too brief"
                )


# ── Required sources ───────────────────────────────────────────────────────────

class TestRequiredSources:
    """Every source explicitly requested by the user must be present."""

    def _get_domains(self, sources):
        return {src["domain"] for src in sources}

    @pytest.mark.parametrize("domain", [
        "bls.gov",
        "bea.gov",
        "fred.stlouisfed.org",
        "census.gov",
        "cbo.gov",
        "pacer.gov",
        "federalregister.gov",
        "c-span.org",
        "apnews.com",
        "reuters.com",
        "afp.com",
        "bbc.com",
        "npr.org",
        "pbs.org",
        "nytimes.com",
        "washingtonpost.com",
        "wsj.com",
        "politico.com",
        "thehill.com",
        "foxnews.com",
        "msnbc.com",
        "cnn.com",
        "breitbart.com",
        "truthsocial.com",
    ])
    def test_required_source_present(self, sources, domain):
        domains = {src["domain"] for src in sources}
        assert domain in domains, f"Required source '{domain}' is missing from registry"


# ── Independence symmetry ──────────────────────────────────────────────────────

class TestIndependenceSymmetry:
    """
    Independence judgments must be symmetric: if a left-aligned outlet is marked
    not-independent, right-aligned outlets with equivalent documentation must also
    be marked not-independent, and vice versa.
    """

    def _get(self, sources, domain):
        return next((s for s in sources if s["domain"] == domain), None)

    def test_fox_news_is_not_independent(self, sources):
        src = self._get(sources, "foxnews.com")
        assert src is not None
        assert src["is_independent"] is False, "Fox News must be marked not-independent"

    def test_msnbc_is_not_independent(self, sources):
        src = self._get(sources, "msnbc.com")
        assert src is not None
        assert src["is_independent"] is False, "MSNBC must be marked not-independent"

    def test_breitbart_is_not_independent(self, sources):
        src = self._get(sources, "breitbart.com")
        assert src is not None
        assert src["is_independent"] == "not_independent", (
            "Breitbart is tertiary — must use 'not_independent' per Rule 1"
        )

    def test_truth_social_is_not_independent(self, sources):
        src = self._get(sources, "truthsocial.com")
        assert src is not None
        assert src["is_independent"] == "not_independent", (
            "Truth Social is tertiary — must use 'not_independent' per Rule 1"
        )

    def test_wire_services_are_independent(self, sources):
        for domain in ("apnews.com", "reuters.com", "afp.com"):
            src = self._get(sources, domain)
            assert src is not None
            assert src["is_independent"] is True, f"{domain} should be independent"

    def test_government_statistical_agencies_are_independent(self, sources):
        for domain in ("bls.gov", "bea.gov", "census.gov", "cbo.gov"):
            src = self._get(sources, domain)
            assert src is not None
            assert src["is_independent"] is True, f"{domain} should be independent"

    def test_nonindependent_count_not_skewed_by_direction(self, sources):
        """
        Both politically left-aligned and right-aligned outlets must appear in
        the not-independent list.  A registry that flags only one political
        direction would violate the symmetry principle.
        """
        not_indep = [s for s in sources if s["is_independent"] is not True and s["is_independent"] != "neutral"]
        notes = " ".join(s["independence_note"].lower() for s in not_indep)
        # At minimum we need documentation of both directions
        assert "republican" in notes or "trump" in notes or "right" in notes, (
            "No right-aligned sources flagged as not-independent"
        )
        assert "democratic" in notes or "left" in notes or "democrat" in notes, (
            "No left-aligned sources flagged as not-independent"
        )


# ── Tier consistency ───────────────────────────────────────────────────────────

class TestTierConsistency:
    def _get(self, sources, domain):
        return next((s for s in sources if s["domain"] == domain), None)

    def test_government_stats_agencies_are_primary(self, sources):
        for domain in ("bls.gov", "bea.gov", "fred.stlouisfed.org", "census.gov",
                       "cbo.gov", "gao.gov", "pacer.gov"):
            src = self._get(sources, domain)
            if src:
                assert src["tier"] == "primary", f"{domain} should be primary tier"

    def test_wire_services_are_secondary(self, sources):
        for domain in ("apnews.com", "reuters.com", "afp.com"):
            src = self._get(sources, domain)
            assert src is not None
            assert src["tier"] == "secondary"

    def test_breitbart_is_tertiary(self, sources):
        src = self._get(sources, "breitbart.com")
        assert src is not None
        assert src["tier"] == "tertiary"

    def test_truth_social_is_tertiary(self, sources):
        src = self._get(sources, "truthsocial.com")
        assert src is not None
        assert src["tier"] == "tertiary"

    def test_at_least_one_primary_source(self, sources):
        primaries = [s for s in sources if s["tier"] == "primary"]
        assert len(primaries) >= 5

    def test_majority_are_secondary(self, sources):
        secondaries = [s for s in sources if s["tier"] == "secondary"]
        assert len(secondaries) > len(sources) // 2


# ── Loader helper ─────────────────────────────────────────────────────────────

class TestLookupSource:
    def test_exact_domain_match(self):
        from backend.sources.registries import lookup_source
        result = lookup_source("apnews.com")
        assert result is not None
        assert result["name"] == "Associated Press"

    def test_url_with_path_matches(self):
        from backend.sources.registries import lookup_source
        result = lookup_source("https://www.bls.gov/news.release/cpi.nr0.htm")
        assert result is not None
        assert result["domain"] == "bls.gov"

    def test_unknown_domain_returns_none(self):
        from backend.sources.registries import lookup_source
        assert lookup_source("unknownsource.example.com") is None

    def test_lookup_is_case_insensitive(self):
        from backend.sources.registries import lookup_source
        assert lookup_source("REUTERS.COM/article") is not None

    def test_fox_news_lookup(self):
        from backend.sources.registries import lookup_source
        result = lookup_source("https://www.foxnews.com/politics/example")
        assert result is not None
        assert result["is_independent"] is False
