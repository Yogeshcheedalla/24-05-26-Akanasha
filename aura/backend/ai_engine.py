import os
import json
import re
import html
import base64
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from openai import OpenAI
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from .database import Memory, ChatMessage, Task

load_dotenv(override=True)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    default_headers={
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Akansha AI Assistant",
    }
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
"""

IST = timezone(timedelta(hours=5, minutes=30), name="IST")


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
            r"president|prime minister|chief minister|ceo|stock|crypto|release date|version|model|trend|trending)\b",
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
}

HINDI_ROMAN_HINTS = {
    "namaste",
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
}


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
    if "ipl" in lowered and re.search(r"\b(today|yesterday|tomorrow|now|current|present|match|teams?|playing|schedule|score|highest|batting|batter|batters|crease|pitch|bowling|bowler)\b", lowered):
        return f"site:iplt20.com OR site:espncricinfo.com OR site:cricbuzz.com {user_input} IPL {date_text} match teams score live score striker non striker bowler scorecard highest scorer"
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
        "Use these source-attributed headlines before generic search results.\n"
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


def generate_chat_stream(
    db: Session,
    user_input: str,
    session_id: str = "default",
    user_tone: str | None = None,
    response_style: str | None = None,
    conversation_mode: str | None = None,
    language_preference: str | None = None,
    attachments: list[dict] | None = None,
):
    """Generator for streaming responses."""
    history_records = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.display_order.desc(), ChatMessage.id.desc())
        .limit(15)
        .all()
    )
    
    # We remove the duplicate manual append since main.py already saved the current user_input to the DB
    history = [{"role": r.role, "content": r.content} for r in reversed(history_records)]
    
    memories = db.query(Memory).order_by(Memory.importance.desc()).all()
    memory_str = "CORE MEMORIES (FACTS YOU MUST USE):\n" + "\n".join([f"- {m.topic}: {m.insight}" for m in memories])
    effective_language_preference = _detect_user_language_preference(user_input, language_preference)

    dynamic_context = [
        f"USER TONE SIGNAL: {user_tone or 'neutral'}",
        f"RESPONSE STYLE PREFERENCE: {response_style or 'friendly'}",
        f"CONVERSATION MODE: {conversation_mode or 'hybrid'}",
        f"LANGUAGE PREFERENCE: {effective_language_preference}",
        "Speak naturally, with short spoken-language sentences when the conversation mode involves voice.",
        _language_instruction(effective_language_preference, language_preference),
        f"CURRENT TIME CONTEXT: {_format_ist_datetime()}. Use IST for today, yesterday, tomorrow, now, present, and current.",
        (
            "CURRENT FACT ACCURACY CONTRACT: For any current/live/recent question in any domain, use DIRECT LIVE DATA "
            "or LIVE WEB CONTEXT as the source of truth. Answer all requested fields directly, include source name and "
            "timestamp/date/unit when available, and do not invent missing details. If the exact detail is not verified "
            "by the live context, say that exact detail is not verified yet and give the closest verified facts. "
            "When the user says re-check/wrong, do a fresh live lookup and do not defend the previous answer from memory."
        ),
    ]
    if _needs_live_web_context(user_input):
        live_context = _build_multi_question_live_context(user_input)
        dynamic_context.append(live_context)
        live_answer_hint = _build_live_answer_hint(user_input, live_context)
        if live_answer_hint:
            dynamic_context.append(live_answer_hint)

    if attachments:
        dynamic_context.append(
            "ATTACHMENT VISION MODE: The user attached screenshots/images/files. Inspect images carefully: visible text, UI controls, layout, colors, warnings, tiny labels, and any likely user intent. "
            "Answer from the attachment content first, then reason about the next useful action. If a detail is not visible, say it is not visible instead of guessing."
        )

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
    
    with open("debug_prompt.txt", "w") as f:
        f.write(json.dumps(messages, indent=2))

    response = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=messages,
        temperature=0.7,
        max_tokens=1200,
        stream=True
    )
    
    full_response = ""
    for chunk in response:
        if chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            full_response += content
            yield content
            
    # We yield a special token at the end or handle the background task in main.py

def analyze_intent_and_memory(db: Session, user_input: str, assistant_response: str):
    """Background task to extract memory and intent (e.g. creating tasks)."""
    _capture_deterministic_memories(db, user_input)
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
        res = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
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
        print(f"Analysis failed: {e}")
