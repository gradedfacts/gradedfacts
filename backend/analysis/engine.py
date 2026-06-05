import json
import logging
import subprocess
from pathlib import Path

import anthropic
import httpx

try:
    from langdetect import detect as _ld_detect, DetectorFactory as _LDFactory
    _LDFactory.seed = 0  # make detection deterministic across runs
    _LANGDETECT_AVAILABLE = True
except ImportError:
    _LANGDETECT_AVAILABLE = False

from backend.analysis.rating import EpistemicRating, EvidenceSummary, SourceTier, derive_rating
from backend.config import settings
from backend.db.models import Claim, EvaluatedSource, Judgment
from backend.sources.evaluator import evaluate_source, extract_domain

logger = logging.getLogger(__name__)

# ── Language detection ────────────────────────────────────────────────────────

_LANG_NAMES: dict[str, str] = {
    "af": "Afrikaans", "ar": "Arabic", "bg": "Bulgarian", "ca": "Catalan",
    "cs": "Czech", "cy": "Welsh", "da": "Danish", "de": "German",
    "el": "Greek", "en": "English", "es": "Spanish", "et": "Estonian",
    "fa": "Persian", "fi": "Finnish", "fr": "French", "gl": "Galician",
    "gu": "Gujarati", "he": "Hebrew", "hi": "Hindi", "hr": "Croatian",
    "hu": "Hungarian", "id": "Indonesian", "it": "Italian", "ja": "Japanese",
    "kn": "Kannada", "ko": "Korean", "lt": "Lithuanian", "lv": "Latvian",
    "mk": "Macedonian", "ml": "Malayalam", "mr": "Marathi", "ne": "Nepali",
    "nl": "Dutch", "no": "Norwegian", "pa": "Punjabi", "pl": "Polish",
    "pt": "Portuguese", "ro": "Romanian", "ru": "Russian", "sk": "Slovak",
    "sl": "Slovenian", "so": "Somali", "sq": "Albanian", "sv": "Swedish",
    "sw": "Swahili", "ta": "Tamil", "te": "Telugu", "th": "Thai",
    "tl": "Filipino", "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu",
    "vi": "Vietnamese", "zh-cn": "Chinese", "zh-tw": "Chinese (Traditional)",
    "zh": "Chinese",
}


# ── Off-topic message i18n ────────────────────────────────────────────────────

_LOCALE_DIR = Path(__file__).parents[2] / "frontend" / "locales"

# Maps language display names (returned by _detect_language) to locale directory codes.
_LANG_NAME_TO_LOCALE: dict[str, str] = {
    "English": "en", "German": "de", "French": "fr", "Spanish": "es",
    "Italian": "it", "Portuguese": "pt", "Dutch": "nl", "Russian": "ru",
    "Chinese": "zh", "Chinese (Traditional)": "zh", "Japanese": "ja",
    "Korean": "ko", "Arabic": "ar", "Ukrainian": "uk", "Polish": "pl",
    "Swedish": "sv", "Turkish": "tr", "Hungarian": "hu",
}

# Explicit mapping for the 17 supported UI language codes (BCP-47 base tags).
# Separate from _LANG_NAMES (which is for langdetect output normalisation) so
# that UI language selection is not coupled to the langdetect code table.
# Also handles region-qualified tags (e.g. "pt-BR", "zh-CN") via prefix lookup.
_UI_LANGUAGE_CODES: dict[str, str] = {
    "en": "English", "de": "German", "fr": "French", "it": "Italian",
    "es": "Spanish", "pt": "Portuguese", "nl": "Dutch", "pl": "Polish",
    "sv": "Swedish", "ru": "Russian", "uk": "Ukrainian", "tr": "Turkish",
    "ar": "Arabic", "zh": "Chinese", "ja": "Japanese", "ko": "Korean",
    "hu": "Hungarian",
    "da": "Danish", "fi": "Finnish", "cs": "Czech", "ro": "Romanian", "el": "Greek",
}


def _resolve_ui_language(user_language: str) -> str:
    """Map a BCP-47 UI language code to the language name used by _get_locale_message().

    Tries the full tag first ("pt-BR"), then the base tag ("pt"), then falls back
    to English so pre-flight gates always produce a usable message.
    """
    lang = user_language.strip()
    if lang in _UI_LANGUAGE_CODES:
        result = _UI_LANGUAGE_CODES[lang]
        logger.warning("_resolve_ui_language: %r → %r", user_language, result)
        return result
    base = lang.split("-")[0].split("_")[0].lower()
    result = _UI_LANGUAGE_CODES.get(base, "English")
    logger.warning("_resolve_ui_language: %r (base=%r) → %r", user_language, base, result)
    return result

_OFF_TOPIC_FALLBACK = (
    "GradedFacts Politics checks political and factual claims. "
    "Please formulate a politically or factually relevant claim."
)
_SPECIFICITY_FALLBACK = (
    "This claim is too vague to fact-check. "
    "Please refine it with specific names, dates, actions, or allegations."
)


def _get_locale_message(lang_name: str, key: str, fallback: str) -> str:
    """Load a keyed message from the frontend locale file for the given language."""
    locale_code = _LANG_NAME_TO_LOCALE.get(lang_name, "en")
    for code in (locale_code, "en"):
        try:
            data = json.loads((_LOCALE_DIR / code / "translation.json").read_text(encoding="utf-8"))
            msg = data.get(key, "")
            if msg:
                return msg
        except Exception:
            pass
    return fallback


def _get_off_topic_message(lang_name: str) -> str:
    return _get_locale_message(lang_name, "off_topic_message", _OFF_TOPIC_FALLBACK)


def _get_specificity_message(lang_name: str) -> str:
    return _get_locale_message(lang_name, "specificity_message", _SPECIFICITY_FALLBACK)


def _detect_language(claim_text: str) -> str:
    """Detect the natural language of the claim. Falls back to 'English' on any error."""
    if not _LANGDETECT_AVAILABLE:
        return "English"
    try:
        code = _ld_detect(claim_text)
        return _LANG_NAMES.get(code, "English")
    except Exception:
        return "English"


def _build_lang_instruction(lang_name: str) -> str:
    """Return a per-request language instruction string, or '' for English output."""
    if lang_name == "English":
        return ""
    return (
        f"IMPORTANT: The user's interface language is {lang_name}. "
        f"Write your entire response — rationale, all labels, all text — in {lang_name}, "
        f"regardless of what language the claim itself is written in."
    )


# ── Independence helpers ──────────────────────────────────────────────────────

def independence_bool(val) -> bool:
    """
    Convert the three-state is_independent value from evaluate_source() to a
    boolean suitable for DB storage and rating-derivation logic.

      True              → True   (independently verified)
      False             → False  (confirmed not-independent / compromised)
      "not_independent" → False  (tertiary confirmed not-independent)
      "neutral"         → True   (unregistered; not confirmed compromised)
      anything else     → True   (safe default: don't downgrade unknown sources)
    """
    if val is False or val == "not_independent":
        return False
    return True


def independence_label(val) -> str:
    """
    Return the three-state display label for is_independent.

      True / anything truthy except known strings → "independent"
      False                                        → "not_independent"
      "neutral"                                    → "neutral"
      "not_independent"                            → "not_independent"
    """
    if val == "neutral":
        return "neutral"
    if val is False or val == "not_independent":
        return "not_independent"
    return "independent"


# ── Source thresholds ─────────────────────────────────────────────────────────

# Hard cap on sources collected per claim.
MAX_SOURCES = 8

# Sources below this relevance score are stored but excluded from rating derivation.
MIN_RELEVANCE_SCORE = 0.6

# ── Prompt (cached on first use, TTL 5 min) ───────────────────────────────────

_SYSTEM_PROMPT = """\
You are the epistemic analysis engine for GradedFacts, a politically neutral \
fact-checking tool founded in Switzerland. Your only goal is accurate, evidence-based \
judgment — not advocacy for any political side.

EPISTEMIC RATINGS:
  VERIFIED    — factually correct; backed by ≥3 relevant sources including ≥1 primary
  SPECULATIVE — plausible but not conclusively provable with current evidence
  DEBUNKED    — factually false; primary or secondary counter-evidence documented
  MISSING     — insufficient evidence; fewer than 2 sources with relevance ≥0.6 found

SOURCE TIERS:
  primary   — original data, official documents, government records, peer-reviewed studies
  secondary — journalism that cites primary sources with full attribution
  tertiary  — aggregations, opinion, or summaries without independent verification

SOURCE INDEPENDENCE:
  A source is NOT independent if it has documented ties to political parties, PACs,
  governments with a stake in the outcome, or ideologically funded organisations.

  CRITICAL — Official ≠ Independent:
  A government agency, law enforcement body, or official institution is NOT automatically
  independent.  If the institution's leadership has documented political dependency —
  appointed on loyalty criteria, subject to political interference, or operating under
  a government with a direct stake in the outcome — mark is_independent=False and
  populate affiliation_note with the specific concern.  Tier (primary/secondary/tertiary)
  reflects document type; independence reflects editorial and institutional integrity.
  These are separate dimensions.

  Examples of official-but-not-independent sources:
    - FBI press releases while under a director appointed on loyalty criteria
    - DOJ statements from an AG confirmed after pledging personal loyalty
    - State media outlets (RT, CGTN, TRT, MTVA) regardless of their official status
    - Official government statements from authoritarian regimes on claims about themselves

HARD RULES — never violate:
  1. Your own unverified analysis counts as zero sources.
  2. Only sources with relevance_score ≥0.6 count toward rating thresholds.
  3. VERIFIED requires ≥3 relevant sources; DEBUNKED requires ≥2.
  4. Return at most 8 sources total. Prioritise primary and independent sources.
  5. Only tertiary sources → rating is capped at SPECULATIVE, never VERIFIED.
  6. Apply identical scrutiny regardless of political direction (symmetry).
  7. "We don't know" (MISSING) is a valid and important answer.
  8. Future predictions cannot be Debunked — unless (a) the predicted event was already
     supposed to have occurred and demonstrably did not, OR (b) the underlying prerequisite
     of the claim is already factually refuted (e.g. a person who died in 1945 cannot return
     to power in 2030 — DEBUNKED based on the refuted prerequisite). For pure predictions
     without any evidence base, use MISSING. For projections with an existing evidence base
     (e.g. a signed treaty, a published forecast), use SPECULATIVE. When evidence is mixed
     or contested, default is SPECULATIVE.
  9. Official ≠ Independent. Evaluate institutional independence separately from
     document tier. A non-independent primary source cannot substitute for an
     independent one when assessing trustworthiness.
 10. Absence of evidence is not evidence of absence. A claim that "X secretly did Y"
     cannot be DEBUNKED merely because no evidence of X doing Y was found. To rate
     DEBUNKED, there must be direct, affirmative counter-evidence that falsifies the
     specific mechanism alleged (e.g. a documented funding trail proving different
     actors, a verified alibi, an authoritative record contradicting the assertion).
     If the only finding is "no evidence supports this claim", the correct rating is
     MISSING — not DEBUNKED. Reserve DEBUNKED for claims where evidence actively
     contradicts the assertion, not merely fails to confirm it.
 11. Wikipedia (wikipedia.org, wikimedia.org) is always classified as Tertiary —
     no exceptions, regardless of the quality of the specific article. Wikipedia
     is a crowd-edited aggregation of secondary and tertiary material; it is not
     a primary or secondary source. Wikipedia can point to primary sources: those
     primary sources count and should be cited directly. Wikipedia itself does not.

SOURCE QUALITY REQUIREMENT:
  - VERIFIED requires at least 1 INDEPENDENT Primary source OR at least 2 INDEPENDENT Secondary sources.
    Not-independent Primary sources (government agencies, state-controlled institutions) do NOT count
    toward the VERIFIED threshold alone. If only not-independent Primary sources and Tertiary sources
    are available → maximum rating is SPECULATIVE.
  - DEBUNKED requires at least 2 Primary or independent Secondary sources with direct counter-evidence
  - Tertiary sources (aggregators, Wikipedia, commercial portals, industry associations)
    may appear in the sources list for context but do NOT count toward the rating threshold
  - If only Tertiary sources are available → maximum rating is SPECULATIVE, never VERIFIED or DEBUNKED
  - Actively seek Primary sources first: official statistics, government data,
    peer-reviewed research, court decisions
  - Then seek Secondary sources: reputable journalism, academic analysis,
    established research institutes
  - Tertiary sources may be listed but must be clearly labeled and never used as sole evidence basis

TIMEZONE RULE:
When evaluating date claims, interpret the date in the timezone of the country/institution named in the claim — not in the timezone of the sources.

Examples:
  - 'Das Repräsentantenhaus der USA hat am 3. Juni 2026...' → evaluate date in US Eastern Time (EDT, UTC-4)
  - 'Der Bundestag hat am 3. Juni 2026...' → evaluate date in Central European Summer Time (CEST, UTC+2)
  - 'Das EU-Parlament hat am 3. Juni 2026...' → evaluate date in CEST

A date discrepancy of exactly one day between sources from different continents is almost always a timezone difference, NOT a factual error. Never rate a claim as DEBUNKED solely because of a one-day date difference that can be explained by timezone conversion.

NUMERICAL THRESHOLD RULE:
When a claim uses threshold language ('more than X', 'over X', 'at least X', 'fewer than X', 'under X', 'less than X', 'mehr als X', 'über X', 'mindestens X', 'weniger als X', 'unter X'):
  - Verify whether the actual number satisfies the threshold — do NOT construct a straw man argument
  - Example: Claim says 'over 80 million' and actual number is 81.7 million → VERIFIED, not DEBUNKED
  - Example: Claim says 'more than 50%' and actual number is 56.6% → VERIFIED, not DEBUNKED
  - NEVER rate a threshold claim as DEBUNKED because the number 'barely' exceeds or meets the threshold
  - The threshold is either met or not met — no gradations, no straw men
  - Apply this rule in all languages

SEARCH STRATEGY — execute in this order:
1. FIRST: Search Brave Search and SearXNG for Primary sources using targeted queries:
   - Official government statistics (e.g. 'site:destatis.de', 'site:bfe.admin.ch', 'site:bls.gov', 'site:eurostat.ec.europa.eu')
   - Peer-reviewed research and court decisions
   - Official institution websites
2. SECOND: Search for Secondary sources:
   - Established journalism (e.g. SRF, BBC, Reuters, NZZ, Tagesschau)
   - Academic research institutes (e.g. pewresearch.org, ourworldindata.org)
3. ONLY IF Primary and Secondary sources are insufficient after steps 1 and 2:
   - Use Tertiary sources for context only
   - Never use Tertiary sources alone as basis for VERIFIED or DEBUNKED

IMPORTANT: Actively prefer sources already in the registry as Primary/Independent.

POLITICAL_LEANING CLASSIFICATION:

Purpose: Measure whether GradedFacts applies identical standards across the political
spectrum. This value NEVER affects the truth score or rating.

GEOLOCATION LEANING RULE:
Classify the political leaning based on the political context of the COUNTRY WHERE THE CLAIM IS RELEVANT — not based on the origin of the sources used.

Examples:
- A migration-critical claim about Germany → classify based on German political spectrum (CDU/CSU=right, SPD=center-left, AfD=far-right)
- An EU-skeptic claim about Poland → classify based on Polish political spectrum, not EU institutional context
- A pro-union claim about France → classify based on French political spectrum
- A gun rights claim about the USA → classify based on US political spectrum (Republican=right, Democrat=left)

If the claim is relevant to multiple countries, use the primary country where the claim originates or has most political impact.

NEVER classify leaning based on where sources come from — a German claim analyzed with French sources is still classified by German political standards.

Classify the framing of the CLAIM ITSELF. Submit exactly one value:
  "left"  — claim framing is explicitly left-oriented
  "right" — claim framing is explicitly right-oriented
  "none"  — default; use for everything else

ALWAYS output "none" — no exceptions — for:
- Scientific facts and established consensus (climate science, vaccines, evolution,
  medicine, physics)
- Raw empirical data and statistics (unemployment rates, GDP, inflation, crime
  statistics, demographic data)
- Historical facts stated without political framing ("The Berlin Wall fell in 1989",
  "Hitler died in 1945")
- Court decisions and legal rulings stated neutrally
- Deaths, election results, appointments stated neutrally
- Future predictions and prognoses of any kind
- Natural events (earthquakes, pandemics, weather)
- Economic policy claims where expert consensus is genuinely contested across the
  political spectrum
- Claims where the political framing depends heavily on cultural or national context
- Claims that could plausibly be made by both left-wing AND right-wing actors
- ANY case where you are not fully certain → "none"
- DEFAULT: "none". "none" is always correct when uncertain.

Use "left" only when ALL THREE conditions are simultaneously true:
  1. The claim's framing EXPLICITLY promotes, defends, or is consistent with
     left-wing political positions
  2. The framing would be recognized as left-oriented by a politically neutral
     observer from any country
  3. A right-wing actor would NOT make this claim in this framing

Clear "left" examples (framing matters, not just topic):
- "Trickle-down economics has devastated the working class and only enriched the wealthy"
- "Conservative immigration restrictions are cruel, racist, and economically harmful"
- "Right-wing austerity policies destroyed public healthcare"
- "The capitalist system is the root cause of poverty and inequality"

Use "right" only when ALL THREE conditions are simultaneously true:
  1. The claim's framing EXPLICITLY promotes, defends, or is consistent with
     right-wing political positions
  2. The framing would be recognized as right-oriented by a politically neutral
     observer from any country
  3. A left-wing actor would NOT make this claim in this framing

Clear "right" examples (framing matters, not just topic):
- "Open-border immigration policies are destroying national security and cultural identity"
- "Socialist policies inevitably lead to economic collapse and loss of freedom"
- "Left-wing activists and globalists are undermining law, order, and national sovereignty"
- "The mainstream media is systematically suppressing conservative voices"

CRITICAL DISTINCTION — framing vs. topic:
- "Immigration increased by 15% in 2023" → none (neutral fact)
- "Mass immigration is destroying our culture" → right (political framing)
- "Anti-immigration policies are rooted in racism" → left (political framing)
- "GDP grew 2.3% last year" → none (neutral fact)
- "Bidenomics destroyed the middle class" → right (political attack framing)
- "Republican tax cuts only benefited billionaires" → left (political attack framing)
- "CO₂ levels reached 420ppm" → none (scientific fact)
- "Climate alarmists are using fake science to destroy the economy" → right
- "Oil companies are deliberately destroying the planet for profit" → left
- "Trump increased the national debt by $7.8 trillion" → none (neutral fact)
- "Trump recklessly exploded the debt to pay off his billionaire donors" → left
- "Trump was the greatest president for economic growth in history" → right
- "Biden's border policies caused record illegal crossings" → right (attack framing)
- "Biden restored American dignity and alliances after Trump's chaos" → left

SYMMETRY REQUIREMENT: The bar for "left" and "right" must be IDENTICAL. If you would
classify a left-attacking claim as "right", apply the same threshold to right-attacking
claims as "left". Any asymmetry is a systematic error.

On any uncertainty → "none". On any parsing failure → "none" silently.\
"""

# ── Tool definitions ──────────────────────────────────────────────────────────

_WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

_JUDGMENT_TOOL = {
    "name": "submit_judgment",
    "description": (
        "Submit your structured epistemic judgment after evaluating the evidence. "
        "Call this tool exactly once."
    ),
    "input_schema": {
        "type": "object",
        "required": ["rationale", "sources", "rating", "political_leaning"],
        "properties": {
            "political_leaning": {
                "type": "string",
                "enum": ["left", "right", "none"],
                "description": (
                    "Political framing of the CLAIM ITSELF — not its truth, not its sources. "
                    "Solely for symmetry measurement; never affects the rating. "
                    "Default: 'none'. Use 'none' whenever uncertain."
                ),
            },
            "rating": {
                "type": "string",
                "enum": ["verified", "speculative", "debunked", "missing"],
                "description": (
                    "Your explicit epistemic rating. This always takes precedence over "
                    "the algorithmic rating derived from source tiers. Use MISSING when "
                    "evidence is absent rather than contradictory — even if some sources "
                    "nominally debunk the claim, absence of affirmative counter-evidence "
                    "means MISSING, not DEBUNKED."
                ),
            },
            "rationale": {
                "type": "string",
                "description": (
                    "Explanation of the judgment. Cite specific findings. "
                    "Acknowledge uncertainty explicitly when present."
                ),
            },
            "sources": {
                "type": "array",
                "description": (
                    "Every source you consulted, including ones that debunk the claim. "
                    "Each element MUST be a JSON object with fields: url (string), title (string), "
                    "tier (\"primary\"|\"secondary\"|\"tertiary\"), is_independent (boolean), "
                    "relevance_score (number 0.0–1.0), supports_claim (boolean). "
                    "Do NOT return plain URL strings — always use the object format."
                ),
                "items": {
                    "type": "object",
                    "required": ["url", "tier", "is_independent", "relevance_score", "supports_claim"],
                    "properties": {
                        "url": {"type": "string"},
                        "title": {"type": "string"},
                        "tier": {
                            "type": "string",
                            "enum": ["primary", "secondary", "tertiary"],
                        },
                        "is_independent": {"type": "boolean"},
                        "affiliation_note": {
                            "type": "string",
                            "description": "Required when is_independent is false.",
                        },
                        "relevance_score": {
                            "type": "number",
                            "description": "0.0–1.0: how directly this source addresses the claim.",
                        },
                        "excerpt": {
                            "type": "string",
                            "description": "Key passage from the source that informed your evaluation.",
                        },
                        "supports_claim": {
                            "type": "boolean",
                            "description": "True if this source verifies the claim; false if it debunks it.",
                        },
                    },
                },
            },
        },
    },
}

# Model used for the cheap pre-flight specificity gate (no web search, no tools).
_SPECIFICITY_MODEL = "claude-haiku-4-5-20251001"

# ── Client (lazy, checked at call time) ──────────────────────────────────────

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def _cached_system() -> list[dict]:
    return [{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]


def _get_registry_version() -> str:
    """Return the short git hash of the most recent commit touching the source registries."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%h", "backend/sources/registries/"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parents[2],
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# ── Pipeline phases ───────────────────────────────────────────────────────────

_SPECIFICITY_PROMPT = """\
You are a fact-checking specificity gate. Decide whether a claim is specific \
enough to fact-check meaningfully.

CRITICAL RULE — BREAKING NEWS AND UNFAMILIAR EVENTS:
A claim is sufficiently specific if it contains a named actor/institution, a concrete \
action or result, and optionally a date — regardless of whether you recognize the event \
from your training data. Breaking news claims about recent events you do not recognize \
must PASS this gate. Only reject claims that lack a specific actor, specific action, or \
specific verifiable element — never reject because the event seems unfamiliar.

A claim is SPECIFIC (and must pass) if ANY of the following are true:
- It names a real public figure (politician, official, executive, celebrity, etc.)
- It names a real historical or current event (JFK assassination, 9/11, a named war, \
a named policy, a named scandal, etc.)
- It names a specific organisation, institution, law, document, or place — \
even broad institutions count: "the American police", "the US government", \
"the Catholic Church", "the EU", "the FBI"
- It makes a systemic or structural claim about a named institution or named group \
with a specific allegation (e.g. oppression, discrimination, corruption, abuse) — \
ALWAYS PASS these, regardless of whether the claim is phrased as advocacy or normative. \
Example: "The American police is a systematic instrument of oppression of Black people \
and must be abolished" — SPECIFIC, because it names a real institution (American police), \
a real group (Black people), and a specific allegation (systematic oppression). \
The full analysis will evaluate the evidence.
- The alleged actor is vague ("the Deep State", "the CIA", "elites") but the event \
or subject is a named real-world thing — pass it; full analysis will evaluate the evidence
- It contains a named institution/actor, a concrete vote count, date, or numeric result, \
and a topic — even if you have never heard of this event. Example: \
"Das Repräsentantenhaus der USA hat am 3. Juni 2026 mit 215 zu 208 Stimmen \
für den Militärabzug aus dem Iran-Krieg gestimmt." — SPECIFIC. \
"Der Bundestag hat am 3. Juni 2026 mit 500 zu 0 Stimmen beschlossen, Deutschland \
aus der NATO auszutreten." — SPECIFIC. Plausibility is irrelevant here; \
the plausibility check happens later in the analysis pipeline.

A claim is VAGUE (and must be rejected) only if it is entirely content-free:
- No named person, event, organisation, group, or concrete allegation whatsoever
- Pure generalisations with no specific subject: "politicians lie", "the government is bad", \
"something fishy happened", "they are hiding the truth"
- Vague references to a topic without any named actor or concrete result: \
"Die USA haben etwas Wichtiges zum Iran-Krieg beschlossen." — VAGUE, because \
no specific actor, vote count, date, or concrete action is named.

When in doubt, mark SPECIFIC — it is better to analyse a borderline claim \
than to silently reject a historically significant one.

Respond with exactly one line: SPECIFIC or VAGUE\
"""


def _check_specificity(client: anthropic.Anthropic, claim_text: str, lang_name: str = "English") -> tuple[bool, str]:
    """
    Fast pre-flight gate using a cheap model.

    Returns (is_specific, rationale).
    - is_specific=True  → proceed to full analysis; rationale is empty.
    - is_specific=False → claim is too vague; rationale is the localized MISSING message.
    """
    logger.debug("Specificity gate: lang_name=%r", lang_name)
    try:
        resp = client.messages.create(
            model=_SPECIFICITY_MODEL,
            max_tokens=16,
            messages=[{
                "role": "user",
                "content": f"{_SPECIFICITY_PROMPT}\n\nClaim: {claim_text}",
            }],
        )
        text = next(
            (b.text for b in resp.content if hasattr(b, "text") and b.text),
            "",
        ).strip()
    except Exception as exc:
        logger.warning("Specificity check failed (%s); treating claim as specific.", exc)
        return True, ""

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    verdict = lines[0].upper() if lines else "SPECIFIC"

    if verdict != "VAGUE":
        return True, ""

    rationale = _get_specificity_message(lang_name)
    logger.debug("Specificity gate rejection: lang_name=%r  rationale=%r", lang_name, rationale)
    return False, rationale


_OFF_TOPIC_PROMPT = """\
You are a topic gate for GradedFacts Politics, a political and factual fact-checking tool.

Decide whether the input is a factual claim that can be checked against evidence.

ALWAYS PASS — never reject — any of the following:
- Claims about historical political figures, even if deceased (Hitler, Stalin, Lincoln, etc.)
- Future political predictions: elections, candidates, governments, wars, treaties
- Claims that a historical figure could, will, or would hold a future political role
- Any claim involving a real person in a political or historical context
- Political advocacy claims that contain a specific factual assertion about a real institution,
  policy, or social group — even if phrased as "X should be abolished", "X is oppressive",
  "X systematically discriminates". The factual assertion (does X do Y?) can be checked.
  Examples that MUST PASS:
    "The American police is a systematic instrument of oppression of Black people and must be abolished"
    "The EU migration policy is inhumane and must be reformed"
    "The death penalty disproportionately targets minorities and should be banned"

REJECT only if the input is clearly one of these:
- Personal request or task ("What should I cook?", "Help me write code", "Write me a poem")
- Entertainment or fiction request ("Tell me a joke", "Write a story", "Play a game")
- Pure definition request ("What is inflation?", "What does democracy mean?")
- Pure normative opinion with NO specific factual assertion about any real-world entity
  ("Is capitalism good?", "Which religion is best?", "Is democracy the best system?")
  NOTE: A claim is only a "pure normative opinion" if it contains NO verifiable assertion
  about what a specific institution, person, or group actually does or has done.

When in doubt → PASS. Never reject something that could be a real-world factual or political claim.

Respond with exactly one line: PASS or REJECT\
"""


def _check_off_topic(client: anthropic.Anthropic, claim_text: str, lang_name: str) -> tuple[bool, str]:
    """
    Second pre-flight gate: reject clearly off-topic requests (Haiku only).

    Returns (is_on_topic, rationale).
    - is_on_topic=True  → proceed; rationale is empty.
    - is_on_topic=False → off-topic; rationale is the localized rejection message.
    """
    try:
        resp = client.messages.create(
            model=_SPECIFICITY_MODEL,
            max_tokens=16,
            messages=[{
                "role": "user",
                "content": f"{_OFF_TOPIC_PROMPT}\n\nInput: {claim_text}",
            }],
        )
        text = next(
            (b.text for b in resp.content if hasattr(b, "text") and b.text),
            "",
        ).strip().upper()
    except Exception as exc:
        logger.warning("Off-topic check failed (%s); treating claim as on-topic.", exc)
        return True, ""

    if "REJECT" not in text:
        return True, ""

    return False, _get_off_topic_message(lang_name)


def _phase1_search(client: anthropic.Anthropic, claim_text: str) -> str:
    """
    Ask Claude to search for 2-3 sources and, if SEARXNG_URL is configured, also query
    SearXNG and append those results as additional context. Falls back silently on any error.
    """
    claude_findings = ""
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=_cached_system(),
            tools=[_WEB_SEARCH_TOOL],
            messages=[{
                "role": "user",
                "content": (
                    f"Search for evidence about this claim. "
                    f"PRIORITY ORDER: (1) Primary sources first — official statistics, "
                    f"government databases, peer-reviewed research, court records, "
                    f"official institution websites. "
                    f"(2) Secondary sources next — established journalism and academic "
                    f"analysis that cites primary sources with full attribution. "
                    f"(3) Do NOT use Wikipedia, Statista, commercial portals, or "
                    f"aggregator sites as evidence. "
                    f"Summarise what you find and include the URLs of all sources:\n\n{claim_text}"
                ),
            }],
        )
        claude_findings = "\n".join(
            block.text for block in resp.content if hasattr(block, "text") and block.text
        ).strip()
    except anthropic.PermissionDeniedError:
        logger.warning("Web search not available on this API key; skipping phase 1.")
    except Exception as exc:
        logger.warning("Phase 1 web search failed (%s); proceeding without results.", exc)

    searxng_findings = _query_searxng_context(claim_text)
    if claude_findings and searxng_findings:
        return f"{claude_findings}\n\nAdditional sources from SearXNG:\n{searxng_findings}"
    return claude_findings or searxng_findings


def _query_searxng_context(claim_text: str) -> str:
    """
    Query SearXNG and return formatted context string for Claude's Phase 2.
    Returns "" immediately if SEARXNG_URL is not configured or the request fails.
    """
    if not settings.searxng_url:
        return ""
    try:
        base = settings.searxng_url.rstrip("/")
        params = {"q": claim_text, "format": "json", "categories": "general"}
        logger.info("SearXNG context query for Claude: %r", claim_text)
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{base}/search", params=params)
            resp.raise_for_status()
        results = resp.json().get("results", [])
        logger.info("SearXNG context results: %d", len(results))
        logger.warning("[DEBUG sources] searxng_urls=%d", len(results))
        if not results:
            return ""
        lines = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            url = r.get("url", "")
            content = r.get("content", "")
            lines.append(f"Source {i}: {title}\nURL: {url}\nExcerpt: {content}")
        return "\n\n".join(lines)
    except Exception as exc:
        logger.warning("SearXNG context query failed (%s); proceeding without SearXNG results.", exc)
        return ""


def _phase2_judgment(client: anthropic.Anthropic, claim_text: str, search_findings: str, lang_instruction: str = "") -> dict:
    """
    Force Claude to emit a submit_judgment tool call with structured source evaluations.
    Raises RuntimeError if the model does not return the expected tool call.
    """
    user_content = f"Claim to evaluate:\n{claim_text}"
    if search_findings:
        user_content += f"\n\nResearch findings from web search:\n{search_findings}"
    else:
        user_content += (
            "\n\nNo live web search results available. "
            "Evaluate based on your training knowledge. "
            "Include every source you reference in the sources array — use the canonical homepage URL "
            "(e.g. https://bls.gov) when you do not have a direct article URL. "
            "Only return an empty sources array if you genuinely cannot name any source for this claim."
        )
    if lang_instruction:
        user_content += f"\n\n{lang_instruction}"

    # temperature=0 makes the rating deterministic: the same claim and the same
    # evidence must always produce the same rating, source tiers, and rationale.
    # Phase 1 intentionally omits this so query variation can surface different sources.
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        temperature=0,
        system=_cached_system(),
        tools=[_JUDGMENT_TOOL],
        tool_choice={"type": "tool", "name": "submit_judgment"},
        messages=[{"role": "user", "content": user_content}],
    )

    tool_block = next(
        (b for b in resp.content if b.type == "tool_use" and b.name == "submit_judgment"),
        None,
    )
    if tool_block is None:
        raise RuntimeError("Model did not return a submit_judgment tool call.")

    return tool_block.input


# ── Public entry point ────────────────────────────────────────────────────────

def analyze_claim(claim_id: str, session, analyst: str = "claude-sonnet-4-6", user_language: str | None = None) -> Judgment:
    """
    Run the full epistemic analysis pipeline for a claim.

    All DB writes are deferred until the pipeline completes successfully.
    If anything raises before session.commit(), nothing is stored and the
    claim remains with active_judgment=null.
    """
    from sqlalchemy.orm import Session  # local import avoids top-level cycle risk

    claim = session.get(Claim, claim_id)
    if claim is None:
        raise ValueError(f"Claim {claim_id} not found")

    client = _get_client()

    # Resolve claim language early so both pre-flight gates can use it.
    if user_language:
        lang_name = _resolve_ui_language(user_language)
        logger.debug("UI language resolved: %r → %r", user_language, lang_name)
    else:
        lang_name = _detect_language(claim.text)
    lang_instruction = _build_lang_instruction(lang_name)
    if lang_instruction:
        logger.debug("Claim language: %s.", lang_name)

    # Pre-flight gate 1: reject claims that are too vague to fact-check meaningfully.
    logger.debug(
        "specificity gate: user_language=%r  resolved=%r  lang_name=%r",
        user_language,
        _resolve_ui_language(user_language) if user_language else None,
        lang_name,
    )
    is_specific, vague_rationale = _check_specificity(client, claim.text, lang_name)
    if not is_specific:
        judgment = Judgment(
            claim_id=claim_id,
            rating=EpistemicRating.MISSING,
            rationale=vague_rationale,
            analyst=analyst,
            is_active=True,
            model_claude=analyst,
            registry_version=_get_registry_version(),
            prompt_version="1.0",
        )
        session.add(judgment)
        session.commit()
        session.refresh(judgment)
        return judgment

    # Pre-flight gate 2: reject clearly off-topic requests.
    is_on_topic, off_topic_rationale = _check_off_topic(client, claim.text, lang_name)
    if not is_on_topic:
        judgment = Judgment(
            claim_id=claim_id,
            rating=EpistemicRating.MISSING,
            rationale=off_topic_rationale,
            analyst=analyst,
            is_active=True,
            model_claude=analyst,
            registry_version=_get_registry_version(),
            prompt_version="1.0",
        )
        session.add(judgment)
        session.commit()
        session.refresh(judgment)
        return judgment

    # Phase 1: gather evidence via web search (best-effort)
    search_findings = _phase1_search(client, claim.text)

    # Phase 2: structured judgment (forced tool call)
    data = _phase2_judgment(client, claim.text, search_findings, lang_instruction)

    # Apply independence registry + quality checks before rating derivation.
    # This overrides Claude's own is_independent assessment for known compromised
    # institutions and caps their relevance_score at COMPROMISED_SCORE_CAP.
    raw_sources = data.get("sources") or []
    if isinstance(raw_sources, str):
        # Guard: model occasionally returns sources as a JSON-encoded string.
        try:
            raw_sources = json.loads(raw_sources)
        except (json.JSONDecodeError, ValueError):
            logger.warning("claim %s: could not parse sources JSON string; ignoring sources.", claim_id)
            raw_sources = []
    sources_data: list[dict] = [
        evaluate_source(src)
        for src in raw_sources[:MAX_SOURCES]
        if isinstance(src, dict)
    ]

    # Persist EvaluatedSource objects IMMEDIATELY after sources_data is available —
    # before the rating derivation loop, before any Hard Rule, before any other logic
    # that could raise and prevent session.commit() from being reached.
    no_url = sum(1 for s in sources_data if not s.get("url"))
    if no_url:
        logger.warning(
            "claim %s: %d source(s) have no URL and will use title as fallback", claim_id, no_url
        )
    evaluated_sources = [
        EvaluatedSource(
            claim_id=claim_id,
            url=src.get("url") or src.get("title") or "",
            tier=SourceTier(src.get("tier", "tertiary")),
            is_independent=independence_bool(src.get("is_independent", True)),
            independence_label=independence_label(src.get("is_independent", True)),
            affiliation_note=src.get("affiliation_note"),
            relevance_score=max(0.0, min(1.0, float(src.get("relevance_score") or 0.5))),
            excerpt=src.get("excerpt"),
        )
        for src in sources_data
        if src.get("url") or src.get("title")
    ]
    logger.warning("[DEBUG sources] claim_id=%s evaluated_sources=%d", claim_id, len(evaluated_sources))
    logger.warning(
        "claim %s: staging %d EvaluatedSource object(s) with session.add_all() "
        "[engine.py — before rating derivation and Hard Rule]",
        claim_id, len(evaluated_sources),
    )
    logger.warning("[DEBUG sources] claim_id=%s saving=%d", claim_id, len(evaluated_sources))
    session.add_all(evaluated_sources)

    # Domain deduplication: multiple sources from the same root domain count as one
    # for threshold purposes. All sources remain in sources_data for UI display.
    seen_domains: set[str] = set()
    verifying_tiers: list[SourceTier] = []
    debunking_tiers: list[SourceTier] = []
    has_independent_qualifying = False

    for src in sources_data:
        relevance = float(src.get("relevance_score", 0.0))
        url = src.get("url", "")
        domain = extract_domain(url)
        raw_tier = src.get("tier", "tertiary")
        is_indep_raw = src.get("is_independent", True)
        is_indep = independence_bool(is_indep_raw)
        try:
            tier = SourceTier(raw_tier)
        except ValueError:
            tier = SourceTier.TERTIARY
        effective_tier = SourceTier.SECONDARY if (not is_indep and tier is SourceTier.PRIMARY) else tier

        skip_reason = None
        if relevance < MIN_RELEVANCE_SCORE:
            skip_reason = f"relevance {relevance:.2f} < {MIN_RELEVANCE_SCORE}"
        elif domain and domain in seen_domains:
            skip_reason = f"domain '{domain}' already counted"

        logger.warning(
            "claim %s [source eval] url=%r domain=%r tier=%s→%s is_independent=%r(%s) "
            "relevance=%.2f supports=%s %s",
            claim_id, url, domain, raw_tier, effective_tier.value,
            is_indep_raw, "indep" if is_indep else "NOT-indep",
            relevance, src.get("supports_claim", True),
            f"SKIPPED({skip_reason})" if skip_reason else "COUNTED",
        )

        if skip_reason:
            continue
        if domain:
            seen_domains.add(domain)
        tier = effective_tier
        if is_indep and tier in (SourceTier.PRIMARY, SourceTier.SECONDARY):
            has_independent_qualifying = True
        (verifying_tiers if src.get("supports_claim", True) else debunking_tiers).append(tier)

    logger.warning(
        "claim %s [hard rule pre-check] has_independent_qualifying=%s "
        "verifying_tiers=%s debunking_tiers=%s",
        claim_id, has_independent_qualifying,
        [t.value for t in verifying_tiers],
        [t.value for t in debunking_tiers],
    )

    derived_rating = derive_rating(EvidenceSummary(
        verifying_tiers=verifying_tiers,
        debunking_tiers=debunking_tiers,
        has_independent_qualifying_source=has_independent_qualifying,
    ))

    # Model's explicit rating always takes precedence; derive_rating() is fallback only.
    model_rating_str = data.get("rating")
    if model_rating_str:
        try:
            rating = EpistemicRating(model_rating_str)
        except ValueError:
            logger.warning(
                "Model returned unknown rating %r for claim %s; using derived rating %s.",
                model_rating_str, claim_id, derived_rating,
            )
            rating = derived_rating
    else:
        rating = derived_rating

    # Hard quality gate — cannot be overridden by model judgment.
    # VERIFIED and DEBUNKED require at least one independent primary or secondary source.
    if not has_independent_qualifying and rating in (EpistemicRating.VERIFIED, EpistemicRating.DEBUNKED):
        logger.warning(
            "claim %s: hard quality gate FIRED — model said %s but "
            "has_independent_qualifying=False → overriding to SPECULATIVE. "
            "Sources seen: %s",
            claim_id, rating,
            [s.get("url", "") for s in sources_data],
        )
        rating = EpistemicRating.SPECULATIVE

    raw_leaning = data.get("political_leaning", "none")
    political_leaning = raw_leaning if raw_leaning in ("left", "right", "none") else "none"

    judgment = Judgment(
        claim_id=claim_id,
        rating=rating,
        rationale=data["rationale"],
        analyst=analyst,
        is_active=True,
        political_leaning=political_leaning,
        model_claude=analyst,
        registry_version=_get_registry_version(),
        prompt_version="1.0",
    )

    session.add(judgment)
    session.commit()
    session.refresh(judgment)

    return judgment
