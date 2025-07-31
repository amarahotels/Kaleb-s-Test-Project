import os
import requests
import json
from datetime import datetime

# Setup
API_KEY = os.environ.get("SERPAPI_KEY")
QUERY = "events in Singapore this weekend"
IMAGE_DIR = "public/data/event_images"
EVENTS_JSON_PATH = "public/data/events.json"

# Ensure directory exists
os.makedirs(IMAGE_DIR, exist_ok=True)

# Query SerpAPI
params = {
    "engine": "google_events",
    "q": QUERY,
    "api_key": API_KEY
}
res = requests.get("https://serpapi.com/search", params=params)
data = res.json()

# Extract events and download images
events = []
for i, e in enumerate(data.get("events_results", [])):
    title = e.get("title")
    image_url = e.get("thumbnail")
    image_path = ""

    if image_url:
        try:
            img_data = requests.get(image_url, timeout=10).content
            image_filename = f"event_{i+1}.jpg"
            image_path = f"{IMAGE_DIR}/{image_filename}"
            with open(image_path, "wb") as img_file:
                img_file.write(img_data)
            # For frontend JSON, use relative public path
            image_path = f"/data/event_images/{image_filename}"
        except Exception as err:
            print(f"❌ Failed to download image {image_url}: {err}")
            image_path = ""  # fallback to empty string

    events.append({
        "title": title,
        "start": e.get("date", {}).get("start_date", ""),
        "end": e.get("date", {}).get("end_date", ""),
        "venue": e.get("address"),
        "address": e.get("address"),
        "url": e.get("link"),
        "image": image_path,
        "category": e.get("event_location", {}).get("name", ""),
        "source": "google_events"
    })

# Save JSON
output = {
    "source": "google_events",
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "events": events
}
with open(EVENTS_JSON_PATH, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✅ Saved {len(events)} events to {EVENTS_JSON_PATH}")
