import os
import json
import requests
from pathlib import Path

# --- Load .env locally if present (for local testing) ---
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
        "Locally: put it in a .env file (GOOGLE_API_KEY=...). "
        "On GitHub: add it as a repo secret and pass it in the workflow."
    )

LAT, LNG = 1.2765, 103.8456         # Tanjong Pagar MRT
RADIUS_METERS = 800                 # adjust if needed
INCLUDED_TYPES = ["restaurant"]     # try also: "cafe", "bar", "tourist_attraction"

NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
TEXT_URL   = "https://places.googleapis.com/v1/places:searchText"

# The FieldMask is required by the new API – list every field you want back
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.rating",
    "places.formattedAddress",
    "places.googleMapsUri"
])

def search_nearby():
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK
    }
    body = {
        "includedTypes": INCLUDED_TYPES,
        "maxResultCount": 20,  # can go up to 20 per call
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

# Try Nearby first; fall back to Text Search if needed
raw = search_nearby() or search_text()

places = []
for p in raw:
    display = p.get("displayName", {}) or {}
    places.append({
        "name": display.get("text"),
        "rating": p.get("rating", "-"),
        "address": p.get("formattedAddress"),
        "place_id": p.get("id"),
        "maps_url": p.get("googleMapsUri")
    })

Path("public/data").mkdir(parents=True, exist_ok=True)
with open("public/data/places.json", "w", encoding="utf-8") as f:
    json.dump(places, f, ensure_ascii=False, indent=2)

print(f"Wrote {len(places)} places to public/data/places.json")
