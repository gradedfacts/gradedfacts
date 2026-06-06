"""
Tests for backend/analysis/consensus.py

Covers:
  - _resolve_consensus: all agreement/disagreement/no-secondary cases
  - _mistral_phase2_judgment: tool-call parsing, error paths
  - analyze_claim_with_consensus: full integration (mocked I/O)
    — models agree
    — models disagree (consensus downgrades to SPECULATIVE)
    — Mistral Phase 2 raises (Claude-only fallback)
    — MISTRAL_API_KEY absent (Claude-only fallback)
    — claim not found
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.analysis.rating import EpistemicRating


# ── _resolve_consensus ────────────────────────────────────────────────────────

class TestResolveConsensus:
    from backend.analysis.consensus import _resolve_consensus  # type: ignore[attr-defined]

    def setup_method(self):
        from backend.analysis.consensus import _resolve_consensus
        self._fn = _resolve_consensus

    def test_both_agree_verified(self):
        rating, agree = self._fn(EpistemicRating.VERIFIED, EpistemicRating.VERIFIED)
        assert rating == EpistemicRating.VERIFIED
        assert agree is True

    def test_both_agree_debunked(self):
        rating, agree = self._fn(EpistemicRating.DEBUNKED, EpistemicRating.DEBUNKED)
        assert rating == EpistemicRating.DEBUNKED
        assert agree is True

    def test_both_agree_speculative(self):
        rating, agree = self._fn(EpistemicRating.SPECULATIVE, EpistemicRating.SPECULATIVE)
        assert rating == EpistemicRating.SPECULATIVE
        assert agree is True

    def test_both_agree_missing(self):
        rating, agree = self._fn(EpistemicRating.MISSING, EpistemicRating.MISSING)
        assert rating == EpistemicRating.MISSING
        assert agree is True

    def test_disagree_downgrades_to_speculative(self):
        rating, agree = self._fn(EpistemicRating.VERIFIED, EpistemicRating.DEBUNKED)
        assert rating == EpistemicRating.SPECULATIVE
        assert agree is False

    def test_disagree_verified_vs_missing(self):
        rating, agree = self._fn(EpistemicRating.VERIFIED, EpistemicRating.MISSING)
        assert rating == EpistemicRating.SPECULATIVE
        assert agree is False

    def test_disagree_debunked_vs_speculative(self):
        rating, agree = self._fn(EpistemicRating.DEBUNKED, EpistemicRating.SPECULATIVE)
        assert rating == EpistemicRating.SPECULATIVE
        assert agree is False

    def test_no_secondary_passes_through_claude_rating(self):
        for r in EpistemicRating:
            rating, agree = self._fn(r, None)
            assert rating == r
            assert agree is None

    def test_debunked_plus_missing_resolves_to_debunked(self):
        rating, agree = self._fn(EpistemicRating.DEBUNKED, EpistemicRating.MISSING)
        assert rating == EpistemicRating.DEBUNKED
        assert agree is False

    def test_missing_plus_debunked_resolves_to_debunked(self):
        rating, agree = self._fn(EpistemicRating.MISSING, EpistemicRating.DEBUNKED)
        assert rating == EpistemicRating.DEBUNKED
        assert agree is False

    def test_verified_plus_missing_resolves_to_speculative(self):
        rating, agree = self._fn(EpistemicRating.VERIFIED, EpistemicRating.MISSING)
        assert rating == EpistemicRating.SPECULATIVE
        assert agree is False

    def test_missing_plus_verified_resolves_to_speculative(self):
        rating, agree = self._fn(EpistemicRating.MISSING, EpistemicRating.VERIFIED)
        assert rating == EpistemicRating.SPECULATIVE
        assert agree is False

    def test_disagree_result_is_never_verified_without_source_quality(self):
        # Without source quality advantage (defaults), disagreement never yields VERIFIED
        ratings = list(EpistemicRating)
        for r1 in ratings:
            for r2 in ratings:
                if r1 != r2:
                    result, flag = self._fn(r1, r2)
                    assert result != EpistemicRating.VERIFIED
                    assert flag is False

    def test_disagree_claude_primary_wins(self):
        rating, agree = self._fn(
            EpistemicRating.VERIFIED, EpistemicRating.DEBUNKED,
            claude_has_primary_independent=True,
            mistral_has_primary_independent=False,
        )
        assert rating == EpistemicRating.VERIFIED
        assert agree is False

    def test_disagree_mistral_primary_wins(self):
        rating, agree = self._fn(
            EpistemicRating.DEBUNKED, EpistemicRating.VERIFIED,
            claude_has_primary_independent=False,
            mistral_has_primary_independent=True,
        )
        assert rating == EpistemicRating.VERIFIED
        assert agree is False

    def test_disagree_both_primary_falls_back_to_speculative(self):
        rating, agree = self._fn(
            EpistemicRating.VERIFIED, EpistemicRating.DEBUNKED,
            claude_has_primary_independent=True,
            mistral_has_primary_independent=True,
        )
        assert rating == EpistemicRating.SPECULATIVE
        assert agree is False

    def test_disagree_debunked_missing_source_quality_does_not_override(self):
        # DEBUNKED+MISSING is resolved before source quality check
        rating, agree = self._fn(
            EpistemicRating.DEBUNKED, EpistemicRating.MISSING,
            claude_has_primary_independent=False,
            mistral_has_primary_independent=True,
        )
        assert rating == EpistemicRating.DEBUNKED
        assert agree is False

    def test_debunked_verified_claude_primary_yields_debunked(self):
        # Claude=DEBUNKED with Primary/Independent beats Mistral=VERIFIED (Mistral has no primary)
        rating, agree = self._fn(
            EpistemicRating.DEBUNKED, EpistemicRating.VERIFIED,
            claude_has_primary_independent=True,
            mistral_has_primary_independent=False,
        )
        assert rating == EpistemicRating.DEBUNKED
        assert agree is False

    def test_debunked_verified_claude_primary_beats_both_primary(self):
        # Claude=DEBUNKED + Primary/Independent wins even when Mistral also has primary sources.
        # Counter-evidence from the primary pipeline prevails over supporting evidence.
        rating, agree = self._fn(
            EpistemicRating.DEBUNKED, EpistemicRating.VERIFIED,
            claude_has_primary_independent=True,
            mistral_has_primary_independent=True,
        )
        assert rating == EpistemicRating.DEBUNKED
        assert agree is False

    def test_real_conflicts_downgrade_to_speculative(self):
        # Pairs that are genuine conflicts (not DEBUNKED+MISSING) → SPECULATIVE
        real_conflicts = [
            (EpistemicRating.VERIFIED, EpistemicRating.DEBUNKED),
            (EpistemicRating.DEBUNKED, EpistemicRating.VERIFIED),
            (EpistemicRating.VERIFIED, EpistemicRating.SPECULATIVE),
            (EpistemicRating.SPECULATIVE, EpistemicRating.VERIFIED),
            (EpistemicRating.DEBUNKED, EpistemicRating.SPECULATIVE),
            (EpistemicRating.SPECULATIVE, EpistemicRating.DEBUNKED),
            (EpistemicRating.SPECULATIVE, EpistemicRating.MISSING),
            (EpistemicRating.MISSING, EpistemicRating.SPECULATIVE),
        ]
        for r1, r2 in real_conflicts:
            result, flag = self._fn(r1, r2)
            assert result == EpistemicRating.SPECULATIVE, f"Expected SPECULATIVE for {r1}+{r2}, got {result}"
            assert flag is False


# ── _mistral_phase2_judgment ──────────────────────────────────────────────────

class TestMistralPhase2:

    def _make_tool_response(self, args: dict) -> MagicMock:
        """Build a mock Mistral chat.complete() response with a single tool call."""
        fn = MagicMock()
        fn.name = "submit_judgment"
        fn.arguments = json.dumps(args)

        call = MagicMock()
        call.function = fn

        message = MagicMock()
        message.tool_calls = [call]

        choice = MagicMock()
        choice.message = message

        response = MagicMock()
        response.choices = [choice]
        return response

    def test_parses_tool_call_correctly(self):
        from backend.analysis.consensus import _mistral_phase2_judgment

        payload = {
            "rating": "verified",
            "rationale": "Evidence found.",
            "sources": [],
        }
        mock_response = self._make_tool_response(payload)
        mock_client = MagicMock()
        mock_client.chat.complete.return_value = mock_response

        with patch("backend.analysis.consensus._get_mistral_client", return_value=mock_client):
            result = _mistral_phase2_judgment("Some claim", "Some findings")

        assert result["rating"] == "verified"
        assert result["rationale"] == "Evidence found."

    def test_parses_dict_arguments_directly(self):
        """Some SDK versions return arguments as a dict rather than a JSON string."""
        from backend.analysis.consensus import _mistral_phase2_judgment

        payload = {"rating": "missing", "rationale": "No sources.", "sources": []}

        fn = MagicMock()
        fn.name = "submit_judgment"
        fn.arguments = payload  # already a dict

        call = MagicMock()
        call.function = fn

        message = MagicMock()
        message.tool_calls = [call]

        choice = MagicMock()
        choice.message = message

        response = MagicMock()
        response.choices = [choice]

        mock_client = MagicMock()
        mock_client.chat.complete.return_value = response

        with patch("backend.analysis.consensus._get_mistral_client", return_value=mock_client):
            result = _mistral_phase2_judgment("Some claim", "")

        assert result["rating"] == "missing"

    def test_raises_when_no_tool_calls(self):
        from backend.analysis.consensus import _mistral_phase2_judgment

        message = MagicMock()
        message.tool_calls = []

        choice = MagicMock()
        choice.message = message

        response = MagicMock()
        response.choices = [choice]

        mock_client = MagicMock()
        mock_client.chat.complete.return_value = response

        with patch("backend.analysis.consensus._get_mistral_client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="did not return any tool calls"):
                _mistral_phase2_judgment("claim", "findings")

    def test_raises_when_wrong_tool_name(self):
        from backend.analysis.consensus import _mistral_phase2_judgment

        fn = MagicMock()
        fn.name = "some_other_tool"
        fn.arguments = "{}"

        call = MagicMock()
        call.function = fn

        message = MagicMock()
        message.tool_calls = [call]

        choice = MagicMock()
        choice.message = message

        response = MagicMock()
        response.choices = [choice]

        mock_client = MagicMock()
        mock_client.chat.complete.return_value = response

        with patch("backend.analysis.consensus._get_mistral_client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="unexpected tool"):
                _mistral_phase2_judgment("claim", "findings")


# ── _correct_mistral_rating ───────────────────────────────────────────────────

class TestCorrectMistralRating:

    def test_verified_with_debunk_phrase_overridden_to_debunked(self):
        from backend.analysis.consensus import _correct_mistral_rating

        args = {
            "rating": "verified",
            "rationale": "Die Zahlen belegen, dass die Behauptung ist daher falsch.",
            "sources": [],
        }
        result = _correct_mistral_rating(args)
        assert result["rating"] == "debunked"
        # Original dict must not be mutated
        assert args["rating"] == "verified"

    @pytest.mark.parametrize("phrase,rationale_template", [
        ("the claim is false",        "After reviewing the evidence, the claim is false."),
        ("is therefore false",        "The data contradicts the statement; it is therefore false."),
        ("is incorrect",              "The figure cited is incorrect according to official records."),
        ("must be rated as debunked", "Given the contrary evidence, this must be rated as debunked."),
        ("therefore debunked",        "No source supports the claim; therefore debunked."),
        ("thus debunked",             "The assertion is unsupported and thus debunked."),
        ("is not correct",            "The statistic is not correct based on primary data."),
    ])
    def test_verified_with_new_debunk_phrase_overridden_to_debunked(self, phrase, rationale_template):
        from backend.analysis.consensus import _correct_mistral_rating

        args = {
            "rating": "verified",
            "rationale": rationale_template,
            "sources": [],
        }
        result = _correct_mistral_rating(args)
        assert result["rating"] == "debunked", (
            f"Expected 'verified' → 'debunked' correction for phrase {phrase!r}"
        )
        assert args["rating"] == "verified"

    def test_verified_without_debunk_phrase_unchanged(self):
        from backend.analysis.consensus import _correct_mistral_rating

        args = {
            "rating": "verified",
            "rationale": "Three independent primary sources confirm the claim.",
            "sources": [],
        }
        result = _correct_mistral_rating(args)
        assert result["rating"] == "verified"

    # ── DEBUNKED → VERIFIED corrections ──────────────────────────────────────

    @pytest.mark.parametrize("phrase,rationale_template", [
        ("verified ist gerechtfertigt",   "Die Quellen belegen die Aussage. Verified ist gerechtfertigt."),
        ("rating is verified",            "All three sources confirm the claim. Rating is verified."),
        ("bewertung lautet verified",      "Die Fakten stützen die Behauptung. Bewertung lautet Verified."),
        ("ist faktisch korrekt",          "Die Behauptung ist faktisch korrekt laut offiziellen Quellen."),
        ("kann als verified eingestuft werden", "Die Behauptung kann als verified eingestuft werden."),
        ("einstufung als verified",       "Nach Prüfung der Belege: Einstufung als Verified."),
        ("the claim is correct",          "The claim is correct according to official statistics."),
        ("die behauptung ist korrekt",    "Die Behauptung ist korrekt und durch Primärquellen belegt."),
        ("the claim is verified",         "Based on the evidence, the claim is verified."),
        ("is therefore verified",         "The statement is supported by primary sources and is therefore verified."),
        ("rated as verified",             "After review, this claim is rated as verified."),
        ("classified as verified",        "The information is classified as verified by independent sources."),
        ("is correct and verified",       "The data is correct and verified across multiple sources."),
        ("therefore verified",            "All sources align; therefore verified."),
        ("thus verified",                 "The claim is supported and thus verified."),
    ])
    def test_debunked_with_verified_phrase_overridden_to_verified(self, phrase, rationale_template):
        from backend.analysis.consensus import _correct_mistral_rating

        args = {
            "rating": "debunked",
            "rationale": rationale_template,
            "sources": [],
        }
        result = _correct_mistral_rating(args)
        assert result["rating"] == "verified", (
            f"Expected 'debunked' → 'verified' correction for phrase {phrase!r}"
        )
        # Original dict must not be mutated
        assert args["rating"] == "debunked"

    def test_debunked_without_verified_phrase_unchanged(self):
        from backend.analysis.consensus import _correct_mistral_rating

        args = {
            "rating": "debunked",
            "rationale": "Two primary sources directly contradict the claim.",
            "sources": [],
        }
        result = _correct_mistral_rating(args)
        assert result["rating"] == "debunked"

    def test_debunked_correction_is_case_insensitive(self):
        from backend.analysis.consensus import _correct_mistral_rating

        args = {
            "rating": "debunked",
            "rationale": "THE CLAIM IS CORRECT based on official records.",
            "sources": [],
        }
        result = _correct_mistral_rating(args)
        assert result["rating"] == "verified"

    def test_other_ratings_not_affected_by_verified_phrases(self):
        """SPECULATIVE and MISSING ratings must not be changed even if rationale has verified phrases."""
        from backend.analysis.consensus import _correct_mistral_rating

        for rating in ("speculative", "missing"):
            args = {
                "rating": rating,
                "rationale": "The claim is correct but evidence is thin.",
                "sources": [],
            }
            result = _correct_mistral_rating(args)
            assert result["rating"] == rating, (
                f"Rating {rating!r} must not be mutated by verified-phrase correction"
            )


# ── _correct_claude_rating ────────────────────────────────────────────────────

class TestCorrectClaudeRating:

    @pytest.mark.parametrize("phrase,rationale_template", [
        ("verified ist vollständig erfüllt",  "Die Quellen belegen die Aussage. Verified ist vollständig erfüllt."),
        ("kriterium verified ist erfüllt",    "Das Kriterium Verified ist erfüllt laut offiziellen Daten."),
        ("das kriterium verified",            "Das Kriterium Verified wird durch drei Primärquellen gestützt."),
        ("bewertung lautet verified",         "Nach Prüfung aller Belege: Bewertung lautet Verified."),
        ("ist als verified einzustufen",      "Die Behauptung ist als Verified einzustufen."),
        ("fully meets the criteria for verified", "The evidence fully meets the criteria for verified."),
        ("rating is verified",               "All sources agree. Rating is verified."),
        ("the claim is verified",            "Based on primary data, the claim is verified."),
        ("therefore verified",               "All evidence aligns; therefore verified."),
        ("is correct and verified",          "The figure is correct and verified by official statistics."),
        ("klar verifiziert",                 "Die Behauptung ist klar verifiziert durch drei unabhängige Quellen."),
        ("klar verified",                    "Das Ergebnis ist klar Verified laut offiziellen Statistiken."),
        ("eindeutig verifiziert",            "Die Aussage ist eindeutig verifiziert durch Primärquellen."),
        ("zweifelsfrei belegt",              "Die Behauptung ist zweifelsfrei belegt durch amtliche Daten."),
        ("ist klar verifiziert",             "Die Aussage ist klar verifiziert und entspricht den Fakten."),
        ("vollständig erfüllt",              "Alle Kriterien sind vollständig erfüllt; die Behauptung ist korrekt."),
        ("kriterium fur verified ist klar erfullt", "Das Kriterium fur Verified ist klar erfullt."),
        ("alle kriterien fur verified",      "Alle Kriterien fur Verified sind durch drei Quellen erfüllt."),
        ("clearly verified",                 "The claim is clearly verified by independent primary sources."),
        ("unambiguously verified",           "Three primary sources confirm the figure; unambiguously verified."),
        ("beyond doubt verified",            "The data is beyond doubt verified by official statistics."),
        ("undoubtedly verified",             "This claim is undoubtedly verified by the official records."),
        ("clearly meets the criteria",       "The evidence clearly meets the criteria for a verified rating."),
        ("all criteria for verified are met","All criteria for verified are met by the available evidence."),
        ("rating verified is clearly justified", "Rating Verified is clearly justified by three primary sources."),
        # German (de) — additions
        ("alle kriterien für verified",          "Alle Kriterien für Verified sind durch drei Quellen erfüllt."),
        ("bewertung verified ist klar gerechtfertigt", "Bewertung Verified ist klar gerechtfertigt laut Primärquellen."),
        # French (fr)
        ("clairement vérifié",                   "La déclaration est clairement vérifié par des sources officielles."),
        ("sans aucun doute vérifié",             "Les données sont sans aucun doute vérifié par trois sources primaires."),
        ("tous les critères pour verified",      "Tous les critères pour Verified sont remplis."),
        ("la notation verified est justifiée",   "La notation Verified est justifiée par les preuves disponibles."),
        # Italian (it)
        ("chiaramente verificato",               "L'affermazione è chiaramente verificato da fonti primarie."),
        ("inequivocabilmente verificato",        "I dati sono inequivocabilmente verificato da tre fonti indipendenti."),
        ("tutti i criteri per verified",         "Tutti i criteri per Verified sono soddisfatti."),
        # Spanish (es)
        ("claramente verificado",                "La afirmación está claramente verificado por fuentes oficiales."),
        ("inequívocamente verificado",           "Los datos son inequívocamente verificado por tres fuentes primarias."),
        ("todos los criterios para verified",    "Todos los criterios para Verified se cumplen."),
        # Portuguese (pt)
        ("inequivocamente verificado",           "Os dados são inequivocamente verificado por fontes primárias."),
        ("todos os critérios para verified",     "Todos os critérios para Verified são cumpridos."),
        # Dutch (nl)
        ("duidelijk geverifieerd",               "De bewering is duidelijk geverifieerd door primaire bronnen."),
        ("ondubbelzinnig geverifieerd",          "De gegevens zijn ondubbelzinnig geverifieerd door drie bronnen."),
        ("aan alle criteria voor verified voldaan", "Er is aan alle criteria voor Verified voldaan."),
        # Polish (pl)
        ("wyraźnie zweryfikowany",               "Twierdzenie jest wyraźnie zweryfikowany przez oficjalne źródła."),
        ("jednoznacznie zweryfikowany",          "Dane są jednoznacznie zweryfikowany przez trzy niezależne źródła."),
        ("wszystkie kryteria dla verified spełnione", "Wszystkie kryteria dla Verified spełnione przez dostępne dowody."),
        # Swedish (sv)
        ("tydligt verifierad",                   "Påståendet är tydligt verifierad av primära källor."),
        ("otvetydigt verifierad",                "Uppgifterna är otvetydigt verifierad av tre oberoende källor."),
        ("alla kriterier för verified uppfyllda","Alla kriterier för Verified uppfyllda av tillgängliga bevis."),
        # Danish (da)
        ("tydeligt verificeret",                 "Påstanden er tydeligt verificeret af officielle kilder."),
        ("utvetydigt verificeret",               "Dataene er utvetydigt verificeret af tre primære kilder."),
        # Finnish (fi)
        ("selvästi vahvistettu",                 "Väite on selvästi vahvistettu virallisten lähteiden perusteella."),
        ("yksiselitteisesti vahvistettu",        "Tiedot ovat yksiselitteisesti vahvistettu kolmen lähteen toimesta."),
        # Czech (cs)
        ("jasně ověřeno",                        "Tvrzení je jasně ověřeno oficiálními zdroji."),
        ("jednoznačně ověřeno",                  "Data jsou jednoznačně ověřeno třemi nezávislými zdroji."),
        # Romanian (ro)
        ("clar verificat",                       "Afirmația este clar verificat de surse oficiale."),
        ("fără îndoială verificat",              "Datele sunt fără îndoială verificat de trei surse primare."),
        # Greek (el)
        ("σαφώς επαληθευμένο",                   "Ο ισχυρισμός είναι σαφώς επαληθευμένο από επίσημες πηγές."),
        ("αναμφίβολα επαληθευμένο",              "Τα δεδομένα είναι αναμφίβολα επαληθευμένο από τρεις πηγές."),
        # Hungarian (hu)
        ("egyértelműen megerősített",            "Az állítás egyértelműen megerősített hivatalos forrásokkal."),
        ("kétségtelenül megerősített",           "Az adatok kétségtelenül megerősített három elsődleges forrással."),
        # Russian (ru)
        ("явно подтверждено",                    "Утверждение явно подтверждено официальными источниками."),
        ("однозначно подтверждено",              "Данные однозначно подтверждено тремя независимыми источниками."),
        # Ukrainian (uk)
        ("явно підтверджено",                    "Твердження явно підтверджено офіційними джерелами."),
        ("однозначно підтверджено",              "Дані однозначно підтверджено трьома незалежними джерелами."),
        # Turkish (tr)
        ("açıkça doğrulandı",                    "İddia resmi kaynaklar tarafından açıkça doğrulandı."),
        ("kesinlikle doğrulandı",                "Veriler üç birincil kaynak tarafından kesinlikle doğrulandı."),
        # Arabic (ar)
        ("محقق بوضوح",                           "الادعاء محقق بوضوح من قبل المصادر الرسمية."),
        ("محقق بشكل لا لبس فيه",                "البيانات محقق بشكل لا لبس فيه من قبل ثلاثة مصادر مستقلة."),
        # Chinese (zh)
        ("明确核实",                              "该声明已经明确核实，通过三个独立的主要来源。"),
        ("毫无疑问核实",                          "数据已经毫无疑问核实，通过官方统计数据。"),
        # Japanese (ja)
        ("明確に確認済み",                        "この主張は公式の情報源によって明確に確認済みです。"),
        ("疑いなく確認済み",                      "データは三つの独立した情報源によって疑いなく確認済みです。"),
        # Korean (ko)
        ("명확히 확인됨",                         "이 주장은 공식 출처에 의해 명확히 확인됨."),
        ("의심할 여지 없이 확인됨",               "데이터는 세 개의 독립적인 출처에 의해 의심할 여지 없이 확인됨."),
    ])
    def test_speculative_with_verified_phrase_overridden_to_verified(self, phrase, rationale_template):
        from backend.analysis.engine import _correct_claude_rating

        args = {"rating": "speculative", "rationale": rationale_template, "sources": []}
        result = _correct_claude_rating(args)
        assert result["rating"] == "verified", (
            f"Expected 'speculative' → 'verified' correction for phrase {phrase!r}"
        )
        assert args["rating"] == "speculative"

    @pytest.mark.parametrize("phrase,rationale_template", [
        # English
        ("the claim is false", "After reviewing the evidence, the claim is false."),
        ("is therefore false", "The data contradicts the statement; it is therefore false."),
        ("is not correct",     "The statistic is not correct based on official records."),
        # German (de)
        ("ist daher falsch",   "Die Zahlen belegen, dass die Behauptung ist daher falsch."),
        ("ist falsch",         "Die Aussage ist falsch laut Primärquellen."),
        ("nicht erfüllt",      "Das Kriterium ist nicht erfüllt."),
        ("widerlegt",          "Die Behauptung wird durch Gegenevidenz widerlegt."),
        ("klar widerlegt",     "Die Behauptung ist klar widerlegt durch amtliche Daten."),
        ("eindeutig widerlegt","Die Aussage ist eindeutig widerlegt durch drei Primärquellen."),
        ("zweifelsfrei falsch","Die Behauptung ist zweifelsfrei falsch laut offiziellen Quellen."),
        ("ist klar widerlegt", "Die Aussage ist klar widerlegt und entspricht nicht den Fakten."),
        # French (fr)
        ("clairement réfuté",       "L'affirmation est clairement réfuté par des sources officielles."),
        ("sans aucun doute faux",   "Les données montrent sans aucun doute faux que le chiffre est incorrect."),
        # Italian (it)
        ("chiaramente confutato",        "L'affermazione è chiaramente confutato da fonti primarie."),
        ("inequivocabilmente falso",     "Il dato è inequivocabilmente falso secondo fonti ufficiali."),
        # Spanish (es)
        ("claramente refutado",          "La afirmación está claramente refutado por fuentes oficiales."),
        ("inequívocamente falso",        "El dato es inequívocamente falso según las estadísticas oficiales."),
        # Portuguese (pt)
        ("claramente refutado",          "A afirmação está claramente refutado por fontes primárias."),
        ("inequivocamente falso",        "O dado é inequivocamente falso segundo as estatísticas oficiais."),
        # Dutch (nl)
        ("duidelijk weerlegd",           "De bewering is duidelijk weerlegd door officiële bronnen."),
        ("ondubbelzinnig onjuist",       "De gegevens zijn ondubbelzinnig onjuist volgens drie primaire bronnen."),
        # Polish (pl)
        ("wyraźnie obalony",             "Twierdzenie jest wyraźnie obalony przez oficjalne źródła."),
        ("jednoznacznie fałszywy",       "Dane są jednoznacznie fałszywy według statystyk oficjalnych."),
        # Swedish (sv)
        ("tydligt motbevisat",           "Påståendet är tydligt motbevisat av officiella källor."),
        ("otvetydigt falskt",            "Uppgifterna är otvetydigt falskt enligt tre primära källor."),
        # Danish (da)
        ("tydeligt afkræftet",           "Påstanden er tydeligt afkræftet af officielle kilder."),
        ("utvetydigt falsk",             "Dataene er utvetydigt falsk ifølge tre primære kilder."),
        # Finnish (fi)
        ("selvästi kumottu",             "Väite on selvästi kumottu virallisten lähteiden perusteella."),
        ("yksiselitteisesti väärä",      "Tiedot ovat yksiselitteisesti väärä virallisten tilastojen mukaan."),
        # Czech (cs)
        ("jasně vyvráceno",              "Tvrzení je jasně vyvráceno oficiálními zdroji."),
        ("jednoznačně nepravdivé",       "Data jsou jednoznačně nepravdivé podle officiálních statistik."),
        # Romanian (ro)
        ("clar infirmat",                "Afirmația este clar infirmat de surse oficiale."),
        ("fără îndoială fals",           "Datele sunt fără îndoială fals conform statisticilor oficiale."),
        # Greek (el)
        ("σαφώς διαψεύστηκε",            "Ο ισχυρισμός σαφώς διαψεύστηκε από επίσημες πηγές."),
        ("αναμφίβολα ψευδές",            "Τα δεδομένα είναι αναμφίβολα ψευδές σύμφωνα με τρεις πηγές."),
        # Hungarian (hu)
        ("egyértelműen megcáfolt",       "Az állítás egyértelműen megcáfolt hivatalos forrásokkal."),
        ("kétségtelenül hamis",          "Az adatok kétségtelenül hamis három elsődleges forrás szerint."),
        # Russian (ru)
        ("явно опровергнуто",            "Утверждение явно опровергнуто официальными источниками."),
        ("однозначно ложно",             "Данные однозначно ложно по данным трёх независимых источников."),
        # Ukrainian (uk)
        ("явно спростовано",             "Твердження явно спростовано офіційними джерелами."),
        ("однозначно хибно",             "Дані однозначно хибно за даними трьох незалежних джерел."),
        # Turkish (tr)
        ("açıkça çürütüldü",             "İddia resmi kaynaklar tarafından açıkça çürütüldü."),
        ("kesinlikle yanlış",            "Veriler üç birincil kaynağa göre kesinlikle yanlış."),
        # Arabic (ar)
        ("مدحوض بوضوح",                  "الادعاء مدحوض بوضوح من قبل المصادر الرسمية."),
        ("خاطئ بشكل لا لبس فيه",        "البيانات خاطئ بشكل لا لبس فيه وفقاً لثلاثة مصادر مستقلة."),
        # Chinese (zh)
        ("明确驳斥",                      "该声明已经明确驳斥，通过三个独立的主要来源。"),
        ("毫无疑问错误",                  "数据毫无疑问错误，与官方统计数据相矛盾。"),
        # Japanese (ja)
        ("明確に反証済み",                "この主張は公式の情報源によって明確に反証済みです。"),
        ("疑いなく誤り",                  "データは三つの独立した情報源によって疑いなく誤りです。"),
        # Korean (ko)
        ("명확히 반증됨",                 "이 주장은 공식 출처에 의해 명확히 반증됨."),
        ("의심할 여지 없이 거짓",         "데이터는 세 개의 독립적인 출처에 의해 의심할 여지 없이 거짓."),
    ])
    def test_speculative_with_debunk_phrase_overridden_to_debunked(self, phrase, rationale_template):
        from backend.analysis.engine import _correct_claude_rating

        args = {"rating": "speculative", "rationale": rationale_template, "sources": []}
        result = _correct_claude_rating(args)
        assert result["rating"] == "debunked", (
            f"Expected 'speculative' → 'debunked' correction for phrase {phrase!r}"
        )
        assert args["rating"] == "speculative"

    def test_debunk_phrase_takes_priority_over_verified_phrase(self):
        from backend.analysis.engine import _correct_claude_rating

        args = {
            "rating": "speculative",
            "rationale": "The claim is false but also the claim is verified.",
            "sources": [],
        }
        result = _correct_claude_rating(args)
        assert result["rating"] == "debunked"

    def test_speculative_without_any_phrase_unchanged(self):
        from backend.analysis.engine import _correct_claude_rating

        args = {
            "rating": "speculative",
            "rationale": "Evidence is thin and contradictory. Cannot determine outcome.",
            "sources": [],
        }
        result = _correct_claude_rating(args)
        assert result["rating"] == "speculative"

    def test_non_speculative_ratings_not_affected(self):
        from backend.analysis.engine import _correct_claude_rating

        for rating in ("verified", "debunked", "missing"):
            args = {
                "rating": rating,
                "rationale": "therefore verified",
                "sources": [],
            }
            result = _correct_claude_rating(args)
            assert result["rating"] == rating, (
                f"Rating {rating!r} must not be mutated by _correct_claude_rating"
            )

    def test_correction_is_case_insensitive(self):
        from backend.analysis.engine import _correct_claude_rating

        args = {
            "rating": "speculative",
            "rationale": "THE CLAIM IS VERIFIED by official primary sources.",
            "sources": [],
        }
        result = _correct_claude_rating(args)
        assert result["rating"] == "verified"

    def test_original_dict_not_mutated(self):
        from backend.analysis.engine import _correct_claude_rating

        args = {"rating": "speculative", "rationale": "therefore verified", "sources": []}
        _correct_claude_rating(args)
        assert args["rating"] == "speculative"


# ── analyze_claim_with_consensus — helpers ────────────────────────────────────

_THREE_INDEPENDENT_PRIMARIES = [
    {
        "url": f"https://www.bls.gov/data/consensus-{i}",
        "tier": "primary",
        "is_independent": True,
        "relevance_score": 0.9,
        "supports_claim": True,
    }
    for i in range(3)
]


def _make_mock_session(claim_text: str = "Test claim"):
    mock_claim = MagicMock()
    mock_claim.text = claim_text

    mock_session = MagicMock()
    mock_session.get.return_value = mock_claim
    return mock_session


def _run_consensus(
    claude_judgment: dict,
    mistral_judgment: dict | None,
    *,
    mistral_raises: Exception | None = None,
    mistral_key: str = "fake-key",
    brave_key: str = "",
    claim_text: str = "Test claim",
):
    """
    Run analyze_claim_with_consensus with fully mocked I/O.
    Returns (judgment, evaluated_sources) captured from session.add() / session.add_all().

    brave_key defaults to "" so Brave Search is bypassed and _mistral_phase2_judgment
    (which is mocked here) receives Claude's findings — matching pre-Brave behaviour.
    Pass a non-empty brave_key to exercise the Brave code path, but then also mock
    _mistral_phase1_brave_search at the call site.
    """
    from backend.analysis import consensus as cons
    from backend.db.models import EvaluatedSource, Judgment

    mock_session = _make_mock_session(claim_text)
    captured: dict = {"sources": []}

    def fake_add(obj):
        if isinstance(obj, Judgment):
            captured["judgment"] = obj

    def fake_add_all(objs):
        captured["sources"].extend(o for o in objs if isinstance(o, EvaluatedSource))

    mock_session.add.side_effect = fake_add
    mock_session.add_all.side_effect = fake_add_all

    with patch.object(cons, "_check_specificity", return_value=(True, "")), \
         patch.object(cons, "_phase1_search", return_value="search findings"), \
         patch.object(cons, "_phase2_judgment", return_value=claude_judgment), \
         patch.object(cons, "_get_client", return_value=MagicMock()), \
         patch("backend.analysis.consensus.settings") as mock_settings:

        mock_settings.mistral_api_key = mistral_key
        mock_settings.brave_api_key = brave_key
        mock_settings.searxng_url = ""

        if mistral_raises is not None:
            patch_target = patch.object(cons, "_mistral_phase2_judgment", side_effect=mistral_raises)
        elif mistral_judgment is not None:
            patch_target = patch.object(cons, "_mistral_phase2_judgment", return_value=mistral_judgment)
        else:
            patch_target = patch.object(cons, "_mistral_phase2_judgment", return_value={})

        with patch_target:
            cons.analyze_claim_with_consensus("claim-1", mock_session)

    return captured.get("judgment"), captured["sources"]


# ── analyze_claim_with_consensus — integration tests ─────────────────────────

class TestAnalyzeClaimWithConsensus:

    def test_models_agree_stores_correct_consensus_fields(self):
        claude_j = {"rationale": "Claude says verified.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral agrees.", "sources": [], "rating": "verified"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert j.rating == EpistemicRating.VERIFIED
        assert j.consensus_rating == EpistemicRating.VERIFIED
        assert j.models_agree is True
        assert j.analyst == "claude-sonnet-4-6"
        assert j.analyst_secondary == "mistral-large-2512"

    def test_models_agree_rationale_is_claude_rationale(self):
        claude_j = {"rationale": "Claude rationale.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral rationale.", "sources": [], "rating": "verified"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert j.rationale == "Claude rationale."

    def test_models_disagree_source_quality_advantage_wins(self):
        """Claude has Primary/Independent sources; Mistral has none — Claude's rating wins."""
        claude_j = {"rationale": "Claude says verified.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral says debunked.", "sources": [], "rating": "debunked"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert j.rating == EpistemicRating.VERIFIED
        assert j.consensus_rating == EpistemicRating.VERIFIED
        assert j.models_agree is False

    def test_models_disagree_no_source_advantage_is_speculative(self):
        """Neither model has Primary/Independent sources — disagreement falls back to SPECULATIVE."""
        claude_j = {"rationale": "Claude says verified.", "sources": [], "rating": "verified"}
        mistral_j = {"rationale": "Mistral says debunked.", "sources": [], "rating": "debunked"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert j.rating == EpistemicRating.SPECULATIVE
        assert j.consensus_rating == EpistemicRating.SPECULATIVE
        assert j.models_agree is False

    def test_models_disagree_rationale_includes_both_verdicts(self):
        claude_j = {"rationale": "Claude says verified.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral says debunked.", "sources": [], "rating": "debunked"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert "VERIFIED" in j.rationale
        assert "DEBUNKED" in j.rationale
        assert "source quality" in j.rationale  # resolved by source quality, not SPECULATIVE

    def test_models_disagree_rationale_speculative_note_when_no_advantage(self):
        claude_j = {"rationale": "Claude says verified.", "sources": [], "rating": "verified"}
        mistral_j = {"rationale": "Mistral says debunked.", "sources": [], "rating": "debunked"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert "Consensus downgraded to SPECULATIVE" in j.rationale

    def test_mistral_phase2_raises_falls_back_to_claude(self):
        claude_j = {"rationale": "Claude only.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}

        j, _ = _run_consensus(claude_j, None, mistral_raises=RuntimeError("API timeout"))

        assert j.rating == EpistemicRating.VERIFIED
        assert j.models_agree is None
        assert j.analyst_secondary is None
        assert j.consensus_rating == EpistemicRating.VERIFIED

    def test_no_mistral_key_falls_back_to_claude(self):
        claude_j = {"rationale": "Claude only.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "speculative"}

        j, _ = _run_consensus(claude_j, None, mistral_key="")

        assert j.rating == EpistemicRating.SPECULATIVE
        assert j.models_agree is None
        assert j.analyst_secondary is None

    def test_mistral_invalid_rating_treated_as_unavailable(self):
        """If Mistral returns an unrecognised rating string, Mistral's verdict is ignored."""
        claude_j = {"rationale": "Claude says verified.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Weird.", "sources": [], "rating": "not-a-real-rating"}

        j, _ = _run_consensus(claude_j, mistral_j)

        # Mistral rating was invalid → mistral_rating=None → pass-through
        assert j.rating == EpistemicRating.VERIFIED
        assert j.models_agree is None

    def test_vague_claim_returns_missing_without_secondary(self):
        from backend.analysis import consensus as cons
        from backend.db.models import Judgment

        mock_session = _make_mock_session()
        captured: dict = {}

        def fake_add(obj):
            if isinstance(obj, Judgment):
                captured["judgment"] = obj

        mock_session.add.side_effect = fake_add
        mock_session.add_all.side_effect = lambda objs: None

        with patch.object(cons, "_check_specificity", return_value=(False, "Too vague.")), \
             patch.object(cons, "_get_client", return_value=MagicMock()), \
             patch("backend.analysis.consensus.settings") as mock_settings:
            mock_settings.mistral_api_key = "fake-key"
            mock_settings.brave_api_key = ""
            cons.analyze_claim_with_consensus("claim-1", mock_session)

        j = captured["judgment"]
        assert j.rating == EpistemicRating.MISSING
        assert j.analyst_secondary is None
        assert j.models_agree is None

    def test_claim_not_found_raises_value_error(self):
        from backend.analysis import consensus as cons

        mock_session = MagicMock()
        mock_session.get.return_value = None

        with patch.object(cons, "_get_client", return_value=MagicMock()), \
             patch("backend.analysis.consensus.settings") as mock_settings:
            mock_settings.mistral_api_key = "fake-key"
            mock_settings.brave_api_key = ""
            with pytest.raises(ValueError, match="not found"):
                cons.analyze_claim_with_consensus("nonexistent", mock_session)

    def test_models_agree_no_sources_returns_missing(self):
        """Both agree on MISSING when no sources are available."""
        claude_j = {"rationale": "No evidence.", "sources": [], "rating": "missing"}
        mistral_j = {"rationale": "No evidence.", "sources": [], "rating": "missing"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert j.rating == EpistemicRating.MISSING
        assert j.models_agree is True

    def test_mistral_secondary_field_absent_on_fallback(self):
        """analyst_secondary must be null when Mistral was not used."""
        claude_j = {"rationale": "Claude.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}

        j, _ = _run_consensus(claude_j, None, mistral_key="")

        assert j.analyst_secondary is None

    def test_mistral_secondary_field_set_when_mistral_ran(self):
        claude_j = {"rationale": "Claude.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral.", "sources": [], "rating": "verified"}

        j, _ = _run_consensus(claude_j, mistral_j)

        assert j.analyst_secondary == "mistral-large-2512"

    def test_evaluated_sources_persisted_when_claude_hard_rule_fires(self):
        """
        EvaluatedSource objects must be added to the session even when the Claude
        Hard Rule downgrades the rating from VERIFIED to SPECULATIVE (no independent
        qualifying source present).
        """
        from backend.db.models import EvaluatedSource

        # Claude claims VERIFIED but provides only a tertiary, non-qualifying source
        # so the Hard Rule will fire and downgrade to SPECULATIVE.
        non_qualifying_source = {
            "url": "https://example.com/tertiary",
            "title": "Tertiary Source",
            "tier": "tertiary",
            "is_independent": True,
            "relevance_score": 0.8,
            "supports_claim": True,
        }
        claude_j = {
            "rationale": "Claude says verified.",
            "sources": [non_qualifying_source],
            "rating": "verified",
        }
        mistral_j = {"rationale": "Mistral agrees.", "sources": [], "rating": "verified"}

        j, sources = _run_consensus(claude_j, mistral_j)

        # Hard Rule should have downgraded the rating
        assert j.rating == EpistemicRating.SPECULATIVE
        # Sources must still be persisted despite the downgrade
        assert len(sources) == 1
        assert all(isinstance(s, EvaluatedSource) for s in sources)
        assert sources[0].url == "https://example.com/tertiary"

    def test_evaluated_sources_persisted_when_consensus_hard_rule_fires(self):
        """
        EvaluatedSource objects must be added to the session even when the consensus
        Hard Rule downgrades the consensus rating from VERIFIED to SPECULATIVE.
        Both models agree on VERIFIED but Claude has no independent qualifying source,
        so the consensus Hard Rule fires.
        """
        from backend.db.models import EvaluatedSource

        # Both models say VERIFIED, but Claude's source is tertiary (non-qualifying),
        # which means claude_has_qualifying=False and the consensus Hard Rule fires.
        non_qualifying_source = {
            "url": "https://wiki.example.com/page",
            "title": "Wikipedia Page",
            "tier": "tertiary",
            "is_independent": True,
            "relevance_score": 0.75,
            "supports_claim": True,
        }
        claude_j = {
            "rationale": "Claude says verified.",
            "sources": [non_qualifying_source],
            "rating": "verified",
        }
        mistral_j = {"rationale": "Mistral agrees.", "sources": [], "rating": "verified"}

        j, sources = _run_consensus(claude_j, mistral_j)

        # Consensus Hard Rule should have downgraded to SPECULATIVE
        assert j.rating == EpistemicRating.SPECULATIVE
        assert j.consensus_rating == EpistemicRating.SPECULATIVE
        # Sources must be persisted in all cases
        assert len(sources) == 1
        assert isinstance(sources[0], EvaluatedSource)
        assert sources[0].url == "https://wiki.example.com/page"


# ── _mistral_phase1_brave_search ──────────────────────────────────────────────

def _make_brave_http_mock(results: list[dict]) -> MagicMock:
    """Return a mock httpx.Client context manager that yields the given results."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"web": {"results": results}}

    mock_http = MagicMock()
    mock_http.__enter__ = MagicMock(return_value=mock_http)
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.get.return_value = mock_response
    return mock_http


class TestBraveSearch:

    def test_returns_formatted_findings_for_valid_response(self):
        from backend.analysis.consensus import _mistral_phase1_brave_search

        results = [
            {"title": "Article A", "url": "https://a.example/1", "description": "Excerpt A."},
            {"title": "Article B", "url": "https://b.example/2", "description": "Excerpt B."},
        ]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "test-brave-key"
            s.searxng_url = ""
            output = _mistral_phase1_brave_search("test claim")

        assert "Article A" in output
        assert "https://a.example/1" in output
        assert "Excerpt A." in output
        assert "Article B" in output
        assert "https://b.example/2" in output

    def test_numbers_each_source(self):
        from backend.analysis.consensus import _mistral_phase1_brave_search

        results = [
            {"title": f"Title {i}", "url": f"https://x.example/{i}", "description": f"Desc {i}."}
            for i in range(3)
        ]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            output = _mistral_phase1_brave_search("claim")

        assert "Source 1:" in output
        assert "Source 2:" in output
        assert "Source 3:" in output

    def test_returns_empty_string_when_key_absent(self):
        """No HTTP call is made and "" is returned immediately when key is not configured."""
        from backend.analysis.consensus import _mistral_phase1_brave_search

        with patch("backend.analysis.consensus.httpx.Client") as mock_client_cls, \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = ""
            s.searxng_url = ""
            result = _mistral_phase1_brave_search("claim")

        assert result == ""
        mock_client_cls.assert_not_called()

    def test_returns_empty_string_when_results_empty(self):
        """Empty result list → "" (not an exception)."""
        from backend.analysis.consensus import _mistral_phase1_brave_search

        mock_http = _make_brave_http_mock([])

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            result = _mistral_phase1_brave_search("claim")

        assert result == ""

    def test_returns_empty_string_on_http_error(self):
        """HTTP error is caught and "" is returned so Mistral still runs."""
        from backend.analysis.consensus import _mistral_phase1_brave_search
        import httpx

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403", request=MagicMock(), response=MagicMock()
        )

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            result = _mistral_phase1_brave_search("claim")

        assert result == ""

    def test_returns_empty_string_on_connection_error(self):
        """Network-level failures are also caught and return ""."""
        from backend.analysis.consensus import _mistral_phase1_brave_search
        import httpx

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.side_effect = httpx.ConnectError("connection refused")

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "key"
            s.searxng_url = ""
            result = _mistral_phase1_brave_search("claim")

        assert result == ""

    def test_sends_claim_as_query_param(self):
        from backend.analysis.consensus import _mistral_phase1_brave_search

        results = [{"title": "T", "url": "https://t.example/", "description": "D"}]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "my-key"
            s.searxng_url = ""
            _mistral_phase1_brave_search("Joe Biden said X")

        call_kwargs = mock_http.get.call_args
        assert call_kwargs.kwargs["params"]["q"] == "Joe Biden said X"

    def test_sends_api_key_header(self):
        from backend.analysis.consensus import _mistral_phase1_brave_search

        results = [{"title": "T", "url": "https://t.example/", "description": "D"}]
        mock_http = _make_brave_http_mock(results)

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "my-secret"
            s.searxng_url = ""
            _mistral_phase1_brave_search("claim text")

        call_kwargs = mock_http.get.call_args
        assert call_kwargs.kwargs["headers"]["X-Subscription-Token"] == "my-secret"


# ── Brave integration in analyze_claim_with_consensus ─────────────────────────

class TestBraveIntegration:

    def test_mistral_receives_brave_findings_when_brave_available(self):
        """When BRAVE_API_KEY is set and Brave succeeds, Mistral Phase 2 gets Brave findings."""
        from backend.analysis import consensus as cons

        claude_j = {"rationale": "Claude.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral.", "sources": [], "rating": "verified"}

        mock_session = _make_mock_session()
        mock_session.add.side_effect = lambda obj: None
        mock_session.add_all.side_effect = lambda objs: None

        captured_findings: list[str] = []

        def fake_mistral_p2(claim_text, findings, lang_instruction=""):
            captured_findings.append(findings)
            return mistral_j

        with patch.object(cons, "_check_specificity", return_value=(True, "")), \
             patch.object(cons, "_phase1_search", return_value="claude findings"), \
             patch.object(cons, "_phase2_judgment", return_value=claude_j), \
             patch.object(cons, "_get_client", return_value=MagicMock()), \
             patch.object(cons, "_mistral_phase1_brave_search", return_value="brave findings"), \
             patch.object(cons, "_mistral_phase2_judgment", side_effect=fake_mistral_p2), \
             patch("backend.analysis.consensus.settings") as mock_settings:
            mock_settings.mistral_api_key = "fake-mistral-key"
            mock_settings.brave_api_key = "fake-brave-key"
            cons.analyze_claim_with_consensus("claim-1", mock_session)

        assert captured_findings == ["brave findings"]

    def test_brave_findings_are_independent_of_claude_findings(self):
        """Mistral receives Brave findings even when Claude's findings are different."""
        from backend.analysis import consensus as cons

        claude_j = {"rationale": "Claude.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral.", "sources": [], "rating": "verified"}

        mock_session = _make_mock_session()
        mock_session.add.side_effect = lambda obj: None
        mock_session.add_all.side_effect = lambda objs: None

        captured_claude: list[str] = []
        captured_mistral: list[str] = []

        def fake_claude_p2(client, claim_text, findings, lang_instruction=""):
            captured_claude.append(findings)
            return claude_j

        def fake_mistral_p2(claim_text, findings, lang_instruction=""):
            captured_mistral.append(findings)
            return mistral_j

        with patch.object(cons, "_check_specificity", return_value=(True, "")), \
             patch.object(cons, "_phase1_search", return_value="claude-only findings"), \
             patch.object(cons, "_phase2_judgment", side_effect=fake_claude_p2), \
             patch.object(cons, "_get_client", return_value=MagicMock()), \
             patch.object(cons, "_mistral_phase1_brave_search", return_value="brave-only findings"), \
             patch.object(cons, "_mistral_phase2_judgment", side_effect=fake_mistral_p2), \
             patch("backend.analysis.consensus.settings") as mock_settings:
            mock_settings.mistral_api_key = "fake-mistral-key"
            mock_settings.brave_api_key = "fake-brave-key"
            cons.analyze_claim_with_consensus("claim-1", mock_session)

        assert captured_claude == ["claude-only findings"]
        assert captured_mistral == ["brave-only findings"]

    def test_mistral_receives_empty_string_when_brave_unavailable(self):
        """When BRAVE_API_KEY is absent, Mistral Phase 2 receives "" — not Claude's findings."""
        from backend.analysis import consensus as cons

        claude_j = {"rationale": "Claude.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral.", "sources": [], "rating": "verified"}

        mock_session = _make_mock_session()
        mock_session.add.side_effect = lambda obj: None
        mock_session.add_all.side_effect = lambda objs: None

        captured_findings: list[str] = []

        def fake_mistral_p2(claim_text, findings, lang_instruction=""):
            captured_findings.append(findings)
            return mistral_j

        with patch.object(cons, "_check_specificity", return_value=(True, "")), \
             patch.object(cons, "_phase1_search", return_value="claude findings"), \
             patch.object(cons, "_phase2_judgment", return_value=claude_j), \
             patch.object(cons, "_get_client", return_value=MagicMock()), \
             patch.object(cons, "_mistral_phase2_judgment", side_effect=fake_mistral_p2), \
             patch("backend.analysis.consensus.settings") as mock_settings:
            mock_settings.mistral_api_key = "fake-mistral-key"
            mock_settings.brave_api_key = ""
            cons.analyze_claim_with_consensus("claim-1", mock_session)

        assert captured_findings == [""]

    def test_mistral_receives_empty_string_when_brave_fails(self):
        """When Brave is configured but the request fails, Mistral gets "" — not Claude's findings."""
        from backend.analysis import consensus as cons

        claude_j = {"rationale": "Claude.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral.", "sources": [], "rating": "verified"}

        mock_session = _make_mock_session()
        mock_session.add.side_effect = lambda obj: None
        mock_session.add_all.side_effect = lambda objs: None

        captured_findings: list[str] = []

        def fake_mistral_p2(claim_text, findings, lang_instruction=""):
            captured_findings.append(findings)
            return mistral_j

        # Mock _mistral_phase1_brave_search to return "" (what it does on any failure)
        with patch.object(cons, "_check_specificity", return_value=(True, "")), \
             patch.object(cons, "_phase1_search", return_value="claude findings"), \
             patch.object(cons, "_phase2_judgment", return_value=claude_j), \
             patch.object(cons, "_get_client", return_value=MagicMock()), \
             patch.object(cons, "_mistral_phase1_brave_search", return_value=""), \
             patch.object(cons, "_mistral_phase2_judgment", side_effect=fake_mistral_p2), \
             patch("backend.analysis.consensus.settings") as mock_settings:
            mock_settings.mistral_api_key = "fake-mistral-key"
            mock_settings.brave_api_key = "fake-brave-key"
            cons.analyze_claim_with_consensus("claim-1", mock_session)

        assert captured_findings == [""]

    def test_consensus_result_correct_regardless_of_brave_availability(self):
        """Consensus rating is correct whether Mistral received Brave findings or ""."""
        claude_j = {"rationale": "Claude verified.", "sources": _THREE_INDEPENDENT_PRIMARIES, "rating": "verified"}
        mistral_j = {"rationale": "Mistral verified.", "sources": [], "rating": "verified"}

        j, _ = _run_consensus(claude_j, mistral_j)  # brave_key="" by default

        assert j.models_agree is True
        assert j.consensus_rating == EpistemicRating.VERIFIED


# ── SearXNG helpers: _query_searxng ──────────────────────────────────────────

def _make_searxng_http_mock(results: list[dict]):
    """Return a mock httpx.Client whose GET response contains the given SearXNG results."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"results": results}

    mock_http = MagicMock()
    mock_http.__enter__ = MagicMock(return_value=mock_http)
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.get.return_value = mock_response
    return mock_http


class TestQuerySearxng:

    def test_returns_normalised_results(self):
        from backend.analysis.consensus import _query_searxng

        raw = [
            {"title": "SearX Result 1", "url": "https://sx.example/1", "content": "SearXNG content 1."},
            {"title": "SearX Result 2", "url": "https://sx.example/2", "content": "SearXNG content 2."},
        ]
        mock_http = _make_searxng_http_mock(raw)

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.searxng_url = "https://searx.example.com"
            results = _query_searxng("test claim")

        assert len(results) == 2
        assert results[0]["title"] == "SearX Result 1"
        assert results[0]["url"] == "https://sx.example/1"
        assert results[0]["description"] == "SearXNG content 1."

    def test_returns_empty_list_when_url_not_configured(self):
        from backend.analysis.consensus import _query_searxng

        with patch("backend.analysis.consensus.httpx.Client") as mock_client_cls, \
             patch("backend.analysis.consensus.settings") as s:
            s.searxng_url = ""
            result = _query_searxng("claim")

        assert result == []
        mock_client_cls.assert_not_called()

    def test_returns_empty_list_on_http_error(self):
        import httpx as _httpx
        from backend.analysis.consensus import _query_searxng

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.return_value.raise_for_status.side_effect = _httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.searxng_url = "https://searx.example.com"
            result = _query_searxng("claim")

        assert result == []

    def test_returns_empty_list_on_connection_error(self):
        import httpx as _httpx
        from backend.analysis.consensus import _query_searxng

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.side_effect = _httpx.ConnectError("refused")

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.searxng_url = "https://searx.example.com"
            result = _query_searxng("claim")

        assert result == []

    def test_sends_correct_query_params(self):
        from backend.analysis.consensus import _query_searxng

        mock_http = _make_searxng_http_mock([
            {"title": "T", "url": "https://t.example/", "content": "C"}
        ])

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.searxng_url = "https://searx.example.com"
            _query_searxng("specific claim text")

        call_kwargs = mock_http.get.call_args
        assert call_kwargs.kwargs["params"]["q"] == "specific claim text"
        assert call_kwargs.kwargs["params"]["format"] == "json"
        assert call_kwargs.kwargs["params"]["categories"] == "general"

    def test_strips_trailing_slash_from_url(self):
        from backend.analysis.consensus import _query_searxng

        mock_http = _make_searxng_http_mock([])

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.searxng_url = "https://searx.example.com/"
            _query_searxng("claim")

        called_url = mock_http.get.call_args.args[0]
        assert called_url == "https://searx.example.com/search"


class TestSearxngInMistralPhase1:

    def test_searxng_results_included_when_configured(self):
        """When SEARXNG_URL is set and Brave is absent, SearXNG results are returned."""
        from backend.analysis.consensus import _mistral_phase1_brave_search

        raw = [{"title": "SX Title", "url": "https://sx.example/1", "content": "SX content."}]
        mock_http = _make_searxng_http_mock(raw)

        with patch("backend.analysis.consensus.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = ""
            s.searxng_url = "https://searx.example.com"
            output = _mistral_phase1_brave_search("test claim")

        assert "SX Title" in output
        assert "https://sx.example/1" in output
        assert "SX content." in output

    def test_deduplicates_by_url_when_both_sources_return_same_url(self):
        """URLs present in both Brave and SearXNG results appear only once."""
        from backend.analysis.consensus import _mistral_phase1_brave_search

        shared_url = "https://shared.example/article"
        brave_results = [
            {"title": "Brave Version", "url": shared_url, "description": "Brave excerpt."},
        ]
        searxng_results = [
            {"title": "SearXNG Version", "url": shared_url, "content": "SearXNG excerpt."},
            {"title": "SearXNG Unique", "url": "https://unique.example/", "content": "Unique."},
        ]

        with patch("backend.analysis.consensus._query_brave", return_value=brave_results), \
             patch("backend.analysis.consensus._query_searxng", return_value=[
                 {"title": "SearXNG Version", "url": shared_url, "description": "SearXNG excerpt."},
                 {"title": "SearXNG Unique", "url": "https://unique.example/", "description": "Unique."},
             ]), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "brave-key"
            s.searxng_url = "https://searx.example.com"
            output = _mistral_phase1_brave_search("claim")

        # shared URL appears exactly once
        assert output.count(shared_url) == 1
        # unique SearXNG URL is also present
        assert "https://unique.example/" in output

    def test_merges_brave_and_searxng_results(self):
        """When both sources are configured, results from both are present."""
        from backend.analysis.consensus import _mistral_phase1_brave_search

        brave_results = [
            {"title": "Brave Article", "url": "https://brave.example/1", "description": "Brave desc."},
        ]
        searxng_results = [
            {"title": "SearXNG Article", "url": "https://searxng.example/1", "description": "SearX desc."},
        ]

        with patch("backend.analysis.consensus._query_brave", return_value=brave_results), \
             patch("backend.analysis.consensus._query_searxng", return_value=searxng_results), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "brave-key"
            s.searxng_url = "https://searx.example.com"
            output = _mistral_phase1_brave_search("claim")

        assert "Brave Article" in output
        assert "https://brave.example/1" in output
        assert "SearXNG Article" in output
        assert "https://searxng.example/1" in output

    def test_returns_empty_string_when_both_unconfigured(self):
        """No HTTP call when neither Brave key nor SearXNG URL is set."""
        from backend.analysis.consensus import _mistral_phase1_brave_search

        with patch("backend.analysis.consensus.httpx.Client") as mock_client_cls, \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = ""
            s.searxng_url = ""
            result = _mistral_phase1_brave_search("claim")

        assert result == ""
        mock_client_cls.assert_not_called()

    def test_searxng_failure_still_returns_brave_results(self):
        """If SearXNG fails, Brave results are still returned (graceful degradation)."""
        from backend.analysis.consensus import _mistral_phase1_brave_search

        brave_results = [
            {"title": "Brave OK", "url": "https://brave.example/1", "description": "Brave desc."},
        ]

        with patch("backend.analysis.consensus._query_brave", return_value=brave_results), \
             patch("backend.analysis.consensus._query_searxng", return_value=[]), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "brave-key"
            s.searxng_url = "https://searx.example.com"
            output = _mistral_phase1_brave_search("claim")

        assert "Brave OK" in output

    def test_brave_failure_still_returns_searxng_results(self):
        """If Brave fails, SearXNG results are still returned (graceful degradation)."""
        from backend.analysis.consensus import _mistral_phase1_brave_search

        searxng_results = [
            {"title": "SearX OK", "url": "https://searxng.example/1", "description": "SearX desc."},
        ]

        with patch("backend.analysis.consensus._query_brave", return_value=[]), \
             patch("backend.analysis.consensus._query_searxng", return_value=searxng_results), \
             patch("backend.analysis.consensus.settings") as s:
            s.brave_api_key = "brave-key"
            s.searxng_url = "https://searx.example.com"
            output = _mistral_phase1_brave_search("claim")

        assert "SearX OK" in output


# ── SearXNG integration in Claude's search phase (engine.py) ─────────────────

class TestSearxngInClaudeSearch:

    def test_searxng_appended_to_claude_findings(self):
        """When SEARXNG_URL is set, SearXNG context is appended to Claude's findings."""
        from backend.analysis import engine as eng

        with patch.object(eng, "_query_searxng_context", return_value="SearXNG context here"), \
             patch("backend.analysis.engine.settings") as s:
            s.searxng_url = "https://searx.example.com"

            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_block = MagicMock()
            mock_block.text = "Claude findings"
            mock_resp.content = [mock_block]
            mock_client.messages.create.return_value = mock_resp

            result = eng._phase1_search(mock_client, "test claim")

        assert "Claude findings" in result
        assert "SearXNG context here" in result

    def test_searxng_not_queried_when_url_empty(self):
        """When SEARXNG_URL is empty, _query_searxng_context returns "" without HTTP call."""
        from backend.analysis import engine as eng

        with patch("backend.analysis.engine.httpx.Client") as mock_client_cls, \
             patch("backend.analysis.engine.settings") as s:
            s.searxng_url = ""
            result = eng._query_searxng_context("claim text")

        assert result == ""
        mock_client_cls.assert_not_called()

    def test_searxng_context_returns_formatted_results(self):
        """_query_searxng_context formats results with title, URL and excerpt."""
        from backend.analysis import engine as eng

        raw = [
            {"title": "Engine Source", "url": "https://eng.example/1", "content": "Engine excerpt."},
        ]
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"results": raw}
        mock_http.get.return_value = mock_response

        with patch("backend.analysis.engine.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.engine.settings") as s:
            s.searxng_url = "https://searx.example.com"
            result = eng._query_searxng_context("test claim")

        assert "Engine Source" in result
        assert "https://eng.example/1" in result
        assert "Engine excerpt." in result

    def test_searxng_context_returns_empty_on_http_error(self):
        """_query_searxng_context returns "" gracefully on HTTP failure."""
        import httpx as _httpx
        from backend.analysis import engine as eng

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.return_value.raise_for_status.side_effect = _httpx.HTTPStatusError(
            "503", request=MagicMock(), response=MagicMock()
        )

        with patch("backend.analysis.engine.httpx.Client", return_value=mock_http), \
             patch("backend.analysis.engine.settings") as s:
            s.searxng_url = "https://searx.example.com"
            result = eng._query_searxng_context("claim")

        assert result == ""

    def test_phase1_search_returns_searxng_only_when_claude_search_fails(self):
        """When Claude's web search is unavailable, SearXNG results are returned."""
        from backend.analysis import engine as eng

        with patch.object(eng, "_query_searxng_context", return_value="SearXNG only results"), \
             patch("backend.analysis.engine.settings") as s:
            s.searxng_url = "https://searx.example.com"

            mock_client = MagicMock()
            mock_client.messages.create.side_effect = Exception("network error")

            result = eng._phase1_search(mock_client, "test claim")

        assert result == "SearXNG only results"
