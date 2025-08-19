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

MAX_CALLS_PER_RUN      = int(os.getenv("EVENTS_MAX_CALLS", "6"))        # total SerpAPI requests per run
TARGET_EVENTS          = int(os.getenv("EVENTS_TARGET_COUNT", "60"))    # final cap
PER_BUCKET_CAP         = int(os.getenv("EVENTS_PER_BUCKET_CAP", "25"))  # per-bucket keep cap
QUERIES_PER_BUCKET_RUN = int(os.getenv("EVENTS_QUERIES_PER_BUCKET", "2"))

OUT_PATH = Path("public/data/events.json")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

SERP_LOCALE = {"engine": "google_events", "hl": "en", "gl": "sg", "location": "Singapore"}

now = datetime.now()
month_year = now.strftime("%B %Y")

# ---------- Query buckets ----------
QUERIES_BY_BUCKET = {
    "family": [
        # tourist-centric
        "sentosa events",
        "gardens by the bay events",
        "mandai wildlife events",
        "singapore zoo events",
        "bird paradise events",
        "artscience museum exhibitions",
        # seasonal/backup
        f"family events singapore {month_year}",
        "family attractions singapore",
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
        "marina bay events",
        "esplanade events",
    ],
}

PAST_GRACE_DAYS = 1  # allow multi-day events that started yesterday

# ---------- Tourist bias for family ----------
TOURIST_ATTR = [
    "sentosa","siloso","palawan","resorts world","universal studios","uss",
    "gardens by the bay","flower dome","cloud forest","satay by the bay",
    "mandai","wildlife","singapore zoo","bird paradise","river wonders","night safari",
    "artscience museum","marina bay sands","marina barrage","singapore flyer",
    "national museum","asian civilizations museum","acm","esplanade","sea aquarium","s.e.a. aquarium",
]
TOURIST_THEMES = ["festival","carnival","light show","illumina","lantern","orchid","garden rhapsody","fireworks","beach festival","exhibition","tour"]

# ---------------- Helpers ----------------
_calls_made = 0

def fetch_events(query: str):
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
    return (r.json() or {}).get("events_results", []) or []

def parse_date_safe(s):
    if not s: return None
    try: return parser.parse(s)
    except Exception: return None

def _coerce_address(addr):
    if not addr: return ""
    if isinstance(addr, str): return addr
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
    if not value: return None
    if isinstance(value, str): return value
    if isinstance(value, dict):
        for k in ("link","url","image","src"):
            v = value.get(k)
            if isinstance(v, str) and v: return v
    if isinstance(value, (list, tuple)):
        for item in value:
            u = _first_string_url(item)
            if u: return u
    return None

def _extract_ticket_url(raw):
    return _first_string_url(raw.get("ticket_info")) or _first_string_url(raw.get("link"))

def _extract_image(raw):
    return _first_string_url(raw.get("image")) or _first_string_url(raw.get("thumbnail"))

def _extract_venue(raw):
    v = raw.get("venue")
    if isinstance(v, str) and v.strip(): return v.strip()
    if isinstance(v, dict):
        name = v.get("name") or v.get("address")
        if isinstance(name, dict): name = name.get("name") or name.get("address")
        if name: return str(name)
    if isinstance(v, (list, tuple)):
        for item in v:
            if isinstance(item, dict):
                name = item.get("name") or _coerce_address(item.get("address"))
                if name: return name
            elif isinstance(item, str) and item.strip():
                return item.strip()
    el = raw.get("event_location")
    if isinstance(el, str): return el
    if isinstance(el, dict): return el.get("name") or _coerce_address(el.get("address"))
    if isinstance(el, (list, tuple)):
        for item in el:
            if isinstance(item, dict):
                name = item.get("name") or _coerce_address(item.get("address"))
                if name: return name
            elif isinstance(item, str) and item.strip():
                return item.strip()
    return ""

def _extract_address(raw):
    addr = raw.get("address")
    if addr: return _coerce_address(addr)
    el = raw.get("event_location")
    if isinstance(el, dict):
        return _coerce_address(el.get("address") or el.get("name"))
    if isinstance(el, (list, tuple)):
        for item in el:
            if isinstance(item, dict):
                s = _coerce_address(item.get("address") or item.get("name"))
                if s: return s
            elif isinstance(item, str) and item.strip():
                return item.strip()
    return ""

def _date_field(date_obj, key):
    if not date_obj: return None
    if isinstance(date_obj, dict): return date_obj.get(key) or date_obj.get("when")
    if isinstance(date_obj, (list, tuple)):
        for item in date_obj:
            if isinstance(item, dict) and (item.get(key) or item.get("when")):
                return item.get(key) or item.get("when")
            if isinstance(item, str): return item
    if isinstance(date_obj, str): return date_obj
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

def deduplicate(events):
    seen, out = set(), []
    for e in events:
        key = ((e.get("title") or "").strip().lower(),
               (e.get("start") or "").strip(),
               (e.get("venue") or "").strip().lower())
        if key not in seen:
            seen.add(key); out.append(e)
    return out

def filter_future(events):
    cutoff = now - timedelta(days=PAST_GRACE_DAYS)
    return [e for e in events if (e.get("parsed_start") is None) or (e["parsed_start"] >= cutoff)]

def sort_by_start(events):
    return sorted(events, key=lambda e: e.get("parsed_start") or datetime.max)

def _is_tourist_friendly(e):
    text = " ".join([
        (e.get("title") or ""), (e.get("venue") or ""), (e.get("address") or "")
    ]).lower()
    if any(k in text for k in TOURIST_ATTR): return True
    if any(k in text for k in TOURIST_THEMES): return True
    return False

# ---------- Round-robin helpers ----------
def load_cursor():
    if not OUT_PATH.exists(): return {}
    try:
        data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        return data.get("_cursor", {}) or {}
    except Exception:
        return {}

def next_queries_for_bucket(bucket_name, all_queries, cursor, n_each):
    if not all_queries: return [], cursor.get(bucket_name, 0), 0
    start = cursor.get(bucket_name, 0) % len(all_queries)
    picked = []
    for i in range(min(n_each, len(all_queries))):
        picked.append(all_queries[(start + i) % len(all_queries)])
    # num actually planned (may be less than n_each if list short)
    return picked, start, len(picked)

# ---------------- Main ----------------
cursor_in = load_cursor()
new_cursor = dict(cursor_in)  # will update per bucket
all_events = []

order = ("family","music","general")
planned = {}

# Choose queries for each bucket (round-robin)
for b in order:
    q_list = QUERIES_BY_BUCKET.get(b, [])
    selected, start_idx, sz = next_queries_for_bucket(b, q_list, cursor_in, QUERIES_PER_BUCKET_RUN)
    planned[b] = selected
    # advance cursor by planned size; we may reduce later if we run out of calls mid-bucket
    if q_list:
        new_cursor[b] = (start_idx + sz) % len(q_list)

print("Queries to run:", planned)

_calls_made = 0

for b in order:
    bucket_queries = planned.get(b, [])
    if not bucket_queries: 
        continue
    bucket = []
    used_from_bucket = 0
    for q in bucket_queries:
        if _calls_made >= MAX_CALLS_PER_RUN or len(all_events) >= TARGET_EVENTS:
            break
        print(f"🔍 [{b}] {q}")
        results = fetch_events(q)
        used_from_bucket += 1
        if not results:
            continue
        bucket.extend(normalize_event(r, b) for r in results)
        bucket = deduplicate(bucket)
        bucket = sort_by_start(filter_future(bucket))[:PER_BUCKET_CAP]

    # if we broke early, roll back the cursor advance we predicted above
    real_used = used_from_bucket
    if real_used < len(bucket_queries) and QUERIES_BY_BUCKET.get(b):
        # step back the unused
        back = (len(bucket_queries) - real_used) % len(QUERIES_BY_BUCKET[b])
        new_cursor[b] = (new_cursor.get(b, 0) - back) % len(QUERIES_BY_BUCKET[b])

    # tourist-friendly bias for family
    if b == "family":
        bucket = [e for e in bucket if _is_tourist_friendly(e)]

    print(f"→ Bucket '{b}': kept {len(bucket)}")
    all_events.extend(bucket)

    if _calls_made >= MAX_CALLS_PER_RUN or len(all_events) >= TARGET_EVENTS:
        break

# Final tidy & save
all_events = deduplicate(all_events)
all_events = sort_by_start(filter_future(all_events))[:TARGET_EVENTS]
for e in all_events:
    e.pop("parsed_start", None); e.pop("parsed_end", None)

payload = {
    "source": "serpapi_google_events",
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "_cursor": new_cursor,        # <-- persists rotation indices
    "events": all_events,
}

with OUT_PATH.open("w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

print(f"✅ Saved {len(all_events)} events to {OUT_PATH} using {_calls_made} call(s).")
