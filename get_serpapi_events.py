import os
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
TARGET_EVENTS          = int(os.getenv("EVENTS_TARGET_COUNT", "60"))    # stop when we have this many
PER_BUCKET_CAP         = int(os.getenv("EVENTS_PER_BUCKET_CAP", "25"))  # max kept from any single bucket

OUT_PATH = Path("public/data/events.json")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

SERP_LOCALE = {"engine": "google_events", "hl": "en", "gl": "sg", "location": "Singapore"}

now = datetime.now()
month_year = now.strftime("%B %Y")

# --- Tourist-leaning queries ---
FAMILY_QUERIES = [
    # venue / attraction anchored + event-y phrasing
    "sentosa events",
    "gardens by the bay events",
    "mandai wildlife events",                 # Zoo / River Wonders / Bird Paradise
    "singapore zoo events",
    "bird paradise events",
    "artscience museum exhibitions",
    "science centre singapore events",
    "children's museum singapore events",
    "jewel changi events",
    "marina bay events family",
    f"kids events singapore {month_year}",
    "family friendly events singapore",
]
MUSIC_QUERIES = [
    f"concerts in Singapore {month_year}",
    "music festivals singapore",
    "live music singapore weekend",
    "classical concert singapore",
    "indie concert singapore",
    "dj events singapore",
]
GENERAL_QUERIES = [
    "events in Singapore this week",
    "things to do in Singapore this weekend",
    f"exhibitions in Singapore {month_year}",
    "festivals in singapore",
    "night festival singapore",
]

PAST_GRACE_DAYS = 1  # keep events that started up to 1 day ago (helps multi-day events)

# --- Heuristics to prefer tourist-friendly family items ---
TOURISTY_TITLE_WORDS = [
    "festival","carnival","exhibition","exhibit","show","performance","parade",
    "fireworks","light","illumination","spectacular","playtime","kidsfest","open house"
]
TOURISTY_VENUE_WORDS = [
    "sentosa","gardens by the bay","mandai","singapore zoo","river wonders","bird paradise",
    "jewel","changi","marina bay sands","marina bay","esplanade","artscience museum",
    "science centre","children's museum","sports hub","national stadium","marina barrage",
    "sea aquarium","s.e.a. aquarium","universal studios","uss","vivo city","vivocity",
    "harbourfront","bayfront","orchard","singapore flyer"
]
DEMOTE_SMALL_TITLE_WORDS = [
    "workshop","course","class","seminar","talk","lecture","meetup","parenting",
    "book club","reading","tuition","coaching","support group"
]
DEMOTE_LOCAL_VENUE_WORDS = [
    "community club","cc","library","hdb","void deck","rc centre","resident committee",
    "secondary school","primary school","student care","kindergarten"
]

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
    """Return first plausible URL from value that can be str|list|dict."""
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
    img = raw.get("image")
    if img:
        url = _first_string_url(img)
        if url:
            return url
    thumb = raw.get("thumbnail")
    return _first_string_url(thumb)

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
    """Safely get date field from dict|list|str shapes."""
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
        "category": category_tag,  # 'family' | 'music' | 'general'
        "source": "serpapi_google_events",
        "parsed_start": parse_date_safe(start_str),
        "parsed_end": parse_date_safe(end_str),
    }

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

# --- Tourist preference scoring (family bucket) ---
def tourist_score(e) -> int:
    title = (e.get("title") or "").lower()
    where = f"{(e.get('venue') or '').lower()} | {(e.get('address') or '').lower()}"
    score = 0

    if any(w in title for w in TOURISTY_TITLE_WORDS):
        score += 4
    if any(w in where for w in TOURISTY_VENUE_WORDS):
        score += 3
    if e.get("image"):
        score += 1

    if any(w in title for w in DEMOTE_SMALL_TITLE_WORDS):
        score -= 3
    if any(w in where for w in DEMOTE_LOCAL_VENUE_WORDS):
        score -= 3

    return score

def prefer_touristy_family(bucket):
    if not bucket:
        return bucket
    # keep only items with an image for nicer cards
    with_img = [e for e in bucket if e.get("image")]
    pool = with_img if len(with_img) >= 6 else bucket  # fallback if too few images

    pool.sort(key=lambda e: (-tourist_score(e), e.get("parsed_start") or datetime.max))
    return pool[:PER_BUCKET_CAP]

# ---------------- Main ----------------
def run_bucket(queries, tag):
    bucket = []
    for q in queries:
        if len(bucket) >= PER_BUCKET_CAP or len(all_events) >= TARGET_EVENTS or _calls_made >= MAX_CALLS_PER_RUN:
            break
        print(f"🔍 [{tag}] {q}")
        results = fetch_events(q)
        if not results:
            continue
        bucket.extend(normalize_event(r, tag) for r in results)
        bucket = deduplicate(bucket)
        bucket = sort_by_start(filter_future(bucket))[:PER_BUCKET_CAP]

    # Tourist preference just for the family bucket
    if tag == "family":
        bucket = prefer_touristy_family(bucket)

    print(f"→ Bucket '{tag}': kept {len(bucket)}")
    return bucket

all_events = []
for queries, tag in (
    (FAMILY_QUERIES, "family"),
    (MUSIC_QUERIES, "music"),
    (GENERAL_QUERIES, "general"),
):
    all_events.extend(run_bucket(queries, tag))
    if len(all_events) >= TARGET_EVENTS or _calls_made >= MAX_CALLS_PER_RUN:
        break

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

print(f"✅ Saved {len(all_events)} events to {OUT_PATH} using {_calls_made} call(s).")
