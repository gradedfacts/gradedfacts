# Registry Governance of GradedFacts
# Registry-Governance von GradedFacts

**Version:** v1.0
**Date / Datum:** June 2026
**Status:** Active / Aktiv
**Companion document / Begleitdokument:** [EPISTEMIC_CONSTITUTION.md](EPISTEMIC_CONSTITUTION.md) §4.3, §5.5, §6.4, §7.2

---

## Table of Contents / Inhaltsverzeichnis

1. [Overview / Überblick](#1-overview--überblick)
2. [Classification Criteria / Klassifikationskriterien](#2-classification-criteria--klassifikationskriterien)
3. [Change Protocol / Änderungsprotokoll](#3-change-protocol--änderungsprotokoll)
4. [Changelog Format / Changelog-Format](#4-changelog-format--changelog-format)
5. [Audit Procedures / Prüfverfahren](#5-audit-procedures--prüfverfahren)
6. [Prohibited Actions / Verbotene Handlungen](#6-prohibited-actions--verbotene-handlungen)
7. [Version History / Versionsgeschichte](#7-version-history--versionsgeschichte)

---

## 1. Overview / Überblick

### What the Registry Is / Was das Registry ist

The GradedFacts source registry (`backend/sources/registries/`) is the authoritative store of institutional independence assessments used during claim analysis. When the analytical engine encounters a source URL, `evaluate_source()` looks it up against the registry to determine:

- Whether the domain is classified as a known institution
- The institution's source tier (Primary / Secondary / Tertiary)
- The institution's independence status (Independent / Neutral / Not Independent)
- Any affiliation note explaining a Not Independent classification

Das GradedFacts-Quellen-Registry (`backend/sources/registries/`) ist der maßgebliche Speicher institutioneller Unabhängigkeitsbewertungen, die bei der Anspruchsanalyse verwendet werden. Wenn die Analyse-Engine auf eine Quell-URL trifft, schlägt `evaluate_source()` diese im Registry nach, um festzustellen:

- Ob die Domain als bekannte Institution klassifiziert ist
- Den Quell-Tier der Institution (Primär / Sekundär / Tertiär)
- Den Unabhängigkeitsstatus der Institution (Unabhängig / Neutral / Nicht-Unabhängig)
- Einen Affiliationshinweis, der eine Nicht-Unabhängig-Klassifikation erläutert

### Why the Registry Matters / Warum das Registry wichtig ist

Registry classifications have direct, deterministic effects on analytical outputs:

- A source classified as Independent Primary can, by itself, satisfy the independence requirement for VERIFIED or DEBUNKED
- A source classified as Not Independent is algorithmically downgraded from Primary to Secondary tier, reducing its weight in threshold calculations
- A source classified as Tertiary — regardless of independence status — can never contribute to a VERIFIED or DEBUNKED verdict

Registry-Klassifikationen haben direkte, deterministische Auswirkungen auf Analyseausgaben:

- Eine als Unabhängig Primär klassifizierte Quelle kann allein die Unabhängigkeitsanforderung für VERIFIED oder DEBUNKED erfüllen
- Eine als Nicht-Unabhängig klassifizierte Quelle wird algorithmisch von Primär auf Sekundär herabgestuft, was ihr Gewicht bei Schwellenberechnungen verringert
- Eine als Tertiär klassifizierte Quelle — unabhängig vom Unabhängigkeitsstatus — kann nie zu einem VERIFIED- oder DEBUNKED-Urteil beitragen

### The Registry as the Epistemically Most Sensitive Component / Das Registry als epistemisch sensibelste Komponente

Of all GradedFacts components, the registry carries the highest risk of introducing systematic analytical bias. A single misclassification of a widely-cited source — upgrading a state-controlled outlet to Independent Primary, or downgrading an independent press organisation to Tertiary — will silently propagate into every future judgment that cites that source, without triggering any algorithmic warning.

Von allen GradedFacts-Komponenten trägt das Registry das höchste Risiko, systematische analytische Verzerrungen einzuführen. Eine einzige Fehlklassifikation einer häufig zitierten Quelle — ein staatlich kontrolliertes Outlet auf Unabhängig Primär hochzustufen oder eine unabhängige Presseorganisation auf Tertiär herabzustufen — wird sich stillschweigend in jedes zukünftige Urteil ausbreiten, das diese Quelle zitiert, ohne einen algorithmischen Alarm auszulösen.

This is why registry governance is stricter than any other change process in the project.

Deshalb ist die Registry-Governance strenger als jeder andere Änderungsprozess im Projekt.

---

## 2. Classification Criteria / Klassifikationskriterien

### 2.1 Source Tier / Quell-Tier

#### Primary (Primär)

A source is Primary if it is the **origin** of the fact being evaluated — not a report about it.

Eine Quelle ist Primär, wenn sie der **Ursprung** der bewerteten Tatsache ist — nicht ein Bericht darüber.

Formal criteria (at least one must apply):

- Official government statistics published by the responsible statistical authority (e.g. Destatis, BLS, Eurostat, ONS)
- Original legislative texts, regulations, or official government decrees
- Court decisions and legal filings from official court systems
- Peer-reviewed scientific studies in indexed journals
- Official institution websites publishing original data, policy positions, or official records
- Central bank and monetary authority publications
- International organisation primary documents (UN, WHO, OECD, IMF — original reports, not press summaries)

Formale Kriterien (mindestens eines muss zutreffen):

- Offizielle Regierungsstatistiken, veröffentlicht von der zuständigen statistischen Behörde
- Originale Gesetzestexte, Verordnungen oder offizielle Regierungserlasse
- Gerichtsentscheidungen und Rechtsschriften aus offiziellen Gerichtssystemen
- Peer-reviewte wissenschaftliche Studien in indizierten Zeitschriften
- Offizielle Institutionswebsites, die Originaldaten, Politikpositionen oder offizielle Aufzeichnungen veröffentlichen
- Zentralbank- und Währungsbehördenpublikationen
- Primärdokumente internationaler Organisationen

#### Secondary (Sekundär)

A source is Secondary if it **reports on** primary facts and **explicitly names** its primary sources with full attribution.

Eine Quelle ist Sekundär, wenn sie über primäre Tatsachen **berichtet** und ihre Primärquellen mit vollständiger Zuschreibung **explizit benennt**.

Formal criteria (all must apply):

- Cites primary sources by name, with specific reference (not vague "according to officials")
- Produced by an organisation with established editorial standards and a public corrections policy
- Does not add original data; synthesises and contextualises primary material
- Not primarily a commentary, opinion, or advocacy outlet

Formale Kriterien (alle müssen zutreffen):

- Zitiert Primärquellen namentlich mit spezifischer Referenz (nicht vage „laut Offiziellen")
- Produziert von einer Organisation mit etablierten redaktionellen Standards und einer öffentlichen Korrekturregel
- Fügt keine Originaldaten hinzu; synthetisiert und kontextualisiert primäres Material
- Ist kein primär kommentierendes, meinungsbildendes oder Advocacy-Outlet

#### Tertiary (Tertiär)

A source is Tertiary by default if it does not meet Primary or Secondary criteria. Tertiary classification is also mandatory — regardless of other properties — for:

Eine Quelle ist standardmäßig Tertiär, wenn sie die Primär- oder Sekundärkritierien nicht erfüllt. Tertiäre Klassifikation ist auch obligatorisch — unabhängig von anderen Eigenschaften — für:

- Wikipedia and all Wikimedia Foundation projects
- Statista and equivalent data aggregation portals
- Commercial research portals that compile third-party data
- Industry association publications and lobby-group reports
- Opinion, editorial, and commentary content from any outlet
- Press releases from non-governmental, non-scientific organisations
- Content farms and AI-generated news aggregators

### 2.2 Independence Assessment / Unabhängigkeitsbewertung

Independence is a separate analytical dimension from tier. Tier describes **what kind of document** a source is. Independence describes **whether the producing institution is free from conflicts of interest** that could compromise the accuracy or completeness of its output.

Unabhängigkeit ist eine von der Tier-Klassifikation getrennte analytische Dimension. Tier beschreibt **welche Art von Dokument** eine Quelle ist. Unabhängigkeit beschreibt **ob die herausgebende Institution frei von Interessenkonflikten** ist, die die Genauigkeit oder Vollständigkeit ihrer Ausgabe beeinträchtigen könnten.

#### Independent (Unabhängig)

No documented institutional conflicts of interest. The organisation has editorial autonomy, is not subject to political direction, and has no financial dependency that creates a systematic incentive to misrepresent facts.

Keine dokumentierten institutionellen Interessenkonflikte. Die Organisation hat redaktionelle Autonomie, unterliegt keiner politischen Weisung und hat keine finanzielle Abhängigkeit, die einen systematischen Anreiz schafft, Tatsachen falsch darzustellen.

#### Neutral (Neutral)

Independence status is **unconfirmed** — the institution is not documented as compromised, but has also not been assessed as definitively independent. Neutral is the default for sources not present in the registry. Neutral sources are not algorithmically downgraded; they are treated as independent for threshold purposes but carry reduced epistemic weight in the overall judgment.

Der Unabhängigkeitsstatus ist **unbestätigt** — die Institution ist nicht als kompromittiert dokumentiert, wurde aber auch nicht als definitiv unabhängig bewertet. Neutral ist der Standard für Quellen, die nicht im Registry vorhanden sind. Neutrale Quellen werden nicht algorithmisch herabgestuft; sie werden für Schweckzwecke als unabhängig behandelt, tragen aber im Gesamturteil ein geringeres epistemisches Gewicht.

#### Not Independent (Nicht-Unabhängig)

The institution has documented conflicts of interest that are judged likely to systematically affect its output on the categories of claims GradedFacts evaluates.

Die Institution hat dokumentierte Interessenkonflikte, die nach Einschätzung die Ausgabe bei den von GradedFacts bewerteten Behauptungskategorien systematisch beeinflussen.

### 2.3 Institutional Independence > Institutional Status / Institutionelle Unabhängigkeit > Institutioneller Status

**Official does not mean independent.** This is the most common classification error and the one with the greatest potential to distort analytical outputs.

**Offiziell bedeutet nicht unabhängig.** Dies ist der häufigste Klassifikationsfehler und derjenige mit dem größten Potenzial, Analyseausgaben zu verzerren.

A government statistical office that operates under ministerial supervision, whose budget is controlled by the ministry whose policies are being evaluated, and whose leadership is appointed by elected officials — is a Primary source for the data it publishes, but it is **not** independent of the government whose claims it may be used to verify or refute.

Ein Regierungsstatistikamt, das unter ministerieller Aufsicht operiert, dessen Budget vom Ministerium kontrolliert wird, dessen Politiken bewertet werden, und dessen Führung von gewählten Beamten ernannt wird — ist eine Primärquelle für die veröffentlichten Daten, aber es ist **nicht** unabhängig von der Regierung, deren Behauptungen es zur Verifikation oder Widerlegung verwendet werden könnte.

The classification reflects the **institutional relationship**, not a judgement about the quality of any specific document.

Die Klassifikation spiegelt die **institutionelle Beziehung** wider, nicht ein Urteil über die Qualität eines spezifischen Dokuments.

### 2.4 Formal Criteria for Not Independent / Formale Kriterien für Nicht-Unabhängig

A source receives Not Independent classification when **at least one** of the following is documented:

Eine Quelle erhält die Nicht-Unabhängig-Klassifikation, wenn **mindestens eines** der folgenden dokumentiert ist:

1. **Direct government oversight or ministerial control** — the institution operates under the legal authority of a government ministry, is subject to ministerial direction, or requires ministerial approval for key decisions (budget, leadership, publication)

   **Direkte Regierungsaufsicht oder ministerielle Kontrolle** — die Institution operiert unter der gesetzlichen Autorität eines Regierungsministeriums, unterliegt ministerieller Weisung oder benötigt ministerielle Genehmigung für wesentliche Entscheidungen

2. **Significant state funding** — more than 50% of the institution's operating budget comes from government sources, creating a structural financial dependency on the political actors whose claims may be evaluated

   **Bedeutende staatliche Finanzierung** — mehr als 50% des Betriebsbudgets der Institution stammen aus Regierungsquellen, was eine strukturelle finanzielle Abhängigkeit von den politischen Akteuren schafft, deren Behauptungen bewertet werden können

3. **Documented political pressure on editorial decisions** — credible, sourced reporting confirms that the institution's editorial output has been subject to political intervention, suppression, or direction — not merely criticism, but verifiable interference

   **Dokumentierter politischer Druck auf redaktionelle Entscheidungen** — glaubwürdige, quellengestützte Berichte bestätigen, dass die redaktionelle Ausgabe der Institution politischer Intervention, Unterdrückung oder Weisung ausgesetzt war — nicht bloße Kritik, sondern nachweisliche Einflussnahme

4. **Commercial conflicts of interest** — the institution has documented financial relationships with actors who have a material stake in the outcome of claims the institution reports on (e.g. a media outlet majority-owned by an arms manufacturer reporting on defence procurement)

   **Kommerzielle Interessenkonflikte** — die Institution hat dokumentierte finanzielle Beziehungen zu Akteuren, die ein wesentliches Interesse am Ausgang von Behauptungen haben, über die die Institution berichtet

These criteria are **institutional, not political**. The classification is not based on whether GradedFacts agrees or disagrees with a source's conclusions, but on whether the institutional structure creates systematic incentives to misrepresent.

Diese Kriterien sind **institutionell, nicht politisch**. Die Klassifikation basiert nicht darauf, ob GradedFacts den Schlussfolgerungen einer Quelle zustimmt oder widerspricht, sondern darauf, ob die institutionelle Struktur systematische Anreize zur Fehlerdarstellung schafft.

---

## 3. Change Protocol / Änderungsprotokoll

### 3.1 Who Can Propose Changes / Wer Änderungen vorschlagen kann

Registry changes may currently be proposed by **Marc Chao (Founder)**. As GradedFacts grows, this governance section will be updated to reflect any expanded review structure. Until then, all registry changes originate from and are approved by the founder.

Registry-Änderungen können derzeit von **Marc Chao (Gründer)** vorgeschlagen werden. Mit dem Wachstum von GradedFacts wird dieser Governance-Abschnitt aktualisiert, um jede erweiterte Prüfstruktur widerzuspiegeln. Bis dahin gehen alle Registry-Änderungen vom Gründer aus und werden von ihm genehmigt.

### 3.2 Review and Approval / Prüfung und Genehmigung

Every proposed registry change must be reviewed against the formal criteria in Section 2 before being committed. The review answers the following questions:

Jede vorgeschlagene Registry-Änderung muss vor dem Commit anhand der formalen Kriterien in Abschnitt 2 geprüft werden. Die Prüfung beantwortet folgende Fragen:

1. **Tier question:** Does the source produce original data / report with attribution / aggregate without attribution?
2. **Independence question:** Which of the Section 2.4 criteria, if any, are documented for this institution? What is the source of that documentation?
3. **Direction question:** Does the proposed classification change move in the same direction regardless of the institution's political associations? Would the same change be made for an institution with opposite political associations but identical structural conditions?
4. **Scope question:** Which existing judgments cite this source? Is a retrospective note warranted?

If the review cannot answer question 3 affirmatively, the change is not approved.

Wenn die Prüfung Frage 3 nicht positiv beantworten kann, wird die Änderung nicht genehmigt.

### 3.3 Mandatory Documentation for Every Change / Obligatorische Dokumentation für jede Änderung

Before any registry change is committed, the following must be recorded in `REGISTRY_CHANGELOG.md` (see Section 4):

Bevor eine Registry-Änderung eingecheckt wird, muss Folgendes in `REGISTRY_CHANGELOG.md` aufgezeichnet werden (siehe Abschnitt 4):

| Field | Requirement |
|-------|-------------|
| **Date** | ISO 8601 date of the change (YYYY-MM-DD) |
| **Domain** | The exact domain(s) added or modified (e.g. `reuters.com`) |
| **Old classification** | Previous tier + independence, or `—` for new entries |
| **New classification** | New tier + independence |
| **Rationale** | Institutional justification citing the specific Section 2.4 criterion met, with named evidence source — not political characterisation |
| **Git commit hash** | Short hash of the commit implementing the change |

The git commit message must also reference the changelog entry. The commit message alone is not sufficient documentation.

Die Git-Commit-Nachricht muss ebenfalls auf den Changelog-Eintrag verweisen. Die Commit-Nachricht allein ist keine ausreichende Dokumentation.

### 3.4 Batch Changes / Massenänderungen

Registry expansions covering more than 10 domains in a single commit must include an audit as described in Section 5 within 30 days of the expansion. Batch changes that reclassify existing entries — as opposed to adding new ones — are subject to individual justification for each modified entry; a single rationale covering multiple reclassifications is not accepted.

Registry-Erweiterungen, die mehr als 10 Domains in einem einzigen Commit abdecken, müssen innerhalb von 30 Tagen nach der Erweiterung einen Audit gemäß Abschnitt 5 umfassen. Massenänderungen, die bestehende Einträge neu klassifizieren — im Gegensatz zum Hinzufügen neuer — unterliegen individueller Begründung für jeden geänderten Eintrag; eine einzelne Begründung für mehrere Neuklassifikationen wird nicht akzeptiert.

---

## 4. Changelog Format / Changelog-Format

### 4.1 File Location and Purpose / Dateiort und Zweck

All registry changes are recorded in `REGISTRY_CHANGELOG.md` at the project root. This file is the authoritative human-readable history of every classification decision. It is distinct from the git log, which is the authoritative machine-readable history.

Alle Registry-Änderungen werden in `REGISTRY_CHANGELOG.md` im Projektstamm aufgezeichnet. Diese Datei ist die maßgebliche menschenlesbare Geschichte jeder Klassifikationsentscheidung. Sie unterscheidet sich vom Git-Log, das die maßgebliche maschinenlesbare Geschichte ist.

### 4.2 Entry Format / Eintragsformat

Each entry follows this format:

```
## YYYY-MM-DD — <domain or batch description>

| Field        | Value |
|--------------|-------|
| Domain       | example.com |
| Change       | [OLD_TIER / OLD_INDEPENDENCE] → [NEW_TIER / NEW_INDEPENDENCE] |
| Rationale    | <Institutional justification citing Section 2.4 criterion and named evidence> |
| Commit       | abc1234 |
```

For new entries where no prior classification existed, use `— / —` as the Old classification.

Für neue Einträge, bei denen keine frühere Klassifikation vorhanden war, wird `— / —` als alte Klassifikation verwendet.

### 4.3 Example Entry / Beispieleintrag

```
## 2026-06-01 — state-broadcaster.example.gov

| Field     | Value |
|-----------|-------|
| Domain    | state-broadcaster.example.gov |
| Change    | Secondary / Neutral → Secondary / Not Independent |
| Rationale | Criterion 2 (significant state funding): Operating budget >80% from
|           | ministry of information; source: institution's own annual report 2025,
|           | p. 14. Criterion 3 (documented political pressure): Three senior editors
|           | dismissed following critical coverage; documented in CPJ report March 2026. |
| Commit    | f3a9b12 |
```

### 4.4 Retroactive Entries / Rückwirkende Einträge

Where registry entries pre-date this governance document and lack changelog entries, they are retroactively documented in a single batch entry at the time this governance document takes effect (June 2026), with available rationale reconstructed from git history and available public records.

Wo Registry-Einträge dieses Governance-Dokument vorausgehen und keine Changelog-Einträge haben, werden sie in einem einzigen Batch-Eintrag zum Zeitpunkt des Inkrafttretens dieses Governance-Dokuments (Juni 2026) rückwirkend dokumentiert, wobei verfügbare Begründungen aus der Git-Geschichte und verfügbaren öffentlichen Aufzeichnungen rekonstruiert werden.

---

## 5. Audit Procedures / Prüfverfahren

### 5.1 When Audits Are Required / Wann Audits erforderlich sind

A registry audit is required:

Ein Registry-Audit ist erforderlich:

- After any batch expansion of more than 10 domains (within 30 days)
- After any change to the independence criteria in this document
- When aggregate output monitoring detects a statistically significant asymmetry in DEBUNKED verdicts between political directions (see EPISTEMIC_CONSTITUTION.md §5.2)
- On an annual basis as part of the general methodology review

### 5.2 Audit Scope / Audit-Umfang

Each audit examines the following sample:

Jeder Audit untersucht die folgende Stichprobe:

**10 randomly selected registered sources / 10 zufällig ausgewählte registrierte Quellen**
- Verify that the current tier and independence classification still matches the formal criteria in Section 2
- Confirm that the evidence cited in the changelog entry is still valid and publicly accessible
- Check for any changes to the institution's governance, ownership, or funding since the last classification

**5 politically sensitive sources / 5 politisch sensible Quellen**
- Sources that have been cited in >10 judgments involving contested political claims
- Verify that the classification is consistent with Section 2.4 criteria and is not the result of editorial agreement with GradedFacts' outputs
- Cross-check classification against an institution not affiliated with GradedFacts (e.g. RSF Press Freedom Index, CPJ database, Media Ownership Monitor)

**5 unregistered sources that appeared in recent judgments / 5 nicht registrierte Quellen aus aktuellen Urteilen**
- Verify that their Neutral default classification is appropriate given available public information
- Determine whether any should be formally added to the registry

### 5.3 Audit Output / Audit-Ausgabe

Each audit produces a written summary including:

Jeder Audit produziert eine schriftliche Zusammenfassung mit:

- Date and scope of the audit
- Sources examined and their current classifications
- Any misclassifications found and their corrections
- Any sources added or modified as a result
- Confirmation that no Tertiary or Neutral source was found to be contributing to a VERIFIED or DEBUNKED threshold calculation
- Assessment of overall registry integrity

The audit summary is committed to the project repository alongside any resulting registry changes.

Die Audit-Zusammenfassung wird zusammen mit resultierenden Registry-Änderungen in das Projekt-Repository eingecheckt.

### 5.4 Threshold Verification / Schwellenwertverifizierung

A core audit check is the **threshold verification**: confirm that no source classified as Tertiary or Neutral is contributing to a VERIFIED or DEBUNKED rating threshold. This is enforced algorithmically by the Hard Rules (EPISTEMIC_CONSTITUTION.md §3.3), but the audit verifies that the registry classifications feeding into those Hard Rules are themselves correct.

Eine zentrale Audit-Prüfung ist die **Schwellenwertverifizierung**: Bestätigung, dass keine als Tertiär oder Neutral klassifizierte Quelle zu einem VERIFIED- oder DEBUNKED-Bewertungsschwellenwert beiträgt. Dies wird algorithmisch durch die Harten Regeln durchgesetzt, aber der Audit überprüft, dass die Registry-Klassifikationen, die in diese Harten Regeln einfließen, selbst korrekt sind.

---

## 6. Prohibited Actions / Verbotene Handlungen

The following actions are prohibited without exception. Violation of any prohibition constitutes a breach of this document and requires immediate correction and public disclosure in the changelog.

Die folgenden Handlungen sind ausnahmslos verboten. Ein Verstoß gegen ein Verbot stellt einen Bruch dieses Dokuments dar und erfordert sofortige Korrektur und öffentliche Offenlegung im Changelog.

### 6.1 Classification Based on Editorial Agreement / Klassifikation basierend auf redaktioneller Übereinstimmung

**Prohibited:** A source may never be upgraded to Independent — or maintained as Independent — because its reporting conclusions align with, confirm, or are consistent with GradedFacts analytical outputs.

**Verboten:** Eine Quelle darf niemals auf Unabhängig hochgestuft werden — oder als Unabhängig beibehalten werden — weil ihre Berichtsschlussfolgerungen mit den analytischen Ausgaben von GradedFacts übereinstimmen, diese bestätigen oder mit ihnen konsistent sind.

Classification must reflect institutional structure. An institution that consistently publishes accurate information but operates under ministerial control remains Not Independent. An institution that sometimes publishes contested analysis but operates without structural conflicts of interest remains Independent.

Die Klassifikation muss die institutionelle Struktur widerspiegeln. Eine Institution, die konsistent genaue Informationen veröffentlicht, aber unter ministerieller Kontrolle operiert, bleibt Nicht-Unabhängig. Eine Institution, die manchmal umstrittene Analysen veröffentlicht, aber ohne strukturelle Interessenkonflikte operiert, bleibt Unabhängig.

### 6.2 Classification Changed Due to Political Pressure / Klassifikation aufgrund politischen Drucks geändert

**Prohibited:** No registry classification may be changed in response to external pressure — from governments, political parties, media organisations, or advocacy groups — regardless of the content or intensity of that pressure.

**Verboten:** Keine Registry-Klassifikation darf als Reaktion auf externen Druck geändert werden — von Regierungen, politischen Parteien, Medienorganisationen oder Interessengruppen — unabhängig vom Inhalt oder der Intensität dieses Drucks.

If a classification is challenged externally, the response is to review the formal criteria in Section 2 and the changelog evidence. If the evidence supports the existing classification, it stands. If the review finds a genuine error, the correction is documented and published — not made quietly to avoid controversy.

Wenn eine Klassifikation extern angefochten wird, ist die Reaktion, die formalen Kriterien in Abschnitt 2 und die Changelog-Nachweise zu überprüfen. Wenn die Nachweise die bestehende Klassifikation stützen, bleibt sie bestehen. Wenn die Überprüfung einen echten Fehler findet, wird die Korrektur dokumentiert und veröffentlicht — nicht still vorgenommen, um Kontroversen zu vermeiden.

### 6.3 Tertiary Sources Classified as Independent / Tertiäre Quellen als Unabhängig klassifiziert

**Prohibited:** No source classified as Tertiary may simultaneously be classified as Independent. Independence is analytically meaningful only for Primary and Secondary sources, because only Primary and Secondary sources can contribute to rating thresholds. Assigning an independence classification to a Tertiary source creates a false impression that the source carries weight it cannot algorithmically contribute.

**Verboten:** Keine als Tertiär klassifizierte Quelle darf gleichzeitig als Unabhängig klassifiziert werden. Unabhängigkeit ist analytisch nur für Primär- und Sekundärquellen bedeutsam, weil nur Primär- und Sekundärquellen zu Bewertungsschwellenwerten beitragen können. Die Zuweisung einer Unabhängigkeitsklassifikation an eine Tertiärquelle erzeugt einen falschen Eindruck, dass die Quelle Gewicht trägt, zu dem sie algorithmisch nicht beitragen kann.

### 6.4 Silent Reclassification / Stille Neuklassifikation

**Prohibited:** No registry entry may be reclassified without a corresponding changelog entry. A change to the registry files without a corresponding `REGISTRY_CHANGELOG.md` entry is a governance violation, regardless of the reason for the change.

**Verboten:** Kein Registry-Eintrag darf ohne entsprechenden Changelog-Eintrag neu klassifiziert werden. Eine Änderung an den Registry-Dateien ohne einen entsprechenden `REGISTRY_CHANGELOG.md`-Eintrag ist ein Governance-Verstoß, unabhängig vom Grund der Änderung.

### 6.5 Asymmetric Application of Criteria / Asymmetrische Anwendung von Kriterien

**Prohibited:** The formal criteria in Section 2.4 must be applied identically across all institutions regardless of their political associations. An institution affiliated with a left-wing government and an institution affiliated with a right-wing government under structurally identical conditions of ministerial control must receive identical independence classifications.

**Verboten:** Die formalen Kriterien in Abschnitt 2.4 müssen identisch auf alle Institutionen angewendet werden, unabhängig von ihren politischen Assoziationen. Eine Institution, die einer linksgerichteten Regierung angegliedert ist, und eine Institution, die einer rechtsgerichteten Regierung unter strukturell identischen Bedingungen ministerieller Kontrolle angegliedert ist, müssen identische Unabhängigkeitsklassifikationen erhalten.

---

## 7. Version History / Versionsgeschichte

| Version | Date | Summary |
|---------|------|---------|
| **v1.0** | June 2026 | Initial release. Establishes formal classification criteria, the change protocol, mandatory changelog format, audit procedures, and the five prohibited actions. Companion to EPISTEMIC_CONSTITUTION.md v1.0 and the introduction of `registry_version` tracking in Judgment metadata. |

---

*GradedFacts — Registry integrity is a precondition for analytical integrity.*

*GradedFacts — Registry-Integrität ist eine Voraussetzung für analytische Integrität.*
