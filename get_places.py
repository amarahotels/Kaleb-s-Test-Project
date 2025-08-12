import os
import json
from datetime import datetime, timezone
import requests
from pathlib import Path
from itertools import islice

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

# -------- CATEGORY SCHEME --------
# Anything that contains these keywords is allowed
ALLOWED_FAMILIES = ("restaurant", "cafe", "bar")

# Be explicit with search types to catch common subtypes
SEARCH_TYPES = [
    # restaurants
    "restaurant", "brunch_restaurant", "italian_restaurant", "pizza_restaurant",
    "japanese_restaurant", "chinese_restaurant", "thai_restaurant", "korean_restaurant",
    "indian_restaurant", "french_restaurant", "seafood_restaurant",
    # cafes / coffee
    "cafe", "coffee_shop",
    # bars
    "bar", "wine_bar", "beer_bar", "pub",
]

def _chunks(iterable, size):
    it = iter(iterable)
    while True:
        chunk = list(islice(it, size))
        if not chunk:
            return
        yield chunk

def search_nearby_types(included_types, max_results=20):
    """
    Call searchNearby using includedTypes (up to 10 per request).
    """
    body = {
        "includedTypes": included_types,
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
        print(f"Nearby error ({included_types}):", data["error"].get("message"))
        return []
    return data.get("places", [])

def text_search_fallback(query: str, max_results: int = 20):
    body = {"textQuery": query, "maxResultCount": max_results}
    r = requests.post(TEXT_URL, headers=_headers(), json=body, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        print("TextSearch error:", data["error"].get("message"))
        return []
    return data.get("places", [])

def first_photo_url(photos, max_h=480, max_w=720):
    if not photos:
        return None
    name = (photos[0] or {}).get("name")
    if not name:
        return None
    return f"https://places.googleapis.com/v1/{name}/media?maxHeightPx={max_h}&maxWidthPx={max_w}&key={API_KEY}"

def is_allowed_place(p: dict) -> bool:
    types = [t.lower() for t in (p.get("types") or [])]
    primary = (p.get("primaryType") or "").lower()
    if any(fam in primary for fam in ALLOWED_FAMILIES):
        return True
    return any(any(fam in t for fam in ALLOWED_FAMILIES) for t in types)

def better(a, b):
    """Return the 'better' place record (higher rating_count, then rating)."""
    ar, br = a.get("userRatingCount") or 0, b.get("userRatingCount") or 0
    if ar != br:
        return a if ar > br else b
    ra, rb = a.get("rating") or 0, b.get("rating") or 0
    return a if ra >= rb else b

# ---- Fetch + dedupe (only our desired types) ----
raw_by_id = {}

try:
    # search in chunks of up to 10 types
    for chunk in _chunks(SEARCH_TYPES, 10):
        results = search_nearby_types(chunk, max_results=20)
        for p in results:
            if not is_allowed_place(p):
                continue
            pid = p.get("id")
            if not pid:
                continue
            # dedupe: keep the better one
            if pid in raw_by_id:
                raw_by_id[pid] = better(raw_by_id[pid], p)
            else:
                raw_by_id[pid] = p
except requests.RequestException as e:
    print(f"Request failed: {e}")

# Optional fallback (rarely needed)
if not raw_by_id:
    for p in text_search_fallback("restaurants, cafes, bars near Tanjong Pagar, Singapore"):
        if is_allowed_place(p):
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

# Sort by rating then rating_count
places.sort(key=lambda x: ((x.get("rating") or 0), (x.get("rating_count") or 0)), reverse=True)

# ---- Write JSON ----
Path("public/data").mkdir(parents=True, exist_ok=True)
meta = {"generated_at": datetime.now(timezone.utc).isoformat()}
out = {"meta": meta, "places": places}

with open("public/data/places.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"Wrote {len(places)} places to public/data/places.json (with metadata)")
