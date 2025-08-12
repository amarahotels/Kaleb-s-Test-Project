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
        "Locally: put it in a .env file. On GitHub: set as repo secret and expose to workflow."
    )

# --- Location & radius (meters) ---
LAT, LNG = 1.2765, 103.8456
RADIUS_METERS = 800

# --- Categories you want available in the UI ---
INCLUDED_PRIMARY_TYPES = [
    "restaurant",
    "cafe",
    "bakery",
    "pharmacy",
    "supermarket",
    "convenience_store",
    "atm",
    # add more if you expose them in the UI filter
]

NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
TEXT_URL   = "https://places.googleapis.com/v1/places:searchText"

# Ask for everything the front end/filter needs
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.rating",
    "places.userRatingCount",
    "places.formattedAddress",
    "places.googleMapsUri",
    "places.photos.name",
    "places.photos.widthPx",
    "places.photos.heightPx",
    "places.types",
    "places.primaryType",
])

def _headers():
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }

def search_nearby_for(primary_type: str, max_results: int = 20):
    """Nearby Search for one primary type."""
    body = {
        "includedPrimaryTypes": [primary_type],
        "maxResultCount": max_results,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": LAT, "longitude": LNG},
                "radius": float(RADIUS_METERS),
            }
        },
    }
    r = requests.post(NEARBY_URL, headers=_headers(), json=body, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        print(f"Nearby error ({primary_type}):", data["error"].get("message"))
        return []
    return data.get("places", [])

def text_search_fallback(query: str, max_results: int = 20):
    """Optional fallback (usually not needed if nearby returns data)."""
    body = {"textQuery": query, "maxResultCount": max_results}
    r = requests.post(TEXT_URL, headers=_headers(), json=body, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        print("TextSearch error:", data["error"].get("message"))
        return []
    return data.get("places", [])

def first_photo_url(photos, max_h=480, max_w=720):
    """Build public photo URL from Places new Photos API."""
    if not photos:
        return None
    name = (photos[0] or {}).get("name")
    if not name:
        return None
    return f"https://places.googleapis.com/v1/{name}/media?maxHeightPx={max_h}&maxWidthPx={max_w}&key={API_KEY}"

# ---- Fetch + dedupe across all categories ----
raw_by_id = {}

for t in INCLUDED_PRIMARY_TYPES:
    try:
        results = search_nearby_for(t)
        for p in results:
            pid = p.get("id")
            if not pid:
                continue
            # last one wins — fine for our purpose
            raw_by_id[pid] = p
    except requests.RequestException as e:
        print(f"Request failed for {t}: {e}")

# Optional fallback if nothing came back at all
if not raw_by_id:
    for p in text_search_fallback("restaurants near Tanjong Pagar, Singapore"):
        pid = p.get("id")
        if pid:
            raw_by_id[pid] = p

# ---- Transform for front-end ----
places = []
for p in raw_by_id.values():
    display = p.get("displayName") or {}
    photo_url = first_photo_url(p.get("photos"))
    places.append({
        "name": display.get("text"),
        "rating": p.get("rating"),
        "rating_count": p.get("userRatingCount"),
        "address": p.get("formattedAddress"),
        "place_id": p.get("id"),
        "maps_url": p.get("googleMapsUri"),
        "photo_url": photo_url,
        "types": p.get("types", []),
        "primary_type": p.get("primaryType"),
    })

# Sort by rating (desc), then rating_count (desc) to keep it tidy
places.sort(key=lambda x: ((x.get("rating") or 0), (x.get("rating_count") or 0)), reverse=True)

# ---- Write JSON for the site ----
Path("public/data").mkdir(parents=True, exist_ok=True)
out_path = Path("public/data/places.json")
with out_path.open("w", encoding="utf-8") as f:
    json.dump(places, f, ensure_ascii=False, indent=2)

print(f"Wrote {len(places)} places to {out_path}")
