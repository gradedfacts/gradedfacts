# Epistemic Constitution of GradedFacts
# Epistemische Verfassung von GradedFacts

**Version:** v1.0
**Date / Datum:** June 2026
**Status:** Active / Aktiv

---

## Table of Contents / Inhaltsverzeichnis

1. [Preamble / Präambel](#1-preamble--präambel)
2. [Core Principles / Kernprinzipien](#2-core-principles--kernprinzipien)
3. [Epistemic Framework / Epistemischer Rahmen](#3-epistemic-framework--epistemischer-rahmen)
4. [Source Classification / Quellenklassifikation](#4-source-classification--quellenklassifikation)
5. [Failure Modes / Fehlermodelle](#5-failure-modes--fehlermodelle)
6. [Anti-Drift Mechanisms / Drift-Schutzmechanismen](#6-anti-drift-mechanisms--drift-schutzmechanismen)
7. [Governance / Governance](#7-governance--governance)
8. [Version History / Versionsgeschichte](#8-version-history--versionsgeschichte)

---

## 1. Preamble / Präambel

### What GradedFacts Is / Was GradedFacts ist

GradedFacts is an epistemically procedural fact-checking institution. It applies a documented, versioned, and publicly inspectable methodology to evaluate political and factual claims. It was founded in Switzerland with the explicit commitment to operate without funding from political parties, political action committees, or politically dependent media organisations.

GradedFacts ist eine epistemisch-prozedurale Faktenprüfinstitution. Sie wendet eine dokumentierte, versionierte und öffentlich einsehbare Methodik auf die Bewertung politischer und faktischer Behauptungen an. Sie wurde in der Schweiz gegründet mit dem ausdrücklichen Bekenntnis, ohne Finanzierung durch politische Parteien, politische Aktionskomitees oder politisch abhängige Medienorganisationen zu operieren.

### What GradedFacts Is Not / Was GradedFacts nicht ist

GradedFacts is **not** a truth authority. It does not possess privileged access to objective reality. It is not the final word on any claim. It is a **procedure** — a documented method for evaluating evidence — that produces outputs graded by confidence level, not by political preference.

GradedFacts ist **keine** Wahrheitsbehörde. Es hat keinen privilegierten Zugang zur objektiven Realität. Es ist nicht das letzte Wort zu einer Behauptung. Es ist ein **Verfahren** — eine dokumentierte Methode zur Bewertung von Beweisen — das Ergebnisse nach Konfidenzgrad liefert, nicht nach politischer Präferenz.

### Founding Principle / Gründungsprinzip

> GradedFacts does not tell you what to think. It documents what the evidence supports, how strongly, and under what conditions that assessment might change.

> GradedFacts sagt Ihnen nicht, was Sie denken sollen. Es dokumentiert, was die Beweise stützen, wie stark, und unter welchen Bedingungen diese Einschätzung sich ändern könnte.

---

## 2. Core Principles / Kernprinzipien

### 2.1 Symmetry Principle / Symmetrieprinzip

Every analytical method applied to a claim from one political direction is applied identically to claims from all other directions. There are no exceptions. If a claim framed as left-wing is subjected to a given evidentiary standard, an equivalent claim framed as right-wing is subjected to the identical standard, and vice versa.

Jede Analysemethode, die auf eine Behauptung aus einer politischen Richtung angewendet wird, wird identisch auf Behauptungen aus allen anderen Richtungen angewendet. Es gibt keine Ausnahmen. Wenn eine als linksorientiert gerahmte Behauptung einem bestimmten Beweisstandard unterworfen wird, wird eine gleichwertige als rechtsorientiert gerahmte Behauptung demselben Standard unterworfen, und umgekehrt.

**Enforcement mechanism:** Asymmetric output distributions (more DEBUNKED verdicts for one political direction than another, over a statistically significant sample) are treated as system errors, not as evidence that one side lies more. Investigation of asymmetry is mandatory before any public reporting on aggregate verdicts.

**Durchsetzungsmechanismus:** Asymmetrische Ausgabeverteilungen (mehr DEBUNKED-Urteile für eine politische Richtung als für eine andere, über eine statistisch signifikante Stichprobe) werden als Systemfehler behandelt, nicht als Beleg dafür, dass eine Seite mehr lügt. Die Untersuchung von Asymmetrien ist obligatorisch, bevor aggregierte Urteile öffentlich berichtet werden.

### 2.2 Transparency Principle / Transparenzprinzip

Every judgment is fully traceable. The following are always stored and publicly accessible:

- The exact claim text as submitted
- Every source evaluated, including its URL, tier classification, independence assessment, and relevance score
- The model version(s) used for analysis
- The registry version (git hash) active at the time of analysis
- The prompt version active at the time of analysis
- The full rationale, including dissenting signals from the secondary model where applicable
- The timestamp of creation and, for revisions, the trigger evidence

Jedes Urteil ist vollständig nachvollziehbar. Folgendes wird immer gespeichert und ist öffentlich zugänglich:

- Der genaue Behauptungstext wie eingereicht
- Jede bewertete Quelle, einschließlich URL, Tier-Klassifikation, Unabhängigkeitsbewertung und Relevanzscore
- Die verwendete(n) Modellversion(en)
- Die Registry-Version (Git-Hash), die zum Zeitpunkt der Analyse aktiv war
- Die Prompt-Version, die zum Zeitpunkt der Analyse aktiv war
- Die vollständige Begründung, einschließlich abweichender Signale des Sekundärmodells, sofern zutreffend
- Der Zeitstempel der Erstellung und, bei Revisionen, die auslösenden Belege

### 2.3 Uncertainty Principle / Unsicherheitsprinzip

MISSING is a first-class epistemic output. "We do not know" is not a failure state — it is the correct answer when evidence is insufficient, absent, or genuinely contradictory without resolution. Suppressing uncertainty in favour of a confident-sounding verdict is a more serious error than returning MISSING.

MISSING ist eine erstklassige epistemische Ausgabe. „Wir wissen es nicht" ist kein Fehlerzustand — es ist die richtige Antwort, wenn Beweise unzureichend, nicht vorhanden oder ohne Auflösung widersprüchlich sind. Unsicherheit zugunsten eines zuversichtlich klingenden Urteils zu unterdrücken ist ein schwerwiegenderer Fehler als MISSING zurückzugeben.

### 2.4 Revision Principle / Revisionsprinzip

New evidence can change any judgment. Revisions are mandatory when material new evidence emerges. However:

- Prior judgments are **never silently overwritten**
- Every revision creates a new Judgment record linked to the prior one
- The trigger evidence is always documented
- The historical record is append-only; deletion is not permitted

Neue Beweise können jedes Urteil ändern. Revisionen sind obligatorisch, wenn wesentliche neue Beweise auftauchen. Jedoch:

- Frühere Urteile werden **niemals stillschweigend überschrieben**
- Jede Revision erstellt einen neuen Judgment-Eintrag, der mit dem vorherigen verknüpft ist
- Die auslösenden Belege werden immer dokumentiert
- Das historische Register ist nur erweiterbar; Löschung ist nicht gestattet

### 2.5 Independence Principle / Unabhängigkeitsprinzip

GradedFacts accepts no funding from:

- Political parties or affiliated organisations
- Political action committees or equivalent structures in any jurisdiction
- Media organisations with documented political ownership or editorial dependency
- Governments with a direct stake in claims routinely evaluated by GradedFacts

GradedFacts nimmt keine Finanzierung an von:

- Politischen Parteien oder angeschlossenen Organisationen
- Politischen Aktionskomitees oder gleichwertigen Strukturen in einer Rechtsprechung
- Medienorganisationen mit dokumentierter politischer Eigentümerschaft oder redaktioneller Abhängigkeit
- Regierungen mit einem direkten Interesse an Behauptungen, die von GradedFacts routinemäßig bewertet werden

All funding sources are publicly disclosed without exception. Institutional independence is a precondition for methodological credibility, not a secondary concern.

Alle Finanzierungsquellen werden ausnahmslos öffentlich offengelegt. Institutionelle Unabhängigkeit ist eine Voraussetzung für methodologische Glaubwürdigkeit, kein sekundäres Anliegen.

---

## 3. Epistemic Framework / Epistemischer Rahmen

### 3.1 Rating System / Bewertungssystem

GradedFacts uses four epistemic ratings. Each rating reflects a defined evidential threshold, not an editorial opinion.

GradedFacts verwendet vier epistemische Bewertungen. Jede Bewertung spiegelt einen definierten Beweisschwellenwert wider, keine redaktionelle Meinung.

| Rating | Farbe | Definition |
|--------|-------|------------|
| **VERIFIED** | Green / Grün | Factually correct; backed by ≥3 relevant sources including ≥1 independent primary or ≥2 independent secondary sources |
| **SPECULATIVE** | Yellow / Gelb | Plausible but not conclusively provable with available evidence; or evidence is present but below VERIFIED threshold |
| **DEBUNKED** | Red / Rot | Factually false; direct affirmative counter-evidence documented from ≥2 primary or independent secondary sources |
| **MISSING** | Grey / Grau | Insufficient evidence; fewer than 2 sources with relevance ≥0.6 found, or evidence is absent or irresolvably contradictory |

### 3.2 When Each Rating Applies / Wann jede Bewertung gilt

**VERIFIED** requires:
- ≥3 sources with relevance score ≥0.6
- At least 1 independent Primary source, OR at least 2 independent Secondary sources
- No material counter-evidence from independent sources

**SPECULATIVE** applies when:
- Evidence is present but below VERIFIED threshold
- Only tertiary sources are available (hard cap: cannot be VERIFIED or DEBUNKED)
- Models disagree without source-quality resolution
- Future predictions with an existing evidence base (projections, signed treaties, published forecasts)

**DEBUNKED** requires:
- ≥2 Primary or independent Secondary sources with direct, affirmative counter-evidence
- Counter-evidence must falsify the specific mechanism alleged — absence of confirming evidence alone is insufficient
- Future predictions cannot be DEBUNKED unless the predicted event was already due and demonstrably did not occur, or the underlying prerequisite is factually refuted

**MISSING** applies when:
- Fewer than 2 sources with relevance ≥0.6 are available
- Evidence is absent — including when a conspiracy-type claim cannot be verified (absence of evidence ≠ DEBUNKED)
- Pure future predictions with no existing evidence base
- The claim is too vague to fact-check meaningfully (specificity gate rejection)

### 3.3 Hard Rules / Harte Regeln

Hard Rules cannot be overridden by model judgment. They are enforced algorithmically after the model's output is received.

Harte Regeln können nicht durch das Urteil des Modells außer Kraft gesetzt werden. Sie werden algorithmisch durchgesetzt, nachdem die Ausgabe des Modells empfangen wurde.

1. **Source threshold:** A model's claim of VERIFIED or DEBUNKED is overridden to SPECULATIVE if the algorithmic source evaluation finds no independent qualifying source (relevance ≥0.6, tier Primary or Secondary, is_independent=True).
2. **Tertiary cap:** Only tertiary sources → maximum rating is SPECULATIVE, never VERIFIED or DEBUNKED.
3. **Temperature=0:** All Phase 2 judgment calls use temperature=0 to ensure identical claims with identical evidence produce identical ratings.
4. **Source limit:** At most 8 sources per claim are evaluated; priority is given to Primary and Independent sources.
5. **Relevance filter:** Sources with relevance score <0.6 are stored but excluded from rating derivation.
6. **Domain deduplication:** Multiple sources from the same root domain count as one source for threshold purposes.
7. **Wikipedia rule:** Wikipedia is always classified as Tertiary — no exceptions, regardless of article quality.
8. **Official ≠ Independent:** Government agencies, law enforcement bodies, and official institutions are not automatically independent. Institutional independence is assessed separately from document tier.
9. **Absence ≠ Debunked:** A claim cannot be rated DEBUNKED because no evidence supporting it was found. DEBUNKED requires direct, affirmative counter-evidence.
10. **Consensus floor:** When Claude and Mistral disagree without a source-quality resolution, the consensus rating is capped at SPECULATIVE regardless of either model's individual verdict.

---

## 4. Source Classification / Quellenklassifikation

### 4.1 Tiers / Tier-Klassifikation

**Primary (Primär)**
Original data, official documents, government records, peer-reviewed studies, court decisions, official institution websites, statistical authorities. The source is the origin of the fact, not a report about it.

Originaldaten, offizielle Dokumente, Regierungsaufzeichnungen, peer-reviewte Studien, Gerichtsentscheidungen, offizielle Institutionswebsites, statistische Behörden. Die Quelle ist der Ursprung der Tatsache, nicht ein Bericht darüber.

Examples: destatis.de, bls.gov, eurostat.ec.europa.eu, pubmed.ncbi.nlm.nih.gov, official court filings

**Secondary (Sekundär)**
Journalism and academic analysis that cites primary sources with full attribution. The source reports on primary facts and names its sources explicitly.

Journalismus und akademische Analyse, die Primärquellen mit vollständiger Zuschreibung zitiert. Die Quelle berichtet über primäre Fakten und benennt ihre Quellen ausdrücklich.

Examples: BBC News (with citations), Reuters, NZZ, SRF, academic journals reviewing primary literature

**Tertiary (Tertiär)**
Aggregations, opinion pieces, summaries without independent verification, encyclopedias, commercial portals, industry associations, Wikipedia. The source compiles or comments on secondary and primary material without adding original verification.

Aggregationen, Meinungsartikel, Zusammenfassungen ohne unabhängige Überprüfung, Enzyklopädien, kommerzielle Portale, Branchenverbände, Wikipedia. Die Quelle kompiliert oder kommentiert sekundäres und primäres Material, ohne eigenständige Überprüfung hinzuzufügen.

### 4.2 Independence / Unabhängigkeit

Independence is a separate dimension from tier. A Primary source can be not-independent; a Secondary source can be independent.

Unabhängigkeit ist eine von der Tier-Klassifikation getrennte Dimension. Eine Primärquelle kann nicht-unabhängig sein; eine Sekundärquelle kann unabhängig sein.

| Label | Definition |
|-------|------------|
| **independent** | No documented ties to political parties, PACs, governments with a direct stake, or ideologically funded organisations |
| **neutral** | Independence status unconfirmed; not documented as compromised |
| **not_independent** | Documented ties to political actors, state ownership, or institutional dependency that creates a conflict of interest |

**Critical distinction:** Official does not mean independent. Examples of official-but-not-independent sources:
- FBI press releases under a director appointed on documented loyalty criteria
- DOJ statements from an Attorney General who pledged personal loyalty to an executive
- State media outlets (RT, CGTN, TRT, MTVA) regardless of official status
- Official government statements from authoritarian regimes evaluating claims about themselves

### 4.3 Registry Governance / Registry-Governance

The source independence registry (`backend/sources/registries/`) is the authoritative reference for known institutional independence assessments. It governs how `evaluate_source()` classifies sources.

Das Quellen-Unabhängigkeitsregister (`backend/sources/registries/`) ist die maßgebliche Referenz für bekannte institutionelle Unabhängigkeitsbewertungen. Es regelt, wie `evaluate_source()` Quellen klassifiziert.

Governance principles for registry changes:
- Every change is committed to version control with a descriptive message citing the evidence for the classification
- No registry entry is added or modified without documented justification
- The git hash of the registry at the time of each analysis is stored in the Judgment record (`registry_version`)
- Registry changes are backward-compatible: existing judgments reference the registry version active when they were created

---

## 5. Failure Modes / Fehlermodelle

This section explicitly documents the ways GradedFacts can fail. Documented failure modes are the first line of defence against them.

Dieser Abschnitt dokumentiert ausdrücklich die Arten, auf die GradedFacts versagen kann. Dokumentierte Fehlermodelle sind die erste Verteidigungslinie dagegen.

### 5.1 Methodological Drift / Methodologischer Drift

**Risk:** The analytical methodology changes gradually through prompt edits, model updates, or registry modifications without those changes being tracked or version-controlled.

**Risiko:** Die Analysemethodik ändert sich schrittweise durch Prompt-Bearbeitungen, Modell-Updates oder Registry-Änderungen, ohne dass diese Änderungen verfolgt oder versionskontrolliert werden.

**Why it matters:** A judgment produced under methodology v1.0 is not directly comparable to one produced under an undocumented variant. Aggregate trend analysis becomes meaningless if the measurement instrument changes silently.

**Warum es wichtig ist:** Ein unter Methodik v1.0 erzeugtes Urteil ist nicht direkt vergleichbar mit einem unter einer undokumentierten Variante erzeugten. Aggregierte Trendanalysen werden bedeutungslos, wenn sich das Messinstrument stillschweigend ändert.

### 5.2 Political Contamination Risk / Politisches Kontaminationsrisiko

**Risk:** Systematic bias in training data, prompts, or registry classifications causes GradedFacts to apply different evidentiary standards to politically opposing claims.

**Risiko:** Systematische Verzerrung in Trainingsdaten, Prompts oder Registry-Klassifikationen veranlasst GradedFacts, unterschiedliche Beweisstandards auf politisch entgegengesetzte Behauptungen anzuwenden.

**Detection:** Monitoring of the `political_leaning` field distribution in aggregate verdicts. A statistically significant skew in DEBUNKED rates between left-leaning and right-leaning claims warrants a methodology audit.

**Erkennung:** Überwachung der Verteilung des `political_leaning`-Feldes in aggregierten Urteilen. Eine statistisch signifikante Verschiebung bei DEBUNKED-Raten zwischen linksorientierten und rechtsorientierten Behauptungen erfordert einen Methodik-Audit.

### 5.3 MISSING ≠ DEBUNKED Confusion / MISSING ≠ DEBUNKED Verwechslung

**Risk:** The system rates claims DEBUNKED when the correct answer is MISSING — specifically, when no evidence supports a claim but no direct counter-evidence exists either.

**Risiko:** Das System bewertet Behauptungen als DEBUNKED, wenn die richtige Antwort MISSING ist — insbesondere wenn keine Belege eine Behauptung stützen, aber auch keine direkten Gegenbelege existieren.

**Why it matters:** Treating absence of evidence as evidence of absence is a logical fallacy. Conspiracy-type claims, unverifiable allegations, and claims about non-public events are especially vulnerable. Rating them DEBUNKED rather than MISSING falsely implies affirmative refutation.

**Warum es wichtig ist:** Abwesenheit von Beweisen als Beweis für Abwesenheit zu behandeln ist ein logischer Fehlschluss. Verschwörungsartige Behauptungen, nicht überprüfbare Vorwürfe und Behauptungen über nicht-öffentliche Ereignisse sind besonders gefährdet. Sie als DEBUNKED statt MISSING zu bewerten impliziert fälschlicherweise eine affirmative Widerlegung.

### 5.4 Asymmetric Output ≠ Bias / Asymmetrische Ausgabe ≠ Verzerrung

**Risk:** Aggregate output showing more DEBUNKED verdicts for claims from one political direction is misread as evidence that GradedFacts is biased against that direction.

**Risiko:** Aggregierte Ausgaben, die mehr DEBUNKED-Urteile für Behauptungen aus einer politischen Richtung zeigen, werden fälschlicherweise als Beweis dafür gelesen, dass GradedFacts gegen diese Richtung voreingenommen ist.

**Why it matters:** If one political direction routinely makes more empirically false claims in a given period, a correctly functioning system will produce more DEBUNKED verdicts for that direction. Asymmetric output is not evidence of bias — it is the expected output of a symmetric procedure applied to asymmetric inputs. **However**, this asymmetry must be verifiable through methodology audit. Asymmetric output without a traceable procedural explanation is a bias signal.

**Warum es wichtig ist:** Wenn eine politische Richtung in einem bestimmten Zeitraum routinemäßig mehr empirisch falsche Behauptungen aufstellt, wird ein korrekt funktionierendes System mehr DEBUNKED-Urteile für diese Richtung produzieren. Asymmetrische Ausgabe ist kein Beweis für Verzerrung — sie ist die erwartete Ausgabe eines symmetrischen Verfahrens, das auf asymmetrische Eingaben angewendet wird. **Jedoch** muss diese Asymmetrie durch einen Methodik-Audit überprüfbar sein. Asymmetrische Ausgabe ohne eine nachvollziehbare verfahrenstechnische Erklärung ist ein Verzerrungssignal.

### 5.5 Registry Capture Risk / Registry-Erfassungsrisiko

**Risk:** The source independence registry is modified — intentionally or through negligence — to systematically reclassify sources affiliated with one political direction as independent, and sources affiliated with another as not-independent.

**Risiko:** Das Quellen-Unabhängigkeitsregister wird — absichtlich oder durch Fahrlässigkeit — dahingehend modifiziert, Quellen, die einer politischen Richtung nahestehen, systematisch als unabhängig und Quellen, die einer anderen nahestehen, als nicht-unabhängig einzustufen.

**Mitigation:** All registry changes are version-controlled. The git hash is stored per judgment. Registry changes require documented justification. Batch reclassifications without justification are prohibited.

**Abschwächung:** Alle Registry-Änderungen werden versionskontrolliert. Der Git-Hash wird pro Urteil gespeichert. Registry-Änderungen erfordern dokumentierte Begründungen. Massenneueinstufungen ohne Begründung sind verboten.

### 5.6 Model Version Drift Risk / Modellversions-Drift-Risiko

**Risk:** A model update — to Claude, Mistral, or the Haiku specificity gate — changes the analytical behaviour in ways that are not documented or detected. Judgments produced before and after the update are not comparable without knowing which model produced them.

**Risiko:** Ein Modell-Update — bei Claude, Mistral oder dem Haiku-Spezifitätsgate — verändert das Analyseverhalten auf Weise, die nicht dokumentiert oder erkannt wird. Urteile, die vor und nach dem Update erstellt wurden, sind nicht vergleichbar, ohne zu wissen, welches Modell sie erzeugt hat.

**Mitigation:** The exact model version string is stored in every Judgment record (`model_claude`, `model_mistral`). Model strings are pinned to specific versions, not floating aliases. Version changes require an explicit code change and commit.

**Abschwächung:** Der genaue Modellversions-String wird in jedem Judgment-Eintrag gespeichert (`model_claude`, `model_mistral`). Modell-Strings sind auf spezifische Versionen festgelegt, keine schwebenden Aliasse. Versionsänderungen erfordern eine explizite Code-Änderung und einen Commit.

---

## 6. Anti-Drift Mechanisms / Drift-Schutzmechanismen

### 6.1 Append-Only Database / Nur-Anfüge-Datenbank

The judgment database is append-only. Prior judgments are never deleted or silently overwritten. Every revision creates a linked new record. This ensures that the full analytical history is always inspectable and that no verdict can be made to disappear.

Die Urteilsdatenbank ist nur erweiterbar. Frühere Urteile werden niemals gelöscht oder stillschweigend überschrieben. Jede Revision erstellt einen verknüpften neuen Eintrag. Dies stellt sicher, dass die vollständige Analysegeschichte immer einsehbar ist und kein Urteil zum Verschwinden gebracht werden kann.

### 6.2 Temperature=0

All Phase 2 judgment calls are made at temperature=0. This ensures that given identical inputs (claim text, search findings, system prompt, model version), the analytical output is deterministic. The same claim, analysed under the same conditions, must produce the same verdict. Stochastic drift in ratings is not acceptable.

Alle Phase-2-Urteilsaufrufe werden bei temperature=0 durchgeführt. Dies stellt sicher, dass bei identischen Eingaben (Behauptungstext, Suchbefunde, Systemprompt, Modellversion) die analytische Ausgabe deterministisch ist. Dieselbe Behauptung, unter denselben Bedingungen analysiert, muss dasselbe Urteil ergeben. Stochastischer Drift bei Bewertungen ist nicht akzeptabel.

### 6.3 Algorithmic Hard Rules

Hard Rules are enforced in code after the model produces its output. They cannot be overridden by model judgment, by prompt engineering, or by any runtime configuration. They represent the floor below which the system cannot be pushed regardless of what any model claims.

Harte Regeln werden im Code durchgesetzt, nachdem das Modell seine Ausgabe produziert hat. Sie können nicht durch das Modellurteil, durch Prompt-Engineering oder durch eine Laufzeitkonfiguration außer Kraft gesetzt werden. Sie stellen die Grenze dar, unter die das System nicht gedrückt werden kann, unabhängig davon, was ein Modell behauptet.

See [Section 3.3](#33-hard-rules--harte-regeln) for the full list.

### 6.4 Registry Versioning / Registry-Versionierung

Every judgment stores the short git hash of the most recent commit touching `backend/sources/registries/` at the time of analysis (`registry_version`). This makes it possible to reconstruct exactly which independence classifications were active when any given judgment was produced.

Jedes Urteil speichert den kurzen Git-Hash des jüngsten Commits, der `backend/sources/registries/` zum Zeitpunkt der Analyse berührt hat (`registry_version`). Dies ermöglicht es, genau zu rekonstruieren, welche Unabhängigkeitseinstufungen bei der Erstellung eines bestimmten Urteils aktiv waren.

### 6.5 Judgment Metadata / Urteilsmetadaten

Every Judgment record stores:

| Field | Purpose |
|-------|---------|
| `model_claude` | Exact Claude model version string used for analysis |
| `model_mistral` | Exact Mistral model version string used (null if single-engine) |
| `registry_version` | Git hash of the source registry at analysis time |
| `prompt_version` | Version identifier of the system prompt active at analysis time |
| `analyst` | Primary model identifier (mirrors `model_claude`) |
| `analyst_secondary` | Secondary model identifier (mirrors `model_mistral`) |
| `created_at` | UTC timestamp of judgment creation |

This metadata makes every judgment independently auditable: given the claim text and these four version identifiers, the analysis is in principle reproducible.

Diese Metadaten machen jedes Urteil unabhängig prüfbar: Angesichts des Behauptungstextes und dieser vier Versionsbezeichner ist die Analyse im Prinzip reproduzierbar.

### 6.6 Cross-Model Validation (Consensus Engine)

The primary analytical pipeline uses Claude (Phase 1 web search + Phase 2 judgment). A secondary independent pipeline uses Mistral with independent search infrastructure (Brave Search / SearXNG). The two pipelines share no findings.

Die primäre Analysepipeline verwendet Claude (Phase-1-Websuche + Phase-2-Urteil). Eine sekundäre unabhängige Pipeline verwendet Mistral mit eigenständiger Suchinfrastruktur (Brave Search / SearXNG). Die beiden Pipelines teilen keine Befunde.

Consensus resolution rules:
- Both models agree → that shared rating
- DEBUNKED + MISSING → DEBUNKED (stronger evidential signal prevails)
- DEBUNKED + VERIFIED with Claude primary/independent sources → DEBUNKED
- Source quality tiebreaker → model with ≥1 Primary/Independent source wins
- All other disagreements → SPECULATIVE (conservative floor)

The `models_agree` field records whether consensus was reached, enabling analysis of systematic model disagreement patterns over time.

Das Feld `models_agree` zeichnet auf, ob Konsens erreicht wurde, und ermöglicht die Analyse systematischer Modell-Uneinigkeitsmuster im Laufe der Zeit.

---

## 7. Governance / Governance

### 7.1 Who Can Change Hard Rules / Wer Harte Regeln ändern kann

Hard Rules (Section 3.3) can only be changed through:

1. A documented proposal explaining the evidential or methodological justification for the change
2. A version increment of this Epistemic Constitution
3. A code commit that implements the change and references the new Constitution version

No Hard Rule may be modified through prompt engineering, runtime configuration, or any mechanism that bypasses version control.

Harte Regeln (Abschnitt 3.3) können nur geändert werden durch:

1. Einen dokumentierten Vorschlag, der die evidenzielle oder methodologische Begründung für die Änderung erläutert
2. Eine Versionserhöhung dieser Epistemischen Verfassung
3. Einen Code-Commit, der die Änderung implementiert und auf die neue Verfassungsversion verweist

Keine Harte Regel darf durch Prompt-Engineering, Laufzeitkonfiguration oder einen Mechanismus, der die Versionskontrolle umgeht, geändert werden.

### 7.2 How Registry Changes Are Documented / Wie Registry-Änderungen dokumentiert werden

Every change to `backend/sources/registries/` must:

1. Be committed to version control as a discrete commit
2. Include a commit message that names the specific source(s) affected and cites the evidence for the new classification
3. Not batch-reclassify sources across political lines without individual justification for each entry

Jede Änderung an `backend/sources/registries/` muss:

1. Als diskreter Commit in die Versionskontrolle eingecheckt werden
2. Eine Commit-Nachricht enthalten, die die betroffene(n) spezifische(n) Quelle(n) benennt und die Belege für die neue Klassifikation zitiert
3. Quellen nicht über politische Grenzen hinweg ohne individuelle Begründung für jeden Eintrag in Massen neu einstufen

### 7.3 How Methodology Versions Are Tracked / Wie Methodologieversionen verfolgt werden

The `prompt_version` field in every Judgment record references the version of the system prompt active at analysis time. Changes to the system prompt that materially affect analytical behaviour require:

1. A new `prompt_version` string
2. An entry in the Version History of this document
3. A code commit that increments the version string before the new prompt is deployed

Das Feld `prompt_version` in jedem Judgment-Eintrag referenziert die Version des Systemprompts, die zum Zeitpunkt der Analyse aktiv war. Änderungen am Systemprompt, die das Analyseverhalten wesentlich beeinflussen, erfordern:

1. Einen neuen `prompt_version`-String
2. Einen Eintrag in der Versionsgeschichte dieses Dokuments
3. Einen Code-Commit, der den Versionsstring erhöht, bevor der neue Prompt eingesetzt wird

### 7.4 How This Constitution Is Amended / Wie diese Verfassung geändert wird

This Epistemic Constitution is itself versioned. Amendments follow the same discipline as methodology changes:

1. A documented rationale for the amendment
2. A version increment in the header and Version History
3. A code commit to the project repository

No substantive change to GradedFacts' analytical procedure is valid unless it is reflected in an updated version of this document.

Diese Epistemische Verfassung ist selbst versioniert. Änderungen folgen derselben Disziplin wie Methodologieänderungen:

1. Eine dokumentierte Begründung für die Änderung
2. Eine Versionserhöhung in der Kopfzeile und Versionsgeschichte
3. Ein Code-Commit in das Projekt-Repository

Keine wesentliche Änderung am Analyseverfahren von GradedFacts ist gültig, wenn sie nicht in einer aktualisierten Version dieses Dokuments widergespiegelt wird.

---

## 8. Version History / Versionsgeschichte

| Version | Date | Summary |
|---------|------|---------|
| **v1.0** | June 2026 | Initial release. Formalises the principles, procedures, failure modes, anti-drift mechanisms, and governance rules active at the time of publication. Accompanies the introduction of Judgment Metadata fields (`model_claude`, `model_mistral`, `registry_version`, `prompt_version`) and the pinning of model versions to `claude-sonnet-4-6` and `mistral-large-2512`. |

---

*GradedFacts — Founded in Switzerland. Politically independent. Epistemically procedural.*

*GradedFacts — Gegründet in der Schweiz. Politisch unabhängig. Epistemisch-prozedural.*
