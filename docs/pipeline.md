# GradedFacts — Pipeline-Dokumentation v1.0
*Stand: 11. Juni 2026 · Belegt durch Live-Audit mit 3 Test-Claims (10.–11. Juni 2026)*

---

## Zweck dieses Dokuments

Dieses Dokument beantwortet vor dem Release belegbar die vier Kernfragen:
1. Welche Suchquellen nutzen Claude und Mistral?
2. Welche URLs werden gefunden und übergeben?
3. Wie werden Quellen klassifiziert?
4. Wie entsteht das finale Rating?

Jeder Mechanismus ist durch mindestens einen Live-Logauszug (uvicorn.log, Produktivserver) aus den drei Audit-Claims belegt. Die Audit-Claims decken bewusst unterschiedliche Fälle ab: historisch-strittig (NATO), Breaking News (Trump/UFC), aktuell-im-Fluss + englischsprachig (EU-Verbrenner).

**Audit-Claims:**
| # | Claim | Sprache | Revisionen | Belegte Mechanismen |
|---|---|---|---|---|
| 1 | "Die NATO hat der Sowjetunion 1990 zugesichert, sich niemals nach Osteuropa auszudehnen" | DE | 6 | Suche, Konsens-Matrix, Dedup/Revisionen, Quellen-pro-Revision, Single-Active-Invariant |
| 2 | "Der U.S. Präsident Donald Trump will an seinem 80. geburtstage einen UFC kampfsport Event vor dem weissen haus abhalten. dies ohne zustimmung des kongress" | DE | 4 | Rating-Gate (Härtung), Threshold-Cap, Auto-Discovery |
| 3 | "The EU has banned the sale of new combustion engine cars from 2035." | EN | 2 | Tiebreaker, Sprach-Routing, Gate-No-Upgrade, Polarity-Pfad |

---

## 1. Suchquellen

**Beide Modelle nutzen identische, unabhängige Suchquellen:** Brave Search API und die selbst gehostete SearXNG-Instanz (195.15.237.247, Infomaniak Jelastic, Schweiz). Anthropic Web Search wird **nicht** verwendet (am 10.6. aus der Claude-Pipeline entfernt).

**Implementierung:** Geteiltes Modul `backend/sources/search.py`, Funktion `search_claim(claim_text)`:
- Der Claim-Text selbst ist die Suchquery (kein LLM-generierter Query-Loop — deterministisch, symmetrisch)
- Brave und SearXNG werden parallel abgefragt (ThreadPoolExecutor)
- Resultate werden per URL dedupliziert und auf max. 20 Findings gekappt (Reihenfolge: Brave zuerst)
- Beide Modell-Pipelines rufen exakt dieselbe Funktion auf

**Konsequenz für die Methodik:** Da beide Modelle denselben Evidenzpool sehen, können Konsens-Differenzen nur aus der Bewertung stammen, nicht aus unterschiedlichen Indizes. Restvarianz zwischen Durchläufen stammt aus der Suchresultat-Varianz der Indizes selbst (siehe §7).

**Live-Beleg (Claim 1, 10.6.):**
```
[DEBUG sources] brave_urls=10
[DEBUG sources] searxng_urls=10
[DEBUG sources] brave_urls=10
[DEBUG sources] searxng_urls=10
```
Zwei Pipelines (Claude, Mistral), je beide Quellen. Beleg auch bei Claim 3 (EN): `brave_urls=10 / searxng_urls=25`.

---

## 2. URL-Übergabe an die Modelle

Die Findings werden als formatierter Klartext ("Source N: title / URL / Excerpt") in die User-Message des jeweiligen Modells injiziert. Die System-Prompts sind als **Evidence-Evaluation** formuliert: Die Modelle führen keine eigene Suche aus, sondern bewerten ausschliesslich die bereitgestellten Findings. Zitierregel im Prompt (SOURCE CITATION RULE): Es dürfen nur Quellen zitiert werden, die in den Findings vorkommen — keine Quellen aus dem Modellgedächtnis.

Beide Modelle laufen parallel mit temperature=0, gepinnte Versionen (claude-sonnet-4-6, mistral-large-2512); Modellversionen werden als Judgment-Metadata gespeichert.

**Sprach-Routing:** Rationale-Sprache = UI-Sprache (Hard Rule #11). Die Sprachanweisung wird beiden Modellen immer explizit mitgegeben — auch für Englisch (Bugfix 11.6.: leere EN-Instruktion liess Mistral in der Claim-Sprache schreiben). Live-Beleg: Claim 3 Rev. 2, EN-UI → englisches Mistral-Rationale.

---

## 3. Quellenklassifikation

Jede zitierte Quelle durchläuft `evaluate_source()`:

1. **Registry-Lookup** (`registry.json`, 274+ kuratierte Quellen, subdomain-aware): liefert Tier (Primary/Secondary/Tertiary) und Unabhängigkeit (Independent/Not independent/Neutral), inkl. Affiliation Notes (z.B. BAKS als Primär/Nicht-unabhängig mit Begründung).
2. **Auto-Discovery:** Unregistrierte Domains werden als Tertiär mit Badge "⚠ Quelle noch nicht verifiziert" geführt und in `new_sources_to_review.json` zur Review gesammelt. Live-Beleg: Claim 2 (tagesspiegel, merkur, watson etc. mit Badge), Claim 3 (theverge, caranddriver).
3. **Social-Media-Blacklist** (19 Plattformen) und Hard Rules: Wikipedia immer Tertiär; Official ≠ Independent; nicht-unabhängige Primärquellen zählen nicht zur VERIFIED-Schwelle.
4. **Domain-Deduplication** (Hard Rule #8): Mehrere Artikel derselben Domain zählen als 1 Quelle für die Schwelle ("3 articles — counts as 1 source for rating threshold" im UI).
5. **Quellen-Persistenz pro Revision:** Jede EvaluatedSource trägt eine judgment_id (FK); die Verdict-Ansicht zeigt nur Quellen des aktiven Judgments. Live-Beleg: Claim 1 — 33 akkumulierte Beweisstücke vor dem Fix, 9 danach.

---

## 4. Rating-Entstehung

Der Weg vom Modell-Output zum finalen Rating hat vier Stufen, jede mit Audit-Logging:

### 4.1 Strukturiertes Rating (Modell)
Das Rating ist ein geschlossenes englisches Enum (verified/speculative/debunked/missing) im submit_judgment-Tool-Schema. Lokalisierung ausschliesslich im Frontend via i18next (SSR-Fallback englisch). RATING LANGUAGE RULE: Das Rationale enthält keine Rating-Keywords in keiner Sprache — das Urteil steht nur im strukturierten Feld.

### 4.2 Konsistenz-Gate (Haiku, temp=0, fail-safe)
Ein Haiku-Call prüft, welches Rating das Rationale **über den Claim** schliesst (explizite Definitionen im Prompt; "judge what the rationale concludes ABOUT THE CLAIM, not whether negative words appear" — Schutz vor der Verneinungsfalle bei Rationales, die Gegenpositionen referieren).
- Übereinstimmung → kein Eingriff (Gate schweigt; Normalfall)
- UNCLEAR oder Haiku-Fehler → strukturiertes Rating bleibt (nie blockierend)
- Gegenpolaritäts-Override (verified↔debunked) nur bei doppelter Haiku-Bestätigung (`[RATING-GATE-CONFLICT]`)
- **Nie Upgrade Richtung VERIFIED** (`[RATING-GATE-NOUPGRADE]`): Das Gate korrigiert oder downgraded, hebt aber nie.

Live-Beleg (Härtungs-Anlass, Claim 2 Rev. 1, vor dem Fix): `[RATING-GATE] structured='verified' haiku_derived='debunked' → overriding` — das Gate kippte ein korrektes Rating; nach der Härtung (Rev. 3) polaritätskonsistent ohne Eingriff.

### 4.3 VERIFIED-Schwelle ([THRESHOLD-CAP], Code-Gesetz)
**Die eine Regel:** VERIFIED erfordert ≥3 verifizierende Quellen (nach Domain-Dedup) UND (≥1 unabhängige Primärquelle ODER ≥2 unabhängige Sekundärquellen). Durchgesetzt per Post-Judgment-Enforcement in beiden Pipelines, pro Modell auf dessen eigene Zitate, vor der Konsens-Resolution. Cappt nur (VERIFIED → SPECULATIVE), hebt nie. Identische Regel in beiden Prompt-Statements und in `derive_rating()`.

Live-Beleg (Claim 2 Rev. 4):
```
[THRESHOLD-CAP] (Claude): model said VERIFIED but threshold not met (verifying=0 indep_secondary=0) → SPECULATIVE.
[THRESHOLD-CAP] (Mistral): model said VERIFIED but threshold not met (verifying=7 indep_secondary=1) → SPECULATIVE.
```
Auditierbarkeit: Feuert ein Cap mit verifying=0, loggt `[THRESHOLD-CAP-DETAIL]` zusätzlich die Roh-Zitate des Modells (False-Downgrade-Überwachung).

### 4.4 Konsens-Resolution (`_resolve_consensus`)
- **Einigkeit** → Rating direkt übernommen (Normalfall; Live-Beleg Claim 1: `consensus=DEBUNKED models_agree=True`)
- **DEBUNKED + MISSING** → DEBUNKED (stärkere Evidenzlage)
- **Nicht-polare Differenz** (z.B. speculative vs. debunked): lexikographischer Quellenqualitäts-Tiebreaker über Tupel (indep. Primär, indep. Sekundär); strikt stärkeres Zitate-Set gewinnt. Live-Beleg (Claim 3 Rev. 2): `[CONSENSUS-TIEBREAK] claude=speculative mistral=debunked → debunked ((1,5) vs (1,6))`
- **Gegenpolarität** (verified↔debunked): Tiebreak nur bei **klarer Marge** — ≥1 unabh. Primärquelle mehr ODER gleich viele Primär UND ≥2 unabh. Sekundär mehr; sonst SPEKULATIV (`[CONSENSUS-POLARITY]`, margin-met/not-met). Die Entscheidung wird dem Nutzer transparent angezeigt (zwei lokalisierte Resolution-Notes, 22 Sprachen).
- Alle Resolution-Texte sind i18n-Keys (SSR-Fallback englisch).

### 4.5 Gates vor der Analyse
Vorgelagert: Specificity Gate und Off-Topic Gate (Claude Haiku) — zu vage oder nicht politisch/sachlich → MISSING (lokalisiert). Breaking-News-Claims passieren das Specificity Gate immer. Timezone Rule: Datumsangaben werden im Kontext des Claim-Landes interpretiert.

---

## 5. Speicherung & Revisionen

- **Append-only:** Urteile werden nie überschrieben. Gleicher Claim-Text → neue Revision (Dedup); Urteilshistorie zeigt alle Urteile mit Gruppierung "X gleiche / Y abweichende".
- **Single-Active-Invariant:** Pro Claim genau ein aktives Judgment; vor jedem Insert wird das vorherige atomar deaktiviert (alle Schreibpfade inkl. vague/off-topic und merge_into_canonical). Daten-Repair 10.6.: 22 Duplikat-aktive Judgments über 8 Claims bereinigt.
- **Quellen pro Revision:** EvaluatedSource → judgment_id (Alembic 0001, Timestamp-Backfill: 1119 Zeilen Server-PostgreSQL, 0 NULL).
- **PostgreSQL** (Infomaniak, Schweiz); Alembic liest DATABASE_URL 3-stufig (env var → .env/pydantic → ini-Fallback) mit Quellen-Logging.

---

## 6. Audit-Logmarker (Übersicht)

| Marker | Bedeutung |
|---|---|
| `[DEBUG sources] brave_urls/searxng_urls` | Suchlauf pro Pipeline |
| `[RATING-GATE]` | Gate-Eingriff inkl. 120-Zeichen-Rationale-Auszug |
| `[RATING-GATE-CONFLICT]` | Gegenpolaritäts-Override ohne doppelte Bestätigung verweigert |
| `[RATING-GATE-NOUPGRADE]` | Upgrade Richtung VERIFIED verweigert |
| `[THRESHOLD-CAP]` / `[THRESHOLD-CAP-DETAIL]` | VERIFIED-Schwelle durchgesetzt / Roh-Zitate bei verifying=0 |
| `[CONSENSUS-TIEBREAK]` | Nicht-polarer Quellenqualitäts-Tiebreak mit Tupeln |
| `[CONSENSUS-POLARITY]` | Polaritätsfall: margin-met → Gewinner / margin-not-met → SPEKULATIV |
| `models_agree=True/False` | Konsens-Pfad |

---

## 7. Bekannte, dokumentierte Varianz

Brave/SearXNG liefern pro Durchlauf leicht unterschiedliche Treffer. Bei identischem Claim-Text und temp=0 kann das Urteile zwischen Revisionen kippen — Claim 1 ergab über 6 Durchläufe: DEBUNKED → SPEKULATIV → DEBUNKED → DEBUNKED → DEBUNKED → SPEKULATIV (Kippfaktor jeweils Mistral; Claude konstant). Dies ist keine Fehlfunktion, sondern Suchindex-Varianz; die Urteilshistorie macht sie transparent. Für Auswertungen (Sensible Claims) gilt: Wiederholungs-Varianz von echter Asymmetrie unterscheiden, kritische Claims 2–3× laufen lassen.

---

*Dieses Dokument ist Teil der Release-Dokumentation (PRIO 0). Die nutzerseitige Beschreibung der Konsens-Matrix inkl. Polaritäts-Margen-Regel gehört zusätzlich auf /methodology (siehe TODO PRIO 3 — Methodology v1.0).*
