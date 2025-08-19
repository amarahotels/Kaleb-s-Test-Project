import os
import re
import json
import requests
from pathlib import Path
from datetime import datetime, timedelta
from dateutil import parser

# ---------------- Config ----------------
API_KEY = os.getenv("SERPAPI_KEY")
if not API_KEY:
    raise RuntimeError("SERPAPI_KEY is not set")

# Quota/refresh controls
MAX_CALLS_PER_RUN      = int(os.getenv("EVENTS_MAX_CALLS", "6"))        # total SerpAPI requests per run
TARGET_EVENTS          = int(os.getenv("EVENTS_TARGET_COUNT", "60"))    # cap saved events
PER_BUCKET_CAP         = int(os.getenv("EVENTS_PER_BUCKET_CAP", "25"))  # per-bucket keep cap
REQUIRE_IMAGE          = os.getenv("EVENTS_REQUIRE_IMAGE", "1") == "1"  # drop events without image

OUT_PATH = Path("public/data/events.json")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

SERP_LOCALE = {"engine": "google_events", "hl": "en", "gl": "sg", "location": "Singapore"}

now = datetime.now()
month_year = now.strftime("%B %Y")

# --- Tourist-friendly queries (we’ll run exactly two per bucket each run) ---
QUERIES_BY_BUCKET = {
    "family": [
        "sentosa events",
        "gardens by the bay events",
        "mandai wildlife events",
        "singapore zoo events",
        "bird paradise events",
        "artscience museum exhibitions",
    ],
    "music": [
        f"concerts in Singapore {month_year}",
        "music festivals singapore",
        "live music singapore weekend",
        "classical concert singapore",
        "indie concert singapore",
        "dj events singapore",
    ],
    "general": [
        "events in Singapore this week",
        "things to do in Singapore this weekend",
        f"exhibitions in Singapore {month_year}",
        "museum events singapore",
        "jewel changi attractions events",
        "national museum singapore events",
    ],
}

PAST_GRACE_DAYS = 1  # keep events that started up to 1 day ago (helps multi-day)

# ---------------- Filtering (tourist-friendly) ----------------
# fitness/race-y
FITNESS_RE = re.compile(
    r"\b(run|running|marathon|ultra|triathlon|race|jog(?:ging)?|"
    r"cycling|bike(?:\s*ride)?|spartan|ironman|5k|10k|15k|21k|42k|km)\b",
    re.I,
)
# business/networking
BIZ_RE = re.compile(r"\b(conference|summit|expo|webinar|seminar|forum|networking|meet-?up|after work)\b", re.I)

# NEW: explicitly block CISO-branded/cybersecurity enterprise events
CISO_RE = re.compile(r"\bciso\b", re.I)

# alcohol/adult
ALCOHOL_RE = re.compile(r"\b(wine|beer|whisk(?:y|ey)|cocktail|gin|rum|vodka|sake|soju|cigar|tasting)\b", re.I)
ADULT_RE = re.compile(r"\b(18\+|21\+|adults\s*only)\b", re.I)

def matches_any(text: str, *patterns) -> bool:
    if not text:
        return False
    for pat in patterns:
        if pat.search(text):
            return True
    return False

def looks_like_interval_walk(text: str) -> bool:
    """Block fitness 'walk training' but keep tourist 'walking tour'."""
    t = (text or "").lower()
    if "walk" not in t:
        return False
    return any(k in t for k in ("interval", "training", "pace", "15k", "10k", "km", "race", "marathon"))

# ---------------- Helpers ----------------
_calls_made = 0

def fetch_events(query: str):
    """SerpAPI call with global budget."""
    global _calls_made
    if _calls_made >= MAX_CALLS_PER_RUN:
        print(f"⛔️ Budget reached ({MAX_CALLS_PER_RUN} calls). Skipping: {query}")
        return []

    params = {**SERP_LOCALE, "q": query, "api_key": API_KEY}
    try:
        r = requests.get("https://serpapi.com/search", params=params, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"❌ Request failed for '{query}': {e}")
        return []

    _calls_made += 1
    data = r.json() or {}
    return data.get("events_results", []) or []

def parse_date_safe(s):
    if not s:
        return None
    try:
        return parser.parse(s)
    except Exception:
        return None

def _coerce_address(addr):
    """Accepts str | list | dict and returns a string address."""
    if not addr:
        return ""
    if isinstance(addr, str):
        return addr
    if isinstance(addr, (list, tuple)):
        parts = []
        for x in addr:
            if isinstance(x, dict):
                parts.append(_coerce_address(x.get("address") or x.get("name") or ""))
            else:
                parts.append(str(x))
        return ", ".join([p for p in parts if p])
    if isinstance(addr, dict):
        return str(addr.get("address") or addr.get("name") or "")
    return str(addr)

def _first_string_url(value):
    if not value:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for k in ("link", "url", "image", "src"):
            v = value.get(k)
            if isinstance(v, str) and v:
                return v
    if isinstance(value, (list, tuple)):
        for item in value:
            u = _first_string_url(item)
            if u:
                return u
    return None

def _extract_ticket_url(raw):
    ti = raw.get("ticket_info")
    url = _first_string_url(ti)
    return url or _first_string_url(raw.get("link"))

def _extract_image(raw):
    img = _first_string_url(raw.get("image"))
    return img or _first_string_url(raw.get("thumbnail"))

def _extract_venue(raw):
    v = raw.get("venue")
    if isinstance(v, str) and v.strip():
        return v.strip()
    if isinstance(v, dict):
        name = v.get("name") or v.get("address")
        if isinstance(name, dict):
            name = name.get("name") or name.get("address")
        if name:
            return str(name)
    if isinstance(v, (list, tuple)):
        for item in v:
            if isinstance(item, dict):
                name = item.get("name") or _coerce_address(item.get("address"))
                if name:
                    return name
            elif isinstance(item, str) and item.strip():
                return item.strip()

    el = raw.get("event_location")
    if isinstance(el, str):
        return el
    if isinstance(el, dict):
        return el.get("name") or _coerce_address(el.get("address"))
    if isinstance(el, (list, tuple)):
        for item in el:
            if isinstance(item, dict):
                name = item.get("name") or _coerce_address(item.get("address"))
                if name:
                    return name
            elif isinstance(item, str) and item.strip():
                return item.strip()

    return ""

def _extract_address(raw):
    addr = raw.get("address")
    if addr:
        return _coerce_address(addr)
    el = raw.get("event_location")
    if isinstance(el, dict):
        return _coerce_address(el.get("address") or el.get("name"))
    if isinstance(el, (list, tuple)):
        for item in el:
            if isinstance(item, dict):
                s = _coerce_address(item.get("address") or item.get("name"))
                if s:
                    return s
            elif isinstance(item, str) and item.strip():
                return item.strip()
    return ""

def _date_field(date_obj, key):
    if not date_obj:
        return None
    if isinstance(date_obj, dict):
        return date_obj.get(key) or date_obj.get("when")
    if isinstance(date_obj, (list, tuple)):
        for item in date_obj:
            if isinstance(item, dict) and (item.get(key) or item.get("when")):
                return item.get(key) or item.get("when")
            if isinstance(item, str):
                return item
    if isinstance(date_obj, str):
        return date_obj
    return None

def normalize_event(raw, category_tag):
    d = raw.get("date", {}) or {}
    start_str = _date_field(d, "start_date")
    end_str   = _date_field(d, "end_date")

    venue_name = _extract_venue(raw)
    address    = _extract_address(raw)
    ticket     = _extract_ticket_url(raw)
    image      = _extract_image(raw)

    return {
        "title": raw.get("title"),
        "start": start_str or "",
        "end": end_str or "",
        "venue": venue_name or address or "",
        "address": address,
        "url": ticket,
        "image": image,
        "category": category_tag,
        "source": "serpapi_google_events",
        "parsed_start": parse_date_safe(start_str),
        "parsed_end": parse_date_safe(end_str),
    }

def should_drop(e, tag: str) -> bool:
    """Category-aware filtering to keep things tourist-friendly."""
    text = " ".join([
        str(e.get("title") or ""),
        str(e.get("venue") or ""),
        str(e.get("address") or "")
    ])

    # General blocks for all categories
    if matches_any(text, FITNESS_RE) or looks_like_interval_walk(text):
        return True
    if matches_any(text, BIZ_RE) or CISO_RE.search(text):  # ← blocks CISO/cybersecurity enterprise events
        return True

    # Require image if configured
    if REQUIRE_IMAGE and not (e.get("image") or "").strip():
        return True

    # Family-specific blocks (no alcohol / adults-only)
    if tag == "family" and (matches_any(text, ALCOHOL_RE, ADULT_RE)):
        return True

    return False

def deduplicate(events):
    seen, out = set(), []
    for e in events:
        key = (
            (e.get("title") or "").strip().lower(),
            (e.get("start") or "").strip(),
            (e.get("venue") or "").strip().lower(),
        )
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out

def filter_future(events):
    cutoff = now - timedelta(days=PAST_GRACE_DAYS)
    return [e for e in events if (e.get("parsed_start") is None) or (e["parsed_start"] >= cutoff)]

def sort_by_start(events):
    return sorted(events, key=lambda e: e.get("parsed_start") or datetime.max)

# -------- Query planning: exactly 2 per category, round-robin within this run --------
def build_query_plan(per_cat: int = 2, max_calls: int = MAX_CALLS_PER_RUN):
    plan = []
    buckets = [("family", QUERIES_BY_BUCKET["family"]),
               ("music", QUERIES_BY_BUCKET["music"]),
               ("general", QUERIES_BY_BUCKET["general"])]
    for i in range(per_cat):
        for tag, qlist in buckets:
            if len(plan) >= max_calls:
                return plan
            if i < len(qlist):
                plan.append((tag, qlist[i]))
    return plan[:max_calls]

# ---------------- Main ----------------
def run_query(tag: str, q: str):
    results = fetch_events(q)
    if not results:
        return []
    normed = [normalize_event(r, tag) for r in results]
    filtered = [e for e in normed if not should_drop(e, tag)]
    filtered = sort_by_start(filter_future(deduplicate(filtered)))[:PER_BUCKET_CAP]
    return filtered

def main():
    all_events = []
    plan = build_query_plan(per_cat=2, max_calls=MAX_CALLS_PER_RUN)
    used = {}
    print("Queries plan:")
    for tag, q in plan:
        print(f"  [{tag}] {q}")
        bucket_events = run_query(tag, q)
        used.setdefault(tag, 0)
        used[tag] += 1
        all_events.extend(bucket_events)

    all_events = deduplicate(all_events)
    all_events = sort_by_start(filter_future(all_events))[:TARGET_EVENTS]

    for e in all_events:
        e.pop("parsed_start", None)
        e.pop("parsed_end", None)

    payload = {
        "source": "serpapi_google_events",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "events": all_events,
    }

    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("-" * 56)
    print(f"Used { _calls_made } call(s). Buckets hit: {used}")
    print(f"✅ Saved {len(all_events)} events to {OUT_PATH}")

if __name__ == "__main__":
    print("▶ Run python get_serpapi_events.py")
    main()
