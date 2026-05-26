"""
Tests for the EU, CH, UK, DE, and FR source registries and the multi-registry
lookup/override functions.

Covers: schema validity, required source entries, independence consistency,
country/region fields, lookup_source_all_registries(), and apply_registry_override().
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REGISTRIES_DIR = Path(__file__).parent.parent / "backend/sources/registries"

_VALID_TIERS = {"primary", "secondary", "tertiary"}
_ALWAYS_REQUIRED = {"name", "domain", "tier", "is_independent", "country", "region"}


def _load(filename: str) -> dict:
    with (_REGISTRIES_DIR / filename).open(encoding="utf-8") as f:
        return json.load(f)


def _sources(filename: str) -> list[dict]:
    return _load(filename)["sources"]


def _get(sources: list[dict], domain: str) -> dict | None:
    return next((s for s in sources if s["domain"] == domain), None)


# ── Parametrised schema checks across all five regional registries ─────────────

@pytest.mark.parametrize("filename", [
    "eu_sources.json",
    "ch_sources.json",
    "uk_sources.json",
    "de_sources.json",
    "fr_sources.json",
])
class TestSchemaAllRegistries:
    def test_json_is_valid(self, filename):
        data = _load(filename)
        assert isinstance(data, dict)

    def test_has_meta_section(self, filename):
        data = _load(filename)
        assert "_meta" in data
        assert "version" in data["_meta"]
        assert "last_updated" in data["_meta"]

    def test_has_sources_list(self, filename):
        sources = _sources(filename)
        assert isinstance(sources, list)
        assert len(sources) >= 5

    def test_all_required_fields_present(self, filename):
        for src in _sources(filename):
            missing = _ALWAYS_REQUIRED - src.keys()
            assert not missing, f"[{filename}] {src.get('name', '?')} missing: {missing}"

    def test_all_tiers_valid(self, filename):
        for src in _sources(filename):
            assert src["tier"] in _VALID_TIERS, (
                f"[{filename}] {src['name']} has invalid tier: {src['tier']!r}"
            )

    def test_is_independent_is_boolean(self, filename):
        for src in _sources(filename):
            assert isinstance(src["is_independent"], bool), (
                f"[{filename}] {src['name']}: is_independent must be bool"
            )

    def test_no_duplicate_domains(self, filename):
        domains = [s["domain"] for s in _sources(filename)]
        assert len(domains) == len(set(domains)), (
            f"[{filename}] duplicate domains found"
        )

    def test_non_independent_sources_have_affiliation_note(self, filename):
        for src in _sources(filename):
            if not src["is_independent"]:
                note = src.get("affiliation_note", "")
                assert note.strip(), (
                    f"[{filename}] {src['name']} is not independent but has no affiliation_note"
                )
                assert len(note) > 80, (
                    f"[{filename}] {src['name']}: affiliation_note is too brief"
                )

    def test_country_field_is_nonempty_string(self, filename):
        for src in _sources(filename):
            assert isinstance(src["country"], str) and src["country"].strip(), (
                f"[{filename}] {src['name']} has empty or missing country"
            )

    def test_region_field_is_nonempty_string(self, filename):
        for src in _sources(filename):
            assert isinstance(src["region"], str) and src["region"].strip(), (
                f"[{filename}] {src['name']} has empty or missing region"
            )

    def test_all_regions_are_europe(self, filename):
        for src in _sources(filename):
            assert src["region"] == "Europe", (
                f"[{filename}] {src['name']} has unexpected region: {src['region']!r}"
            )


# ── EU registry — specific source checks ──────────────────────────────────────

class TestEUSources:
    @pytest.fixture(scope="class")
    def sources(self):
        return _sources("eu_sources.json")

    @pytest.mark.parametrize("domain", [
        "eurostat.ec.europa.eu",
        "ecb.europa.eu",
        "europarl.europa.eu",
        "ec.europa.eu",
        "curia.europa.eu",
        "echr.coe.int",
        "ombudsman.europa.eu",
        "publications.europa.eu",
        "eeas.europa.eu",
    ])
    def test_required_source_present(self, sources, domain):
        assert _get(sources, domain) is not None, f"Required EU source '{domain}' missing"

    def test_eurostat_is_independent_and_primary(self, sources):
        src = _get(sources, "eurostat.ec.europa.eu")
        assert src["is_independent"] is True
        assert src["tier"] == "primary"

    def test_ecb_is_independent_and_primary(self, sources):
        src = _get(sources, "ecb.europa.eu")
        assert src["is_independent"] is True
        assert src["tier"] == "primary"

    def test_curia_is_independent_and_primary(self, sources):
        src = _get(sources, "curia.europa.eu")
        assert src["is_independent"] is True
        assert src["tier"] == "primary"

    def test_echr_is_independent_and_primary(self, sources):
        src = _get(sources, "echr.coe.int")
        assert src["is_independent"] is True
        assert src["tier"] == "primary"

    def test_european_commission_is_not_independent(self, sources):
        src = _get(sources, "ec.europa.eu")
        assert src["is_independent"] is False

    def test_eeas_is_not_independent(self, sources):
        src = _get(sources, "eeas.europa.eu")
        assert src["is_independent"] is False

    def test_eu_institutions_have_eu_country(self, sources):
        eu_domains = [
            "eurostat.ec.europa.eu", "ecb.europa.eu", "europarl.europa.eu",
            "ec.europa.eu", "curia.europa.eu", "ombudsman.europa.eu",
            "publications.europa.eu", "eeas.europa.eu",
        ]
        for domain in eu_domains:
            src = _get(sources, domain)
            assert src["country"] == "EU", f"{domain} should have country=EU"

    def test_echr_has_int_country(self, sources):
        src = _get(sources, "echr.coe.int")
        assert src["country"] == "INT"


# ── CH registry — specific source checks ──────────────────────────────────────

class TestCHSources:
    @pytest.fixture(scope="class")
    def sources(self):
        return _sources("ch_sources.json")

    @pytest.mark.parametrize("domain", [
        "bfs.admin.ch",
        "bk.admin.ch",
        "bger.ch",
        "swissinfo.ch",
        "nzz.ch",
        "tagesanzeiger.ch",
        "srf.ch",
        "rts.ch",
    ])
    def test_required_source_present(self, sources, domain):
        assert _get(sources, domain) is not None, f"Required CH source '{domain}' missing"

    def test_bfs_is_independent_and_primary(self, sources):
        src = _get(sources, "bfs.admin.ch")
        assert src["is_independent"] is True
        assert src["tier"] == "primary"

    def test_bger_is_independent_and_primary(self, sources):
        src = _get(sources, "bger.ch")
        assert src["is_independent"] is True
        assert src["tier"] == "primary"

    def test_federal_chancellery_is_not_independent(self, sources):
        src = _get(sources, "bk.admin.ch")
        assert src["is_independent"] is False

    def test_media_sources_are_secondary(self, sources):
        for domain in ("swissinfo.ch", "nzz.ch", "tagesanzeiger.ch", "srf.ch", "rts.ch"):
            src = _get(sources, domain)
            assert src["tier"] == "secondary", f"{domain} should be secondary"

    def test_all_have_ch_country(self, sources):
        for src in sources:
            assert src["country"] == "CH"


# ── UK registry — specific source checks ──────────────────────────────────────

class TestUKSources:
    @pytest.fixture(scope="class")
    def sources(self):
        return _sources("uk_sources.json")

    @pytest.mark.parametrize("domain", [
        "ons.gov.uk",
        "bbc.co.uk",
        "theguardian.com",
        "parliament.uk",
        "supremecourt.uk",
        "gov.uk",
    ])
    def test_required_source_present(self, sources, domain):
        assert _get(sources, domain) is not None, f"Required UK source '{domain}' missing"

    def test_ons_is_independent_and_primary(self, sources):
        src = _get(sources, "ons.gov.uk")
        assert src["is_independent"] is True
        assert src["tier"] == "primary"

    def test_parliament_is_independent_and_primary(self, sources):
        src = _get(sources, "parliament.uk")
        assert src["is_independent"] is True
        assert src["tier"] == "primary"

    def test_supreme_court_is_independent_and_primary(self, sources):
        src = _get(sources, "supremecourt.uk")
        assert src["is_independent"] is True
        assert src["tier"] == "primary"

    def test_bbc_uk_is_independent_and_secondary(self, sources):
        src = _get(sources, "bbc.co.uk")
        assert src["is_independent"] is True
        assert src["tier"] == "secondary"

    def test_guardian_is_independent_and_secondary(self, sources):
        src = _get(sources, "theguardian.com")
        assert src["is_independent"] is True
        assert src["tier"] == "secondary"

    def test_gov_uk_is_not_independent(self, sources):
        src = _get(sources, "gov.uk")
        assert src["is_independent"] is False

    def test_all_have_gb_country(self, sources):
        for src in sources:
            assert src["country"] == "GB"


# ── DE registry — specific source checks ──────────────────────────────────────

class TestDESources:
    @pytest.fixture(scope="class")
    def sources(self):
        return _sources("de_sources.json")

    @pytest.mark.parametrize("domain", [
        "destatis.de",
        "bundestag.de",
        "bundesverfassungsgericht.de",
        "ard.de",
        "spiegel.de",
        "zeit.de",
    ])
    def test_required_source_present(self, sources, domain):
        assert _get(sources, domain) is not None, f"Required DE source '{domain}' missing"

    def test_destatis_is_independent_and_primary(self, sources):
        src = _get(sources, "destatis.de")
        assert src["is_independent"] is True
        assert src["tier"] == "primary"

    def test_bundestag_is_independent_and_primary(self, sources):
        src = _get(sources, "bundestag.de")
        assert src["is_independent"] is True
        assert src["tier"] == "primary"

    def test_bundesverfassungsgericht_is_independent_and_primary(self, sources):
        src = _get(sources, "bundesverfassungsgericht.de")
        assert src["is_independent"] is True
        assert src["tier"] == "primary"

    def test_media_sources_are_secondary(self, sources):
        for domain in ("ard.de", "spiegel.de", "zeit.de"):
            src = _get(sources, domain)
            assert src["tier"] == "secondary", f"{domain} should be secondary"

    def test_all_are_independent(self, sources):
        for src in sources:
            assert src["is_independent"] is True, f"{src['name']} should be independent"

    def test_all_have_de_country(self, sources):
        for src in sources:
            assert src["country"] == "DE"


# ── FR registry — specific source checks ──────────────────────────────────────

class TestFRSources:
    @pytest.fixture(scope="class")
    def sources(self):
        return _sources("fr_sources.json")

    @pytest.mark.parametrize("domain", [
        "insee.fr",
        "assemblee-nationale.fr",
        "conseil-constitutionnel.fr",
        "lemonde.fr",
        "france24.com",
    ])
    def test_required_source_present(self, sources, domain):
        assert _get(sources, domain) is not None, f"Required FR source '{domain}' missing"

    def test_insee_is_independent_and_primary(self, sources):
        src = _get(sources, "insee.fr")
        assert src["is_independent"] is True
        assert src["tier"] == "primary"

    def test_assemblee_nationale_is_independent_and_primary(self, sources):
        src = _get(sources, "assemblee-nationale.fr")
        assert src["is_independent"] is True
        assert src["tier"] == "primary"

    def test_conseil_constitutionnel_is_independent_and_primary(self, sources):
        src = _get(sources, "conseil-constitutionnel.fr")
        assert src["is_independent"] is True
        assert src["tier"] == "primary"

    def test_lemonde_is_independent_and_secondary(self, sources):
        src = _get(sources, "lemonde.fr")
        assert src["is_independent"] is True
        assert src["tier"] == "secondary"

    def test_france24_is_not_independent(self, sources):
        src = _get(sources, "france24.com")
        assert src["is_independent"] is False

    def test_france24_affiliation_note_mentions_state_funding(self, sources):
        src = _get(sources, "france24.com")
        note = src.get("affiliation_note", "").lower()
        assert "state" in note or "government" in note or "public" in note

    def test_all_have_fr_country(self, sources):
        for src in sources:
            assert src["country"] == "FR"


# ── lookup_source_all_registries() ────────────────────────────────────────────

class TestLookupSourceAllRegistries:
    def test_us_source_found(self):
        from backend.sources.registries import lookup_source_all_registries
        result = lookup_source_all_registries("https://www.reuters.com/article/example")
        assert result is not None
        assert result["domain"] == "reuters.com"

    def test_eurostat_found(self):
        from backend.sources.registries import lookup_source_all_registries
        result = lookup_source_all_registries("https://eurostat.ec.europa.eu/databrowser/view/")
        assert result is not None
        assert "eurostat" in result["domain"]

    def test_ecb_found(self):
        from backend.sources.registries import lookup_source_all_registries
        result = lookup_source_all_registries("https://www.ecb.europa.eu/press/pr/date/2026/html/ecb.mp260306~9de3f9ce48.en.html")
        assert result is not None
        assert result["domain"] == "ecb.europa.eu"

    def test_bfs_found(self):
        from backend.sources.registries import lookup_source_all_registries
        result = lookup_source_all_registries("https://www.bfs.admin.ch/bfs/de/home/statistiken.html")
        assert result is not None
        assert result["domain"] == "bfs.admin.ch"

    def test_ons_found(self):
        from backend.sources.registries import lookup_source_all_registries
        result = lookup_source_all_registries("https://www.ons.gov.uk/economy/grossdomesticproduct")
        assert result is not None
        assert result["domain"] == "ons.gov.uk"

    def test_destatis_found(self):
        from backend.sources.registries import lookup_source_all_registries
        result = lookup_source_all_registries("https://www.destatis.de/DE/Themen/Wirtschaft/")
        assert result is not None
        assert result["domain"] == "destatis.de"

    def test_insee_found(self):
        from backend.sources.registries import lookup_source_all_registries
        result = lookup_source_all_registries("https://www.insee.fr/fr/statistiques/")
        assert result is not None
        assert result["domain"] == "insee.fr"

    def test_unknown_domain_returns_none(self):
        from backend.sources.registries import lookup_source_all_registries
        assert lookup_source_all_registries("https://unknownoutlet.example.com/article") is None

    def test_lookup_is_case_insensitive(self):
        from backend.sources.registries import lookup_source_all_registries
        assert lookup_source_all_registries("HTTPS://WWW.DESTATIS.DE/THEMEN") is not None

    def test_eurostat_not_confused_with_ec(self):
        from backend.sources.registries import lookup_source_all_registries
        result = lookup_source_all_registries("https://eurostat.ec.europa.eu/")
        assert result is not None
        assert result["domain"] == "eurostat.ec.europa.eu"
        assert result["is_independent"] is True


# ── apply_registry_override() ─────────────────────────────────────────────────

class TestApplyRegistryOverride:
    def test_eurostat_url_sets_is_independent_true(self):
        from backend.sources.registries import apply_registry_override
        src = {
            "url": "https://eurostat.ec.europa.eu/databrowser/view/",
            "tier": "secondary",
            "is_independent": False,
            "relevance_score": 0.8,
        }
        result = apply_registry_override(src)
        assert result["is_independent"] is True

    def test_eurostat_url_sets_tier_to_primary(self):
        from backend.sources.registries import apply_registry_override
        src = {
            "url": "https://eurostat.ec.europa.eu/databrowser/view/",
            "tier": "secondary",
            "is_independent": False,
            "relevance_score": 0.8,
        }
        result = apply_registry_override(src)
        assert result["tier"] == "primary"

    def test_eurostat_url_adds_country_and_region(self):
        from backend.sources.registries import apply_registry_override
        src = {"url": "https://eurostat.ec.europa.eu/", "tier": "primary", "is_independent": True}
        result = apply_registry_override(src)
        assert result["country"] == "EU"
        assert result["region"] == "Europe"

    def test_ec_url_sets_is_independent_false(self):
        from backend.sources.registries import apply_registry_override
        src = {
            "url": "https://ec.europa.eu/commission/presscorner/detail/en/ip_26_1234",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
        }
        result = apply_registry_override(src)
        assert result["is_independent"] is False
        assert result.get("affiliation_note")

    def test_france24_url_sets_is_independent_false(self):
        from backend.sources.registries import apply_registry_override
        src = {
            "url": "https://www.france24.com/en/europe/article",
            "tier": "secondary",
            "is_independent": True,
            "relevance_score": 0.8,
        }
        result = apply_registry_override(src)
        assert result["is_independent"] is False
        assert result.get("affiliation_note")

    def test_independent_source_affiliation_note_cleared(self):
        from backend.sources.registries import apply_registry_override
        src = {
            "url": "https://www.ecb.europa.eu/press/pr/",
            "tier": "primary",
            "is_independent": False,
            "affiliation_note": "Claude's incorrect assessment",
            "relevance_score": 0.9,
        }
        result = apply_registry_override(src)
        assert result["is_independent"] is True
        assert "affiliation_note" not in result

    def test_unknown_source_gets_conservative_defaults(self):
        from backend.sources.registries import apply_registry_override
        src = {
            "url": "https://unknownoutlet.example.com/article",
            "tier": "secondary",
            "is_independent": True,
            "relevance_score": 0.7,
        }
        result = apply_registry_override(src)
        # Unregistered sources must be conservatively downgraded — Claude's judgment
        # cannot be trusted for sources absent from the curated registry.
        assert result["tier"] == "tertiary"
        assert result["is_independent"] == "neutral"
        assert result["counts_for_threshold"] is False
        assert result is not src  # a new dict is returned

    def test_does_not_mutate_input_dict(self):
        from backend.sources.registries import apply_registry_override
        src = {
            "url": "https://www.france24.com/en/article",
            "tier": "secondary",
            "is_independent": True,
            "relevance_score": 0.8,
        }
        original_is_independent = src["is_independent"]
        _ = apply_registry_override(src)
        assert src["is_independent"] == original_is_independent


# ── evaluate_source() integration with regional registries ────────────────────

class TestEvaluatorWithRegionalRegistries:
    def test_eurostat_source_evaluated_as_independent(self):
        from backend.sources.evaluator import evaluate_source
        src = {
            "url": "https://eurostat.ec.europa.eu/databrowser/",
            "tier": "secondary",
            "is_independent": False,
            "relevance_score": 0.8,
        }
        result = evaluate_source(src)
        assert result["is_independent"] is True
        assert result["tier"] == "primary"

    def test_ec_source_evaluated_as_not_independent_with_note(self):
        from backend.sources.evaluator import evaluate_source
        src = {
            "url": "https://ec.europa.eu/commission/presscorner/",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
        }
        result = evaluate_source(src)
        assert result["is_independent"] is False
        assert result.get("affiliation_note")

    def test_ons_source_evaluated_as_independent(self):
        from backend.sources.evaluator import evaluate_source
        src = {
            "url": "https://www.ons.gov.uk/economy/grossdomesticproduct",
            "tier": "secondary",
            "is_independent": False,
            "relevance_score": 0.85,
        }
        result = evaluate_source(src)
        assert result["is_independent"] is True
        assert result["tier"] == "primary"

    def test_fbi_compromised_registry_still_overrides_regional(self):
        """Compromised-institution registry must take priority over regional registries."""
        from backend.sources.evaluator import evaluate_source
        src = {
            "url": "https://www.fbi.gov/news/press-releases/statement",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.95,
        }
        result = evaluate_source(src)
        assert result["is_independent"] is False
        assert "Kash Patel" in result.get("affiliation_note", "")

    def test_regional_source_gets_country_and_region(self):
        from backend.sources.evaluator import evaluate_source
        src = {
            "url": "https://www.destatis.de/DE/Themen/",
            "tier": "secondary",
            "is_independent": True,
            "relevance_score": 0.9,
        }
        result = evaluate_source(src)
        assert result.get("country") == "DE"
        assert result.get("region") == "Europe"

    def test_relevance_score_still_clamped_after_registry_override(self):
        from backend.sources.evaluator import evaluate_source
        src = {
            "url": "https://www.bfs.admin.ch/bfs/de/home/statistiken.html",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 1.5,
        }
        result = evaluate_source(src)
        assert result["relevance_score"] == 1.0
