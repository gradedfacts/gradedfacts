"""
Tests for wire-agency cascade deduplication.

Covers:
  - detect_wire_agency: attribution detection vs. topic-mention rejection
  - engine.analyze_claim: agency dedup reduces independent_secondary_verifying_count
  - Same vs. different agencies (two from dpa → 1; dpa + Reuters → 2)
  - Domain dedup and agency dedup compose correctly
  - Regression: claim that reached VERIFIED via two same-agency reprints → SPECULATIVE
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.analysis.rating import EpistemicRating
from backend.sources.agencies import detect_wire_agency


# ── helpers ───────────────────────────────────────────────────────────────────

def _run_engine(sources: list[dict]) -> "Judgment":
    """Run engine.analyze_claim() with the given source list; return the Judgment."""
    from backend.analysis import engine as eng
    from backend.db.models import Judgment

    judgment_data = {"rationale": "test", "rating": "verified", "sources": sources}
    mock_claim = MagicMock()
    mock_claim.text = "Test claim"
    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim

    captured: dict = {}

    def fake_add(obj):
        if isinstance(obj, Judgment):
            captured["judgment"] = obj

    mock_session.add.side_effect = fake_add
    mock_session.add_all.side_effect = lambda objs: None

    with patch.object(eng, "_phase1_search", return_value="Source 1: Test findings\nURL: https://example.com/test\nExcerpt: Test excerpt."), \
         patch.object(eng, "_phase2_judgment", return_value=judgment_data), \
         patch.object(eng, "_get_client", return_value=MagicMock()), \
         patch("backend.analysis.engine.evaluate_source", side_effect=lambda src: src):
        eng.analyze_claim("claim-1", mock_session)

    return captured["judgment"]


def _sec(url: str, title: str, excerpt: str = "") -> dict:
    """Build an independent secondary verifying source dict."""
    return {
        "url": url,
        "title": title,
        "excerpt": excerpt,
        "tier": "secondary",
        "is_independent": True,
        "relevance_score": 0.9,
        "supports_claim": True,
    }


def _ter(url: str) -> dict:
    """Build an independent tertiary verifying source dict."""
    return {
        "url": url,
        "title": "Some context",
        "tier": "tertiary",
        "is_independent": True,
        "relevance_score": 0.9,
        "supports_claim": True,
    }


# ── detect_wire_agency: positive cases ───────────────────────────────────────

class TestDetectWireAgencyPositive:

    def test_parenthetical_dpa(self):
        assert detect_wire_agency("Artikel (dpa)", "") == "dpa"

    def test_parenthetical_ap(self):
        assert detect_wire_agency("Article (AP)", "") == "AP"

    def test_parenthetical_dpa_afp_slash(self):
        # "(dpa/AFP)" → dpa is checked first in the registry order
        result = detect_wire_agency("Titel (dpa/AFP)", "")
        assert result in ("dpa", "AFP")  # either agency attribution detected

    def test_quelle_afp(self):
        assert detect_wire_agency("", "Quelle: AFP") == "AFP"

    def test_laut_reuters(self):
        assert detect_wire_agency("", "laut Reuters berichtet die Agentur") == "Reuters"

    def test_laut_der_nachrichtenagentur_dpa(self):
        assert detect_wire_agency("", "laut der Nachrichtenagentur dpa") == "dpa"

    def test_berichtet_die_nachrichtenagentur_ap(self):
        assert detect_wire_agency("", "berichtet die Nachrichtenagentur AP") == "AP"

    def test_von_dpa(self):
        assert detect_wire_agency("Von dpa – Artikel text", "") == "dpa"

    def test_by_reuters(self):
        assert detect_wire_agency("By Reuters", "") == "Reuters"

    def test_via_afp(self):
        assert detect_wire_agency("", "via AFP") == "AFP"

    def test_slash_byline_left(self):
        # "dpa/" at start of title — some agency in the slash byline is detected
        result = detect_wire_agency("dpa/Reuters – Meldung", "")
        assert result in ("dpa", "Reuters")  # both are valid attributions in this byline

    def test_slash_byline_right(self):
        # "/Reuters" after other text
        assert detect_wire_agency("", "Agentur/Reuters hier") == "Reuters"

    def test_source_colon_reuters(self):
        assert detect_wire_agency("", "Source: Reuters") == "Reuters"

    def test_associated_press_long_form(self):
        assert detect_wire_agency("(Associated Press)", "") == "AP"

    def test_tass_parenthetical(self):
        assert detect_wire_agency("(TASS)", "") == "TASS"

    def test_ansa_laut(self):
        assert detect_wire_agency("", "laut ANSA") == "ANSA"

    def test_efe_by(self):
        assert detect_wire_agency("", "by EFE") == "EFE"

    def test_sda_parenthetical(self):
        assert detect_wire_agency("(SDA)", "") == "SDA"

    def test_apa_quelle(self):
        assert detect_wire_agency("", "Quelle: APA") == "APA"


# ── detect_wire_agency: negative cases (topic mentions must NOT match) ────────

class TestDetectWireAgencyNegative:

    def test_topic_mention_reuters_company(self):
        """'Reuters published a study' is a topic mention, not an attribution byline."""
        assert detect_wire_agency(
            "Reuters publishes annual report on media freedom", ""
        ) is None

    def test_topic_mention_reuters_subject(self):
        assert detect_wire_agency(
            "", "A new Reuters study found that global temperatures are rising."
        ) is None

    def test_topic_mention_ap_subject(self):
        """'AP journalist' is a topic mention, not a byline."""
        assert detect_wire_agency(
            "AP journalist arrested in conflict zone", ""
        ) is None

    def test_topic_mention_dpa_about(self):
        assert detect_wire_agency(
            "", "The article is about dpa's editorial decisions last year."
        ) is None

    def test_bare_agency_name_in_sentence(self):
        """Agency name appearing mid-sentence without attribution keyword → None."""
        assert detect_wire_agency(
            "", "Critics say Reuters has editorial bias on this topic."
        ) is None

    def test_none_when_no_agency(self):
        assert detect_wire_agency("A completely unrelated headline", "No wire attribution.") is None

    def test_empty_strings(self):
        assert detect_wire_agency("", "") is None


# ── Agency dedup reduces independent_secondary_verifying_count ────────────────

class TestAgencyDedupThreshold:

    def test_two_dpa_secondaries_count_as_one(self):
        """
        Two independent secondary sources both attributed to dpa must collapse to
        ONE independent secondary toward the VERIFIED threshold.

        Without agency dedup: indep_secondary=2, verifying_tiers=[S,S,T] → VERIFIED.
        With agency dedup: indep_secondary=1, verifying_tiers=[S,T] → SPECULATIVE.

        Uses .example TLD to bypass source registry tier overrides.
        """
        sources = [
            _sec("https://paper-one.example/a1", "Bericht (dpa)"),
            _sec("https://paper-two.example/a1", "Meldung (dpa)"),
            _ter("https://context.example/c"),
        ]
        j = _run_engine(sources)
        assert j.rating == EpistemicRating.SPECULATIVE

    def test_two_different_agencies_count_as_two(self):
        """
        One dpa source and one Reuters source are from DIFFERENT agencies → both
        count as independent secondary sources → VERIFIED path is intact.

        Uses .example TLD domains to bypass the source registry tier overrides.
        """
        sources = [
            _sec("https://paper-alpha.example/a1", "Bericht (dpa)"),
            _sec("https://paper-beta.example/a1", "Report (Reuters)"),
            _ter("https://context.example/c"),
        ]
        j = _run_engine(sources)
        # indep_secondary=2, verifying_tiers=[S,S,T] (≥3) → VERIFIED
        assert j.rating == EpistemicRating.VERIFIED

    def test_agency_without_attribution_not_deduped(self):
        """
        Secondary sources with no wire-agency attribution in title/excerpt are
        never collapsed — they each count independently.
        """
        sources = [
            _sec("https://alpha-news.example/a1", "Independent analysis of the claim"),
            _sec("https://beta-news.example/a1", "Investigation report"),
            _ter("https://context.example/c"),
        ]
        j = _run_engine(sources)
        # Both secondaries count: indep_secondary=2 → VERIFIED
        assert j.rating == EpistemicRating.VERIFIED

    def test_three_dpa_secondaries_still_count_as_one(self):
        """Three sources, all dpa — should yield only 1 independent secondary."""
        sources = [
            _sec("https://a-paper.example/1", "Bericht (dpa)"),
            _sec("https://b-paper.example/1", "Meldung (dpa)"),
            _sec("https://c-paper.example/1", "News (dpa)"),
        ]
        j = _run_engine(sources)
        # verifying_tiers=[SECONDARY], indep_secondary=1, total < MIN_VERIFIED_SOURCES
        assert j.rating == EpistemicRating.SPECULATIVE


# ── Domain dedup and agency dedup compose ─────────────────────────────────────

class TestDedupComposition:

    def test_domain_dedup_fires_before_agency_dedup(self):
        """
        Second article from the same domain is skipped by domain dedup regardless
        of its agency attribution.  The agency entry IS added for the first (counted)
        source, so a later source from a different domain but same agency is
        correctly skipped by agency dedup.

        Uses .example TLD domains to bypass registry tier overrides.
        """
        sources = [
            # Source 1: alpha.example, dpa — counted; domain + agency dpa tracked
            _sec("https://alpha.example/article1", "Bericht (dpa)"),
            # Source 2: alpha.example again — SKIPPED by domain dedup
            _sec("https://alpha.example/article2", "Update (dpa)"),
            # Source 3: beta.example, also dpa — SKIPPED by agency dedup (dpa already seen)
            _sec("https://beta.example/article1", "Meldung (dpa)"),
            # Source 4: gamma.example, Reuters — different agency → counted
            _sec("https://gamma.example/article1", "By Reuters – Bericht"),
            # Source 5: tertiary for minimum total
            _ter("https://delta.example/c"),
        ]
        j = _run_engine(sources)
        # After both dedups:
        #   source 1 (alpha/dpa)    → counted: verifying=[S], indep_secondary=1
        #   source 2 (alpha dup)    → domain-deduped: skipped
        #   source 3 (beta/dpa)     → agency-deduped: skipped
        #   source 4 (gamma/Reuters)→ counted: verifying=[S,S], indep_secondary=2
        #   source 5 (tertiary)     → counted: verifying=[S,S,T]
        # → 3 in verifying_tiers, indep_secondary=2 → VERIFIED
        assert j.rating == EpistemicRating.VERIFIED

    def test_agency_dedup_does_not_block_non_secondary_sources(self):
        """
        Agency dedup only applies to independent secondary verifying sources.
        A PRIMARY-tier source is never checked for wire-agency attribution, so it
        does not consume the agency slot — a subsequent secondary from the same
        agency is still counted as the first (and only) secondary for that agency.

        Uses .example TLD to prevent registry from overriding tiers.
        """
        sources = [
            # Primary source with AFP attribution — must NOT set seen_agencies["AFP"]
            {
                "url": "https://govt-stats.example/report",
                "title": "Official report via AFP",
                "tier": "primary",
                "is_independent": True,
                "relevance_score": 0.9,
                "supports_claim": True,
            },
            # First (and only) AFP secondary — should be counted, not skipped
            _sec("https://paper-a.example/a", "laut AFP"),
            # Second AFP secondary — should be skipped by agency dedup
            _sec("https://paper-b.example/a", "Quelle: AFP"),
            _ter("https://context.example/c"),
        ]
        j = _run_engine(sources)
        # primary (no agency tracking) → verifying=[P], indep_secondary=0
        # paper-a AFP secondary (first AFP) → verifying=[P,S], indep_secondary=1
        # paper-b AFP secondary (AFP already seen) → AGENCY-DEDUPED: skipped
        # tertiary → verifying=[P,S,T]
        # VERIFIED: ≥3 verifying AND ≥1 independent primary → VERIFIED
        assert j.rating == EpistemicRating.VERIFIED


# ── Regression: VERIFIED via two same-agency reprints → now SPECULATIVE ───────

class TestVerifiedRegressionSameAgency:

    def test_claim_with_two_dpa_reprints_caps_to_speculative(self):
        """
        Regression guard: a claim that previously could reach VERIFIED solely via
        two dpa-attributed secondary sources (+ 1 tertiary) must now be capped at
        SPECULATIVE because both secondaries collapse to one independent secondary.

        This is the canonical test for the spec's requirement:
          'a claim that previously reached VERIFIED via 2 same-agency reprints now
           does NOT (caps to SPECULATIVE)'

        Uses .example TLD to bypass source registry tier overrides.
        """
        # Two dpa reprints + one tertiary = 3 sources total.
        # Without agency dedup: indep_secondary=2, verifying=[S,S,T] → VERIFIED
        # With agency dedup:    indep_secondary=1, verifying=[S,T]   → SPECULATIVE
        sources = [
            _sec("https://localpress-a.example/a", "Polizei warnt vor Betrug (dpa)"),
            _sec("https://localpress-b.example/a", "Betrugsmasche im Umlauf (dpa)"),
            _ter("https://ratgeber.example/context"),
        ]
        j = _run_engine(sources)
        assert j.rating == EpistemicRating.SPECULATIVE

    def test_adding_independent_secondary_restores_verified(self):
        """
        When a genuinely independent secondary (no wire attribution) is added to
        the two-dpa case, the claim can still reach VERIFIED via the second
        independent secondary from a different agency/source.
        """
        sources = [
            _sec("https://outlet-a.example/a", "Bericht (dpa)"),
            _sec("https://outlet-b.example/a", "Meldung (dpa)"),
            _sec("https://outlet-c.example/a", "Eigene Recherche — independent reporting"),
            _ter("https://context.example/c"),
        ]
        j = _run_engine(sources)
        # dpa counted once (indep_secondary=1), dpa skipped, outlet-c counted (indep_secondary=2)
        # verifying=[S, S, T], indep_secondary=2, total=3 → VERIFIED
        assert j.rating == EpistemicRating.VERIFIED
