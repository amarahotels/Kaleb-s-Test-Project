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

# Quota / sizing (override via env if you want)
MAX_CALLS_PER_RUN       = int(os.getenv("EVENTS_MAX_CALLS", "6"))         # total SerpAPI requests per run
TARGET_EVENTS           = int(os.getenv("EVENTS_TARGET_COUNT", "60"))     # keep at most this many after merge
PER_BUCKET_CAP          = int(os.getenv("EVENTS_PER_BUCKET_CAP", "25"))   # cap per category before merge
PER_BUCKET_PER_RUN      = int(os.getenv("EVENTS_PER_BUCKET_PER_RUN", "3"))# rotate this many queries per bucket per run
PAST_GRACE_DAYS         = int(os.getenv("EVENTS_PAST_GRACE_DAYS", "1"))   # keep events that started up to N days ago
KEEP_DAYS               = int(os.getenv("EVENTS_KEEP_DAYS", "45"))        # keep only events within next N days

OUT_PATH   = Path("public/data/events.json")
STATE_PATH = Path("public/data/events_state.json")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

SERP_LOCALE = {"engine": "google_events", "hl": "en", "gl": "sg", "location": "Singapore"}

now = datetime.now()
month_year = now.strftime("%B %Y")

# ---------- Ordered query lists (rotate in order, then wrap) ----------
QUERIES_BY_BUCKET = {
    "family": [
        "carnivals singapore",
#        "indoor playground singapore",
        "family attractions singapore",
        "sentosa family activities",
        "gardens by the bay children activities",
        "zoo events singapore",
#        "science centre singapore events",
        f"family events singapore {month_year}",
#        "family friendly shows singapore",
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
        # "art festivals singapore",
        # "night festival singapore",
    ],
}

# ---------------- Helpers ----------------
_calls_made = 0

def file_json_load(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path: Path, obj):
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def load_state():
    state = file_json_load(STATE_PATH, {})
    cursors = state.get("cursors", {})
    # ensure all buckets exist
    for b in QUERIES_BY_BUCKET.keys():
        cursors.setdefault(b, 0)
    state["cursors"] = cursors
    return state

def save_state(state):
    state["last_run"] = datetime.utcnow().isoformat() + "Z"
    save_json(STATE_PATH, state)

def pick_queries_in_order(state, bucket):
    """Return the next N queries for this bucket, wraparound, and update cursor."""
    all_qs = QUERIES_BY_BUCKET.get(bucket, [])
    if not all_qs:
        return []
    start_idx = state["cursors"].get(bucket, 0) % len(all_qs)
    k = min(PER_BUCKET_PER_RUN, len(all_qs))
    chosen = [all_qs[(start_idx + i) % len(all_qs)] for i in range(k)]
    state["cursors"][bucket] = (start_idx + k) % len(all_qs)
    return chosen

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
    img = raw.get("image")
    if img:
        u = _first_string_url(img)
        if u:
            return u
    return _first_string_url(raw.get("thumbnail"))

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
                nm = item.get("name") or _coerce_address(item.get("address"))
                if nm:
                    return nm
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
                nm = item.get("name") or _coerce_address(item.get("address"))
                if nm:
                    return nm
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

def load_existing(path: Path):
    data = file_json_load(path, {})
    items = data.get("events", [])
    for e in items:
        e["parsed_start"] = parse_date_safe(e.get("start"))
        e["parsed_end"] = parse_date_safe(e.get("end"))
    return items

def within_window(e, now_):
    start = e.get("parsed_start")
    if not start:
        return True
    if start < (now_ - timedelta(days=PAST_GRACE_DAYS)):
        return False
    return start <= (now_ + timedelta(days=KEEP_DAYS))

# ---------------- Main ----------------
def run_bucket(queries, tag):
    bucket = []
    for q in queries:
        if len(bucket) >= PER_BUCKET_CAP or _calls_made >= MAX_CALLS_PER_RUN:
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

def main():
    # 1) choose next queries (rotate) with global call budget
    state = load_state()
    calls_left = MAX_CALLS_PER_RUN
    selected = {}
    for tag in ("family", "music", "general"):
        qs = pick_queries_in_order(state, tag)
        if calls_left <= 0:
            qs = []
        elif len(qs) > calls_left:
            qs = qs[:calls_left]
        selected[tag] = qs
        calls_left -= len(qs)

    # 2) fetch new events for chosen queries
    all_new = []
    for tag in ("family", "music", "general"):
        all_new.extend(run_bucket(selected.get(tag, []), tag))

    # 3) merge with existing file
    existing = load_existing(OUT_PATH)
    combined = deduplicate(existing + all_new)
    combined = [e for e in combined if within_window(e, now)]
    combined = sort_by_start(filter_future(combined))[:TARGET_EVENTS]

    # 4) strip helper fields and save
    for e in combined:
        e.pop("parsed_start", None)
        e.pop("parsed_end", None)

    payload = {
        "source": "serpapi_google_events",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "events": combined,
    }
    save_json(OUT_PATH, payload)
    save_state(state)

    print("--------------------------------------------------")
    print(f"Used {_calls_made} call(s).")
    print(f"Queries run: {selected}")
    print(f"✅ Saved {len(combined)} merged events to {OUT_PATH}")

if __name__ == "__main__":
    main()
