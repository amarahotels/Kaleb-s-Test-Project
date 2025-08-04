import os
import requests
import json
from datetime import datetime
from dateutil import parser

API_KEY = os.environ.get("SERPAPI_KEY")

QUERIES = [
    "events in Singapore this week",
#    "exhibitions or concerts in Singapore",
    "upcoming tourist attractions in Singapore"
]

def fetch_events(query):
    params = {
        "engine": "google_events",
        "q": query,
        "api_key": API_KEY
    }
    res = requests.get("https://serpapi.com/search", params=params)
    if res.status_code != 200:
        print(f"❌ Failed query: {query} — {res.status_code}")
        return []
    data = res.json()
    return data.get("events_results", [])

def parse_date_safe(date_str):
    if not date_str:
        return None
    try:
        return parser.parse(date_str)
    except:
        return None

def normalize_event(e):
    raw_start = e.get("date", {}).get("start_date", "")
    return {
        "title": e.get("title"),
        "start": raw_start,
        "end": e.get("date", {}).get("end_date", ""),
        "venue": e.get("address"),
        "address": e.get("address"),
        "url": e.get("link"),
        "image": e.get("image") or e.get("thumbnail"),
        "category": e.get("event_location", {}).get("name", ""),
        "source": "google_events",
        "parsed_start": parse_date_safe(raw_start)
    }

def deduplicate(events):
    seen = set()
    unique = []
    for e in events:
        key = (e["title"], e["start"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique

def sort_by_start(events):
    return sorted(events, key=lambda e: e.get("parsed_start") or datetime.max)

# --- MAIN ---
all_events = []
for q in QUERIES:
    print(f"🔍 Searching: {q}")
    raw = fetch_events(q)
    all_events.extend(map(normalize_event, raw))

all_events = deduplicate(all_events)
all_events = sort_by_start(all_events)[:50]

# Remove parsed_start before saving
for e in all_events:
    e.pop("parsed_start", None)

output = {
    "source": "google_events",
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "events": all_events
}

with open("events.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✅ Saved {len(all_events)} events to events.json")
