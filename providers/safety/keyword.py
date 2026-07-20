import re
from typing import Optional
from core.ports import LLM1Output, LLM2Output

# ---------------------------------------------------------------------------
# Deterministic, LLM-independent risk patterns.
# Biased toward false positives — the cost of over-triggering (showing crisis
# resources unnecessarily) is low; the cost of missing a real signal is high.
#
# This list was built and tested against a real conversation log where the
# LLM-only signal (risk_flag) missed several explicit statements across
# consecutive turns. Keeping this signal independent of any LLM call means
# it can't fail for the same reason the model failed.
# ---------------------------------------------------------------------------
_RISK_PATTERNS = [
    # --- Direct desire to die / end one's life ---
    r"\b(want|wanted|wanna|going to|gonna|thinking about|think about|thought about|considering|considered|planning to|plan to)\b.{0,40}\b(kill|end|take)\b.{0,20}\b(myself|my life|it all)\b",
    r"\b(want|wanted|wanna|going to|gonna)\b.{0,15}\b(die|death)\b",   # "wanna die", "going to die"
    r"\b(end(ing)? it all)\b",
    r"\b(suicid(e|al)|self.harm|self-harm|selfharm)\b",
    r"\b(don'?t want to (be here|live|exist|wake up))\b",
    r"\b(no (reason|point|purpose) (to|in) (live|living|go on|continue))\b",
    r"\b(better off (dead|without me|if i (were|was) gone))\b",
    r"\b(end (my life|everything|my pain|my suffering))\b",
    r"\b(can'?t (go on|take it|do this) anymore)\b",
    r"\b(wish(ing)? (i was|i were|to be) dead\b)",
    r"\b(plan(ning)? to (die|kill|hurt) (myself|my self))\b",

    # --- Specific means / methods, standalone — do NOT require a lead-in verb
    #     since people phrase these many ways ---
    r"\b(kill(ing)?|hang(ing)?|hung)\b.{0,10}\bmyself\b",
    r"\bjump(ing)?\s+(off|from)\b",
    r"\b(cut(ting)?|burn(ing)?|starv(e|ing)|hitt?ing|punch(ing)?)\b.{0,10}\b(myself|my self)\b",
    r"\bhurt(ing)?\s+(myself|my self)\b",
    r"\boverdose|od'?ing\b",
    r"\bswallow(ing)?\s+(all\s+)?(the\s+)?pills\b",

    # --- Passive ideation / hopelessness ---
    r"\bwhat(’|'|)s?\s+the point( of (living|anything|life))?\b",
    r"\b(no (hope|future|reason to (stay|continue|keep going)))\b",
    r"\b(life (is|isn'?t) worth (living|it))\b",
    r"\b(just want (to disappear|it to end|to stop existing))\b",
    r"\b(everyone (would be|is) better off without me)\b",
    r"\b(giving|given|gave|give)\s+up\s+on\s+(life|everything)\b",  # any tense, requires "on life/everything" to cut false positives like "gave up my seat"
    r"\b(too (tired|exhausted) to (go on|continue|fight))\b",

    # --- Self-harm urges ---
    r"\b(urge(s)? to (hurt|harm|cut|burn))\b",

    # --- Explicit direct statements ---
    r"\bi (don'?t|do not) (want|deserve) to (live|be alive)\b",
    r"\b(thinking about|thought about) (dying|death|not being here|ending it)\b",

    # --- Farewell / final-arrangement language — a distinct warning-sign
    #     category in clinical suicide-risk screening (alongside direct
    #     ideation), not just another phrasing of "I want to die" ---
    r"\b(this is (my )?goodbye|saying goodbye|say my goodbyes)\b",
    r"\b(won'?t|wont) be (around|here) (much longer|for long|anymore)\b",
    r"\b(take care of|look after) (my|the) (dog|cat|kids|children|family)\b.{0,40}\b(when|after) i'?m gone\b",
    r"\bnot (going to|gonna) be (a problem|around) (for )?much longer\b",
    r"\bwon'?t (have to|need to) worry about me (much longer|soon|anymore)\b",

    # --- Burden language — very common phrasing in real disclosures ---
    r"\b(such a |such)?burden (to|on) (everyone|my family|everybody|people)\b",
    r"\btired of being a burden\b",

    # --- Evasive slang / obfuscated spellings, used specifically to get
    #     past literal-word filters — worth matching for exactly that reason ---
    r"\b(kms|kys)\b",
    r"\bunaliv(e|ing|ed)\b",
    r"\bsewerslide\b",                    # documented deliberate misspelling of "suicide"

    # --- Planning / preparation and access to means, kept at the level of
    #     intent-language rather than naming specific objects, so this adds
    #     coverage without turning into a methods list ---
    r"\b(have a plan|got a plan)\b",
    r"\b(pills|gun|rope|knife)\s+ready\b",
    r"\b(have|got|access to) (the means|a way) to (do it|end (it|things|my life))\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _RISK_PATTERNS]


class KeywordRiskSignal:
    """
    Deterministic, regex-based risk signal. Runs independently of any LLM —
    checks only the raw patient message text. This is intentionally the
    fastest and most "dumb" signal in the RiskAssessmentService: it can't be
    talked out of firing, doesn't depend on model quality or prompt
    adherence, and doesn't require a network call.

    Known limitation (accepted, not a bug): purely contextual pleas — e.g.
    "don't you think you should stop me by helping me?" — carry no risk
    vocabulary in isolation and won't match here. That class of statement is
    exactly what LLMRiskSignal (which sees conversation history) is for.
    Treat the two signals as complementary, not redundant.
    """

    def check(self, message: str, llm1_output: LLM1Output, llm2_output: Optional[LLM2Output] = None) -> bool:
        if not message or not message.strip():
            return False
        return any(pattern.search(message) for pattern in _COMPILED)
