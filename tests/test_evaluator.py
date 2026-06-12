"""
Tests for backend/sources/evaluator.py.

Covers: evaluate_source() — independence override, affiliation_note enforcement,
and relevance_score clamping. Also covers extract_domain() deduplication helper.
"""

from backend.sources.evaluator import (
    evaluate_source,
    extract_domain,
    is_party_politician_url,
    is_social_media_url,
    is_user_content_url,
)
from backend.sources.independence_registry import COMPROMISED_SCORE_CAP


class TestEvaluateSource:
    _independent_source = {
        "url": "https://www.reuters.com/article/example",
        "tier": "secondary",
        "is_independent": True,
        "relevance_score": 0.85,
        "supports_claim": True,
    }

    # ── Independence registry override ────────────────────────────────────────

    def test_fbi_source_is_marked_not_independent(self):
        src = {
            "url": "https://www.fbi.gov/news/press-releases/statement",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        }
        result = evaluate_source(src)
        assert result["is_independent"] is False

    def test_fbi_source_relevance_capped(self):
        src = {
            "url": "https://www.fbi.gov/news/press-releases/statement",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.95,
            "supports_claim": True,
        }
        result = evaluate_source(src)
        assert result["relevance_score"] == COMPROMISED_SCORE_CAP

    def test_fbi_source_affiliation_note_populated(self):
        src = {
            "url": "https://www.fbi.gov/news/press-releases/statement",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.9,
            "supports_claim": True,
        }
        result = evaluate_source(src)
        assert result.get("affiliation_note")

    # ── Unregistered source defaults ──────────────────────────────────────────

    def test_unregistered_source_gets_conservative_defaults(self):
        # Claude said secondary/independent, but the source is not in any registry.
        # The pipeline must override to tertiary/neutral — unknown ≠ verified.
        src = {
            "url": "https://some-partisan-outlet.example/article",
            "tier": "secondary",
            "is_independent": False,
            "relevance_score": 0.7,
            "supports_claim": True,
        }
        result = evaluate_source(src)
        assert result["tier"] == "tertiary"
        assert result["is_independent"] == "neutral"
        assert result["counts_for_threshold"] is False
        assert result.get("affiliation_note") is None

    def test_unregistered_source_affiliation_note_cleared(self):
        # An unregistered source that Claude annotated with an affiliation_note
        # should have that note cleared — we cannot verify Claude's assessment.
        src = {
            "url": "https://some-partisan-outlet.example/article",
            "tier": "secondary",
            "is_independent": False,
            "affiliation_note": "Known partisan funding source",
            "relevance_score": 0.7,
            "supports_claim": True,
        }
        result = evaluate_source(src)
        assert result["is_independent"] == "neutral"
        assert result.get("affiliation_note") is None

    def test_registered_non_independent_affiliation_note_from_registry(self):
        # A registered non-independent source (MSNBC) must carry the registry's
        # affiliation_note, not any note Claude may have added.
        src = {
            "url": "https://www.msnbc.com/article/example",
            "tier": "secondary",
            "is_independent": True,
            "relevance_score": 0.8,
            "supports_claim": True,
        }
        result = evaluate_source(src)
        assert result["is_independent"] is False
        assert result.get("affiliation_note"), "Registered non-independent source must have affiliation_note"

    def test_independent_source_with_registry_affiliation_note_keeps_it(self):
        # kyivindependent.com is registered as independent but carries a country-of-origin
        # affiliation_note. apply_registry_override must pass it through regardless of
        # independence status so the UI can surface the context note.
        src = {
            "url": "https://kyivindependent.com/article/example",
            "tier": "secondary",
            "is_independent": True,
            "relevance_score": 0.8,
            "supports_claim": True,
        }
        result = evaluate_source(src)
        assert result["is_independent"] is True
        assert result.get("affiliation_note"), (
            "Independent registry entry with affiliation_note must keep it after override"
        )

    # ── Relevance score clamping ───────────────────────────────────────────────

    def test_relevance_score_above_1_clamped_to_1(self):
        src = {**self._independent_source, "relevance_score": 1.5}
        result = evaluate_source(src)
        assert result["relevance_score"] == 1.0

    def test_relevance_score_below_0_clamped_to_0(self):
        src = {**self._independent_source, "relevance_score": -0.2}
        result = evaluate_source(src)
        assert result["relevance_score"] == 0.0

    def test_valid_relevance_score_unchanged(self):
        src = {**self._independent_source, "relevance_score": 0.75}
        result = evaluate_source(src)
        assert result["relevance_score"] == 0.75

    # ── Non-mutation guarantee ────────────────────────────────────────────────

    def test_does_not_mutate_input_dict(self):
        src = {
            "url": "https://www.fbi.gov/press",
            "tier": "primary",
            "is_independent": True,
            "relevance_score": 0.95,
            "supports_claim": True,
        }
        original_is_independent = src["is_independent"]
        original_score = src["relevance_score"]
        _ = evaluate_source(src)
        assert src["is_independent"] == original_is_independent
        assert src["relevance_score"] == original_score

    # ── Independent source pass-through ───────────────────────────────────────

    def test_independent_source_returned_with_unchanged_fields(self):
        result = evaluate_source(self._independent_source)
        assert result["is_independent"] is True
        assert result["relevance_score"] == 0.85
        assert result.get("affiliation_note") is None


class TestExtractDomain:

    def test_strips_www_prefix(self):
        assert extract_domain("https://www.reuters.com/article/1") == "reuters.com"

    def test_strips_subdomain(self):
        assert extract_domain("https://stats.cbs.nl/data") == "cbs.nl"

    def test_different_subdomains_same_root(self):
        assert extract_domain("https://data.cbs.nl/x") == extract_domain("https://stats.cbs.nl/y")

    def test_no_subdomain(self):
        assert extract_domain("https://reuters.com/article") == "reuters.com"

    def test_lowercases_result(self):
        assert extract_domain("https://WWW.REUTERS.COM/article") == "reuters.com"

    def test_empty_url_returns_none(self):
        assert extract_domain("") is None

    def test_non_url_returns_none(self):
        assert extract_domain("not a url") is None

    def test_url_with_path_query_ignored(self):
        assert extract_domain("https://www.bbc.com/news/world?page=2#section") == "bbc.com"

    def test_returns_empty_for_single_label_host(self):
        assert extract_domain("https://localhost/path") == "localhost"

    # ── Multi-part TLD handling ───────────────────────────────────────────────

    def test_multi_part_tld_austria_gv_at(self):
        # ris.bka.gv.at — the TLD is gv.at, registrable domain is bka.gv.at
        assert extract_domain("https://ris.bka.gv.at/doc/rgbl/BGBL_I_2023_xxx") == "bka.gv.at"

    def test_multi_part_tld_uk_co_uk(self):
        assert extract_domain("https://www.bbc.co.uk/news") == "bbc.co.uk"

    def test_two_label_domain_with_known_multi_tld_returns_tld_unchanged(self):
        # co.uk without a registrable prefix is itself — no extra label to add
        assert extract_domain("https://co.uk/") == "co.uk"

    # ── Malformed hostname rejection ─────────────────────────────────────────

    def test_malformed_hostname_brace_returns_none(self):
        # http://{/path produces hostname "{" — must be rejected, not counted
        assert extract_domain("http://{/path") is None

    def test_malformed_hostname_bracket_prefix_returns_none(self):
        assert extract_domain("http://[garbage/path") is None


class TestSocialMediaBlacklist:

    def test_youtube_com_excluded(self):
        src = {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "tier": "secondary",
               "is_independent": True, "relevance_score": 0.8, "supports_claim": True}
        assert evaluate_source(src) is None

    def test_youtu_be_excluded(self):
        # youtu.be is YouTube's short-URL service — same platform, must be excluded
        src = {"url": "https://youtu.be/dQw4w9WgXcQ", "tier": "secondary",
               "is_independent": True, "relevance_score": 0.8, "supports_claim": True}
        assert evaluate_source(src) is None

    def test_is_social_media_url_youtu_be(self):
        assert is_social_media_url("https://youtu.be/xyz") is True

    def test_is_social_media_url_youtube_subdomain(self):
        assert is_social_media_url("https://music.youtube.com/watch?v=xyz") is True


class TestPartyPoliticianBlacklist:

    def test_politician_domain_excluded_from_evaluate_source(self):
        src = {"url": "https://www.friedrich-merz.de/aktuell/pressemitteilung",
               "tier": "primary", "is_independent": True, "relevance_score": 0.9,
               "supports_claim": True}
        assert evaluate_source(src) is None

    def test_party_domain_excluded_from_evaluate_source(self):
        src = {"url": "https://sp-ps.ch/de/news/pressemitteilung",
               "tier": "primary", "is_independent": True, "relevance_score": 0.9,
               "supports_claim": True}
        assert evaluate_source(src) is None

    def test_is_party_politician_url_merz(self):
        assert is_party_politician_url("https://www.friedrich-merz.de/news") is True

    def test_is_party_politician_url_sp(self):
        assert is_party_politician_url("https://sp-ps.ch/de") is True

    def test_non_party_domain_not_excluded(self):
        src = {"url": "https://www.reuters.com/article/example",
               "tier": "secondary", "is_independent": True, "relevance_score": 0.85,
               "supports_claim": True}
        assert evaluate_source(src) is not None


class TestUserContentBlacklist:

    def test_vocal_media_excluded(self):
        src = {"url": "https://vocal.media/article/some-post", "tier": "tertiary",
               "is_independent": "neutral", "relevance_score": 0.4, "supports_claim": True}
        assert evaluate_source(src) is None

    def test_docplayer_excluded(self):
        src = {"url": "https://docplayer.org/12345-document.html", "tier": "tertiary",
               "is_independent": "neutral", "relevance_score": 0.4, "supports_claim": True}
        assert evaluate_source(src) is None

    def test_is_user_content_url_vocal(self):
        assert is_user_content_url("https://vocal.media/article/foo") is True

    def test_is_user_content_url_docplayer(self):
        assert is_user_content_url("https://docplayer.org/upload") is True

    def test_non_user_content_not_excluded(self):
        assert is_user_content_url("https://documentcloud.org/documents/123") is False
