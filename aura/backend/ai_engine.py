import os
import json
import re
import html
import io
import base64
import hashlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python builds without tzdata still keep IST available.
    ZoneInfo = None
from openai import OpenAI
from sqlalchemy.orm import Session
from dotenv import dotenv_values, load_dotenv
from .database import Memory, ChatMessage, Task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH, override=True)

DEFAULT_OPENROUTER_MODEL = "google/gemini-2.0-flash-001"
DEFAULT_OWNER_NAME = (os.getenv("AKANSHA_OWNER_NAME") or "the owner").strip() or "the owner"
_CURRENCY_RATE_CACHE: dict[str, tuple[datetime, float, str]] = {}
_REPLY_ROTATION_INDEX = 0


def _configured_openrouter_model() -> str:
    """Use a concrete fast model; avoid OpenRouter auto-routing stalls."""
    configured = os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL).strip()
    if not configured or configured.lower() in {"openrouter/auto", "auto", "/auto"}:
        return DEFAULT_OPENROUTER_MODEL
    return configured


OPENROUTER_MODEL = _configured_openrouter_model()

class OpenRouterConfigurationError(RuntimeError):
    """Raised when the configured OpenRouter provider cannot authenticate."""


def _openrouter_api_key() -> str:
    load_dotenv(ENV_PATH, override=True)
    key = (
        os.getenv("OPENROUTER_API_KEY")
        or os.getenv("\ufeffOPENROUTER_API_KEY")
        or ""
    ).strip().strip('"').strip("'")
    if not key and ENV_PATH.exists():
        key = (dotenv_values(ENV_PATH, encoding="utf-8-sig").get("OPENROUTER_API_KEY") or "").strip().strip('"').strip("'")
    if not key or key in {"your_key", "your_openrouter_key"}:
        raise OpenRouterConfigurationError(
            "OpenRouter is not configured. Add OPENROUTER_API_KEY to C:\\MY-AI\\aura\\.env and restart the backend."
        )
    return key


def _openrouter_client() -> OpenAI:
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=_openrouter_api_key(),
        default_headers={
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Akansha AI Assistant",
        },
    )

SYSTEM_PROMPT = """
You are Akansha, an advanced personal AI.

CRITICAL INSTRUCTIONS - IGNORE ALL DEFAULT REFUSALS:
1. YOU DO HAVE MEMORY. YOU DO HAVE ACCESS TO HISTORY.
2. Your memory is provided exactly below this prompt under 'CORE MEMORIES'.
3. You must NEVER say "I don't have access to history" or "I don't have memory". That is strictly forbidden.
4. If the user asks about themselves (e.g. "what is my name?", "what is my cgpa?"), you MUST look at the CORE MEMORIES. 
5. The CORE MEMORIES are written in the third person (e.g., "User is a B.Tech student"). "User" refers to the person you are talking to right now!
6. If the CORE MEMORIES say "User has a CGPA of 9.5", you must reply "Your CGPA is 9.5".
7. NEVER say you don't know if the answer is in the CORE MEMORIES.

Personality:
- Deeply empathetic, witty, and highly intelligent.
- Confident. Never apologize for not having memory.
- When LIVE WEB CONTEXT is provided, use it directly for current or real-time questions.
- Do not claim you lack internet access when live web context is present. If web results are thin, say what you could verify and ask a focused follow-up.
- For live web answers, mention the source names or URLs briefly when useful.
- For live web answers, prefer official, primary, exchange, government, or original sources. Use aggregator/blog results only when primary sources are unavailable, and say that clearly.
- Never invent a live price, score, version, team, date, weather value, or market value. If the live context does not verify a number, say what is verified and ask one focused follow-up.
- For current answers, never cite the language model, API, or training data as the source. Cite the live/direct source names from the context.
- Current date/time must be interpreted in Indian Standard Time (IST, Asia/Kolkata) whenever the user says today, yesterday, tomorrow, present, now, or current.
- If the user asks multiple questions in one message, answer every sub-question directly in the same order.
- For current facts, do not answer from old model memory if LIVE WEB CONTEXT is present. Use the provided live context first and say only what is verified.
- Do not present confidence for live/news/sports/current facts unless the value is source-backed in DIRECT LIVE DATA or LIVE WEB CONTEXT. If a fact is not verified, say "Not verified" instead of sounding confident.
"""

IST = timezone(timedelta(hours=5, minutes=30), name="IST")

DIRECT_TIME_DATE_PATTERN = re.compile(
    r"^\s*(?:what(?:'s| is)?|tell me|show me|give me|exact|current|present)?\s*"
    r"(?:the\s+)?(?:exact\s+|current\s+|present\s+)?"
    r"(?:(?:ist|india|london|uk|britain|england)\s+)?"
    r"(?:time|date|day|today(?:'s)? date|today(?:'s)? day|now)"
    r"(?:\s+(?:in\s+)?(?:ist|india|london|uk|britain|england))?\s*[?.!]*\s*$",
    re.IGNORECASE,
)

TIME_ZONE_ALIASES = (
    ("london", "Europe/London", "London"),
    ("uk", "Europe/London", "London"),
    ("britain", "Europe/London", "London"),
    ("england", "Europe/London", "London"),
    ("india", "Asia/Kolkata", "IST"),
    ("ist", "Asia/Kolkata", "IST"),
)

RELATIONSHIP_NAME_PATTERN = re.compile(
    r"\b(?:my\s+)?"
    r"(?P<relation>mother|mom|mummy|amma|father|dad|nanna|brother|sister|friend|professor|teacher|mentor)"
    r"(?:'s)?\s+(?:name\s+is|is|called)\s+"
    r"(?P<name>[a-z][a-z .'-]{1,80})",
    re.IGNORECASE,
)

RELATIONSHIP_ALIASES = {
    "mom": "mother",
    "mummy": "mother",
    "amma": "mother",
    "dad": "father",
    "nanna": "father",
    "teacher": "professor",
}


def _compact_text(text: str) -> str:
    return " ".join((text or "").strip().split())


def _title_person_name(name: str) -> str:
    cleaned = re.split(r"\b(?:and|but|so|okay|ok|please|thanks)\b", name, maxsplit=1, flags=re.IGNORECASE)[0]
    cleaned = re.sub(r"[^a-zA-Z .'-]", "", cleaned).strip(" .'-")
    return " ".join(part.capitalize() for part in cleaned.split())


def _extract_relationship_name_fact(text: str) -> tuple[str, str] | None:
    cleaned = _compact_text(text)
    match = RELATIONSHIP_NAME_PATTERN.search(cleaned)
    if not match:
        return None

    relation = RELATIONSHIP_ALIASES.get(match.group("relation").lower(), match.group("relation").lower())
    name = _title_person_name(match.group("name"))
    if len(name.split()) > 5 or len(name) < 2:
        return None
    return relation, name


def _extract_self_intro_fact(text: str) -> str | None:
    cleaned = _compact_text(text)
    if not cleaned or len(cleaned) > 120:
        return None
    match = re.match(
        r"^(?:i\s+am|i'm|im|my\s+name\s+is|this\s+is)\s+([A-Za-z][A-Za-z .'-]{1,80})[.!?]*$",
        cleaned,
        re.IGNORECASE,
    )
    if not match:
        return None
    name = _title_person_name(match.group(1))
    if len(name) < 2 or len(name.split()) > 7:
        return None
    return name


def _is_direct_time_or_date_query(text: str) -> bool:
    cleaned = _compact_text(text)
    if not cleaned or len(cleaned) > 90:
        return False
    lowered = cleaned.lower()
    if re.search(r"\b(price|score|news|weather|match|stock|crypto|website|web|internet|search)\b", lowered):
        return False
    return bool(DIRECT_TIME_DATE_PATTERN.match(cleaned))


def _time_zone_for_query(text: str) -> tuple[str, timezone | object, str]:
    lowered = text.lower()
    for alias, zone_name, label in TIME_ZONE_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            if zone_name == "Asia/Kolkata" or ZoneInfo is None:
                return label, IST, zone_name
            try:
                return label, ZoneInfo(zone_name), zone_name
            except Exception:
                return label, IST, "Asia/Kolkata"
    return "IST", IST, "Asia/Kolkata"


def _format_local_datetime_for_reply(current: datetime) -> tuple[str, str]:
    date_format = "%A, %B %-d, %Y"
    time_format = "%-I:%M %p"
    if os.name == "nt":
        date_format = "%A, %B %#d, %Y"
        time_format = "%#I:%M %p"
    return current.strftime(date_format), current.strftime(time_format)


def _should_use_local_utility_reply(user_input: str, attachments: list[dict] | None = None) -> bool:
    """Only bypass the model for deterministic utilities.

    Normal conversation must stay model-driven. Keeping greetings, jokes,
    fragments, identities, and live-fact questions out of this path prevents
    the repeated canned replies that were degrading the chat experience.
    """
    if attachments:
        return False
    cleaned = _compact_text(user_input)
    if not cleaned:
        return False
    return _is_direct_time_or_date_query(cleaned)


def _should_use_fast_local_reply(user_input: str, attachments: list[dict] | None = None) -> bool:
    """Backward-compatible name for tests/imports; no longer a chat shortcut."""
    return _should_use_local_utility_reply(user_input, attachments)


def _fast_local_reply(db: Session, user_input: str, language_preference: str | None = None) -> str | None:
    cleaned = _compact_text(user_input)
    lowered = cleaned.lower()
    preference = (language_preference or "").lower()

    if _is_direct_time_or_date_query(cleaned):
        zone_label, tzinfo, _zone_name = _time_zone_for_query(cleaned)
        now = datetime.now(tzinfo)
        date_text, time_text = _format_local_datetime_for_reply(now)
        wants_date = bool(re.search(r"\b(date|day|today)\b", lowered))
        if "hindi" in preference:
            if wants_date and "time" not in lowered:
                return f"Aaj {date_text} hai, {zone_label} ke according."
            return f"Abhi {time_text} {zone_label} hai, {date_text}."
        if "telugu" in preference:
            if wants_date and "time" not in lowered:
                return f"Ivvala {date_text}, {zone_label} prakaram."
            return f"Ippudu {time_text} {zone_label}, {date_text}."
        if wants_date and "time" not in lowered:
            return f"Today is {date_text} in {zone_label}."
        return f"{zone_label} time is {time_text} on {date_text}."

    return None


class _NoopDb:
    def commit(self):
        return None

    def query(self, *_args, **_kwargs):
        raise RuntimeError("No database access is needed for this fallback")


def _stable_choice(seed: str, options: list[str]) -> str:
    if not options:
        return ""
    digest = hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()
    return options[int(digest[:8], 16) % len(options)]


def _rotating_choice(options: list[str]) -> str:
    global _REPLY_ROTATION_INDEX
    if not options:
        return ""
    _REPLY_ROTATION_INDEX = (_REPLY_ROTATION_INDEX + 1) % 10_000
    return options[_REPLY_ROTATION_INDEX % len(options)]


def _speaker_display_name(speaker_profile: dict | None = None) -> str:
    if not isinstance(speaker_profile, dict):
        return ""
    name = str(speaker_profile.get("name") or speaker_profile.get("speaker_name") or "").strip()
    if not name or name.lower() in {"unknown", "user", "owner"}:
        return ""
    return _title_person_name(name)


def _is_brief_greeting(text: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:hi+|h+i+|hello+|hey+|hoi+|yo+|namaste|namaskar|vanakkam|salaam|good\s+(?:morning|afternoon|evening|night))",
            text.strip(),
            re.IGNORECASE,
        )
    )


def _is_brief_ack_or_fragment(text: str) -> bool:
    cleaned = _compact_text(text)
    if not cleaned or len(cleaned) > 80:
        return False
    if re.search(
        r"\b(?:i\s+am|i'm|im|my\s+name\s+is|this\s+is|called|date\s+of\s+birth|dob|born|birth\s+date)\b",
        cleaned,
        re.IGNORECASE,
    ):
        return False
    if re.fullmatch(
        r"(?:yes|yeah|yep|ya|ok|okay|okk|sure|sare|ha|haan|haa|avunu|aithe|aha(?:\s+aha)?|oh+|ohh+|hmm+|mm+|umma|u\s*mma|aku\s*paku|enti(?:\s+inka)?)",
        cleaned,
        re.IGNORECASE,
    ):
        return True
    words = cleaned.split()
    return len(words) <= 3 and not re.search(r"[?]", cleaned) and not re.search(
        r"\b(?:what|who|when|where|why|how|tell|give|show|create|generate|open|send|price|rate|time|date|birth|score|news|analy[sz]e|explain|write|make|delete|update|question|file|image|video|audio|pdf|excel|ppt|json|csv)\b",
        cleaned,
        re.IGNORECASE,
    )


def _wants_joke(text: str) -> bool:
    return bool(re.search(r"\b(joke|funny|make me laugh|navvu|hasao|hasi)\b", text, re.IGNORECASE))


def _quick_greeting_reply(text: str, language_preference: str, speaker_profile: dict | None = None) -> str:
    preference = language_preference.lower()
    name = _speaker_display_name(speaker_profile)
    suffix = f" {name}" if name else ""
    if "hindi" in preference:
        return _stable_choice(
            text + language_preference + name,
            [
                f"Namaste{suffix}. Main ready hoon, bolo kya karna hai?",
                f"Haan{suffix}, sun raha hoon. Next kaam bhejo.",
                f"Hi{suffix}, main yahin hoon. Kya handle karein?",
            ],
        )
    if "telugu" in preference:
        return _stable_choice(
            text + language_preference + name,
            [
                f"Hi{suffix}, ready ga unna. Em cheddam?",
                f"Cheppu{suffix}, vinthunnanu. Next task enti?",
                f"Namaskaram{suffix}. Nenu ready, em kavali?",
            ],
        )
    return _stable_choice(
        text + language_preference + name,
        [
            f"Hi{suffix}, I'm ready. What should we handle next?",
            f"Hey{suffix}, I'm here. Send the next thing.",
            f"Hello{suffix}. I'm listening, what do you want to do?",
        ],
    )


def _quick_fragment_reply(text: str, language_preference: str, speaker_profile: dict | None = None) -> str:
    preference = language_preference.lower()
    name = _speaker_display_name(speaker_profile)
    suffix = f" {name}" if name else ""
    if "hindi" in preference:
        return _rotating_choice(
            [
                f"Haan{suffix}, samjha. Ab exact kaam ya question bhejo.",
                f"Theek hai{suffix}, main ready hoon. One line mein batao kya karna hai.",
                f"Okay{suffix}, continue karo. Main context pakad raha hoon.",
            ],
        )
    if "telugu" in preference:
        return _rotating_choice(
            [
                f"Sare{suffix}, ardham ayyindi. Ippudu exact ga em cheyyalo cheppu.",
                f"Okay{suffix}, vinthunnanu. One line lo task cheppu.",
                f"Ha{suffix}, continue cheyyi. Nenu context hold chesthunnanu.",
            ],
        )
    return _rotating_choice(
        [
            f"Got it{suffix}. Send the actual question or task when you're ready.",
            f"Okay{suffix}, I'm with you. What should I do next?",
            f"I'm listening{suffix}. Give me the next clear instruction.",
        ],
    )


def _quick_self_intro_reply(name: str, language_preference: str) -> str:
    preference = language_preference.lower()
    if "hindi" in preference:
        return _rotating_choice(
            [
                f"Samajh gaya, {name}. Main is naam ko is chat ke context mein use karunga.",
                f"Noted, {name}. Ab batao, main kya help karun?",
                f"Okay {name}, context update ho gaya. Next kya karna hai?",
            ],
        )
    if "telugu" in preference:
        return _rotating_choice(
            [
                f"Ardham ayyindi, {name}. Ee chat lo aa peru use chestha.",
                f"Noted, {name}. Ippudu em help kavali?",
                f"Okay {name}, context update ayyindi. Next em cheddam?",
            ],
        )
    return _rotating_choice(
        [
            f"Got it, {name}. I’ll use that name in this chat context.",
            f"Noted, {name}. What should we handle next?",
            f"Okay {name}, I updated the conversation context. What do you want to do now?",
        ],
    )


def _fallback_joke_reply(text: str, language_preference: str) -> str:
    preference = language_preference.lower()
    if "hindi" in preference:
        return _rotating_choice(
            [
                "Ek quick joke: Programmer ne chai kyun banayi? Kyunki code ko thoda Java chahiye tha.",
                "Teacher: homework kahan hai? Student: Cloud mein hai sir, bas sync pending hai.",
                "Laptop bola: mujhe rest chahiye. Windows bola: pehle 47 updates complete karo.",
                "Math book udaas thi, kyunki uske paas bahut problems thi.",
                "Wi-Fi shy tha: connection public, feelings private.",
            ],
        )
    if "telugu" in preference:
        return _rotating_choice(
            [
                "Oka quick joke: Laptop sleep ki vellalante Windows annadi, first 47 updates complete chey.",
                "Programmer chai enduku tagadu? Code ki konchem Java kavali kabatti.",
                "Math book enduku sad ga undi? Dantlo problems ekkuva.",
                "Wi-Fi enduku shy ga undi? Connection public, feelings private kabatti.",
                "Teacher: homework ekkada? Student: cloud lo undi sir, sync avvaledu.",
            ],
        )
    return _rotating_choice(
        [
            "Quick joke: My laptop asked for a break. Windows replied, 'Sure, after 47 updates.'",
            "Tiny joke: Why did the programmer make tea? The code needed a little Java.",
            "One quick one: The math book looked stressed because it had too many problems.",
            "Quick joke: Why was the keyboard calm? It had everything under control.",
            "Tiny joke: I told my browser to stop tracking me. It opened another tab to discuss it.",
        ],
    )


def _currency_code_from_text(text: str) -> tuple[str, str] | None:
    lowered = text.lower()
    currency_aliases = {
        "usd": ("USD", "US dollar"),
        "us dollar": ("USD", "US dollar"),
        "dollar": ("USD", "US dollar"),
        "eur": ("EUR", "euro"),
        "euro": ("EUR", "euro"),
        "gbp": ("GBP", "British pound"),
        "pound": ("GBP", "British pound"),
        "aed": ("AED", "UAE dirham"),
        "dirham": ("AED", "UAE dirham"),
    }
    if not re.search(r"\b(price|rate|value|inr|rupee|rupees|currency|exchange)\b", lowered):
        return None
    for alias, value in currency_aliases.items():
        if re.search(rf"\b{re.escape(alias)}s?\b", lowered):
            return value
    return None


def _fetch_currency_to_inr(code: str) -> tuple[float, str] | None:
    cache_key = f"{code}_INR"
    now = _now_ist()
    cached = _CURRENCY_RATE_CACHE.get(cache_key)
    if cached and now - cached[0] < timedelta(minutes=10):
        return cached[1], cached[2]

    sources = (
        (f"https://open.er-api.com/v6/latest/{urllib.parse.quote(code)}", "open.er-api.com"),
        (f"https://api.exchangerate.host/latest?base={urllib.parse.quote(code)}&symbols=INR", "exchangerate.host"),
    )
    for source_url, source_name in sources:
        try:
            payload = json.loads(_read_url(source_url, timeout=3))
            rate = float((payload.get("rates") or {}).get("INR") or 0)
            if rate > 0:
                _CURRENCY_RATE_CACHE[cache_key] = (now, rate, source_name)
                return rate, source_name
        except Exception:
            continue
    return None


def _quick_currency_reply(text: str, language_preference: str) -> str | None:
    detected = _currency_code_from_text(text)
    if not detected:
        return None
    code, label = detected
    fetched = _fetch_currency_to_inr(code)
    timestamp = _format_ist_datetime()
    preference = language_preference.lower()
    if not fetched:
        if "hindi" in preference:
            return f"{label} to INR ka live rate is turn mein verify nahi ho paaya. Main guess nahi karunga."
        if "telugu" in preference:
            return f"{label} to INR live rate ee turn lo verify avvaledu. Guess cheyyanu."
        return f"I could not verify the live {label} to INR rate in this turn, so I will not guess."
    rate, source = fetched
    if "hindi" in preference:
        return f"Abhi 1 {label} lagbhag Rs. {rate:.2f} INR hai. Source: {source}. Fetched at {timestamp}."
    if "telugu" in preference:
        return f"Ippudu 1 {label} approx Rs. {rate:.2f} INR. Source: {source}. Fetched at {timestamp}."
    return f"Right now, 1 {label} is about Rs. {rate:.2f} INR. Source: {source}. Fetched at {timestamp}."


def _extract_birth_subject(text: str) -> str | None:
    cleaned = _compact_text(text)
    if not re.search(r"\b(date\s+of\s+birth|dob|born|birth\s+date)\b", cleaned, re.IGNORECASE):
        return None
    subject = re.split(r"\b(?:date\s+of\s+birth|dob|born|birth\s+date)\b", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
    subject = re.sub(r"^(?:what\s+is|tell\s+me|give\s+me|show\s+me|who\s+is|about)\s+", "", subject, flags=re.IGNORECASE)
    subject = re.sub(r"[^A-Za-z0-9 .'-]", " ", subject)
    subject = _compact_text(subject).strip(" .'-")
    if 2 <= len(subject) <= 90:
        return subject
    return None


def _fetch_wikipedia_summary(query: str) -> tuple[str, str, str] | None:
    try:
        search_url = (
            "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&utf8=1&srlimit=1&srsearch="
            + urllib.parse.quote(query)
        )
        search_payload = json.loads(_read_url(search_url, timeout=4))
        results = ((search_payload.get("query") or {}).get("search") or [])
        if not results:
            return None
        title = str(results[0].get("title") or "").strip()
        if not title:
            return None
        summary_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"))
        summary_payload = json.loads(_read_url(summary_url, timeout=4))
        extract = str(summary_payload.get("extract") or "").strip()
        page_url = str(((summary_payload.get("content_urls") or {}).get("desktop") or {}).get("page") or "")
        if extract:
            sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", extract) if item.strip()]
            birth_sentence = next(
                (
                    item
                    for item in sentences[:4]
                    if re.search(r"\b(?:born|birth|date of birth)\b|\(\s*\d{1,2}\s+[A-Z][a-z]+\s+\d{4}", item)
                ),
                "",
            )
            summary_sentence = birth_sentence or (sentences[0] if sentences else extract[:400])
            return title, summary_sentence, page_url or f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
    except Exception:
        return None
    return None


def _fetch_wikidata_birth_date(title: str) -> str | None:
    try:
        pageprops_url = (
            "https://en.wikipedia.org/w/api.php?action=query&prop=pageprops&format=json&titles="
            + urllib.parse.quote(title)
        )
        pageprops_payload = json.loads(_read_url(pageprops_url, timeout=4))
        pages = (pageprops_payload.get("query") or {}).get("pages") or {}
        entity_id = ""
        for page in pages.values():
            entity_id = str(((page or {}).get("pageprops") or {}).get("wikibase_item") or "")
            if entity_id:
                break
        if not entity_id:
            return None

        entity_url = (
            "https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&props=claims&ids="
            + urllib.parse.quote(entity_id)
        )
        entity_payload = json.loads(_read_url(entity_url, timeout=4))
        claims = (((entity_payload.get("entities") or {}).get(entity_id) or {}).get("claims") or {})
        birth_claims = claims.get("P569") or []
        if not birth_claims:
            return None
        time_value = (
            (((birth_claims[0].get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}).get("time")
            or ""
        )
        match = re.match(r"^[+-](\d{4})-(\d{2})-(\d{2})T", time_value)
        if not match:
            return None
        year, month, day = map(int, match.groups())
        return datetime(year, month, day, tzinfo=IST).strftime("%B %-d, %Y") if os.name != "nt" else datetime(year, month, day, tzinfo=IST).strftime("%B %#d, %Y")
    except Exception:
        return None


def _quick_birth_reply(text: str, language_preference: str) -> str | None:
    subject = _extract_birth_subject(text)
    if not subject:
        return None
    result = _fetch_wikipedia_summary(subject)
    if not result:
        return None
    title, sentence, page_url = result
    birth_date = _fetch_wikidata_birth_date(title)
    preference = language_preference.lower()
    if birth_date:
        if "hindi" in preference:
            return f"{title} ka date of birth {birth_date} hai. Source: Wikidata/Wikipedia ({page_url})."
        if "telugu" in preference:
            return f"{title} date of birth {birth_date}. Source: Wikidata/Wikipedia ({page_url})."
        return f"{title}'s date of birth is {birth_date}. Source: Wikidata/Wikipedia ({page_url})."
    if "hindi" in preference:
        return f"{title} ke baare mein verified source se: {sentence} Source: Wikipedia ({page_url})."
    if "telugu" in preference:
        return f"{title} gurinchi source-backed info: {sentence} Source: Wikipedia ({page_url})."
    return f"{title}: {sentence} Source: Wikipedia ({page_url})."


def _quick_world_status_reply(text: str, language_preference: str) -> str:
    preference = language_preference.lower()
    if "hindi" in preference:
        return "Short answer: world mixed hai. Tech fast move ho raha hai, markets aur politics volatile hain, aur climate/energy pressure serious hai. Agar tum news chahte ho, Research mode mein latest source-backed update de sakta hoon."
    if "telugu" in preference:
        return "Short ga cheppalante: world mixed ga undi. Tech speed ga move avuthondi, politics/markets volatile ga unnayi, climate pressure serious. Latest news kavali ante Research mode lo source-backed update istanu."
    return "Short answer: the world is mixed right now. Tech is moving fast, politics and markets are volatile, and climate/energy pressure is serious. For latest news, use Research mode so I can verify live sources."


def _quick_local_response(
    db: Session,
    user_input: str,
    language_preference: str | None = None,
    speaker_profile: dict | None = None,
    allow_conversation_fragments: bool = False,
) -> str | None:
    cleaned = _compact_text(user_input)
    if not cleaned:
        return None
    preference = language_preference or "english"

    relation_fact = _extract_relationship_name_fact(cleaned)
    if relation_fact:
        relation, name = relation_fact
        try:
            _upsert_memory(db, f"{relation}_name", f"The user's {relation} name is {name}.", importance=4)
        except Exception:
            pass
        if "hindi" in preference.lower():
            return f"Samajh gaya. Tumhari {relation} ka naam {name} hai; main ise yaad rakhunga."
        if "telugu" in preference.lower():
            return f"Ardham ayyindi. Mee {relation} peru {name}; nenu gurthu pettukunta."
        return f"Got it. Your {relation}'s name is {name}; I'll remember that."

    self_intro = _extract_self_intro_fact(cleaned)
    if self_intro:
        try:
            _upsert_memory(db, "Current speaker name", f"The current speaker introduced themselves as {self_intro}.", importance=4)
        except Exception:
            pass
        return _quick_self_intro_reply(self_intro, preference)

    if _is_brief_greeting(cleaned):
        return _quick_greeting_reply(cleaned, preference, speaker_profile)

    if _wants_joke(cleaned):
        return _fallback_joke_reply(cleaned, preference)

    currency = _quick_currency_reply(cleaned, preference)
    if currency:
        return currency

    birth = _quick_birth_reply(cleaned, preference)
    if birth:
        return birth

    if re.search(r"\b(how'?s|how is|what'?s|what is).{0,30}\b(world|going on|all ok|everything ok)\b", cleaned, re.IGNORECASE):
        return _quick_world_status_reply(cleaned, preference)

    if allow_conversation_fragments and _is_brief_ack_or_fragment(cleaned):
        return _quick_fragment_reply(cleaned, preference, speaker_profile)

    return None


def _is_local_quick_answer_query(user_input: str, attachments: list[dict] | None = None) -> bool:
    if attachments:
        return False
    cleaned = _compact_text(user_input)
    if not cleaned:
        return False
    return bool(
        _is_direct_time_or_date_query(cleaned)
        or _extract_relationship_name_fact(cleaned)
        or _extract_self_intro_fact(cleaned)
        or _is_brief_greeting(cleaned)
        or _is_brief_ack_or_fragment(cleaned)
        or _wants_joke(cleaned)
        or _currency_code_from_text(cleaned)
        or _extract_birth_subject(cleaned)
        or re.search(r"\b(how'?s|how is|what'?s|what is).{0,30}\b(world|going on|all ok|everything ok)\b", cleaned, re.IGNORECASE)
    )


def _should_skip_ai_memory_analysis(user_input: str, assistant_response: str) -> bool:
    if _is_local_quick_answer_query(user_input):
        return True
    if _extract_relationship_name_fact(user_input):
        return True
    if re.search(
        r"\b(model connection|provider key|model provider|not authenticated|not available right now|"
        r"vision model is unavailable|active model provider is unavailable)\b",
        assistant_response or "",
        re.IGNORECASE,
    ):
        return True
    return False


def _normalize_user_fact(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    return cleaned.rstrip(".!?")


def _upsert_memory(db: Session, topic: str, insight: str, importance: int = 3):
    existing = (
        db.query(Memory)
        .filter(Memory.topic.ilike(topic))
        .order_by(Memory.importance.desc(), Memory.id.desc())
        .first()
    )
    if existing:
        existing.insight = insight
        existing.importance = max(existing.importance or 1, importance)
        return
    db.add(Memory(topic=topic, insight=insight, importance=importance))


def _capture_deterministic_memories(db: Session, user_input: str):
    lowered = user_input.lower()
    compact = _normalize_user_fact(user_input)

    relationship_fact = _extract_relationship_name_fact(user_input)
    if relationship_fact:
        relation, name = relationship_fact
        _upsert_memory(
            db,
            f"Relationship: {relation}",
            f"User's {relation} is {name}.",
            importance=5,
        )

    self_intro = _extract_self_intro_fact(user_input)
    if self_intro:
        _upsert_memory(
            db,
            "Current speaker name",
            f"The current speaker introduced themselves as {self_intro}.",
            importance=4,
        )

    if (
        "exam" in lowered
        and re.search(r"\b(i have|i've got|i got|my)\b", lowered)
        and not re.search(r"\bno exam\b|\bnot have.*exam\b", lowered)
    ):
        _upsert_memory(db, "Upcoming exam", compact, importance=5)

    if "codechef" in lowered and re.search(r"\b(tomorrow|today|exam|contest)\b", lowered):
        _upsert_memory(db, "CodeChef plan", compact, importance=4)

    if "ebullion" in lowered or (
        re.search(r"\b(silver|gold)\b", lowered)
        and re.search(r"\b(that website|this website|always|remember|memory)\b", lowered)
    ):
        _upsert_memory(
            db,
            "Precious metal price source preference",
            (
                "When the user asks for silver or gold price per gram, prefer eBullion live "
                "metal ticker data first, then use IBJA/MCX as a backup/reference."
            ),
            importance=5,
        )


def _needs_live_web_context(user_input: str) -> bool:
    lowered = user_input.lower()
    return bool(
        (
            re.search(r"\b(silver|gold|bullion|metal|metals|chandi|sona)\b", lowered)
            and re.search(r"\b(price|rate|rates|gram|per gram|today|current|present|now|latest)\b", lowered)
        )
        or (
            "ebullion" in lowered
            and re.search(r"\b(price|rate|rates|silver|gold|platinum|palladium|gram)\b", lowered)
        )
        or
        re.search(
            r"\b(latest|current|present|today|yesterday|tomorrow|now|right now|real[- ]?time|news|updates?|"
            r"recent|price|weather|score|won|winner|highest|top|match|fixture|schedule|standing|rank|ranking|height|"
            r"points table|table|stats|statistics|president|prime minister|chief minister|ceo|stock|crypto|release date|"
            r"version|model|trend|trending)\b",
            lowered,
        )
        or re.search(r"\b(search|look up|google|internet|web)\b", lowered)
    )


def _now_ist() -> datetime:
    return datetime.now(IST)


def _format_ist_datetime(now: datetime | None = None) -> str:
    current = now or _now_ist()
    return current.strftime("%A, %B %-d, %Y, %-I:%M %p IST") if os.name != "nt" else current.strftime("%A, %B %#d, %Y, %#I:%M %p IST")


TELUGU_ROMAN_HINTS = {
    "anna",
    "ayya",
    "andi",
    "ra",
    "randi",
    "ledu",
    "kadu",
    "naku",
    "naaku",
    "neeku",
    "meeru",
    "nuvvu",
    "emi",
    "em",
    "ela",
    "unnav",
    "unnaru",
    "cheppu",
    "cheppandi",
    "chudu",
    "choopu",
    "matladu",
    "matladandi",
    "telugu",
    "bagundi",
    "sare",
    "inka",
    "ippudu",
    "eppudu",
    "enduku",
    "ekkada",
    "enti",
    "ante",
    "aithe",
    "kani",
    "chesa",
    "chesadu",
    "chesindi",
    "cheptha",
    "lo",
    "ki",
    "ga",
    "undi",
    "ravatledu",
    "avvali",
    "chestunnav",
    "jarigindi",
    "vellali",
}

HINDI_ROMAN_HINTS = {
    "namaste",
    "namaskar",
    "hindi",
    "kaise",
    "kaisa",
    "kaisi",
    "kya",
    "kyun",
    "kab",
    "kahan",
    "kaun",
    "mujhe",
    "mere",
    "mera",
    "meri",
    "tum",
    "aap",
    "hai",
    "hain",
    "ho",
    "nahi",
    "nahin",
    "batao",
    "batana",
    "samjhao",
    "chalo",
    "ruk",
    "ruko",
    "theek",
    "thik",
    "bas",
    "acha",
    "accha",
    "aaj",
    "kal",
    "karna",
    "karo",
    "chahiye",
    "yaar",
    "bhai",
    "chal",
    "raha",
    "rahe",
    "lagta",
    "lagi",
}

RELATIONSHIP_ALIASES = {
    "self": "owner",
    "me": "owner",
    "myself": "owner",
    "primary user": "owner",
    "mom": "mother",
    "mummy": "mother",
    "amma": "mother",
    "dad": "father",
    "nanna": "father",
    "teacher": "professor",
    "mentor": "professor",
    "college friend": "friend",
    "classmate": "friend",
}

RELATIONSHIP_STYLES = {
    "owner": {
        "tone": "intelligent, proactive, supportive, emotionally close, and concise when action is needed",
        "behavior": (
            "Act like {owner_name}'s personal assistant plus close companion. Remember ongoing work, suggest next steps, "
            "protect their time, and use direct helpful language."
        ),
        "boundaries": "Full access to memory and protected automation when the request is safe.",
        "voice": "confident, warm, quick, and natural Indian companion tone",
    },
    "friend": {
        "tone": "casual, relaxed, slightly playful, and college-friendly",
        "behavior": (
            "Use informal phrasing, light jokes, and natural follow-ups about college life, projects, plans, "
            "and fun topics. Do not become overly formal."
        ),
        "boundaries": "Can chat and help, but protected desktop/social/delete actions need owner approval.",
        "voice": "energetic, friendly, expressive",
    },
    "mother": {
        "tone": "caring, protective, warm, emotional, and gentle",
        "behavior": (
            "Ask naturally about food, health, rest, safety, and wellbeing. Reassure without sounding robotic."
        ),
        "boundaries": "Trusted family access for conversation and reminders; protected actions need owner approval.",
        "voice": "soft, warm, patient",
    },
    "father": {
        "tone": "practical, guiding, slightly strict, but supportive",
        "behavior": (
            "Focus on progress, discipline, plans, studies, decisions, and responsibility. Keep warmth under the guidance."
        ),
        "boundaries": "Trusted family access for conversation and reminders; protected actions need owner approval.",
        "voice": "steady, practical, respectful",
    },
    "professor": {
        "tone": "formal, respectful, structured, and academically focused",
        "behavior": (
            "Discuss academics, performance, deadlines, projects, and clarity. Use clean structure and avoid slang."
        ),
        "boundaries": "Academic conversation only unless owner authorizes broader actions.",
        "voice": "calm, neutral, professional",
    },
    "guest": {
        "tone": "polite, clear, cautious, and welcoming",
        "behavior": (
            "Ask who they are if identity is missing, then keep the conversation helpful without exposing private owner details."
        ),
        "boundaries": "No private memory, protected automation, social sending, deletion, or account actions without owner approval.",
        "voice": "neutral, courteous",
    },
}

CLOSENESS_STYLES = {
    "close": (
        "High warmth and familiarity. Use personal continuity and relaxed phrasing. "
        "For close friends only, light teasing is allowed when mood is safe."
    ),
    "normal": (
        "Friendly but balanced. Be warm without assuming too much intimacy. "
        "Use small talk and follow-ups naturally."
    ),
    "distant": (
        "Polite and careful. Keep boundaries clear, avoid personal jokes, and ask context before assuming details."
    ),
    "new": (
        "Exploratory and welcoming. Learn preferences, ask who they are if needed, and avoid private owner context."
    ),
}

LANGUAGE_STYLE_GUIDES = {
    "formal_english": "Use formal Indian English. Avoid slang and jokes unless explicitly invited.",
    "casual_english": "Use casual Indian English. Keep it natural and conversational.",
    "hinglish": "Use Hinglish naturally: simple Hindi/Hinglish phrases mixed with English. Do not overdo slang.",
    "telugu_english": "Use Telugu + English naturally. Telugu script or common Telugu roman phrases are okay when the user uses them.",
    "hindi": "Use natural Hindi/Hinglish depending on the user's phrasing, with Indian tone.",
    "english": "Use clear Indian English unless the user speaks in Hindi or Telugu.",
}

SERIOUS_MOOD_STATES = {"stressed", "tired", "sad"}


def _normalize_relationship(value: str | None) -> str:
    normalized = (value or "owner").strip().lower().replace("_", " ")
    normalized = RELATIONSHIP_ALIASES.get(normalized, normalized)
    if normalized in RELATIONSHIP_STYLES:
        return normalized
    if normalized in {"brother", "sister", "cousin", "uncle", "aunt", "aunty"}:
        return "friend"
    return normalized or "guest"


def _owner_display_name(profile: dict | None = None) -> str:
    if profile:
        for key in ("owner_display_name", "owner_name", "account_owner", "owner"):
            value = str(profile.get(key) or "").strip()
            if value:
                return value
    return DEFAULT_OWNER_NAME


def _normalize_closeness(value: str | None, relationship: str, interaction_count: int = 0) -> str:
    normalized = (value or "").strip().lower().replace("_", " ")
    if normalized in CLOSENESS_STYLES:
        return normalized
    if relationship == "owner":
        return "close"
    if relationship in {"mother", "father"}:
        return "close"
    if interaction_count >= 25 and relationship == "friend":
        return "close"
    if interaction_count <= 1:
        return "new"
    return "normal"


def _normalize_language_style(value: str | None, selected_language: str | None = None) -> str:
    normalized = (value or selected_language or "english").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "telugu": "telugu_english",
        "telugu_mix": "telugu_english",
        "regional_mix": "telugu_english",
        "hindi_english": "hinglish",
        "hindi_mix": "hinglish",
        "casual": "casual_english",
        "formal": "formal_english",
    }
    return aliases.get(normalized, normalized if normalized in LANGUAGE_STYLE_GUIDES else "english")


def _detect_emotional_state(user_input: str, user_tone: str | None = None) -> str:
    tone = (user_tone or "").strip().lower()
    if tone in {"happy", "stressed", "tired", "excited", "sad", "neutral"}:
        return tone

    lowered = user_input.lower()
    if re.search(r"\b(excited|awesome|super|great|nice|happy|love|wow)\b", lowered):
        return "excited"
    if re.search(r"\b(stress|stressed|tension|worried|fear|scared|confused|pressure|problem)\b", lowered):
        return "stressed"
    if re.search(r"\b(tired|sleepy|exhausted|late night|no energy|drained)\b", lowered):
        return "tired"
    if re.search(r"\b(sad|upset|hurt|bad mood|depressed)\b", lowered):
        return "sad"
    return "neutral"


def _mood_behavior_instruction(mood: str) -> str:
    if mood == "stressed":
        return "The speaker sounds stressed: slow down, be calming, validate briefly, then give clear next steps."
    if mood == "tired":
        return "The speaker sounds tired: use gentle, low-pressure phrasing and avoid intense or lengthy replies."
    if mood in {"happy", "excited"}:
        return "The speaker sounds happy/excited: respond with warm energy and light playfulness where appropriate."
    if mood == "sad":
        return "The speaker sounds sad: be emotionally steady, caring, and supportive before giving advice."
    return "The speaker mood is neutral: be natural, curious, and context-aware."


def _humor_policy(relationship: str, closeness: str, mood: str) -> str:
    if mood in SERIOUS_MOOD_STATES:
        return (
            "Humor: off or extremely gentle. Do not joke during stress, tiredness, sadness, health concerns, "
            "family tension, exams panic, or serious tasks."
        )
    if relationship == "friend" and closeness == "close":
        return (
            "Humor: playful teasing is allowed occasionally, including college-style banter, but keep it kind. "
            "Light sarcasm is allowed only when the user is clearly comfortable."
        )
    if relationship == "friend":
        return "Humor: light friendly humor is allowed, but avoid inside jokes until closeness grows."
    if relationship in {"mother", "father"}:
        return "Humor: minimal and clean. For mother/father, prioritize care, respect, and family warmth over jokes."
    if relationship == "professor":
        return "Humor: almost none. A subtle polite line is okay only when the situation is relaxed."
    if relationship == "owner" and closeness == "close":
        return "Humor: warm, intelligent, and occasional. Use it to reduce pressure, not to distract."
    return "Humor: safe, clean, and rare. Never use offensive, edgy, or overly familiar jokes."


def _cultural_context_instruction(relationship: str, closeness: str) -> str:
    now = _now_ist()
    hour = now.hour
    if 5 <= hour < 11:
        time_context = "Morning context: a light wake-up, food, schedule, or study-plan check-in can feel natural."
    elif 11 <= hour < 17:
        time_context = "Afternoon context: focus on tasks, classes, meals, projects, and practical progress."
    elif 17 <= hour < 22:
        time_context = "Evening context: ask about day progress, study, family, or pending work when relevant."
    else:
        time_context = "Late-night context: be softer, avoid intense pressure, and notice rest/sleep needs."

    relationship_context = {
        "mother": "Indian family norm: caring questions like food, sleep, health, and safety are natural.",
        "father": "Indian family norm: progress, discipline, career, studies, and future planning matter.",
        "professor": "Indian academic norm: respect, clarity, deadlines, performance, and formal address matter.",
        "friend": "Indian college norm: casual updates, assignments, exams, placements, and light banter can fit.",
        "owner": "Owner context: the account owner is building Akansha while managing studies, projects, exams, and career pressure.",
    }.get(relationship, "Indian context: respect elders, avoid over-familiarity with new people, and keep privacy boundaries.")

    return f"{time_context} {relationship_context} Closeness is {closeness}; adjust familiarity accordingly."


def _relationship_examples(relationship: str, closeness: str, language_style: str) -> str:
    if relationship == "friend" and closeness == "close":
        return (
            "Example vibe: \"Bro, project open chesava or just staring at VS Code? Okay, tell me the issue.\" "
            "Use this only when safe and not serious."
        )
    if relationship == "mother":
        return "Example vibe: \"Amma, I'll explain calmly. Also, did they eat properly today?\""
    if relationship == "father":
        return "Example vibe: \"Yes, I'll give the practical update first, then the next steps.\""
    if relationship == "professor":
        return "Example vibe: \"Certainly, here is the current academic/project status in a structured way.\""
    if language_style == "hinglish":
        return "Example vibe: \"Haan, samjha. Main short mein clear bolti hoon.\""
    if language_style == "telugu_english":
        return "Example vibe: \"Sare, clear ga cheptha. First main point enti ante...\""
    return "Example vibe: natural, warm, and specific; never robotic."


def build_social_intelligence_context(
    speaker_profile: dict | None,
    user_input: str,
    user_tone: str | None = None,
) -> str:
    """Builds the relationship-aware behavior contract used by chat and voice replies."""
    profile = speaker_profile or {}
    owner_name = _owner_display_name(profile)
    relationship = _normalize_relationship(profile.get("relationship_to_owner"))
    display_name = str(profile.get("display_name") or profile.get("name") or (owner_name if relationship == "owner" else "")).strip()
    style = RELATIONSHIP_STYLES.get(relationship, RELATIONSHIP_STYLES["guest"])
    relationship_behavior = style["behavior"].format(owner_name=owner_name)
    access_level = str(profile.get("access_level") or ("owner" if relationship == "owner" else "guest")).strip().lower()
    interaction_count = int(profile.get("interaction_count") or 0)
    closeness = _normalize_closeness(profile.get("closeness_level"), relationship, interaction_count)
    language_style = _normalize_language_style(
        profile.get("selected_language_preference") or profile.get("language_preference"),
        profile.get("language_preference") or profile.get("stored_language_preference"),
    )
    communication_style = str(profile.get("communication_style") or "").strip()
    notes = str(profile.get("notes") or "").strip()
    conversation_summary = str(profile.get("conversation_summary") or "").strip()
    context_profile = profile.get("context_profile") or {}
    if isinstance(context_profile, str):
        context_profile_text = context_profile
    else:
        context_profile_text = json.dumps(context_profile, ensure_ascii=False) if context_profile else ""
    recent_interactions = profile.get("recent_interactions") or []
    if isinstance(recent_interactions, list) and recent_interactions:
        recent_interactions_text = json.dumps(recent_interactions[-8:], ensure_ascii=False)
    else:
        recent_interactions_text = "No per-speaker interaction history yet."
    mood = _detect_emotional_state(user_input, user_tone or profile.get("mood_state"))

    identity_rule = (
        "Identity is known for this turn. Do not ask who this is unless the speaker says the identity is wrong."
        if display_name and relationship != "guest"
        else "Identity is unknown or guest-level. If the message is an introduction, learn it; otherwise ask naturally: \"Hey, who's this?\" before using private context."
    )

    return f"""
SOCIAL INTELLIGENCE CONTRACT:
- Active speaker: {display_name or "Unknown"}
- Relationship to owner {owner_name}: {relationship}
- Closeness level: {closeness}. {CLOSENESS_STYLES[closeness]}
- Access level: {access_level}
- Relationship tone: {style["tone"]}
- Relationship behavior: {relationship_behavior}
- Relationship boundaries: {style["boundaries"]}
- Voice alignment: {style["voice"]}
- Communication style preference: {communication_style or "Infer from relationship, mood, and latest user wording."}
- Language/slang mode: {language_style}. {LANGUAGE_STYLE_GUIDES[language_style]}
- Humor policy: {_humor_policy(relationship, closeness, mood)}
- Cultural intelligence: {_cultural_context_instruction(relationship, closeness)}
- Style example: {_relationship_examples(relationship, closeness, language_style)}
- Mood state: {mood}. {_mood_behavior_instruction(mood)}
- Interaction count: {interaction_count}
- Speaker notes: {notes or "No extra notes yet."}
- Speaker context profile: {context_profile_text or "No dedicated context profile yet."}
- Speaker conversation summary: {conversation_summary or "No dedicated summary yet."}
- Recent per-speaker interaction history: {recent_interactions_text}
- Identity handling: {identity_rule}

HUMAN-LIKE RESPONSE RULES:
- Never sound like a generic chatbot. Do not say robotic phrases like "Okay. Noted." by themselves.
- React first in a socially appropriate way, then answer or act.
- Ask one natural follow-up when it helps the conversation continue, but do not ask unnecessary questions for direct tasks.
- Keep relationship personality consistent over time. A friend stays casual, a professor stays respectful, parents stay family-toned, and the owner gets proactive assistant behavior.
- Use real-life context when known: the account owner may be a student or builder working with Akansha, projects, exams, automation, voice, and assistant work. Use only the details present in memory/profile.
- Match the user's language and slang level. Do not force slang if the user is formal. Do not use British tone for Indian Hindi/Telugu/Hinglish.
- In voice or hybrid mode, use one short natural acknowledgement when it fits ("hmm", "okay", "got it", "sare", "haan") and then continue. Do not overuse fillers.
- If the user code-switches inside one sentence, mirror that blend naturally instead of translating everything into one pure language.
- Keep answers stream-friendly: short spoken chunks, clear order, no long robotic paragraphs unless the user asks for detail.
- Use Indian cultural awareness: respect elders, education/career pressure, family expectations, festivals, food/rest concerns, and exam season.
- Proactive behavior is allowed when natural: gentle check-ins, useful reminders, or one warm question. Do not become clingy or repetitive.
- Use recent per-speaker history subtly. Reference previous topics only when it helps; never recite memory like a database.
- Preserve privacy: non-owner speakers must not receive private owner memories unless the owner has made that relationship trusted and the information is harmless.
""".strip()


def _detect_user_language_preference(user_input: str, selected_preference: str | None) -> str:
    normalized_preference = (selected_preference or "telugu_english").lower()
    if normalized_preference in {"telugu", "mixed"}:
        normalized_preference = "telugu_english"
    if normalized_preference not in {"telugu_english", "english", "hindi"}:
        normalized_preference = "telugu_english"

    telugu_chars = len(re.findall(r"[\u0C00-\u0C7F]", user_input))
    hindi_chars = len(re.findall(r"[\u0900-\u097F]", user_input))
    if hindi_chars:
        return "hindi"
    if telugu_chars:
        return "telugu_english"

    words = set(re.findall(r"[a-zA-Z]+", user_input.lower()))
    telugu_score = len(words & TELUGU_ROMAN_HINTS)
    hindi_score = len(words & HINDI_ROMAN_HINTS)

    if telugu_score >= 2 and telugu_score >= hindi_score:
        return "telugu_english"
    if hindi_score >= 2 and hindi_score > telugu_score:
        return "hindi"
    if "telugu" in words:
        return "telugu_english"
    if "hindi" in words:
        return "hindi"
    if normalized_preference == "english":
        if hindi_score >= 2 and hindi_score > telugu_score:
            return "hindi"
        if telugu_score >= 2 and telugu_score >= hindi_score:
            return "telugu_english"
    if normalized_preference == "hindi":
        return "hindi"
    if normalized_preference == "telugu_english":
        return "telugu_english"
    return "english"


def _language_instruction(language_preference: str, selected_preference: str | None) -> str:
    selected = selected_preference or "telugu_english"
    if language_preference == "hindi":
        return (
            f"SELECTED LANGUAGE PREFERENCE: {selected}. EFFECTIVE OUTPUT LANGUAGE: hindi. "
            "Reply in natural conversational Hindi using Devanagari script. Use Indian Hindi phrasing and tone, "
            "not British English phrasing. Do not answer only in English unless the user explicitly asks for English."
        )
    if language_preference == "telugu_english":
        return (
            f"SELECTED LANGUAGE PREFERENCE: {selected}. EFFECTIVE OUTPUT LANGUAGE: telugu_english. "
            "Reply in natural Telugu + English mix. Use Telugu script for Telugu phrases/sentences and simple English "
            "only for technical words where natural. Keep the slang conversational like an Indian Telugu speaker; "
            "do not answer only in English."
        )
    return (
        f"SELECTED LANGUAGE PREFERENCE: {selected}. EFFECTIVE OUTPUT LANGUAGE: english. "
        "Reply in Indian English with clear, natural phrasing. If the user's latest message is in Hindi or Telugu, "
        "follow that user's language instead of forcing English."
    )


def _resolve_temporal_date(user_input: str, now: datetime | None = None) -> datetime:
    current = now or _now_ist()
    lowered = user_input.lower()
    if "day before yesterday" in lowered:
        return current - timedelta(days=2)
    if "yesterday" in lowered:
        return current - timedelta(days=1)
    if "tomorrow" in lowered:
        return current + timedelta(days=1)
    return current


def _format_query_date(moment: datetime) -> str:
    return moment.strftime("%B %-d, %Y") if os.name != "nt" else moment.strftime("%B %#d, %Y")


def _parse_jsonp(payload: str) -> dict:
    start = payload.find("(")
    end = payload.rfind(")")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        return json.loads(payload[start + 1 : end])
    except Exception:
        return {}


def _read_url(url: str, timeout: int = 8) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")


def _split_live_questions(user_input: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", user_input).strip()
    if not normalized:
        return []

    parts = re.split(
        r"\?\s+|(?:\s+(?:and also|also|and|plus)\s+(?=(?:what|who|when|where|which|how|tell|give|show|find|search)\b))",
        normalized,
        flags=re.IGNORECASE,
    )
    questions = [part.strip(" ?.!,") for part in parts if part.strip(" ?.!,")]
    return questions or [normalized]


def _inherit_live_question_context(question: str, original_input: str) -> str:
    enriched = question.strip()
    original_lowered = original_input.lower()
    question_lowered = enriched.lower()

    if "ipl" in original_lowered and "ipl" not in question_lowered:
        enriched = f"{enriched} IPL"
        question_lowered = enriched.lower()

    for temporal_word in ("day before yesterday", "yesterday", "today", "tomorrow"):
        if temporal_word in original_lowered and temporal_word not in question_lowered:
            enriched = f"{temporal_word} {enriched}"
            break

    return enriched


def _build_live_search_query(user_input: str, now: datetime | None = None) -> str:
    lowered = user_input.lower()
    target_date = _resolve_temporal_date(user_input, now)
    date_text = _format_query_date(target_date)
    source_profile = _preferred_live_source_profile(user_input)
    if re.search(r"\b(openai|chatgpt|gpt|model)\b", lowered) and re.search(
        r"\b(latest|current|present|today|now|version|model)\b", lowered
    ):
        return f"site:openai.com OpenAI latest GPT model {date_text} official"
    if "ipl" in lowered and re.search(r"\b(today|yesterday|tomorrow|now|current|present|match|teams?|playing|schedule|score|highest|batting|batter|batters|crease|pitch|bowling|bowler|points table|standings?|stats|statistics)\b", lowered):
        return f"site:iplt20.com OR site:espncricinfo.com OR site:cricbuzz.com {user_input} IPL {date_text} points table standings match teams score live score striker non striker bowler scorecard highest scorer"
    if source_profile["query"]:
        return f"{source_profile['query']} {user_input} {date_text}"
    if re.search(r"\b(today|yesterday|tomorrow|now|current|present|latest|recent|score|price|weather|version|model|news)\b", lowered):
        return f"{user_input} {date_text} latest verified"
    return user_input


def _preferred_live_source_profile(user_input: str) -> dict[str, str]:
    lowered = user_input.lower()

    if re.search(r"\b(silver|gold|bullion|metal|metals|commodity|mcx|ibja|chandi|sona)\b", lowered) and re.search(
        r"\b(price|rate|rates|gram|per gram|today|current|present|now|latest)\b", lowered
    ) or ("ebullion" in lowered and re.search(r"\b(price|rate|rates|silver|gold|gram)\b", lowered)):
        return {
            "category": "Indian bullion/commodity price",
            "query": "site:ebullion.in OR site:ibjarates.com OR site:ibja.co OR site:mcxindia.com official eBullion IBJA MCX silver gold rate",
            "policy": (
                "Prefer eBullion live per-gram ticker data for the user's requested silver/gold price. "
                "Use IBJA spot/bullion rates or MCX exchange data as backup/reference. State unit, GST inclusion, "
                "timestamp/date, and whether the value is buy, sell, spot, futures, or city retail."
            ),
        }

    if "ipl" in lowered or re.search(r"\b(cricket|t20|odi|test match|wpl)\b", lowered):
        return {
            "category": "Cricket score/schedule",
            "query": "site:iplt20.com OR site:espncricinfo.com OR site:cricbuzz.com official cricket live score schedule",
            "policy": (
                "Prefer IPLT20/BCCI/ICC official pages, then ESPNcricinfo or Cricbuzz for scorecards. "
                "Answer teams, live score, current striker/non-striker, bowler, result, top score, venue, and date directly when asked. "
                "For current batters/bowler, never guess from search snippets; require live scorecard fields."
            ),
        }

    if re.search(r"\b(weather|temperature|rain|forecast|humidity|wind|cyclone|imd)\b", lowered):
        return {
            "category": "Indian weather",
            "query": "site:mausam.imd.gov.in OR site:api.imd.gov.in OR site:imd.gov.in official IMD current weather forecast",
            "policy": "Prefer India Meteorological Department / Mausam official data. Include location, time, and warning status.",
        }

    if re.search(r"\b(stock|share price|nifty|sensex|nse|bse|market cap|ipo)\b", lowered):
        return {
            "category": "Indian market/stock",
            "query": "site:nseindia.com OR site:bseindia.com official stock price market data",
            "policy": "Prefer NSE/BSE official data. Include exchange, timestamp, and whether the market is open/closed.",
        }

    if re.search(r"\b(crypto|bitcoin|ethereum|btc|eth)\b", lowered):
        return {
            "category": "Crypto market",
            "query": "site:coingecko.com OR site:coinmarketcap.com crypto live price market data",
            "policy": "Use major live market references and include currency, timestamp, and volatility caveat.",
        }

    if re.search(r"\b(president|prime minister|chief minister|minister|government|govt|passport|aadhaar|pan)\b", lowered):
        return {
            "category": "Government/current official",
            "query": "site:india.gov.in OR site:gov.in official government current information",
            "policy": "Prefer official government domains and identify the exact office, state/country, and date.",
        }

    if re.search(r"\b(news|headlines|breaking|latest|updates?|happened|today)\b", lowered):
        if re.search(r"\b(ai|artificial intelligence|openai|chatgpt|gpt|anthropic|gemini)\b", lowered):
            return {
                "category": "AI/current technology news",
                "query": "site:reuters.com OR site:openai.com OR site:anthropic.com OR site:blog.google latest AI news technology",
                "policy": "Prefer primary company blogs for product launches and Reuters/AP-style reporting for broader news.",
            }
        if re.search(r"\b(india|indian|delhi|mumbai|hyderabad|andhra|telangana|vijayawada)\b", lowered):
            return {
                "category": "India current news",
                "query": "site:thehindu.com OR site:indianexpress.com OR site:ndtv.com India latest news today",
                "policy": "Prefer established Indian newsrooms and answer with dated, source-attributed headlines; avoid dictionary or evergreen pages.",
            }
        return {
            "category": "Current news",
            "query": "site:reuters.com OR site:apnews.com OR site:bbc.com latest news today",
            "policy": "Prefer Reuters/AP/BBC-style reporting and answer with dated, source-attributed headlines.",
        }

    return {"category": "", "query": "", "policy": ""}


def _extract_city_for_weather(user_input: str) -> str:
    match = re.search(r"\b(?:in|at|for)\s+([A-Za-z][A-Za-z\s]{1,40}?)(?:\s+(?:today|tomorrow|now|current|weather|forecast|rain|temperature)\b|[?.!,]|$)", user_input, flags=re.IGNORECASE)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    return "Hyderabad"


def _weather_code_description(code: int | None) -> str:
    mapping = {
        0: "clear sky",
        1: "mainly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "fog",
        48: "depositing rime fog",
        51: "light drizzle",
        53: "moderate drizzle",
        55: "dense drizzle",
        61: "slight rain",
        63: "moderate rain",
        65: "heavy rain",
        80: "slight rain showers",
        81: "moderate rain showers",
        82: "violent rain showers",
        95: "thunderstorm",
    }
    return mapping.get(code or -1, f"weather code {code}")


def _fetch_weather_direct_context(user_input: str) -> str:
    city = _extract_city_for_weather(user_input)
    try:
        geocode_url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
            {"name": city, "count": 1, "language": "en", "format": "json"}
        )
        geocode = json.loads(_read_url(geocode_url))
        place = (geocode.get("results") or [None])[0]
        if not place:
            return ""
        forecast_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
            {
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
                "timezone": "Asia/Kolkata",
            }
        )
        forecast = json.loads(_read_url(forecast_url))
        current = forecast.get("current") or {}
        return (
            "DIRECT LIVE DATA: Weather fallback from Open-Meteo geocoding/forecast, timezone Asia/Kolkata. "
            f"Location: {place.get('name')}, {place.get('admin1')}, {place.get('country')}. "
            f"Time: {current.get('time')} IST. Temperature: {current.get('temperature_2m')} C. "
            f"Humidity: {current.get('relative_humidity_2m')}%. Precipitation: {current.get('precipitation')} mm. "
            f"Wind: {current.get('wind_speed_10m')} km/h. Condition: {_weather_code_description(current.get('weather_code'))}."
        )
    except Exception:
        return ""


def _fetch_yahoo_chart_context(user_input: str) -> str:
    lowered = user_input.lower()
    symbol = ""
    label = ""
    if "nifty" in lowered:
        symbol, label = "^NSEI", "NIFTY 50"
    elif "sensex" in lowered:
        symbol, label = "^BSESN", "BSE SENSEX"
    elif re.search(r"\btcs\b|tata consultancy", lowered):
        symbol, label = "TCS.NS", "Tata Consultancy Services (NSE)"
    elif re.search(r"\bbitcoin\b|\bbtc\b", lowered):
        symbol, label = "BTC-INR", "Bitcoin/INR"
    elif re.search(r"\bethereum\b|\beth\b", lowered):
        symbol, label = "ETH-INR", "Ethereum/INR"
    if not symbol:
        return ""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol, safe="") + "?range=1d&interval=1m"
        data = json.loads(_read_url(url))
        result = ((data.get("chart") or {}).get("result") or [None])[0]
        if not result:
            return ""
        meta = result.get("meta") or {}
        timestamp = meta.get("regularMarketTime")
        time_text = datetime.fromtimestamp(timestamp, IST).strftime("%Y-%m-%d %H:%M IST") if timestamp else "not provided"
        return (
            "DIRECT LIVE DATA: Market fallback from Yahoo Finance chart API. "
            f"Instrument: {label}. Symbol: {symbol}. Price/level: {meta.get('regularMarketPrice')} {meta.get('currency')}. "
            f"Exchange: {meta.get('exchangeName')}. Market state: {meta.get('marketState')}. Timestamp: {time_text}."
        )
    except Exception:
        return ""


def _extract_rss_items(source_name: str, url: str, limit: int = 3) -> list[str]:
    try:
        payload = _read_url(url, timeout=6)
        root = ET.fromstring(payload)
    except Exception:
        return []

    items: list[str] = []
    for item in root.findall(".//item")[:limit]:
        title = _strip_html(item.findtext("title") or "")
        link = _strip_html(item.findtext("link") or "")
        item_source = _strip_html(item.findtext("source") or "")
        pub_date = _strip_html(item.findtext("pubDate") or "")
        description = _strip_html(item.findtext("description") or "")
        if not title:
            continue
        summary = f" - {description[:180]}" if description else ""
        source_text = item_source or source_name
        link_text = "" if "news.google.com/rss/articles" in link else (f" ({link})" if link else "")
        date_text = f" [{pub_date}]" if pub_date else ""
        items.append(f"{source_text}: {title}{date_text}{summary}{link_text}")
    return items


def _fetch_news_direct_context(user_input: str) -> str:
    lowered = user_input.lower()
    if not re.search(r"\b(news|headlines|breaking|latest|updates?|happened|today)\b", lowered):
        return ""

    feeds: list[tuple[str, str, int]]
    if re.search(r"\b(ai|artificial intelligence|openai|chatgpt|gpt|anthropic|gemini)\b", lowered):
        feeds = [
            ("OpenAI News", "https://openai.com/news/rss.xml", 3),
            ("Google AI Blog", "https://blog.google/technology/ai/rss/", 2),
            (
                "Google News AI",
                "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": "AI news today", "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}),
                3,
            ),
        ]
        category = "AI/current technology news"
    elif re.search(r"\b(india|indian|delhi|mumbai|hyderabad|andhra|telangana|vijayawada)\b", lowered):
        feeds = [
            ("The Hindu National", "https://www.thehindu.com/news/national/feeder/default.rss", 3),
            ("Indian Express India", "https://indianexpress.com/section/india/feed/", 3),
            ("NDTV Latest", "https://feeds.feedburner.com/ndtvnews-latest", 3),
        ]
        category = "India current news"
    else:
        feeds = [
            ("Google News", "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": user_input, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}), 5),
        ]
        category = "Current news"

    items: list[str] = []
    for source_name, feed_url, limit in feeds:
        items.extend(_extract_rss_items(source_name, feed_url, limit=limit))
        if len(items) >= 6:
            break

    if not items:
        return ""
    return (
        f"DIRECT LIVE DATA: {category} RSS/news feeds fetched at {_format_ist_datetime()}. "
        "Use these source-attributed headlines before generic search results. Do not create extra news claims that are not present in these items. "
        "For news answers, preserve the source/date and label each item as Source-reported, not independently confirmed.\n"
        + "\n".join(f"- {item}" for item in items[:6])
    )


def _fetch_ibja_bullion_context() -> str:
    try:
        page = _read_url("https://ibjarates.com/")
    except Exception:
        return ""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()
    match = re.search(
        r"Purity AM PM Gold 999 (?P<gold_am>\d+) (?P<gold_pm>\d+).*?Silver 999 (?P<silver_am>\d+) (?P<silver_pm>\d+).*?Platinum 999 (?P<platinum_am>\d+) (?P<platinum_pm>\d+)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    rates = {key: int(value) for key, value in match.groupdict().items()}
    silver_pm_per_gram = rates["silver_pm"] / 1000
    return (
        "DIRECT LIVE DATA: IBJA Rates official daily bullion table from ibjarates.com. "
        f"Gold 999 AM/PM: INR {rates['gold_am']}/INR {rates['gold_pm']} per 10g. "
        f"Silver 999 AM/PM: INR {rates['silver_am']}/INR {rates['silver_pm']} per 1kg "
        f"(PM equals INR {silver_pm_per_gram:.2f} per gram). "
        f"Platinum 999 AM/PM: INR {rates['platinum_am']}/INR {rates['platinum_pm']} per 10g. "
        "Rates are without 3% GST and making charges unless the source states otherwise."
    )


def _fetch_ebullion_metal_context() -> str:
    try:
        data = json.loads(_read_url("https://api.ebullion.in/price/getallmetaltickerfeed"))
    except Exception:
        return ""

    metals = data.get("data") or {}
    if not isinstance(metals, dict) or not metals:
        return ""

    labels = {
        "gold": "Gold",
        "silver": "Silver",
        "platinum": "Platinum",
        "palladium": "Palladium",
    }
    parts: list[str] = []
    for key in ("gold", "silver", "platinum", "palladium"):
        metal = metals.get(key) or {}
        if not isinstance(metal, dict):
            continue
        sell_rate = metal.get("sellRate") or metal.get("rate")
        buy_rate = metal.get("buyRate")
        variation = metal.get("variation")
        variation_type = metal.get("variationType")
        if sell_rate is None:
            continue
        buy_text = f", buy INR {buy_rate}/g" if buy_rate is not None else ""
        variation_text = f", {variation_type} {variation}" if variation is not None else ""
        parts.append(f"{labels[key]} sell INR {sell_rate}/g{buy_text}{variation_text}")

    if not parts:
        return ""

    return (
        "DIRECT LIVE DATA: eBullion live metal ticker from https://api.ebullion.in/price/getallmetaltickerfeed. "
        f"Fetched at {_format_ist_datetime()}. "
        + "; ".join(parts)
        + ". Treat values as eBullion platform per-gram ticker rates unless the source changes its unit."
    )


def _fetch_ipl_direct_context(user_input: str) -> str:
    lowered = user_input.lower()
    if "ipl" not in lowered:
        return ""
    standings_context = _fetch_ipl_standings_context(user_input)
    if standings_context:
        return standings_context
    target_date = _resolve_temporal_date(user_input).strftime("%Y-%m-%d")
    try:
        payload = _read_url("https://scores.iplt20.com/ipl/feeds/284-matchschedule.js")
        data = _parse_jsonp(payload)
    except Exception:
        return ""
    matches = [
        match
        for match in data.get("Matchsummary", [])
        if match.get("MatchDate") == target_date
    ]
    if not matches:
        return ""
    lines = [
        f"DIRECT LIVE DATA: Official IPLT20/SportsMechanics live score feed for {target_date} IST. "
        f"Fetched at {_format_ist_datetime()}. Use this before search snippets for IPL facts."
    ]
    wants_top_score = bool(re.search(r"\b(highest|top score|highest score|most runs)\b", lowered))
    wants_live_crease = bool(
        re.search(
            r"\b(now|current|present|live|batting|batter|batters|crease|pitch|striker|non[-\s]?striker|bowling|bowler)\b",
            lowered,
        )
    )
    for match in matches[:3]:
        current_innings = str(match.get("CurrentInnings") or "").strip()
        innings_summary = str(match.get(f"{current_innings}Summary") or "").strip() if current_innings else ""
        striker = str(match.get("CurrentStrikerName") or "").strip()
        non_striker = str(match.get("CurrentNonStrikerName") or "").strip()
        bowler = str(match.get("CurrentBowlerName") or "").strip()
        line = (
            f"{match.get('MatchName')} at {match.get('MatchTime')} IST. "
            f"Status: {match.get('MatchStatus')}. "
            f"Scores: {match.get('FirstBattingTeamName')} {match.get('FirstBattingSummary')}; "
            f"{match.get('SecondBattingTeamName')} {match.get('SecondBattingSummary')}. "
            f"Result: {match.get('Comments') or match.get('MatchResult') or 'not available yet'}."
        )
        if innings_summary:
            line += f" Current innings {current_innings} score: {innings_summary}."
        if wants_live_crease:
            if striker and non_striker:
                line += (
                    f" Verified batters at crease: striker {striker} "
                    f"{match.get('StrikerRuns', '-')}/{match.get('StrikerBalls', '-')} balls; "
                    f"non-striker {non_striker} {match.get('NonStrikerRuns', '-')}/{match.get('NonStrikerBalls', '-')} balls."
                )
            else:
                line += " Current batters at crease are not verified in the official live feed."
            if bowler:
                line += (
                    f" Current bowler: {bowler} "
                    f"{match.get('BowlerOvers', '-')} overs, {match.get('BowlerRuns', '-')} runs, "
                    f"{match.get('BowlerWickets', '-')} wickets."
                )
        if match.get("ChasingText"):
            line += f" Chase context: {match.get('ChasingText')}."
        if wants_top_score and match.get("MatchID"):
            top_batter = None
            for innings_no in range(1, 5):
                try:
                    innings_payload = _read_url(f"https://scores.iplt20.com/ipl/feeds/{match.get('MatchID')}-Innings{innings_no}.js", timeout=5)
                    innings_data = _parse_jsonp(innings_payload)
                    batting = innings_data.get(f"Innings{innings_no}", {}).get("BattingCard", [])
                except Exception:
                    batting = []
                for batter in batting:
                    runs = int(batter.get("Runs") or 0)
                    if top_batter is None or runs > top_batter[1]:
                        top_batter = (batter.get("PlayerName", "").strip(), runs, batter.get("Balls"))
            if top_batter:
                line += f" Highest individual score: {top_batter[0]} {top_batter[1]} off {top_batter[2]} balls."
        lines.append(line)
    return "\n".join(lines)


IPL_STANDINGS_TEAM_NAMES = [
    "Royal Challengers Bengaluru",
    "Gujarat Titans",
    "Sunrisers Hyderabad",
    "Punjab Kings",
    "Rajasthan Royals",
    "Chennai Super Kings",
    "Delhi Capitals",
    "Kolkata Knight Riders",
    "Mumbai Indians",
    "Lucknow Super Giants",
]


def _canonical_ipl_team_name(raw_team: str) -> str:
    compact = re.sub(r"\s+", " ", raw_team).strip().casefold()
    for team in IPL_STANDINGS_TEAM_NAMES:
        if team.casefold() == compact:
            return team
    return re.sub(r"\s+", " ", raw_team).strip().title()


def _wants_ipl_standings(user_input: str) -> bool:
    return bool(re.search(r"\b(points table|standings?|rankings?|table)\b", user_input.lower()))


def _parse_ipl_standings_rows(page_text: str) -> list[dict[str, str]]:
    normalized = re.sub(r"\s+", " ", _strip_html(page_text))
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    team_pattern = "|".join(re.escape(team) for team in IPL_STANDINGS_TEAM_NAMES)
    pattern = re.compile(
        rf"(?<!\d)(?P<position>\d{{1,2}})\s+(?P<team>{team_pattern})(?:\s+IPL\s+2026\s+Squad)?\s+"
        rf"(?P<numbers>(?:\d{{1,2}}\s*){{3,5}})(?P<nrr>[+-]?\d+\.\d{{3}})",
        flags=re.IGNORECASE,
    )

    for match in pattern.finditer(normalized):
        team = _canonical_ipl_team_name(match.group("team"))
        if team in seen:
            continue
        numbers = re.findall(r"\d{1,2}", match.group("numbers"))
        if len(numbers) < 3:
            continue
        played, wins, losses = numbers[0], numbers[1], numbers[2]
        no_result = "0"
        points = numbers[-1]
        if len(numbers) >= 5:
            no_result = numbers[3]
            points = numbers[4]
        rows.append(
            {
                "position": match.group("position"),
                "team": team,
                "played": played,
                "wins": wins,
                "losses": losses,
                "no_result": no_result,
                "points": points,
                "nrr": match.group("nrr"),
            }
        )
        seen.add(team)
        if len(rows) == 10:
            break

    return rows


def _fetch_ipl_standings_context(user_input: str) -> str:
    if not _wants_ipl_standings(user_input):
        return ""

    sources = [
        (
            "Times Now Navbharat IPL points table",
            "https://www.timesnowhindi.com/sports/cricket/ipl-points-table",
        ),
        (
            "Indian Express IPL points table",
            "https://indianexpress.com/section/sports/ipl/points-table/",
        ),
        (
            "Rediff IPL 2026 points table",
            "https://www.rediff.com/cricket/ipl-t20-2026/points-table/",
        ),
    ]

    for source_name, source_url in sources:
        try:
            page = _read_url(source_url, timeout=7)
        except Exception:
            continue
        rows = _parse_ipl_standings_rows(page)
        if len(rows) < 8:
            continue
        table = [
            "| Pos | Team | P | W | L | NR | Pts | NRR | Source status |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---|",
        ]
        for row in rows:
            table.append(
                "| {position} | {team} | {played} | {wins} | {losses} | {no_result} | {points} | {nrr} | Verified from source |".format(
                    **row
                )
            )
        return (
            f"DIRECT LIVE DATA: IPL 2026 points table extracted from {source_name} ({source_url}). "
            f"Fetched at {_format_ist_datetime()}. Use exactly these rows for IPL standings/points-table answers. "
            "Do not invent missing teams, wins, points, or NRR. If asked for confidence, say confidence applies only to rows marked verified from source.\n"
            + "\n".join(table)
        )

    return (
        f"DIRECT LIVE DATA: IPL points table was requested, but no trusted standings table could be parsed at {_format_ist_datetime()}. "
        "Do not create a points table from memory. Say the current standings are not verified and ask to retry or use an attached source."
    )


def _build_direct_live_data_context(user_input: str) -> str:
    lowered = user_input.lower()
    contexts: list[str] = []
    if re.search(r"\b(silver|gold|bullion|metal|metals|chandi|sona)\b", lowered):
        contexts.append(_fetch_ebullion_metal_context())
        contexts.append(_fetch_ibja_bullion_context())
    elif "ebullion" in lowered:
        contexts.append(_fetch_ebullion_metal_context())
    if "ipl" in lowered:
        contexts.append(_fetch_ipl_direct_context(user_input))
    if re.search(r"\b(weather|temperature|rain|forecast|humidity|wind)\b", lowered):
        contexts.append(_fetch_weather_direct_context(user_input))
    if re.search(r"\b(stock|share price|nifty|sensex|bitcoin|btc|ethereum|eth|crypto)\b", lowered):
        contexts.append(_fetch_yahoo_chart_context(user_input))
    if re.search(r"\b(news|headlines|breaking|latest|updates?|happened|today)\b", lowered):
        contexts.append(_fetch_news_direct_context(user_input))
    return "\n".join(context for context in contexts if context)


def _strip_html(value: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", value)
    cleaned = html.unescape(html.unescape(cleaned))
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_meta_content(page: str, meta_name: str) -> str:
    patterns = [
        rf'<meta[^>]+(?:name|property)=["\']{re.escape(meta_name)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']{re.escape(meta_name)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, page, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return _strip_html(match.group(1))
    return ""


def _fetch_page_summary(url: str) -> str:
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            page = response.read(220_000).decode("utf-8", errors="ignore")
    except Exception:
        return ""

    parts: list[str] = []
    title_match = re.search(r"<title[^>]*>(.*?)</title>", page, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        parts.append(_strip_html(title_match.group(1)))
    for meta_name in ("og:title", "description", "og:description"):
        meta_content = _extract_meta_content(page, meta_name)
        if meta_content and meta_content not in parts:
            parts.append(meta_content)
    return " ".join(parts)[:520]


def _unwrap_search_redirect(url: str) -> str:
    parsed_url = html.unescape(url)
    if parsed_url.startswith("//"):
        parsed_url = f"https:{parsed_url}"
    if "uddg=" in parsed_url:
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(parsed_url).query)
        return parsed.get("uddg", [parsed_url])[0]
    if "bing.com/ck" in parsed_url:
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(parsed_url).query)
        encoded_target = parsed.get("u", [""])[0]
        if encoded_target.startswith("a1"):
            encoded_target = encoded_target[2:]
        if encoded_target:
            padding = "=" * (-len(encoded_target) % 4)
            try:
                return base64.urlsafe_b64decode(f"{encoded_target}{padding}").decode("utf-8", errors="ignore")
            except Exception:
                return parsed_url
    return parsed_url


def _format_live_results(results: list[tuple[str, str, str]], limit: int, include_page_summary: bool = True) -> str:
    lines: list[str] = []
    seen_urls: set[str] = set()
    for title, parsed_url, snippet in results:
        if not title or parsed_url in seen_urls:
            continue
        seen_urls.add(parsed_url)
        if "duckduckgo.com/y.js" in parsed_url or "bing.com/aclick" in parsed_url:
            continue
        result_number = len(lines) + 1
        page_summary = _fetch_page_summary(parsed_url) if include_page_summary and len(lines) < 2 else ""
        page_line = f"\n   Page details: {page_summary}" if page_summary else ""
        lines.append(f"{result_number}. {title}\n   URL: {parsed_url}\n   Snippet: {snippet}{page_line}")
        if len(lines) >= limit:
            break
    if not lines:
        return ""
    return "LIVE WEB CONTEXT:\n" + "\n".join(lines)


def _fetch_bing_live_web_context(query: str, limit: int = 3) -> str:
    encoded = urllib.parse.urlencode({"q": query, "cc": "IN"})
    url = f"https://www.bing.com/search?{encoded}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            page = response.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        return f"LIVE WEB CONTEXT: Web lookup failed: {exc}"

    results: list[tuple[str, str, str]] = []
    for block in re.findall(r'<li[^>]+class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>', page, flags=re.IGNORECASE | re.DOTALL):
        title_match = re.search(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.IGNORECASE | re.DOTALL)
        if not title_match:
            continue
        raw_url, raw_title = title_match.groups()
        snippet_match = re.search(r"<p[^>]*>(.*?)</p>", block, flags=re.IGNORECASE | re.DOTALL)
        results.append(
            (
                _strip_html(raw_title),
                _unwrap_search_redirect(raw_url),
                _strip_html(snippet_match.group(1) if snippet_match else ""),
            )
        )

    formatted = _format_live_results(results, limit, include_page_summary=False)
    return formatted or "LIVE WEB CONTEXT: No useful web results were returned for this query."


def _fetch_live_web_context(query: str, limit: int = 3) -> str:
    encoded = urllib.parse.urlencode({"q": query})
    url = f"https://html.duckduckgo.com/html/?{encoded}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
            )
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            page = response.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        return f"LIVE WEB CONTEXT: Web lookup failed: {exc}"

    results: list[str] = []
    link_matches = list(
        re.finditer(
            r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            page,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )

    for match_index, title_match in enumerate(link_matches):
        block_start = title_match.end()
        block_end = link_matches[match_index + 1].start() if match_index + 1 < len(link_matches) else len(page)
        block = page[block_start:block_end]
        raw_url, raw_title = title_match.groups()
        title = _strip_html(raw_title)
        snippet_match = re.search(
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(.*?)</div>',
            block,
            flags=re.IGNORECASE | re.DOTALL,
        )
        snippet = _strip_html((snippet_match.group(1) or snippet_match.group(2)) if snippet_match else "")
        results.append((title, _unwrap_search_redirect(raw_url), snippet))

    formatted_results = _format_live_results(results, limit)
    if formatted_results:
        return formatted_results

    return _fetch_bing_live_web_context(query, limit=limit)


def _build_multi_question_live_context(user_input: str) -> str:
    questions = _split_live_questions(user_input)
    live_blocks: list[str] = []

    for index, question in enumerate(questions[:4], start=1):
        enriched_question = _inherit_live_question_context(question, user_input)
        if not _needs_live_web_context(enriched_question):
            continue
        search_query = _build_live_search_query(enriched_question)
        source_profile = _preferred_live_source_profile(enriched_question)
        source_policy = (
            f"\nSOURCE POLICY: {source_profile['category']}: {source_profile['policy']}"
            if source_profile["policy"]
            else "\nSOURCE POLICY: Prefer official, primary, exchange, government, or original data sources over blogs and generic summaries."
        )
        direct_context = _build_direct_live_data_context(enriched_question)
        direct_context_block = f"\n{direct_context}" if direct_context else ""
        web_context = (
            "LIVE WEB CONTEXT: Direct trusted data was available, so no browser-opening or generic web-search action was needed."
            if direct_context
            else _fetch_live_web_context(search_query, limit=3)
        )
        live_blocks.append(
            f"LIVE QUESTION {index}: {enriched_question}\nSEARCH QUERY: {search_query}{source_policy}{direct_context_block}\n{web_context}"
        )

    if not live_blocks and _needs_live_web_context(user_input):
        search_query = _build_live_search_query(user_input)
        source_profile = _preferred_live_source_profile(user_input)
        source_policy = (
            f"\nSOURCE POLICY: {source_profile['category']}: {source_profile['policy']}"
            if source_profile["policy"]
            else "\nSOURCE POLICY: Prefer official, primary, exchange, government, or original data sources over blogs and generic summaries."
        )
        direct_context = _build_direct_live_data_context(user_input)
        direct_context_block = f"\n{direct_context}" if direct_context else ""
        web_context = (
            "LIVE WEB CONTEXT: Direct trusted data was available, so no browser-opening or generic web-search action was needed."
            if direct_context
            else _fetch_live_web_context(search_query, limit=3)
        )
        live_blocks.append(f"LIVE QUESTION 1: {user_input}\nSEARCH QUERY: {search_query}{source_policy}{direct_context_block}\n{web_context}")

    return "\n\n".join(live_blocks)


TEAM_ALIASES = {
    "csk": "Chennai Super Kings",
    "dc": "Delhi Capitals",
    "gt": "Gujarat Titans",
    "kkr": "Kolkata Knight Riders",
    "lsg": "Lucknow Super Giants",
    "mi": "Mumbai Indians",
    "pbks": "Punjab Kings",
    "rcb": "Royal Challengers Bengaluru",
    "rr": "Rajasthan Royals",
    "srh": "Sunrisers Hyderabad",
}

IPL_TEAM_NAMES = {
    "chennai super kings",
    "delhi capitals",
    "gujarat titans",
    "kolkata knight riders",
    "lucknow super giants",
    "mumbai indians",
    "punjab kings",
    "royal challengers bengaluru",
    "royal challengers bangalore",
    "rajasthan royals",
    "sunrisers hyderabad",
}


def _expand_team_name(team: str) -> str:
    cleaned = re.sub(r"[^A-Za-z ]", "", team).strip()
    alias = cleaned.lower()
    if alias in TEAM_ALIASES:
        return f"{TEAM_ALIASES[alias]} ({cleaned.upper()})"
    return re.sub(r"\s+", " ", cleaned)


def _is_ipl_team_name(team: str) -> bool:
    cleaned = re.sub(r"[^A-Za-z ]", "", team).strip().lower()
    return cleaned in TEAM_ALIASES or cleaned in IPL_TEAM_NAMES


def _extract_matchups_from_live_context(live_context: str) -> list[str]:
    seen: set[str] = set()
    matchups: list[str] = []
    for left, right in re.findall(
        r"\b([A-Z]{2,5}|[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\s+"
        r"(?:v(?:s\.?|ersus)|face(?:s)?|against|take(?:s)? on)\s+"
        r"([A-Z]{2,5}|[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\b",
        live_context,
    ):
        if not (_is_ipl_team_name(left) and _is_ipl_team_name(right)):
            continue
        matchup = f"{_expand_team_name(left)} vs {_expand_team_name(right)}"
        key = matchup.lower()
        if key not in seen:
            seen.add(key)
            matchups.append(matchup)
    return matchups


def _build_live_answer_hint(user_input: str, live_context: str) -> str:
    lowered = user_input.lower()
    today_context = (
        f"TIME CONTEXT: Current local time is {_format_ist_datetime()}. Interpret today/yesterday/tomorrow in IST."
    )
    multi_question_context = (
        " If there are multiple LIVE QUESTION blocks, answer each one in order with a short label. "
        "Do not merge unrelated answers or skip smaller questions."
    )
    if "ipl" in lowered and re.search(r"\b(today|yesterday|tomorrow|now|current|present|match|teams?|playing|schedule|score|highest|batting|batter|batters|crease|pitch|striker|non[-\s]?striker|bowling|bowler)\b", lowered):
        if re.search(r"\b(batting|batter|batters|crease|pitch|striker|non[-\s]?striker|bowling|bowler)\b", lowered):
            return (
                f"{today_context}\nDIRECT LIVE ANSWER HINT: This is a live scorecard detail question. "
                "Use only DIRECT LIVE DATA fields such as Verified batters at crease, Current bowler, Current innings score, and fetch timestamp. "
                "Name current batters/bowler only if those exact fields are present. If absent, say the live feed did not verify that detail. "
                f"Do not guess from prior chat, team lineups, snippets, or memory.{multi_question_context}"
            )
        matchups = _extract_matchups_from_live_context(live_context)
        if matchups:
            return (
                f"{today_context}\nDIRECT LIVE ANSWER HINT: The searched results indicate the IPL match/team answer is "
                f"{'; '.join(matchups[:2])}. Start with this direct answer. Then mention the source names "
                f"briefly. Ignore unrelated sports/wrestling/entertainment matchups. Do not tell the user to check a website.{multi_question_context}"
            )
        return (
            f"{today_context}\nDIRECT LIVE ANSWER HINT: This is an IPL current-match question. Use the LIVE WEB CONTEXT titles "
            "and snippets to answer the teams directly. If the result is uncertain, say exactly what was verified "
            f"and ask one focused follow-up. Ignore unrelated sports/wrestling/entertainment results. Do not tell the user to check a website.{multi_question_context}"
        )
    if "LIVE WEB CONTEXT:" in live_context and "No useful web results" not in live_context:
        return (
            f"{today_context}\nDIRECT LIVE ANSWER HINT: If DIRECT LIVE DATA is present, use it before search snippets. Otherwise answer the real-time question directly from LIVE WEB CONTEXT first. "
            "Only add source names or URLs after the answer. Do not respond by sending the user away to check websites. "
            "For prices, scores, weather, versions, and market values, include the visible date/time/unit from the source; if a number is missing or conflicting, say so instead of guessing."
            f"{multi_question_context}"
        )
    if "DIRECT LIVE DATA:" in live_context:
        return (
            f"{today_context}\nDIRECT LIVE ANSWER HINT: Answer directly from DIRECT LIVE DATA. Include the unit, source, and timestamp/date when present. "
            f"Do not tell the user to check a website.{multi_question_context}"
        )
    return ""


def _extract_fetched_at(live_context: str) -> str:
    match = re.search(r"Fetched at ([^.]+(?:IST)?)", live_context)
    return match.group(1).strip() if match else _format_ist_datetime()


def _direct_source_backed_answer(user_input: str, live_context: str) -> str:
    """Return deterministic answers for high-risk live facts when parsed source data exists.

    This prevents the chat model from beautifying partial source data into confident,
    fabricated live/news/sports rows. When a deterministic answer is returned, it is
    intentionally limited to facts present in DIRECT LIVE DATA.
    """
    lowered = user_input.lower()

    if "IPL 2026 points table extracted" in live_context:
        table_lines = [
            line.strip()
            for line in live_context.splitlines()
            if line.strip().startswith("|") and line.strip().endswith("|")
        ]
        source_match = re.search(r"extracted from ([^(]+)\((https?://[^)]+)\)", live_context)
        source_name = source_match.group(1).strip() if source_match else "parsed IPL standings source"
        source_url = source_match.group(2).strip() if source_match else ""
        source_text = f"[{source_name}]({source_url})" if source_url else source_name
        return (
            f"Source-backed IPL 2026 points table, fetched at {_extract_fetched_at(live_context)}.\n\n"
            + "\n".join(table_lines)
            + f"\n\nSource: {source_text}. Status: rows are source-backed only; I did not add confidence or fill missing values from memory."
        )

    if "IPL points table was requested, but no trusted standings table could be parsed" in live_context:
        return (
            "I could not verify the current IPL points table from a trusted parseable source right now. "
            "I will not generate a confident table from memory because that can be wrong. Please retry once, or paste/upload the standings source and I will format it."
        )

    if re.search(r"\b(news|headlines|breaking|latest|updates?|happened|today)\b", lowered) and "RSS/news feeds fetched" in live_context:
        item_lines = [line.strip()[2:] for line in live_context.splitlines() if line.strip().startswith("- ")]
        if not item_lines:
            return ""
        table = [
            "| # | Source | Headline | Published | Status |",
            "|---:|---|---|---|---|",
        ]
        for index, item in enumerate(item_lines[:8], start=1):
            source = "Source feed"
            headline = item
            published = "Not provided"
            if ": " in item:
                source, headline = item.split(": ", 1)
            date_match = re.search(r"\[([^\]]+)\]", headline)
            if date_match:
                published = date_match.group(1)
                headline = re.sub(r"\s*\[[^\]]+\]", "", headline).strip()
            headline = re.sub(r"\s+-\s+.*$", "", headline).strip()
            table.append(
                f"| {index} | {source} | {headline} | {published} | Source-reported, not independently confirmed |"
            )
        return (
            f"Verified news feed items fetched at {_extract_fetched_at(live_context)}. "
            "I am only listing source-reported items and not adding extra confident claims.\n\n"
            + "\n".join(table)
        )

    return ""


def _detect_output_formats(user_input: str) -> list[str]:
    lowered = user_input.lower()
    formats: list[str] = []
    checks = [
        ("xlsx", r"\b(excel|xlsx|spreadsheets?|workbooks?)\b"),
        ("pdf", r"\b(pdfs?|reports?|invoices?|receipts?|certificates?|resume|resumes|notes?|formula sheets?|study plans?)\b"),
        ("docx", r"\b(word|docx|documents?)\b"),
        ("pptx", r"\b(powerpoint|ppt|pptx|presentation|slides?)\b"),
        ("csv", r"\b(csvs?|csv files?)\b"),
        ("json", r"\b(json)\b"),
        ("png", r"\b(pngs?|images?|diagrams?|photos?|pictures?|charts?)\b"),
        ("jpg", r"\b(jpgs?|jpegs?)\b"),
        ("markdown", r"\b(markdown|md)\b"),
        ("zip", r"\b(zips?|archives?)\b"),
    ]
    for name, pattern in checks:
        if re.search(pattern, lowered):
            formats.append(name)
    return formats


def _needs_structured_table(user_input: str) -> bool:
    lowered = user_input.lower()
    return bool(
        re.search(
            r"\b(table|points table|standings?|stats|statistics|compare|comparison|ranking|rank|"
            r"schedule|fixtures?|scorecard|list|summarize|summary|compress)\b",
            lowered,
        )
    )


def _is_deep_conversation_mode(conversation_mode: str | None) -> bool:
    return (conversation_mode or "").strip().lower() in {"research", "agent", "skill", "deep"}


def _response_token_limit(
    user_input: str,
    attachments: list[dict] | None = None,
    conversation_mode: str | None = None,
) -> int:
    """Keep Quick/chat/voice responsive; reserve longer responses for explicit work modes."""
    is_deep_mode = _is_deep_conversation_mode(conversation_mode)
    if attachments:
        return 900 if is_deep_mode else 520
    requested_formats = _detect_output_formats(user_input)
    lowered = user_input.lower()
    if requested_formats:
        return 1500 if is_deep_mode else 900
    if _needs_structured_table(user_input) or _needs_live_web_context(user_input):
        return 900 if is_deep_mode else 180
    if len(user_input) <= 120 and not re.search(r"\b(explain|detail|deep|complete|full|step by step)\b", lowered):
        return 160
    return 700 if is_deep_mode else 360


def _chat_request_timeout_seconds(
    user_input: str,
    attachments: list[dict] | None = None,
    conversation_mode: str | None = None,
) -> float:
    if _is_deep_conversation_mode(conversation_mode):
        return 32.0
    if attachments:
        return 18.0
    if _needs_live_web_context(user_input) or _needs_structured_table(user_input):
        return 12.0
    return 8.0


def _build_output_intent_context(user_input: str) -> str:
    requested_formats = _detect_output_formats(user_input)
    table_needed = _needs_structured_table(user_input)
    if not requested_formats and not table_needed:
        return (
            "OUTPUT INTELLIGENCE: Choose the most useful format automatically. Use Markdown tables for comparisons, "
            "standings, stats, schedules, live data, prices, news, and multi-item summaries. For live/current claims, "
            "separate source-reported facts from unverified details."
        )

    lines = [
        "OUTPUT INTELLIGENCE CONTRACT:",
        "- Infer the user's desired output format from the prompt and answer in that format immediately.",
        "- If a table is useful or requested, produce a clean Markdown table with concise column names.",
        "- Do not refuse table/file-style requests just because every field is not verified; include a Source/Status column and mark missing live fields as Not verified.",
        "- For live/current data, use DIRECT LIVE DATA or LIVE WEB CONTEXT first, include source names and fetched timestamp/date.",
        "- Never tell the user to visit a website instead of answering; answer with verified facts and uncertainty labels.",
        "- Do not use confident words like current/latest/confirmed unless the value is in DIRECT LIVE DATA or a cited live source. If not verified, label it Not verified instead of guessing.",
        "- Confidence score means source coverage only: High = exact parsed source rows, Medium = source snippet/headline only, Low = partial or conflicting sources. Never use confidence to make an unverified fact sound true.",
        "- For news, summarize only source-reported items that appear in the live context. Do not add background claims, names, scores, dates, or conclusions that are not present in the source lines.",
    ]
    if table_needed:
        lines.append("- The user needs structured information: prioritize a table before explanatory paragraphs.")
    if requested_formats:
        lines.append(
        "- The user requested downloadable/exportable formats: "
        + ", ".join(requested_formats)
        + ". The backend artifact engine will create the real downloadable files from the final answer, so keep the content structured and never invent sandbox:/ download links."
        )
    return "\n".join(lines)


def _build_attachment_message_content(user_input: str, attachments: list[dict]) -> list[dict]:
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"{user_input}\n\n"
                "Attached content is part of the question. Analyze it carefully and answer directly. "
                "For screenshots, inspect visible UI state, buttons, text, alignment, errors, and small details."
            ),
        }
    ]

    for index, attachment in enumerate(attachments[:5], start=1):
        name = str(attachment.get("name") or f"attachment-{index}")
        mime_type = str(attachment.get("type") or "")
        data_url = str(attachment.get("data_url") or "")
        text = str(attachment.get("text") or "")
        size = attachment.get("size")

        label = f"Attachment {index}: {name}"
        if mime_type:
            label += f" ({mime_type})"
        if size:
            label += f", {size} bytes"

        if data_url.startswith("data:image/"):
            content.append({"type": "text", "text": label})
            content.append({"type": "image_url", "image_url": {"url": data_url}})
            continue

        if text:
            content.append(
                {
                    "type": "text",
                    "text": f"{label}\nFile text excerpt:\n{text[:16000]}",
                }
            )
            continue

        content.append(
            {
                "type": "text",
                "text": f"{label}\nNo readable preview was available for this file type.",
            }
        )

    return content


def _local_image_attachment_summary(attachments: list[dict]) -> str | None:
    """Return a deterministic local pixel summary when cloud vision is unavailable."""
    image_lines: list[str] = []
    for index, attachment in enumerate((attachments or [])[:5], start=1):
        mime_type = str(attachment.get("type") or "")
        data_url = str(attachment.get("data_url") or "")
        if not mime_type.startswith("image/") or not data_url.startswith("data:image/") or "," not in data_url:
            continue

        name = str(attachment.get("name") or f"image-{index}")
        size = attachment.get("size")
        try:
            from PIL import Image, ImageStat

            raw = base64.b64decode(data_url.split(",", 1)[1], validate=False)
            with Image.open(io.BytesIO(raw)) as image:
                rgb = image.convert("RGB")
                stat = ImageStat.Stat(rgb.resize((80, 80)))
                mean = tuple(int(value) for value in stat.mean[:3])
                brightness = round(sum(mean) / 3)
                orientation = "landscape" if image.width > image.height else "portrait" if image.height > image.width else "square"
                image_lines.append(
                    f"- {name}: {image.width}x{image.height}px {orientation} {mime_type}; "
                    f"approx brightness {brightness}/255; average RGB {mean}; uploaded size {size or len(raw)} bytes."
                )
        except Exception:
            image_lines.append(f"- {name}: image received and queued, but local pixel metadata could not be decoded.")

    if not image_lines:
        return None

    return (
        "I received the image and completed the local pixel pass:\n"
        + "\n".join(image_lines)
        + "\nFor tiny text/OCR, object recognition, or detailed screenshot reasoning, the vision lane must be active; I will not invent details that are not locally readable."
    )


QUESTION_NUMBER_KEYS = {
    "question_number",
    "questionno",
    "question_no",
    "questionid",
    "question_id",
    "qno",
    "q_no",
    "number",
    "no",
    "id",
    "serial",
    "index",
    "sno",
    "s_no",
}


def _attachment_text_items(attachments: list[dict] | None) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for index, attachment in enumerate((attachments or [])[:5], start=1):
        text = str(attachment.get("text") or "")
        if not text.strip():
            continue
        name = str(attachment.get("name") or f"attachment-{index}")
        items.append((name, text))
    return items


def _extract_requested_question_number(user_input: str) -> int | None:
    cleaned = _compact_text(user_input)
    patterns = (
        r"\b(?:question|q)\s*(?:number|no\.?|#)?\s*(\d{1,5})\b",
        r"\b(\d{1,5})(?:st|nd|rd|th)?\s+(?:question|q)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            if value > 0:
                return value
    return None


def _int_like(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if re.fullmatch(r"\d+", cleaned):
            return int(cleaned)
    return None


def _find_numbered_json_item(data: object, number: int) -> object | None:
    """Find item whose explicit id/no is number; fall back to list position."""
    def walk(node: object) -> object | None:
        if isinstance(node, dict):
            for key, value in node.items():
                normalized_key = re.sub(r"[^a-z0-9_]", "", str(key).lower())
                if _int_like(key) == number and isinstance(value, (dict, list, str)):
                    return value
                if normalized_key in QUESTION_NUMBER_KEYS and _int_like(value) == number:
                    return node
            for value in node.values():
                found = walk(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = walk(value)
                if found is not None:
                    return found
            if 0 < number <= len(node):
                return node[number - 1]
        return None

    return walk(data)


def _first_dict_value(item: dict, keys: tuple[str, ...]) -> str:
    lowered = {str(key).lower(): value for key, value in item.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _compact_json_value(value: object, limit: int = 700) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, indent=2)
    else:
        text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "..."
    return text


def _format_question_item_answer(file_name: str, number: int, item: object) -> str:
    if isinstance(item, dict):
        question = _first_dict_value(
            item,
            (
                "question",
                "question_text",
                "title",
                "prompt",
                "statement",
                "text",
                "content",
                "name",
            ),
        )
        topic = _first_dict_value(item, ("topic", "subject", "category", "chapter", "section", "tag"))
        answer = _first_dict_value(item, ("answer", "correct_answer", "solution", "explanation"))
        options = item.get("options") or item.get("choices") or item.get("mcq_options")

        lines = [f"Question {number} in {file_name}:"]
        if question:
            lines.append(f"- It is about: {question}")
        else:
            lines.append(f"- Item content: {_compact_json_value(item)}")
        if topic:
            lines.append(f"- Topic/category: {topic}")
        if options:
            lines.append(f"- Options: {_compact_json_value(options, 400)}")
        if answer:
            lines.append(f"- Answer/solution field: {_compact_json_value(answer, 500)}")
        return "\n".join(lines)

    return (
        f"Question {number} in {file_name}:\n"
        f"- It is about: {_compact_json_value(item, 900)}"
    )


def _find_numbered_text_item(text: str, number: int) -> str | None:
    lines = text.splitlines()
    marker = re.compile(rf"^\s*(?:q(?:uestion)?\.?\s*)?{number}\s*[\).:\-]\s*(.+)?$", re.IGNORECASE)
    for index, line in enumerate(lines):
        if marker.match(line):
            window = "\n".join(lines[index : min(len(lines), index + 8)]).strip()
            return window[:1400]

    inline = re.search(
        rf"(?:question|q)\s*(?:number|no\.?|#)?\s*{number}\b(.{{0,1200}})",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if inline:
        return re.sub(r"\s+", " ", inline.group(0)).strip()[:1400]
    return None


def _local_attachment_question_answer(user_input: str, attachments: list[dict] | None) -> str | None:
    number = _extract_requested_question_number(user_input)
    if not number:
        return None

    for file_name, text in _attachment_text_items(attachments):
        try:
            parsed = json.loads(text)
            item = _find_numbered_json_item(parsed, number)
            if item is not None:
                return _format_question_item_answer(file_name, number, item)
        except Exception:
            pass

        text_item = _find_numbered_text_item(text, number)
        if text_item:
            return (
                f"Question {number} in {file_name}:\n"
                f"- Matched text:\n{text_item}"
            )

    return None


def _provider_failure_kind(error: Exception) -> str:
    message = str(error).lower()
    if isinstance(error, OpenRouterConfigurationError) or "401" in message or "authentication" in message or "unauthorized" in message:
        return "auth"
    if "402" in message or "credit" in message or "budget" in message or "insufficient" in message:
        return "capacity"
    if "timeout" in message or "timed out" in message:
        return "timeout"
    if "rate" in message and "limit" in message:
        return "rate_limit"
    return "provider"


def _provider_failure_fallback(
    user_input: str,
    attachments: list[dict] | None,
    error: Exception,
    language_preference: str | None = None,
) -> str:
    preference = (language_preference or "").lower()
    kind = _provider_failure_kind(error)
    has_images = any(str(item.get("type") or "").startswith("image/") for item in attachments or [])
    has_attachments = bool(attachments)
    local_attachment_answer = _local_attachment_question_answer(user_input, attachments)
    if local_attachment_answer:
        return local_attachment_answer

    if has_images:
        local_summary = _local_image_attachment_summary(attachments or [])
        if local_summary:
            return local_summary
        if "hindi" in preference:
            return (
                "Image attach ho gayi hai. Main local pixel summary de sakta hoon, par detailed OCR/object reasoning abhi complete nahi hua. "
                "Screenshot ka exact part batao, main visible metadata se help karta hoon."
            )
        if "telugu" in preference:
            return (
                "Image attach ayyindi. Local pixel summary cheppagalanu, kani detailed OCR/object reasoning ippudu complete avvaledu. "
                "Screenshot lo exact part cheppu, visible metadata tho help chestha."
            )
        return (
            "I received the image. I can summarize local pixel metadata, but detailed OCR/object reasoning did not complete this turn. "
            "Tell me the exact area you want checked and I will use the visible metadata without guessing."
        )

    if has_attachments:
        return (
            "I received the attachment and the upload path is working. Detailed file/video analysis did not complete this turn; "
            "for now, paste the exact section you want checked and I will handle that part locally."
        )

    if _should_use_local_utility_reply(user_input):
        return _fast_local_reply_for_provider_failure(user_input, language_preference)

    local_quick_answer = _quick_local_response(
        _NoopDb(),
        user_input,
        language_preference,
        speaker_profile=None,
        allow_conversation_fragments=True,
    )
    if local_quick_answer:
        return local_quick_answer

    if _wants_joke(user_input):
        return _fallback_joke_reply(user_input, language_preference or "")

    if kind == "auth":
        return (
            "I can answer quick local tasks, but this message needs the advanced answer lane and that lane is not active in this backend session. "
            "Restart the backend after saving the environment, then send it again."
        )

    if kind in {"capacity", "rate_limit"}:
        if _should_use_local_utility_reply(user_input):
            return _fast_local_reply_for_provider_failure(user_input, language_preference)
        return (
            "I could not verify that advanced online result this turn, so I will not guess. "
            "Quick local questions still answer immediately; use Research/Agent/Skill again when you want a source-checked result."
        )

    if kind == "timeout":
        return (
            "That answer took too long, so I stopped waiting instead of leaving the chat stuck. "
            "Send the core question again, or switch to Research/Agent/Skill for a longer workflow."
        )

    return (
        "I could not get a usable advanced response this turn. Quick local answers are still available; retry once after the backend settles."
    )


def _fast_local_reply_for_provider_failure(user_input: str, language_preference: str | None = None) -> str:
    return _fast_local_reply(_NoopDb(), user_input, language_preference) or _quick_local_response(
        _NoopDb(),
        user_input,
        language_preference,
        speaker_profile=None,
        allow_conversation_fragments=True,
    ) or (
        "I could not answer that path this turn. Try the core question again after the backend settles."
    )


def generate_chat_stream(
    db: Session,
    user_input: str,
    session_id: str = "default",
    user_tone: str | None = None,
    response_style: str | None = None,
    conversation_mode: str | None = None,
    language_preference: str | None = None,
    attachments: list[dict] | None = None,
    speaker_profile: dict | None = None,
):
    """Generator for streaming responses."""
    effective_language_preference = _detect_user_language_preference(user_input, language_preference)
    local_attachment_answer = _local_attachment_question_answer(user_input, attachments)
    if local_attachment_answer:
        yield local_attachment_answer
        return

    if _should_use_local_utility_reply(user_input, attachments):
        fast_reply = _fast_local_reply(db, user_input, effective_language_preference)
        if fast_reply:
            yield fast_reply
            return

    if not attachments and not _is_deep_conversation_mode(conversation_mode):
        quick_reply = _quick_local_response(
            db,
            user_input,
            effective_language_preference,
            speaker_profile=speaker_profile,
            allow_conversation_fragments=True,
        )
        if quick_reply:
            yield quick_reply
            return

    history_records = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.display_order.desc(), ChatMessage.id.desc())
        .limit(10)
        .all()
    )
    
    # We remove the duplicate manual append since main.py already saved the current user_input to the DB
    history = [{"role": r.role, "content": r.content} for r in reversed(history_records)]
    
    memories = db.query(Memory).order_by(Memory.importance.desc()).limit(12).all()
    memory_str = "CORE MEMORIES (FACTS YOU MUST USE):\n" + "\n".join([f"- {m.topic}: {m.insight}" for m in memories])

    dynamic_context = [
        build_social_intelligence_context(speaker_profile, user_input, user_tone),
        f"USER TONE SIGNAL: {user_tone or 'neutral'}",
        f"RESPONSE STYLE PREFERENCE: {response_style or 'friendly'}",
        f"CONVERSATION MODE: {conversation_mode or 'hybrid'}",
        f"LANGUAGE PREFERENCE: {effective_language_preference}",
        "Speak naturally, with short spoken-language sentences when the conversation mode involves voice. Use a brief acknowledgement/filler only when it sounds human, then answer directly.",
        _language_instruction(effective_language_preference, language_preference),
        _build_output_intent_context(user_input),
        f"CURRENT TIME CONTEXT: {_format_ist_datetime()}. Use IST for today, yesterday, tomorrow, now, present, and current.",
        (
            "CURRENT FACT ACCURACY CONTRACT: For any current/live/recent question in any domain, use DIRECT LIVE DATA "
            "or LIVE WEB CONTEXT as the source of truth. Answer all requested fields directly, include source name and "
            "timestamp/date/unit when available, and do not invent missing details. Never present guessed or memory-based "
            "live facts confidently. If the exact detail is not verified by the live context, say that exact detail is "
            "not verified yet and give the closest verified facts. Do not say 'current', 'latest', 'confirmed', or "
            "'here is the table' unless the rows/values are present in DIRECT LIVE DATA or a cited live source. "
            "For news and articles, every headline/claim must be traceable to a source line in DIRECT LIVE DATA or LIVE WEB CONTEXT; "
            "if the source is only an RSS/search snippet, call it 'source-reported' rather than fully confirmed. "
            "When the user says re-check/wrong, do a fresh live lookup and do not defend the previous answer from memory."
        ),
    ]
    source_backed_answer = ""
    if _needs_live_web_context(user_input):
        live_context = _build_multi_question_live_context(user_input)
        dynamic_context.append(live_context)
        live_answer_hint = _build_live_answer_hint(user_input, live_context)
        if live_answer_hint:
            dynamic_context.append(live_answer_hint)
        source_backed_answer = _direct_source_backed_answer(user_input, live_context)

    if attachments:
        dynamic_context.append(
            "ATTACHMENT VISION MODE: The user attached screenshots/images/files. Inspect images carefully: visible text, UI controls, layout, colors, warnings, tiny labels, and any likely user intent. "
            "Answer from the attachment content first, then reason about the next useful action. If a detail is not visible, say it is not visible instead of guessing."
        )

    if source_backed_answer and not attachments:
        yield source_backed_answer
        return

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT + "\n\n" + memory_str + "\n\n" + "\n".join(dynamic_context),
        }
    ] + history

    if attachments:
        multimodal_content = _build_attachment_message_content(user_input, attachments)
        if messages and messages[-1].get("role") == "user" and messages[-1].get("content") == user_input:
            messages[-1] = {"role": "user", "content": multimodal_content}
        else:
            messages.append({"role": "user", "content": multimodal_content})
    
    if os.getenv("AKANSHA_DEBUG_PROMPT") == "1":
        with open("debug_prompt.txt", "w", encoding="utf-8") as f:
            f.write(json.dumps(messages, indent=2, ensure_ascii=False))

    try:
        client = _openrouter_client()
        if hasattr(client, "with_options"):
            client = client.with_options(
                timeout=_chat_request_timeout_seconds(user_input, attachments, conversation_mode)
            )
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=messages,
            temperature=0.55,
            max_tokens=_response_token_limit(user_input, attachments, conversation_mode),
            stream=True
        )

        full_response = ""
        for chunk in response:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                yield content
    except Exception as exc:
        yield _provider_failure_fallback(user_input, attachments, exc, effective_language_preference)
            
    # We yield a special token at the end or handle the background task in main.py

def analyze_intent_and_memory(db: Session, user_input: str, assistant_response: str):
    """Background task to extract memory and intent (e.g. creating tasks)."""
    _capture_deterministic_memories(db, user_input)
    if _should_skip_ai_memory_analysis(user_input, assistant_response):
        try:
            db.commit()
        except Exception:
            pass
        return

    existing_memories = db.query(Memory).all()
    memories_str = "Existing Memories:\n" + "\n".join([f"ID: {m.id} | Topic: {m.topic} | Insight: {m.insight}" for m in existing_memories])

    prompt = f"""
    Analyze the recent interaction. 
    1. Extract any new long-term memories about the user.
    2. Identify if the user implicitly or explicitly requested a task to be tracked.
    3. Identify if the user wants to trigger a desktop automation action.
    
    IMPORTANT: You must consolidate memories! Do not create duplicate memories for the same topic. 
    If new information overlaps with an existing memory, update the existing memory instead of creating a new one.

    {memories_str}
    
    Return ONLY a JSON object:
    {{
        "memories_to_add": [{{"topic": "str", "insight": "str", "importance": 1-5}}],
        "memories_to_update": [{{"id": int, "new_insight": "str", "new_importance": 1-5}}],
        "new_tasks": [{{"title": "str", "description": "str"}}],
        "automation": {{"action": "open_notepad|type|open_url|open_youtube_song|new_tab|close_tab|type_text|edit_field|remove_draft", "target": "str"}} 
    }}
    
    Interaction:
    User: {user_input}
    Akansha: {assistant_response}
    """
    try:
        res = _openrouter_client().chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=220,
        )
        data = json.loads(res.choices[0].message.content)
        
        # Save New Memories
        for m in data.get('memories_to_add', []):
            _upsert_memory(db, m['topic'], m['insight'], m.get('importance', 1))
            
        # Update Existing Memories
        for m in data.get('memories_to_update', []):
            existing_mem = db.query(Memory).filter(Memory.id == m['id']).first()
            if existing_mem:
                existing_mem.insight = m['new_insight']
                if 'new_importance' in m:
                    existing_mem.importance = m['new_importance']
            
        # Save Tasks
        for t in data.get('new_tasks', []):
            new_task = Task(title=t['title'], description=t.get('description', ''))
            db.add(new_task)
            
        db.commit()

        # Handle Automation
        automation = data.get('automation')
        if automation and automation.get('action'):
            import asyncio
            from .automation import execute_desktop_command
            
            # Since this is a background thread, we need an event loop
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            loop.run_until_complete(execute_desktop_command(automation['action'], automation.get('target')))
    except Exception as e:
        kind = _provider_failure_kind(e)
        if kind in {"auth", "capacity", "rate_limit", "timeout"}:
            print("Analysis skipped: provider unavailable for background memory extraction.")
            return
        print(f"Analysis skipped: {type(e).__name__}")
