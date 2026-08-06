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
