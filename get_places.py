import os
import json
import requests
from pathlib import Path

# --- Load .env locally if present (optional) ---
env_path = Path(".env")
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path)
    except ImportError:
        pass

API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "GOOGLE_API_KEY is not set. "
        "Locally: .env file. On GitHub: repo secret and env in workflow."
    )

LAT, LNG = 1.2765, 103.8456
RADIUS_METERS = 800
INCLUDED_TYPES = ["restaurant"]

NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
TEXT_URL   = "https://places.googleapis.com/v1/places:searchText"

# IMPORTANT: request the photo metadata so we can build a media URL
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.rating",
    "places.formattedAddress",
    "places.googleMapsUri",
    "places.photos.name",
    "places.photos.widthPx",
    "places.photos.heightPx"
])

def search_nearby():
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK
    }
    body = {
        "includedTypes": INCLUDED_TYPES,
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": LAT, "longitude": LNG},
                "radius": float(RADIUS_METERS)
            }
        }
    }
    r = requests.post(NEARBY_URL, headers=headers, json=body, timeout=30)
    data = r.json()
    if "error" in data:
        print("Nearby error:", data["error"].get("message"))
        return []
    return data.get("places", [])

def search_text():
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK
    }
    body = {
        "textQuery": "restaurants near Tanjong Pagar, Singapore",
        "maxResultCount": 20
    }
    r = requests.post(TEXT_URL, headers=headers, json=body, timeout=30)
    data = r.json()
    if "error" in data:
        print("TextSearch error:", data["error"].get("message"))
        return []
    return data.get("places", [])

def first_photo_url(photos, max_h=240, max_w=320):
    """
    Build a public photo URL for the <img> tag using the Places (New) media endpoint.
    This includes your API key in the query string — restrict the key by HTTP referrers.
    """
    if not photos:
        return None
    name = photos[0].get("name")  # e.g., "places/ChIJ.../photos/AbCd..."
    if not name:
        return None
    return f"https://places.googleapis.com/v1/{name}/media?maxHeightPx={max_h}&maxWidthPx={max_w}&key={API_KEY}"

# ---- Fetch and transform ----
raw = search_nearby() or search_text()

places = []
for p in raw:
    display = p.get("displayName") or {}
    photo_url = first_photo_url(p.get("photos"))
    places.append({
        "name": display.get("text"),
        "rating": p.get("rating", "-"),
        "address": p.get("formattedAddress"),
        "place_id": p.get("id"),
        "maps_url": p.get("googleMapsUri"),
        "photo_url": photo_url  # NEW
    })

Path("public/data").mkdir(parents=True, exist_ok=True)
with open("public/data/places.json", "w", encoding="utf-8") as f:
    json.dump(places, f, ensure_ascii=False, indent=2)

print(f"Wrote {len(places)} places to public/data/places.json")

# testing the cost of the API call
