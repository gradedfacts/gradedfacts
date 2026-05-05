# GradedFacts — Source Independence Criteria

**Version:** 1.0.0  
**Last updated:** 2026-05-05  
**Applies to:** All source registries in `backend/sources/registries/` and the compromised-institution registry in `backend/sources/independence_registry.py`

---

## 1. Two dimensions, evaluated separately

Every source is assessed on two independent dimensions. Conflating them is one of the most common errors in automated fact-checking.

### Tier — document type

| Tier | Meaning |
|------|---------|
| **Primary** | Original data, official documents, government records, court filings, peer-reviewed research, or direct statements from the relevant institution. Closest to the underlying event or dataset. |
| **Secondary** | Journalism or analysis that cites and attributes primary sources with full transparency. Does not generate new data — accurately reports and contextualises existing data. |
| **Tertiary** | Aggregations, opinion pieces, summaries, or commentary without independent verification of the underlying data. A claim supported only by tertiary sources is capped at **Speculative** and cannot be rated **Verified**. |

Tier describes what a document *is*, not how reliable it is.

### Independence — institutional integrity

Independence describes whether the institution that produced a source is free from documented conflicts of interest that would systematically bias its output. **Official status does not imply independence.** A government agency can be a primary-tier source while simultaneously being non-independent — the two dimensions do not correlate.

When a primary-tier source is non-independent, it is treated as secondary weight for rating purposes: a captured institution cannot substitute for an independent primary source when establishing a **Verified** rating.

---

## 2. Classification criteria: "not independent"

A source is classified `is_independent: false` when one or more of the following is documented:

1. **Political appointment on loyalty criteria.** The institution's leadership was appointed with documented requirements of personal loyalty to a political actor rather than professional qualification — and that actor has a direct stake in the claims the institution produces.

2. **Documented political interference.** There is a documented record of political actors directing, suppressing, or altering the institution's output — through staff removals, pressure campaigns, selective disclosure, or published internal communications showing editorial coordination with a political agenda.

3. **Ownership or control by a partisan entity.** The institution is owned, funded, or editorially controlled by a political party, PAC, partisan foundation, or individual whose primary public identity is political. This includes both right-aligned and left-aligned owners; the standard is applied symmetrically.

4. **State media without structural editorial independence.** The institution is a government-funded broadcaster or news outlet without a legally enforceable editorial independence mechanism (such as a Royal Charter, statutory prohibition on government interference, or equivalent). Full state funding combined with a government-appointed leadership structure is treated as structural non-independence.

5. **Financial dependency on political actors.** The institution receives a dominant share of its funding from a single political actor or politically aligned foundation, and no documented firewall between funder and editorial decisions exists.

The criteria are applied symmetrically: the same standard that marks a left-aligned partisan outlet non-independent marks a right-aligned one non-independent, and vice versa.

---

## 3. Current non-independent sources

The table below covers all sources currently classified `is_independent: false` across GradedFacts registries. Sources are grouped by the primary reason for their classification.

### 3a. State-controlled media — structural non-independence

These outlets operate under direct state editorial control. No editorial charter or structural independence mechanism exists. Independence is not a matter of degree; it is structurally impossible.

| Source | Domain | Reason | Evidence |
|--------|--------|--------|----------|
| **RT** (Russia Today) | `rt.com` | Kremlin-controlled broadcaster. | RT is wholly owned by ANO TV-Novosti, a Russian state entity funded by the federal budget. The Russian Foreign Agents Act designates RT a foreign agent in multiple jurisdictions. RT has been banned from broadcasting in the EU (Council Regulation 2022/350) for "media manipulation." Editorially directed by the Kremlin. |
| **CGTN** (China Global Television Network) | `cgtn.com` | CCP-controlled broadcaster. | CGTN is operated by China Central Television (CCTV), which reports directly to the CCP Propaganda Department. UK regulator Ofcom revoked CGTN's broadcast licence in 2021, finding that editorial control ultimately rested with the Chinese Communist Party. |
| **TRT World / TRT** (Turkish Radio and Television) | `trt.net.tr`, `trtworld.com` | Turkish state broadcaster under AKP government control. | TRT is a public broadcaster governed by a board whose members are appointed by the president and the Council of Ministers. RSF (Reporters Without Borders) ranks Turkey in the bottom quartile globally for press freedom; TRT's coverage consistently aligns with AKP government positions. Anadolu Agency (aa.com.tr) follows the same appointment structure. |

### 3b. Executive institutions under politically appointed leadership

These are official government institutions whose independence is currently compromised by documented political appointment criteria. The classification is time-bounded: entries carry a `compromised_since` date and may be updated when leadership changes.

| Source | Domain | Reason | Evidence |
|--------|--------|--------|----------|
| **FBI** (under Director Kash Patel) | `fbi.gov` | Director appointed on loyalty criteria; stated intent to use the Bureau against political opponents. | Kash Patel confirmed as FBI Director on 2025-02-20. Senate confirmation hearings documented his statements about using federal law enforcement against perceived political enemies of the administration. Multiple career FBI officials departed or were removed following his appointment. |
| **DOJ** (under AG Pam Bondi) | `justice.gov` | Attorney General confirmed after pledging personal loyalty to the President; career staff resignations citing political interference. | Pam Bondi confirmed as Attorney General on 2025-01-22. Senate testimony included statements of personal loyalty to President Trump. Multiple career prosecutors in the DC US Attorney's Office and Main Justice resigned or were reassigned citing political direction of charging decisions. |

### 3c. Government executive communications — official but not independent by design

These sources are the authentic voice of their respective governments and are reliable primary sources for what a government *says* or *decides*. They are not independent because their content *is* government policy — they cannot assess that policy objectively.

| Source | Domain | Reason | Evidence |
|--------|--------|--------|----------|
| **European Commission** | `ec.europa.eu` | EU's political executive body; content reflects Commission political program, not independent analysis. | Commissioners are nominated by member state governments and approved by the European Parliament based on a political agenda. Press releases and policy proposals represent the current Commission's priorities. Reliable as the authoritative text of EU regulations and decisions; not reliable for independent assessment of those measures. |
| **EEAS** (European External Action Service) | `eeas.europa.eu` | EU diplomatic service operating under direct political authority of the High Representative. | The EEAS High Representative simultaneously serves as a Vice-President of the European Commission. EEAS publications represent official EU foreign policy positions, not independent international analysis. |
| **France 24** | `france24.com` | State-funded broadcaster under French government structural control. | France 24 is owned and funded entirely by France Médias Monde, a public company under French state control, receiving 100% of its budget through state appropriations. Established partly to promote French perspectives internationally. Unlike RT or CGTN, France 24's editorial charter provides formal independence protections and its journalism meets professional standards — but structural independence from the French state cannot be assumed, particularly on French foreign policy coverage. |
| **Federal Chancellery (CH)** | `bk.admin.ch` | General staff of the Swiss Federal Council; content reflects executive positions by definition. | The Federal Chancellery coordinates official Swiss government communications and publishes federal legislation via the Federal Gazette. Content reflects current Federal Council positions. Reliable as an authoritative record of official federal decisions and legislation; not independent of the executive. |
| **Gov.uk** | `gov.uk` | Official UK government website; content represents current government policy. | Gov.uk publishes policy documents, guidance, and official statistics across all UK departments. Content represents current government policy and communications. Useful as a primary source for official government decisions, legislation, and announcements; not a source of independent analysis. |

### 3d. Editorially partisan media

These are privately owned outlets whose editorial output is documented to systematically align with a specific political agenda. Unlike state media, independence is theoretically possible — but documented evidence establishes that it does not exist in practice.

| Source | Domain | Reason | Evidence |
|--------|--------|--------|----------|
| **Fox News** | `foxnews.com` | Ownership-driven partisan alignment; internal communications confirmed knowing broadcast of false claims. | Owned by Fox Corporation (Murdoch family). In *Dominion Voting Systems Corp. v. Fox News Network* (Delaware Superior Court, 2023), internal communications produced under subpoena showed Fox hosts and executives privately acknowledged the falsity of 2020 election fraud claims while publicly broadcasting them. Settled for $787.5 million in April 2023. Multiple academic studies document systematic alignment with Republican Party messaging in prime-time programming. |
| **MSNBC** | `msnbc.com` | Systematic editorial alignment with Democratic Party positions; ownership structure creates misaligned commercial incentives. | Owned by NBCUniversal/Comcast. Multiple peer-reviewed content analyses (including Pew Research Center studies on cable news framing) document consistent progressive-leaning framing and systematic alignment with Democratic Party positions in prime-time and daytime programming. Opinion and news programming share on-air talent, reducing audience ability to distinguish them. |
| **Breitbart News** | `breitbart.com` | Documented partisan investor ownership; leadership with direct ties to a presidential campaign. | Mercer family (Robert Mercer, Renaissance Technologies co-CEO and major Republican donor) provided documented major investment beginning approximately 2012. Former executive chairman Steve Bannon simultaneously served as CEO of the 2016 Trump presidential campaign and subsequently as White House Chief Strategist. IFCN-member fact-checking organizations have documented a sustained pattern of false or misleading articles. |
| **Truth Social** | `truthsocial.com` | Owned by a political actor with a majority equity stake; platform created to serve that actor's political communications. | Owned by Trump Media & Technology Group (TMTG, NASDAQ: DJT). Former President Donald Trump holds a majority equity stake as of 2025. The platform was created as Trump's primary social media outlet following his removal from Twitter/X. Posts by Trump are valid primary sources for his own statements; the platform cannot be treated as an independent source on claims involving Trump or his political interests. |

---

## 4. Wikipedia and Wikimedia — always Tertiary

Wikipedia (wikipedia.org) and all Wikimedia-operated properties (wikimedia.org) are classified as **Tertiary** in all cases, regardless of the quality of the specific article. This is a hard rule with no exceptions.

**Rationale:** Wikipedia is a crowd-edited aggregation of secondary and tertiary material. Individual articles may be accurate and well-sourced, but the platform itself does not generate original data, conduct independent reporting, or subject content to editorial accountability equivalent to journalism or peer review. Wikipedia can point to primary and secondary sources — those underlying sources count and should be cited directly. Wikipedia itself does not.

This rule applies to all language editions and all Wikimedia sub-projects (Wikidata, Wikisource, Wikinews, etc.).

---

## 5. Process: how sources enter the registry, who reviews, how to challenge

### Adding a source

Sources are added to the relevant regional registry JSON file (`us_sources.json`, `eu_sources.json`, etc.) or to the compromised-institution registry (`independence_registry.py`) via a pull request to the [GradedFacts GitHub repository](https://github.com/gradedfacts/gradedfacts).

Every new non-independent entry must include:
- `affiliation_note`: a precise, documented reason referencing named evidence (court filings, published research, regulatory decisions, etc.)
- For the compromised-institution registry: `compromised_since` (ISO date) and `compromised_until` if applicable

Every new independent entry must include:
- An `independence_note` documenting the ownership and funding structure that supports the independence assessment

### Review

Pull requests adding or modifying independence assessments require:
1. At least one named, publicly verifiable source for any factual claim in the `affiliation_note`
2. Consistency with the criteria in Section 2 — the same standard applied to sources across all political directions
3. Review by a GradedFacts maintainer before merge

### Challenging an assessment

If you believe a source has been incorrectly classified — either marked non-independent when it should be independent, or vice versa — open an issue on the [GitHub repository](https://github.com/gradedfacts/gradedfacts) with:
1. The source name and domain
2. The current classification
3. The evidence you believe supports a different classification
4. The specific criterion in Section 2 that you believe applies or does not apply

Assessments are revised when new evidence changes the factual basis for the classification. A leadership change at a compromised institution, a change of ownership, or a documented reversal of editorial interference would trigger a review. All revisions are timestamped in the git history.

---

*This document is part of the GradedFacts open-source methodology. It is versioned alongside the source registries and updated when classifications change.*
