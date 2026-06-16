"""Tests for backend/sources/search.py — multilang query decoupling."""

from unittest.mock import MagicMock, call, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_brave_http_mock(results: list[dict]) -> MagicMock:
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"web": {"results": results}}
    mock_response.status_code = 200
    mock_http = MagicMock()
    mock_http.__enter__ = MagicMock(return_value=mock_http)
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.get.return_value = mock_response
    return mock_http


def _make_haiku_response(text: str) -> MagicMock:
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


# ── _translate_to_english ─────────────────────────────────────────────────────

class TestTranslateToEnglish:

    def test_returns_none_when_no_api_key(self):
        """No Anthropic key → None without hitting the API."""
        from backend.sources.search import _translate_to_english

        with patch("backend.sources.search.settings") as s, \
             patch("backend.sources.search.anthropic") as mock_anthropic:
            s.anthropic_api_key = ""
            result = _translate_to_english("Irgendein Anspruch")

        mock_anthropic.Anthropic.assert_not_called()
        assert result is None

    def test_returns_none_on_exception(self):
        """Any exception from the Haiku call returns None and never raises."""
        from backend.sources.search import _translate_to_english

        with patch("backend.sources.search.settings") as s, \
             patch("backend.sources.search.anthropic") as mock_anthropic:
            s.anthropic_api_key = "key"
            mock_anthropic.Anthropic.return_value.messages.create.side_effect = RuntimeError("network error")
            result = _translate_to_english("Irgendein Anspruch")

        assert result is None

    def test_returns_none_on_empty_response(self):
        """Empty text content from Haiku returns None."""
        from backend.sources.search import _translate_to_english

        empty_block = MagicMock()
        empty_block.text = ""
        mock_resp = MagicMock()
        mock_resp.content = [empty_block]

        with patch("backend.sources.search.settings") as s, \
             patch("backend.sources.search.anthropic") as mock_anthropic:
            s.anthropic_api_key = "key"
            mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_resp
            result = _translate_to_english("Irgendein Anspruch")

        assert result is None

    def test_returns_translated_text(self):
        """Successful call returns the stripped translation string."""
        from backend.sources.search import _translate_to_english

        with patch("backend.sources.search.settings") as s, \
             patch("backend.sources.search.anthropic") as mock_anthropic:
            s.anthropic_api_key = "key"
            mock_anthropic.Anthropic.return_value.messages.create.return_value = (
                _make_haiku_response("  Some English claim  ")
            )
            result = _translate_to_english("Irgendein Anspruch")

        assert result == "Some English claim"

    def test_uses_haiku_model_temperature_zero(self):
        """Translation call uses the correct model and temperature=0."""
        from backend.sources.search import _translate_to_english, _TRANSLATION_MODEL

        with patch("backend.sources.search.settings") as s, \
             patch("backend.sources.search.anthropic") as mock_anthropic:
            s.anthropic_api_key = "key"
            mock_anthropic.Anthropic.return_value.messages.create.return_value = (
                _make_haiku_response("English text")
            )
            _translate_to_english("Text")

        call_kwargs = mock_anthropic.Anthropic.return_value.messages.create.call_args
        assert call_kwargs.kwargs["model"] == _TRANSLATION_MODEL
        assert call_kwargs.kwargs["temperature"] == 0


# ── search_claim: single-query path (English claim) ──────────────────────────

class TestSearchClaimEnglishClaim:

    def test_english_claim_issues_only_one_brave_query(self):
        """When translation returns the same text, _query_brave is called exactly once."""
        from backend.sources.search import search_claim

        results = [{"title": "T", "url": "https://t.example/", "description": "D"}]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.sources.search._translate_to_english", return_value="English claim"), \
             patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            search_claim("English claim")

        # get() called exactly once (one query, not two)
        assert mock_http.get.call_count == 1

    def test_english_claim_translation_none_issues_one_query(self):
        """Translation failure (None) → single original query, still returns results."""
        from backend.sources.search import search_claim

        results = [{"title": "T", "url": "https://t.example/1", "description": "D"}]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.sources.search._translate_to_english", return_value=None), \
             patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            output = search_claim("Some claim")

        assert mock_http.get.call_count == 1
        assert "https://t.example/1" in output


# ── search_claim: dual-query path (non-English claim) ────────────────────────

class TestSearchClaimMultilang:

    def test_german_claim_issues_two_brave_queries(self):
        """German claim with a different English translation → _query_brave called twice."""
        from backend.sources.search import search_claim

        results = [{"title": "T", "url": "https://t.example/1", "description": "D"}]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.sources.search._translate_to_english",
                   return_value="Gaza civilian casualties exceed 50 000"), \
             patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            search_claim("Die Zahl der zivilen Opfer in Gaza übersteigt 50.000")

        # Two queries → two Brave GET calls
        assert mock_http.get.call_count == 2

    def test_multilang_results_merged_and_deduped(self):
        """Results from original and English queries are merged; duplicate URLs removed."""
        from backend.sources.search import search_claim

        shared_url = "https://shared.example/article"
        orig_results = [
            {"title": "Orig A", "url": "https://orig.example/a", "description": "Orig A desc"},
            {"title": "Shared", "url": shared_url, "description": "Shared desc"},
        ]
        en_results = [
            {"title": "EN B", "url": "https://en.example/b", "description": "EN B desc"},
            {"title": "Shared dup", "url": shared_url, "description": "Should be dropped"},
        ]

        call_count = [0]

        def brave_side_effect(url, headers=None, params=None):
            q = params["q"]
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.status_code = 200
            if "Opfer" in q:  # original German query
                mock_response.json.return_value = {"web": {"results": orig_results}}
            else:  # English query
                mock_response.json.return_value = {"web": {"results": en_results}}
            return mock_response

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.side_effect = brave_side_effect

        with patch("backend.sources.search._translate_to_english",
                   return_value="Gaza civilian casualties"), \
             patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            output = search_claim("Opfer in Gaza")

        assert "https://orig.example/a" in output
        assert "https://en.example/b" in output
        # Shared URL appears exactly once
        assert output.count(shared_url) == 1
        assert "Should be dropped" not in output

    def test_original_lang_results_take_url_priority(self):
        """When the same URL appears in both queries, the original-language version wins."""
        from backend.sources.search import search_claim

        shared_url = "https://shared.example/article"

        def brave_side_effect(url, headers=None, params=None):
            q = params["q"]
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.status_code = 200
            if "German" in q:
                mock_response.json.return_value = {"web": {"results": [
                    {"title": "Original version", "url": shared_url, "description": "orig desc"},
                ]}}
            else:
                mock_response.json.return_value = {"web": {"results": [
                    {"title": "English version", "url": shared_url, "description": "en desc"},
                ]}}
            return mock_response

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.side_effect = brave_side_effect

        with patch("backend.sources.search._translate_to_english",
                   return_value="English claim text"), \
             patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            output = search_claim("German claim text")

        assert "orig desc" in output
        assert "en desc" not in output


# ── search_claim: translation failure fallback ────────────────────────────────

class TestSearchClaimTranslationFailure:

    def test_translation_failure_falls_back_to_original_only(self):
        """When _translate_to_english returns None, search proceeds with original text only."""
        from backend.sources.search import search_claim

        results = [{"title": "Fallback", "url": "https://fallback.example/", "description": "D"}]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.sources.search._translate_to_english", return_value=None), \
             patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            output = search_claim("Irgendein Anspruch")

        assert "Fallback" in output
        assert "https://fallback.example/" in output
        # Only one query was issued
        assert mock_http.get.call_count == 1


# ── search_claim: 30-result cap ───────────────────────────────────────────────

class TestSearchClaimCap:

    def test_cap_is_30_not_20(self):
        """Post-dedup result list is capped at 30 sources."""
        from backend.sources.search import search_claim

        results = [
            {"title": f"Title {i}", "url": f"https://x.example/{i}", "description": f"Desc {i}"}
            for i in range(35)
        ]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.sources.search._translate_to_english", return_value=None), \
             patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            output = search_claim("claim")

        assert "Source 30:" in output
        assert "Source 31:" not in output

    def test_cap_applied_after_dedup_across_both_queries(self):
        """With two queries each returning 20 results (40 total, 30 unique), cap is 30."""
        from backend.sources.search import search_claim

        orig_results = [
            {"title": f"Orig {i}", "url": f"https://orig.example/{i}", "description": ""}
            for i in range(20)
        ]
        en_results = [
            {"title": f"EN {i}", "url": f"https://en.example/{i}", "description": ""}
            for i in range(20)
        ]

        def brave_side_effect(url, headers=None, params=None):
            q = params["q"]
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.status_code = 200
            if "german" in q.lower():
                mock_response.json.return_value = {"web": {"results": orig_results}}
            else:
                mock_response.json.return_value = {"web": {"results": en_results}}
            return mock_response

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.side_effect = brave_side_effect

        with patch("backend.sources.search._translate_to_english",
                   return_value="English translation"), \
             patch("backend.sources.search.httpx.Client", return_value=mock_http), \
             patch("backend.sources.search.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            output = search_claim("german claim")

        assert "Source 30:" in output
        assert "Source 31:" not in output
