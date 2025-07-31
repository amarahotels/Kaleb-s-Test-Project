import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime

# Load SERPAPI key from env
API_KEY = os.environ.get("SERPAPI_KEY")
QUERY = "events in Singapore this weekend"

# Create image directory if it doesn't exist
os.makedirs("public/data/event_images", exist_ok=True)

# SerpAPI search parameters
params = {
    "engine": "google_events",
    "q": QUERY,
    "api_key": API_KEY
}

# Step 1: Call SerpAPI
res = requests.get("https://serpapi.com/search", params=params)
data = res.json()

def get_high_res_image(event_url):
    """Scrape high-res image from event page using og:image"""
    try:
        resp = requests.get(event_url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        tag = soup.find("meta", property="og:image")
        if tag and tag.get("content"):
            return tag["content"]
    except:
        pass
    return None

def download_image(image_url, index):
    """Download image to local directory and return local path"""
    try:
        resp = requests.get(image_url, stream=True, timeout=10)
        ext = os.path.splitext(urlparse(image_url).path)[1] or ".jpg"
        filename = f"event_{index}{ext}"
        filepath = f"public/data/event_images/{filename}"
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(1024):
                f.write(chunk)
        return f"/data/event_images/{filename}"
    except:
        return ""

# Step 2: Extract & download events
events = []
for idx, e in enumerate(data.get("events_results", [])):
    url = e.get("link")
    fallback_thumb = e.get("thumbnail", "")
    og_image = get_high_res_image(url) or fallback_thumb
    local_image_path = download_image(og_image, idx)

    events.append({
        "title": e.get("title"),
        "start": e.get("date", {}).get("start_date", ""),
        "end": e.get("date", {}).get("end_date", ""),
        "venue": e.get("address"),
        "address": e.get("address"),
        "url": url,
        "image": local_image_path,  # 🔁 Now points to local Firebase-hosted file
        "category": e.get("event_location", {}).get("name", ""),
        "source": "google_events"
    })

# Step 3: Save final JSON to public/data/
output = {
    "source": "google_events",
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "events": events
}

with open("public/data/events.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✅ Saved {len(events)} events and downloaded images to public/data")
