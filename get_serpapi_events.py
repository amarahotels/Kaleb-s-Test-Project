# get_serpapi_events.py
import os
import requests
import json
from datetime import datetime

API_KEY = os.environ.get("SERPAPI_KEY")
QUERY = "events in Singapore this weekend"

params = {
    "engine": "google_events",
    "q": QUERY,
    "api_key": API_KEY
}

res = requests.get("https://serpapi.com/search", params=params)
data = res.json()

events = []
for e in data.get("events_results", []):
    events.append({
        "title": e.get("title"),
        "start": e.get("date", {}).get("start_date", ""),
        "end": e.get("date", {}).get("end_date", ""),
        "venue": e.get("address"),
        "address": e.get("address"),
        "url": e.get("link"),
        "image": e.get("thumbnail"),
        "category": e.get("event_location", {}).get("name", ""),
        "source": "google_events"
    })

output = {
    "source": "google_events",
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "events": events
}

with open("events.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✅ Saved {len(events)} events to events.json")
