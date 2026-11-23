# Registry Changelog / Registry-Änderungsprotokoll

**Companion document:** [REGISTRY_GOVERNANCE.md](REGISTRY_GOVERNANCE.md) §3.3, §4, §6.4
**Covers:** `backend/sources/registries/registry.json`
**Status:** Active / Aktiv — created 2026-08-06

---

## Purpose / Zweck

This file is the authoritative **human-readable** history of every registry classification
decision. It is distinct from the git log, which is the authoritative machine-readable history.

`REGISTRY_GOVERNANCE.md` §3.3 requires that, before any registry change is committed, the
following is recorded here: **Date · Domain · Old classification · New classification ·
Rationale · Git commit hash.** The rationale must cite the specific §2.4 criterion met, with
named evidence — not political characterisation. §3.3 is explicit that *"the commit message
alone is not sufficient documentation"*, and §6.4 (Silent Reclassification) makes a registry
change without a corresponding entry here a governance violation regardless of the reason for
the change.

Diese Datei ist die maßgebliche **menschenlesbare** Geschichte jeder Registry-Klassifikations-
entscheidung. Sie unterscheidet sich vom Git-Log, das die maßgebliche maschinenlesbare
Geschichte ist. `REGISTRY_GOVERNANCE.md` §3.3 verlangt die Aufzeichnung jeder Änderung hier vor
dem Commit; §6.4 macht eine Registry-Änderung ohne entsprechenden Eintrag zu einem
Governance-Verstoß.

### Note on this file's own history

**This file did not exist until 2026-08-06.** Every registry change before that date was
therefore committed in technical violation of §6.4. §4.4 of the governance document anticipates
exactly this situation and prescribes the remedy: *"Where registry entries pre-date this
governance document and lack changelog entries, they are retroactively documented in a single
batch entry … with available rationale reconstructed from git history and available public
records."* The retroactive entry for `e6f02c6` below is the first application of §4.4. Earlier
commits remain undocumented here and should be reconstructed in a future §5 audit.

### Format

```
## YYYY-MM-DD — <domain or batch description>

| Field     | Value |
|-----------|-------|
| Domain    | example.com |
| Change    | [OLD_TIER / OLD_INDEPENDENCE] → [NEW_TIER / NEW_INDEPENDENCE] |
| Rationale | <Institutional justification citing §2.4 criterion and named evidence> |
| Commit    | abc1234 |
```

For new entries where no prior classification existed, the old classification is `— / —`.

---

## 2026-11-23 — Registry Batch E+F: +111 entries, blacklist changes, msnbc.com fact correction

Basis: `docs/registry_review/Registry_Batch_E_Review.md` (§6 overrides §3/§4),
`docs/registry_review/Registry_Batch_F_Review.md` (✅ rows only), implementation plan
`registry_batch_ef_plan.md`, and Marc's decisions of 2026-11-23 (numbered as in the plan, §5).
Collision rule: (a) same facts → keep existing; (b) changed facts → correct with date and evidence.

| Field     | Value |
|-----------|-------|
| Scope     | 111 new entries (777 → **888**), 1 fact correction (`msnbc.com`), 4 note extensions (CH Media), blacklist: +3 / −1 |
| Commit    | the commit that adds this entry ("Registry Batch E+F: +111 entries, …"); hash to be filled in afterwards, as in `a06ab72` |

### 1. Fact correction — `msnbc.com` (case (b), NOT a reclassification)

| Field     | Value |
|-----------|-------|
| Domain    | `msnbc.com` |
| Change    | Secondary / Not Independent → Secondary / Not Independent (**unchanged**) |
| Type      | (b) fact correction: ownership clause in `affiliation_note` and `independence_note` |
| Old       | *"Owned by NBCUniversal/Comcast."* / *"Owned by NBCUniversal (Comcast)."* |
| New       | Ownership by NBCUniversal/Comcast ended with the Comcast cable-network spin-off: separated from NBC News on 2025-10-06, rebranded **MS NOW** (`ms.now`) on **2025-11-15**, now part of **Versant**. |
| Evidence  | NewscastStudio, 2025-11-15 (*"On Nov. 15, 2025, MSNBC rebranded as MS NOW"*; separation from NBC News 2025-10-06; Versant). |
| Rationale | Fact about ownership, not a §2.4 re-assessment. tier and is_independent unchanged; the rest of both notes is untouched. Legacy debt in the entry (dead `category` field, two overlapping note fields, no country/region) deliberately left as is, to keep this change a pure fact correction. |

### 2. Note extensions — CH Media cross-notes (case (b), classifications unchanged)

`tagblatt.ch` joins as fifth CH-Media title (decision 7). The `independence_note` enumeration of
the four existing titles was extended to name it (alphabetical, self excluded):
`aargauerzeitung.ch`, `luzernerzeitung.ch`, `schweizheute.ch`, `watson.ch`. **No tier or
independence value changed.** Evidence for tagblatt.ch's CH-Media ownership: Batch E §3.2 note
(St. Galler Tagblatt, CH-Media group, Wanner). Reminder: `independence_note` is not read by the
pipeline (see the 2026-08-06 entry below).

### 3. Blacklist changes — `backend/sources/evaluator.py`

| Domain | Change | Rationale |
|---|---|---|
| `windows.net` | **removed** from `_USER_CONTENT_BLACKLIST` | The blacklist matches on `extract_domain()`, so it silently dropped every IEA report hosted on `iea.blob.core.windows.net` (Batch E §6.1). Removal verified with the real lookup before adding the subdomain entry: `lookup_source_all_registries("https://iea.blob.core.windows.net/…")` → `iea.blob.core.windows.net`, `evaluate_source()` → primary / independent. Every **other** Azure container now falls back to the unregistered default (tertiary / neutral, `counts_for_threshold: false`) instead of being dropped. |
| `ithy.com` | added to `_USER_CONTENT_BLACKLIST` | AI-generated answer aggregator, no human author (Batch E §6.3). Not assessable for independence or tier. Precedent `blogspan.net`. |
| `beyondtmrw.org` | added to `_USER_CONTENT_BLACKLIST` | About page: articles *"researched and drafted with AI tools"*, *"No human reads each piece before it goes live"* (ZYNK PTY LTD; Batch F §2). |
| `wordpress.com` | added to `_USER_CONTENT_BLACKLIST` | Blog-hosting platform with arbitrary user blogs on subdomains (Batch F §2), analogous to `blogspan.net`. Note: `blogspot.com`, `medium.com`, `substack.com` are not listed; consistency left for a future review. |

Not changed: `github.com` stays blacklisted (decision 1; Batch E §3.5 proposal dropped).
`mattioli1885journals.com` is **not** blacklisted (decision 17) but registered, see below.

### 4. Decision 13 — no umbrella domains

Government portals that host many distinct institutions were **not** registered at the root;
only the subdomain that actually occurred was registered:

| Planned root | Registered instead | Reason |
|---|---|---|
| `niedersachsen.de` | `mb.niedersachsen.de` | subdomain hit |
| `bundeswehr.de` | `zms.bundeswehr.de` | subdomain hit |
| `wien.gv.at` | `geschichtewiki.wien.gv.at` | subdomain hit |
| `hessen.de` | — (nothing) | hit was `hlz.hessen.de` (Landeszentrale); skipped in this batch by decision |
| `vorarlberg.at` | — (nothing) | Land portal = umbrella; hit URL not available locally, so root vs. subdomain could not be established. Skipped; reappears in the next unknown-sources run |

All other government domains in the batch are single-institution sites (a ministry, agency,
embassy network, municipality or project portal), whose subdomains belong to the same institution.

### 5. New entries (111)

Old classification for all: `— / —`. Every Not Independent entry names its §2.4 criterion and
evidence; the same text is in the entry's `affiliation_note`.

| Domain | Change | institution_type | Source | Rationale / NI criterion |
|---|---|---|---|---|
| `lpb-bw.de` | — / — → Secondary / Independent | government | E §2 | Classified per review; see note in entry. |
| `hanisauland.de` | — / — → Secondary / Independent | government | E §2 | Classified per review; see note in entry. |
| `hdg.de` | — / — → Secondary / Independent | other | E §2 | Classified per review; see note in entry. |
| `irishstar.com` | — / — → Tertiary / Neutral | media | E §2 | Classified per review; see note in entry. |
| `unfccc.int` | — / — → Primary / Not Independent | government | E §2 | **§2.4 criterion 1**: UN treaty secretariat; member states direct mandates and outputs. Standing UN rule (`docs/registry_review/Registry_Review_301_Domains.md:26`, *"nie 'independent'"*), identical to `un.org`, `who.int`, `ipcc.ch`. |
| `dgvn.de` | — / — → Secondary / Not Independent | ngo | E §2 | **§2.4 criterion 2** (>50% state funding): Bundestag lobby register R001926, FY2025 — Federal Foreign Office institutional grant EUR 1.34–1.35m + BMZ EUR 0.21–0.22m vs membership fees EUR 0.13–0.14m. Plus programmatic pro-UN mission (stated in note, not a criterion). |
| `ms.now` | — / — → Secondary / Not Independent | media | E §2 | **Successor domain, no new §2.4 finding.** Same outlet as `msnbc.com` under a new name (NewscastStudio, 2025-11-15); classification inherited unchanged. `msnbc.com`'s own NI basis predates this changelog and is not reconstructed here. |
| `zms.bundeswehr.de` | — / — → Primary / Not Independent | government | E §2 + decision 13 | **§2.4 criterion 1** (direct government oversight): the site is operated by a government body itself. ZMSBw = research centre of the Bundeswehr (MoD); site self-identifies as *Zentrum für Militärgeschichte und Sozialwissenschaften der Bundeswehr* (fetched 2026-11-23). |
| `bmz.de` | — / — → Primary / Not Independent | government | E §2 | **§2.4 criterion 1** (direct government oversight): the site is operated by a government body itself. Federal ministry. |
| `history.com` | — / — → Tertiary / Neutral | media | E §2 | Classified per review; see note in entry. |
| `ebsco.com` | — / — → Tertiary / Neutral | aggregator | E §2 | Classified per review; see note in entry. |
| `yahoo.com` | — / — → Tertiary / Neutral | aggregator | E §2 | Classified per review; see note in entry. |
| `auswaertiges-amt.de` | — / — → Primary / Not Independent | government | E §3.1 | **§2.4 criterion 1** (direct government oversight): the site is operated by a government body itself. Federal ministry. |
| `bundesumweltministerium.de` | — / — → Primary / Not Independent | government | E §3.1 | **§2.4 criterion 1** (direct government oversight): the site is operated by a government body itself. Federal ministry (supervising ministry of `umweltbundesamt.de`). |
| `bundeskanzler.de` | — / — → Primary / Not Independent | government | E §3.1 | **§2.4 criterion 1** (direct government oversight): the site is operated by a government body itself. Federal Chancellery web presence (cf. `bundesregierung.de`). |
| `geschichtewiki.wien.gv.at` | — / — → Primary / Not Independent | government | E §3.1 + decision 13 | **§2.4 criterion 1** (direct government oversight): the site is operated by a government body itself. Page footer: *"Ein Service der Stadt Wien"* (fetched 2026-11-23). |
| `bmwet.gv.at` | — / — → Primary / Not Independent | government | E §3.1 | **§2.4 criterion 1** (direct government oversight): the site is operated by a government body itself. Federal ministry (precedent: `*.gv.at` siblings, all primary/NI). |
| `bmeia.gv.at` | — / — → Primary / Not Independent | government | E §3.1 | **§2.4 criterion 1** (direct government oversight): the site is operated by a government body itself. Federal ministry. |
| `bmluk.gv.at` | — / — → Primary / Not Independent | government | E §3.1 | **§2.4 criterion 1** (direct government oversight): the site is operated by a government body itself. Federal ministry. |
| `ambafrance.org` | — / — → Primary / Not Independent | government | E §3.1 | **§2.4 criterion 1** (direct government oversight): the site is operated by a government body itself. French embassy network (foreign service). |
| `datenschutz.de` | — / — → Secondary / Independent | government | E §6.5 + decision 23.11. | Classified per review; see note in entry. |
| `theatlantic.com` | — / — → Secondary / Independent | media | E §3.2 | Classified per review convention. |
| `newyorker.com` | — / — → Secondary / Independent | media | E §3.2 | Classified per review convention. |
| `independent.co.uk` | — / — → Secondary / Independent | media | E §3.2 | Classified per review convention. |
| `stern.de` | — / — → Secondary / Independent | media | E §3.2 | Classified per review convention. |
| `forbes.com` | — / — → Secondary / Independent | media | E §3.2 | Classified per review; see note in entry. |
| `fortune.com` | — / — → Secondary / Independent | media | E §3.2 | Classified per review convention. |
| `inquirer.com` | — / — → Secondary / Independent | media | E §3.2 | Classified per review convention. |
| `sun-sentinel.com` | — / — → Secondary / Independent | media | E §3.2 | Classified per review convention. |
| `tagblatt.ch` | — / — → Secondary / Independent | media | E §3.2 + decision 7 | Classified per review; see note in entry. |
| `statnews.com` | — / — → Secondary / Independent | media | E §3.2 | Classified per review convention. |
| `dailymail.com` | — / — → Tertiary / Neutral | media | E §3.3 | Classified per review convention. |
| `dailystar.co.uk` | — / — → Tertiary / Neutral | media | E §3.3 | Classified per review; see note in entry. |
| `theblast.com` | — / — → Tertiary / Neutral | media | E §3.3 | Classified per review convention. |
| `indiatimes.com` | — / — → Tertiary / Neutral | media | E §3.3 | Classified per review convention. |
| `onthisday.com` | — / — → Tertiary / Neutral | aggregator | E §3.4 | Classified per review convention. |
| `newworldencyclopedia.org` | — / — → Tertiary / Neutral | aggregator | E §3.4 | Classified per review convention. |
| `dewiki.de` | — / — → Tertiary / Neutral | aggregator | E §6.2 | Classified per review; see note in entry. |
| `lexicanum.de` | — / — → Tertiary / Neutral | aggregator | E §3.4 | Classified per review; see note in entry. |
| `lingoda.com` | — / — → Tertiary / Not Independent | company | E §3.5 | **§2.4 criterion 4** (commercial interest): corporate source, registry convention *"Corporate source; not editorially independent."* (precedent `ubs.com`). |
| `advisori.de` | — / — → Tertiary / Not Independent | company | E §3.5 | **§2.4 criterion 4** (commercial interest): corporate source, registry convention *"Corporate source; not editorially independent."* (precedent `ubs.com`). |
| `morningstar.de` | — / — → Tertiary / Neutral | media | E §3.5 + decision 10 | Classified per review convention. |
| `swissdaytours.com` | — / — → Tertiary / Not Independent | company | E §3.5 | **§2.4 criterion 4** (commercial interest): corporate source, registry convention *"Corporate source; not editorially independent."* (precedent `ubs.com`). |
| `myswitzerland.com` | — / — → Tertiary / Not Independent | government | E §6.4 | **§2.4 criterion 4** (closest match; commercial/promotional interest): Switzerland Tourism, public-law corporation (HR Zürich CH-020.8.900.013-0) whose mandate is national tourism marketing; content is promotional (E §6.4). |
| `baublatt.ch` | — / — → Tertiary / Not Independent | company | E §3.5 | **§2.4 criterion 4** (commercial interest): corporate source, registry convention *"Corporate source; not editorially independent."* (precedent `ubs.com`). |
| `cstoredive.com` | — / — → Tertiary / Not Independent | company | E §3.5 | **§2.4 criterion 4** (commercial interest): corporate source, registry convention *"Corporate source; not editorially independent."* (precedent `ubs.com`). |
| `prpg.digital` | — / — → Tertiary / Not Independent | company | E §6.2 | **§2.4 criterion 4** (commercial interest): corporate source, registry convention *"Corporate source; not editorially independent."* (precedent `ubs.com`). |
| `healthdigest.com` | — / — → Tertiary / Not Independent | company | E §3.5 | **§2.4 criterion 4** (commercial interest): corporate source, registry convention *"Corporate source; not editorially independent."* (precedent `ubs.com`). |
| `thedrive.com` | — / — → Tertiary / Not Independent | company | E §3.5 | **§2.4 criterion 4** (commercial interest): corporate source, registry convention *"Corporate source; not editorially independent."* (precedent `ubs.com`). |
| `cornell.edu` | — / — → Secondary / Independent | academic | E §3.6 | Classified per review convention. |
| `mattioli1885journals.com` | — / — → Tertiary / Neutral | academic | E §6.3 + decision 17 | Classified per review; see note in entry. |
| `planet-wissen.de` | — / — → Secondary / Independent | media | E §6.2 | Classified per review; see note in entry. |
| `myclimate.org` | — / — → Secondary / Not Independent | ngo | E §3.7 | **§2.4 criterion 4** (commercial conflict of interest): sells carbon-offset services while advocating on climate policy. |
| `amnesty-todesstrafe.de` | — / — → Secondary / Independent | ngo | E §6.1 | Classified per review; see note in entry. |
| `progress.org.uk` | — / — → Secondary / Independent | ngo | E §6.1 | Classified per review; see note in entry. |
| `demokratiezentrum.org` | — / — → Secondary / Independent | ngo | E §3.7 | Classified per review convention. |
| `easyvote.ch` | — / — → Secondary / Independent | ngo | E §6.4 | Classified per review; see note in entry. |
| `chstiftung.ch` | — / — → Secondary / Not Independent | ngo | E §6.2 + decision 16 | **§2.4 criterion 2** (>50% state funding) **and criterion 1** (governance by government members): annual report 2025 — cantonal contributions CHF 5,097,615 of CHF 6,447,457 revenue = 79.1% (83.7% incl. SECO); foundation council = one government member per canton. |
| `amendmentsproject.org` | — / — → Secondary / Independent | academic | E §6.2 | Classified per review; see note in entry. |
| `treffpunkteuropa.de` | — / — → Tertiary / Not Independent | ngo | E §3.7 | ⚠️ **No numbered §2.4 criterion documented.** Classification rests on the Batch E §3.7 advocacy convention (programmatic advocacy line → NI; precedent `amadeu-antonio-stiftung.de`): magazine of the Junge Europäische Föderalisten (JEF), a pro-European advocacy organisation. Funding not examined. |
| `stiftung-berliner-mauer.de` | — / — → Secondary / Independent | other | E §6.2 | Classified per review; see note in entry. |
| `nationalww2museum.org` | — / — → Tertiary / Neutral | other | E §6.4 | Classified per review; see note in entry. |
| `snopes.com` | — / — → Secondary / Independent | media | E §3.9 | Classified per review convention. |
| `schweiz.blog` | — / — → Tertiary / Neutral | media | E §6.2 | Classified per review convention. |
| `politicalwire.com` | — / — → Tertiary / Neutral | media | E §6.2 | Classified per review; see note in entry. |
| `2mecs.de` | — / — → Tertiary / Neutral | other | E §6.2 | Classified per review convention. |
| `sajr.co.za` | — / — → Secondary / Independent | media | E §6.2 | Classified per review convention. |
| `winfuture.de` | — / — → Secondary / Independent | media | E §6.2 | Classified per review convention. |
| `atlantablackstar.com` | — / — → Secondary / Independent | media | E §6.2 | Classified per review convention. |
| `glarus-sued.ch` | — / — → Primary / Not Independent | government | E §6.4 | **§2.4 criterion 1** (direct government oversight): the site is operated by a government body itself. Official municipal site (checked by hand, Marc, 2026-11-23). |
| `schienenverkehr-schweiz.ch` | — / — → Tertiary / Neutral | other | E §4a + decision 18 | Classified per review; see note in entry. |
| `iea.blob.core.windows.net` | — / — → Primary / Independent | — | E §6.1 + decision 23.11. | Classified per review; see note in entry. |
| `csr-in-deutschland.de` | — / — → Primary / Not Independent | government | F §1 | **§2.4 criterion 1** (direct government oversight): the site is operated by a government body itself. Imprint: *"© 2026 Bundesministerium für Arbeit und Soziales"* (F §1). |
| `theemancipator.org` | — / — → Secondary / Independent | media | F §1 | Classified per review; see note in entry. |
| `frontiersin.org` | — / — → Secondary / Independent | academic | F §1 | Classified per review convention. |
| `ntd.com` | — / — → Secondary / Not Independent | media | F §1 + decision 16 | **Media-group dependency:** same group as The Epoch Times (Epoch Media Group) with shared leadership (NBC News investigation, August 2019); About page calls The Epoch Times its *"sister media"*. ⚠️ None of the four §2.4 criteria matches verbatim; recorded as decided 2026-11-23 (decision 16). **§3.2 question 3:** a media outlet sharing ownership and leadership with any other outlet is assessed identically regardless of political direction. |
| `zukunft-braucht-erinnerung.de` | — / — → Tertiary / Neutral | other | F §1 | Classified per review convention. |
| `democracydocket.com` | — / — → Secondary / Not Independent | media | F §1 + decision 16 | **§2.4 criterion 4** (documented financial relationship with an actor that has a material stake in the claims covered): founder and publisher Marc Elias is a paid legal adviser to the Democratic National Committee (Bloomberg Law, 2026-08-04). **§3.2 question 3:** an equivalent outlet published by a paid adviser to the RNC would be classified identically. |
| `nps.gov` | — / — → Primary / Not Independent | government | F §3.1 | **§2.4 criterion 1** (direct government oversight): the site is operated by a government body itself. US federal agency (Department of the Interior). |
| `mb.niedersachsen.de` | — / — → Primary / Not Independent | government | F §3.1 + decision 13 | **§2.4 criterion 1** (direct government oversight): the site is operated by a government body itself. State ministry; page title *"Nds. Ministerium für Bundes- und Europaangelegenheiten und Regionale Entwicklung"* (fetched 2026-11-23). |
| `armywarcollege.edu` | — / — → Secondary / Not Independent | academic | F §3.1 + decision 11 | **§2.4 criterion 1**: government-operated military college (US Army). Classified identically to the precedent `westpoint.edu` (secondary / NI / academic), decision 11. |
| `slate.com` | — / — → Secondary / Independent | media | F §3.2 | Classified per review convention. |
| `livemint.com` | — / — → Secondary / Independent | media | F §3.2 | Classified per review convention. |
| `finews.ch` | — / — → Secondary / Independent | media | F §3.2 | Classified per review convention. |
| `commercialappeal.com` | — / — → Secondary / Independent | media | F §3.2 | Classified per review convention. |
| `abc7ny.com` | — / — → Secondary / Independent | media | F §3.2 | Classified per review convention. |
| `fox5dc.com` | — / — → Secondary / Independent | media | F §3.2 | Classified per review convention. |
| `wjcl.com` | — / — → Secondary / Independent | media | F §3.2 | Classified per review convention. |
| `rfi.fr` | — / — → Secondary / Not Independent | media | F §3.3 | **§2.4 criterion 2**: part of France Médias Monde, the state-controlled company that also owns `france24.com`, whose entry documents 100% state appropriations. Same parent, same classification. |
| `mcgill.ca` | — / — → Secondary / Independent | academic | F §3.4 | Classified per review convention. |
| `vcu.edu` | — / — → Secondary / Independent | academic | F §3.4 | Classified per review convention. |
| `plos.org` | — / — → Secondary / Independent | academic | F §3.4 | Classified per review convention. |
| `poynter.org` | — / — → Secondary / Independent | academic | F §3.7 | Classified per review; see note in entry. |
| `taylorwessing.com` | — / — → Tertiary / Not Independent | company | F §3.5 | **§2.4 criterion 4** (commercial interest): corporate source, registry convention *"Corporate source; not editorially independent."* (precedent `ubs.com`). |
| `twobirds.com` | — / — → Tertiary / Not Independent | company | F §3.5 | **§2.4 criterion 4** (commercial interest): corporate source, registry convention *"Corporate source; not editorially independent."* (precedent `ubs.com`). |
| `osborneclarke.com` | — / — → Tertiary / Not Independent | company | F §3.5 | **§2.4 criterion 4** (commercial interest): corporate source, registry convention *"Corporate source; not editorially independent."* (precedent `ubs.com`). |
| `legaltegrity.com` | — / — → Tertiary / Not Independent | company | F §3.5 | **§2.4 criterion 4** (commercial interest): corporate source, registry convention *"Corporate source; not editorially independent."* (precedent `ubs.com`). |
| `eclear.com` | — / — → Tertiary / Not Independent | company | F §3.5 | **§2.4 criterion 4** (commercial interest): corporate source, registry convention *"Corporate source; not editorially independent."* (precedent `ubs.com`). |
| `vattenfall.de` | — / — → Tertiary / Not Independent | company | F §3.5 | **§2.4 criterion 4** (commercial interest): corporate source, registry convention *"Corporate source; not editorially independent."* (precedent `ubs.com`). |
| `unioncitizenship.com` | — / — → Tertiary / Not Independent | company | F §3.5 | **§2.4 criterion 4** (commercial interest): corporate source, registry convention *"Corporate source; not editorially independent."* (precedent `ubs.com`). |
| `unilad.com` | — / — → Tertiary / Neutral | media | F §3.6 | Classified per review convention. |
| `fiveable.me` | — / — → Tertiary / Neutral | other | F §3.6 | Classified per review convention. |
| `military.com` | — / — → Tertiary / Neutral | media | F §3.7 | Classified per review; see note in entry. |
| `normandy1944.info` | — / — → Tertiary / Neutral | other | F §3.6 | Classified per review convention. |
| `iamexpat.ch` | — / — → Tertiary / Neutral | media | F §3.6 | Classified per review convention. |
| `frontaliereticino.ch` | — / — → Tertiary / Neutral | media | F §3.6 | Classified per review convention. |
| `travelnews.ch` | — / — → Tertiary / Neutral | media | F §3.6 | Classified per review convention. |
| `moneycab.com` | — / — → Secondary / Independent | media | F §3.7 | Classified per review convention. |
| `vermoegenmagazin.de` | — / — → Tertiary / Neutral | media | F §3.6 | Classified per review convention. |
| `anwalt.org` | — / — → Tertiary / Neutral | other | F §3.6 | Classified per review convention. |
| `gfmag.com` | — / — → Secondary / Independent | media | F §3.7 | Classified per review; see note in entry. |

**Open governance items from this batch:**

- ⚠️ **§3.4 audit due by 2026-12-23** (111 domains > 10). The audit for `e6f02c6` (due 2026-08-01) is still outstanding.
- ⚠️ **Not Independent without a verbatim §2.4 criterion:** `ntd.com` (media-group dependency) and `treffpunkteuropa.de` (advocacy convention). Flagged for the next governance review.
- `geschichtewiki.wien.gv.at` is a wiki (with public contributions) registered with the planned `wien.gv.at` classification (primary). Its tier should be reviewed.
- `dailymail.co.uk` is **not** registered. HTTP check 2026-11-23: `https://www.dailymail.co.uk/` 301-redirects to `https://www.dailymail.com/home/index.html` (title *"UK Home | Daily Mail Online"*), so it is the same outlet. Unregistered URLs default to tertiary / neutral, which already equals the `dailymail.com` classification.
- Registry-wide side effect of the `windows.net` change: `extract_domain()` still reduces all Azure containers to `windows.net`, so for domain dedup in the rating, all Azure-hosted sources in one judgment count as one domain.

---

## 2026-08-06 — Fact corrections and one reclassification (3 domains)

Basis: the collision rule in force since 2026-08-06 — **(a)** same facts → keep the existing
entry; **(b)** changed or incorrect facts → the entry *must* be corrected, documented with date
and evidence. Cases 1 and 2 below are (b) fact corrections with no classification change.
Case 3 is **not** a fact correction but a genuine reclassification, and carries the individual
justification §3.3 requires.

No Batch-E candidate domains were added in this commit; the 79 proposals from
`registry_batch_e_duplicates.md` remain unapproved.

### 1. luzernerzeitung.ch — missing owner-concentration note

| Field     | Value |
|-----------|-------|
| Domain    | `luzernerzeitung.ch` |
| Change    | Secondary / Independent → Secondary / Independent (**unchanged**) |
| Type      | (b) fact correction — note added, classification untouched |
| Rationale | Ownership fact, not a judgement change. The entry is named *"Luzerner Zeitung (CH Media)"* but was the only one of the four registered CH-Media titles without the owner-concentration note the other three received in commit `e6f02c6` (2026-07-02). Evidence: the entry's own `name` field records the CH-Media affiliation; the note wording is copied verbatim from the `aargauerzeitung.ch` sibling. This is **not** a §2.4 finding — CH Media is a private publisher and the title remains editorially independent. The note exists so that citing several CH-Media titles is not mistaken for independent corroboration, per the Symmetry and Transparency Principles. |
| Commit    | `e40f115` |

Concurrent housekeeping in the same commit: the enumerated title list inside all four CH-Media
notes was extended so each entry names the other three (alphabetical, self excluded). Previously
the lists named only two of three siblings and omitted `luzernerzeitung.ch` entirely. Affected:
`aargauerzeitung.ch`, `schweizheute.ch`, `watson.ch`. **No tier or independence value changed on
any of them.**

⚠️ Known limitation, recorded deliberately: all four CH-Media notes live in the
`independence_note` field, which `apply_registry_override()` does **not** read
(`backend/sources/registries/__init__.py:140-143` copies only `affiliation_note`). These notes
are therefore documentation for reviewers and do not reach a judgment at runtime. Moving them to
`affiliation_note` would be a behaviour change and was left out of scope; it should be decided
separately for the whole class of independent-but-owner-concentrated sources.

### 2. gouv.fr — incomplete Stufe-1 note

| Field     | Value |
|-----------|-------|
| Domain    | `gouv.fr` |
| Change    | Primary / Not Independent → Primary / Not Independent (**unchanged**) |
| Type      | (b) fact correction — note completed, classification untouched |
| Old value | `"Official government institution of France."` |
| New value | `"Official government institution of France. Not editorially independent."` |
| Rationale | §2.4 criterion 1 (direct government oversight / ministerial control) — already the basis of the existing Not Independent classification, which is not being changed. The note was missing the second sentence of the standard Stufe-1 template documented in `docs/registry_review/Registry_Batch_D_Staatsquellen.md:11` and carried by 71 other entries (e.g. `gov.pl`, `bmi.gv.at`). Evidence: the template itself and the 71 conforming entries. A drafting omission, corrected for consistency. |
| Commit    | `e40f115` |

### 3. ipcc.ch — RECLASSIFICATION (individual justification per §3.3)

| Field     | Value |
|-----------|-------|
| Domain    | `ipcc.ch` |
| Change    | **Primary / Neutral → Primary / Not Independent** |
| Type      | Reclassification — not a fact correction |
| Commit    | `e40f115` |

**Old entry:**
```json
    {
      "name": "Intergovernmental Panel on Climate Change (IPCC)",
      "domain": "ipcc.ch",
      "tier": "primary",
      "is_independent": "neutral",
      "institution_type": "government",
      "country": "INT",
      "region": "INT"
    },
```

**New entry:**
```json
    {
      "name": "Intergovernmental Panel on Climate Change (IPCC)",
      "domain": "ipcc.ch",
      "tier": "primary",
      "is_independent": false,
      "institution_type": "government",
      "affiliation_note": "Intergovernmental body of the United Nations (WMO/UNEP); member states exercise political direction over the IPCC's mandate, work programme, and the line-by-line government approval of Summary for Policymakers texts. Structurally identical to un.org and who.int, both classified primary / not independent. The underlying assessment chapters are authored by scientists under scholarly standards and remain authoritative primary sources for the state of climate research; the approved policymaker summaries are negotiated documents. Reclassified 2026-08-06 from neutral to not independent to remove an unexplained exception to the standing UN rule (see REGISTRY_CHANGELOG.md).",
      "country": "INT",
      "region": "INT"
    },
```

**Rationale — §2.4 criterion 1 (direct government oversight / ministerial control).**
The IPCC is an intergovernmental body established by the WMO and UNEP. Member-state governments
exercise political direction over its mandate and work programme, and the Summary for
Policymakers is subject to line-by-line government approval before publication. This is the same
structural relationship as `un.org` (*"member states exercise political direction over mandates
and outputs"*) and `who.int` (*"UN specialized agency; member states exercise political direction
over mandates and health policy"*), both classified `primary / not independent`.

**Named evidence for the rule being applied:** `docs/registry_review/Registry_Review_301_Domains.md:26`
states the standing convention verbatim — *"Konsistent zur UN-Regel: nie 'independent'."* The
same document (line 32) proposed `ipcc.ch` as `P/N`, which is where the outlier originated. The
Neutral classification was never justified in the registry: the entry carried no note at all.

**§3.2 question 3 (direction test) — answered affirmatively.** The change moves in the same
direction irrespective of political association: it applies the identical criterion already
applied to `un.org`, `who.int`, `nato.int`, and `press.un.org`. An intergovernmental body whose
outputs are government-approved is classified Not Independent regardless of the policy area or
of whether GradedFacts agrees with its conclusions. `REGISTRY_GOVERNANCE.md` §6.1 is explicit
that a source may not retain Independent (or here, the more permissive Neutral) status because
its conclusions are considered correct. The scientific quality of the assessment reports is not
in question and is stated in the note — Not Independent describes the institutional
relationship, not the accuracy of the output (§2.3).

**§3.2 question 4 (scope) — answered; no retrospective note warranted.**
Neutral and Not Independent differ materially in the pipeline: a Neutral source is *"treated as
independent for threshold purposes"* (§2.2), whereas Not Independent is algorithmically
downgraded from Primary to Secondary (§1). Existing judgments citing `ipcc.ch` could therefore
have counted it toward an independence requirement it no longer satisfies.

A database check against production on 2026-08-06 found **0 active VERIFIED or DEBUNKED
judgments citing `ipcc.ch`**. No judgment's rating threshold depended on the old Neutral
classification, so the reclassification has no retroactive effect. **No scope review and no
retroactive note are required.** Recorded here as the answer to §3.2 question 4.

---

## 2026-07-02 — Registry batch review: +61 sources (retroactive entry per §4.4)

⚠️ **Reconstructed after the fact on 2026-08-06.** This batch was committed on 2026-07-02, before
`REGISTRY_CHANGELOG.md` existed. The entry below is reconstructed from the git commit and diff,
per `REGISTRY_GOVERNANCE.md` §4.4. It is **not** contemporaneous documentation, and the
per-domain rationales that §3.3 requires were never recorded — only the aggregate description
below can be reconstructed. This is a documented gap, not a complete record.

| Field     | Value |
|-----------|-------|
| Domain    | 61 domains (see commit diff) |
| Change    | `— / —` → various (new entries only) |
| Commit    | `e6f02c6` |

**Reconstructed scope, from the commit message and diff:**

- **+61 new source entries**, taking the registry from 716 to **777** entries. The diff against
  `registry.json` shows 614 insertions and 1 deletion; the single deleted line is the final line
  of the previously-last entry, re-emitted with a trailing comma to open the append. **No
  existing entry was modified or reclassified in that commit.**
- **CH-Media owner-concentration notes** added to `watson.ch`, `aargauerzeitung.ch`, and
  `schweizheute.ch`, recording sole Wanner ownership since 2026-04-01. (`luzernerzeitung.ch` was
  missed; corrected above on 2026-08-06.)
- **Blacklist additions** in `backend/sources/evaluator.py` (5 lines): `t.co`,
  `quora.com`, `blogspan.net`, `michael-mannheimer.net`, `michael-donth.de`.
- **5 conflicts resolved keep-existing** — five proposed domains already existed in the registry;
  the proposals were dropped and the existing classifications left untouched. The individual
  domains were not recorded and are no longer recoverable from the diff.
- 764 tests green at time of commit.

**Outstanding governance obligations from this batch:**

- ⚠️ **§3.4 audit overdue.** A batch expansion of more than 10 domains requires a §5 audit within
  30 days. The deadline was **2026-08-01**; no audit has been produced. `registry_audit.txt` at
  the project root reports `Total sources: 274` and pre-dates the 2.0.0 unified-registry merge,
  so it does not cover this batch.
- ⚠️ Per-domain rationales for the 61 additions were never recorded and cannot be reconstructed
  from the diff alone.

---

*GradedFacts — Registry integrity is a precondition for analytical integrity.*
