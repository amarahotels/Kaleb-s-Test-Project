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

# Quota/refresh controls (tweak via env vars)
MAX_CALLS_PER_RUN      = int(os.getenv("EVENTS_MAX_CALLS", "6"))        # total SerpAPI requests per run
TARGET_EVENTS          = int(os.getenv("EVENTS_TARGET_COUNT", "60"))    # stop when we have this many
PER_BUCKET_CAP         = int(os.getenv("EVENTS_PER_BUCKET_CAP", "25"))  # max kept from any single bucket

OUT_PATH = Path("public/data/events.json")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

SERP_LOCALE = {"engine": "google_events", "hl": "en", "gl": "sg", "location": "Singapore"}

now = datetime.now()
month_year = now.strftime("%B %Y")

# --- Minimal queries (6 total) ---
FAMILY_QUERIES  = [
    "family activities Singapore",
    f"family events Singapore {month_year}",
]
MUSIC_QUERIES   = [
    f"concerts in Singapore {month_year}",
    "music festivals Singapore",
]
GENERAL_QUERIES = [
    "events in Singapore this week",
    "things to do in Singapore this weekend",
]

PAST_GRACE_DAYS = 1  # keep events that started up to 1 day ago (helps multi-day events)

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
    if not addr:
        return ""
    if isinstance(addr, (list, tuple)):
        return ", ".join([str(x) for x in addr if x])
    return str(addr)

def normalize_event(raw, category_tag):
    d = raw.get("date", {}) or {}
    start_str = d.get("start_date") or d.get("when") or ""
    end_str   = d.get("end_date") or ""

    venue_name = (raw.get("venue") or raw.get("event_location", {}) or {}).get("name")
    address    = _coerce_address(raw.get("address") or raw.get("event_location", {}).get("address"))
    ticket     = (raw.get("ticket_info") or {}).get("link") or raw.get("link")
    image      = raw.get("image") or raw.get("thumbnail")

    return {
        "title": raw.get("title"),
        "start": start_str,
        "end": end_str,
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
s