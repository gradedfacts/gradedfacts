"""
Tests for backend/sources/independence_registry.py.

Covers: lookup(), apply_independence_override(), COMPROMISED_SCORE_CAP,
and the registry entries for known compromised institutions.
"""

import pytest

from backend.sources.independence_registry import (
    COMPROMISED_SCORE_CAP,
    CompromisedEntry,
    apply_independence_override,
    lookup,
)


# ── lookup() ──────────────────────────────────────────────────────────────────

class TestLookup:
    def test_fbi_url_returns_entry(self):
        entry = lookup("https://www.fbi.gov/news/press-releases/2025/statement")
        assert entry is not None
        assert "FBI" in entry.institution
        assert entry.country == "US"

    def test_doj_url_returns_entry(self):
        entry = lookup("https://www.justice.gov/opa/press-release/2025/03/01")
        assert entry is not None
        assert "DOJ" in entry.institution
        assert entry.country == "US"

    def test_russian_rt_returns_entry(self):
        entry = lookup("https://www.rt.com/news/example")
        assert entry is not None
        assert entry.country == "RU"

    def test_russian_kremlin_returns_entry(self):
        entry = lookup("http://kremlin.ru/events/president/news/12345")
        assert entry is not None
        assert entry.country == "RU"

    def test_russian_tass_returns_entry(self):
        entry = lookup("https://tass.com/politics/12345")
        assert entry is not None
        assert entry.country == "RU"

    def test_chinese_xinhua_returns_entry(self):
        entry = lookup("http://www.xinhuanet.com/english/2025-01/01/c_1234.htm")
        assert entry is not None
        assert entry.country == "CN"

    def test_chinese_cgtn_returns_entry(self):
        entry = lookup("https://www.cgtn.com/story/example")
        assert entry is not None
        assert entry.country == "CN"

    def test_chinese_gov_cn_returns_entry(self):
        entry = lookup("https://www.gov.cn/xinwen/2025-01/01/content_12345.htm")
        assert entry is not None
        assert entry.country == "CN"

    def test_turkish_trt_returns_entry(self):
        entry = lookup("https://www.trtworld.com/asia/example")
        assert entry is not None
        assert entry.country == "TR"

    def test_hungarian_mtva_returns_entry(self):
        entry = lookup("https://www.mtva.hu/hirek/example")
        assert entry is not None
        assert entry.country == "HU"

    def test_belarusian_belta_returns_entry(self):
        entry = lookup("https://www.belta.by/world/view/example")
        assert entry is not None
        assert entry.country == "BY"

    def test_independent_news_returns_none(self):
        assert lookup("https://www.reuters.com/world/example") is None

    def test_bbc_returns_none(self):
        assert lookup("https://www.bbc.com/news/example") is None

    def test_nature_returns_none(self):
        assert lookup("https://www.nature.com/articles/example") is None

    def test_empty_url_returns_none(self):
        assert lookup("") is None

    def test_lookup_is_case_insensitive(self):
        assert lookup("HTTPS://WWW.FBI.GOV/PRESS") is not None

    def test_url_with_path_components_still_matches(self):
        # Pattern should match even when domain is buried in a longer URL string
        entry = lookup("https://subdomain.justice.gov/some/deep/path?q=1")
        assert entry is not None


# ── apply_independence_override() ─────────────────────────────────────────────

class TestApplyIndependenceOverride:
    _fbi_source = {
        "url": "https://www.fbi.gov/news/press-releases/2025/statement",
        "tier": "primary",
        "is_independent": True,
        "relevance_score": 0.9,
        "supports_claim": True,
    }

    def test_sets_is_independent_false(self):
        result = apply_independence_override(self._fbi_source)
        assert result["is_independent"] is False

    def test_caps_relevance_score_at_compromised_cap(self):
        result = apply_independence_override(self._fbi_source)
        assert result["relevance_score"] == COMPROMISED_SCORE_CAP

    def test_score_already_below_cap_is_preserved(self):
        src = {**self._fbi_source, "relevance_score": 0.5}
        result = apply_independence_override(src)
        assert result["relevance_score"] == 0.5

    def test_affiliation_note_is_set(self):
        result = apply_independence_override(self._fbi_source)
        assert result.get("affiliation_note")
        assert "Kash Patel" in result["affiliation_note"]

    def test_affiliation_note_overrides_claude_value(self):
        src = {**self._fbi_source, "affiliation_note": "Claude's incorrect assessment"}
        result = apply_independence_override(src)
        assert "Claude's incorrect assessment" not in result["affiliation_note"]
        assert "Kash Patel" in result["affiliation_note"]

    def test_does_not_mutate_original_dict(self):
        original = dict(self._fbi_source)
        _ = apply_independence_override(original)
        assert original["is_independent"] is True
        assert original["relevance_score"] == 0.9

    def test_unaffected_fields_preserved(self):
        result = apply_independence_override(self._fbi_source)
        assert result["tier"] == "primary"
        assert result["supports_claim"] is True
        assert result["url"] == self._fbi_source["url"]

    def test_independent_source_returned_unchanged(self):
        src = {
            "url": "https://www.reuters.com/article/example",
            "tier": "secondary",
            "is_independent": True,
            "relevance_score": 0.85,
            "supports_claim": True,
        }
        result = apply_independence_override(src)
        assert result is src  # identity preserved — no copy made

    def test_doj_override_applied(self):
        src = {
            "url": "https://www.justice.gov/opa/press-release/2025",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.95,
            "supports_claim": False,
        }
        result = apply_independence_override(src)
        assert result["is_independent"] is False
        assert result["relevance_score"] == COMPROMISED_SCORE_CAP
        assert "Bondi" in result["affiliation_note"] or "DOJ" in result["affiliation_note"]

    def test_compromised_score_cap_is_075(self):
        assert COMPROMISED_SCORE_CAP == 0.75


# ── Registry completeness sanity checks ───────────────────────────────────────

class TestRegistryEntries:
    def test_all_entries_have_nonempty_affiliation_note(self):
        from backend.sources.independence_registry import _REGISTRY
        for entry in _REGISTRY:
            assert entry.affiliation_note.strip(), f"{entry.institution} has empty affiliation_note"

    def test_all_entries_have_nonempty_domain_patterns(self):
        from backend.sources.independence_registry import _REGISTRY
        for entry in _REGISTRY:
            assert entry.domain_patterns, f"{entry.institution} has no domain_patterns"

    def test_all_domain_patterns_are_lowercase(self):
        from backend.sources.independence_registry import _REGISTRY
        for entry in _REGISTRY:
            for pattern in entry.domain_patterns:
                assert pattern == pattern.lower(), (
                    f"Pattern '{pattern}' in {entry.institution} is not lowercase"
                )

    def test_countries_covered(self):
        from backend.sources.independence_registry import _REGISTRY
        countries = {e.country for e in _REGISTRY}
        assert "US" in countries
        assert "RU" in countries
        assert "CN" in countries
        assert "TR" in countries
        assert "HU" in countries
        assert "BY" in countries
