import os
import requests
import json
from datetime import datetime
from bs4 import BeautifulSoup

API_KEY = os.environ.get("SERPAPI_KEY")
QUERY = "events in Singapore this weekend"

params = {
    "engine": "google_events",
    "q": QUERY,
    "api_key": API_KEY
}

def fetch_og_image(url):
    try:
        res = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.text, "html.parser")
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            return og["content"]
    except Exception as e:
        print(f"⚠️ Failed to fetch OG image for {url}: {e}")
    return None

res = requests.get("https://serpapi.com/search", params=params)
data = res.json()

events = []
for e in data.get("events_results", []):
    link = e.get("link")
    fallback_thumbnail = e.get("thumbnail", "")
    high_res_image = fetch_og_image(link) or fallback_thumbnail or "images/default_event.jpg"

    events.append({
        "title": e.get("title"),
        "start": e.get("date", {}).get("start_date", ""),
        "end": e.get("date", {}).get("end_date", ""),
        "venue": e.get("address"),
        "address": e.get("address"),
        "url": link,
        "image": high_res_image,
        "category": e.get("event_location", {}).get("name", ""),
        "source": "google_events"
    })

output = {
    "source": "google_events",
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "events": events
}

# Make sure it's saving to the right place
output_path = os.path.join("public", "data", "events.json")
os.makedirs(os.path.dirname(output_path), exist_ok=True)

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✅ Saved {len(events)} events to {output_path}")
