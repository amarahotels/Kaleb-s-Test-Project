import os
import json
import time
from datetime import datetime, timezone
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

NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
TEXT_URL   = "https://places.googleapis.com/v1/places:searchText"

# Ask only for fields the front end needs (+ nextPageToken for paging)
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
    "nextPageToken",
])

def _headers():
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }

# ---------------- Buckets ----------------
BUCKETS = {
    "restaurants": [
        "restaurant", "brunch_restaurant", "italian_restaurant",
        "pizza_restaurant", "japanese_restaurant", "chinese_restaurant",
        "thai_restaurant", "korean_restaurant", "indian_restaurant",
        "french_restaurant", "seafood_restaurant", "steak_house",
        "barbecue_restaurant",
    ],
    "cafes": [
        "cafe", "coffee_shop", "tea_house",
    ],
    "bars": [
        "bar", "cocktail_bar", "wine_bar", "beer_bar", "pub", "speakeasy",
    ],
}

TEXT_QUERIES = {
    "restaurants": [
        "best restaurants near Tanjong Pagar",
        "dinner near Tanjong Pagar",
        "lunch near Tanjong Pagar",
    ],
    "cafes": [
        "best cafes near Tanjong Pagar",
        "coffee near Tanjong Pagar",
        "brunch near Tanjong Pagar",
    ],
    "bars": [
        "best bars near Tanjong Pagar",
        "cocktails near Tanjong Pagar",
        "wine bars near Tanjong Pagar",
    ],
}

# 👉 Hawker fetch configuration
HAWKER_TYPES = ["food_court"]  # includedTypes
HAWKER_TEXT_QUERIES = [
    "hawker centre near Tanjong Pagar",
    "hawker center near Tanjong Pagar",
    "food centre near Tanjong Pagar",
    "food center near Tanjong Pagar",
    "Lau Pa Sat",
    "Maxwell Food Centre",
    "Amoy Street Food Centre",
    "Chinatown Complex",
    "Chinatown Hawker Centre",
]

# Canonical centre names (lowercase)
HAWKER_NAME_SET = {
    "lau pa sat",
    "maxwell food centre",
    "maxwell food center",
    "amoy street food centre",
    "amoy street food center",
    "chinatown complex",
    "chinatown hawker centre",
    "chinatown hawker center",
}

EXCLUDED_PRIMARY = {"lodging"}  # and anything containing "hotel"

def is_allowed_primary(primary: str) -> bool:
    p = (primary or "").lower()
    if p in EXCLUDED_PRIMARY or "hotel" in p:
        return False
    # allow dining + hawker
    return p in ("cafe", "bar", "food_court") or ("restaurant" in p)

# ---- Nearby with pagination (PRIMARY TYPES) ----
MAX_PAGES_PER_CHUNK = 3          # up to 3 pages per chunk
PAGE_DELAY_SEC = 2.0             # token warm-up
PER_PAGE = 20                    # Places API limit per page

def nearby_all_pages(included_primary_types):
    """Search with includedPrimaryTypes (good for restaurant/cafe/bar primaries)."""
    items = []
    page_token = None
    for _ in range(MAX_PAGES_PER_CHUNK):
        body = {
            "includedPrimaryTypes": included_primary_types,
            "maxResultCount": PER_PAGE,
            "rankPreference": "POPULARITY",
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": LAT, "longitude": LNG},
                    "radius": float(RADIUS_METERS),
                }
            },
        }
        if page_token:
            body["pageToken"] = page_token

        r = requests.post(NEARBY_URL, headers=_headers(), json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            print(f"Nearby error ({included_primary_types}):", data["error"].get("message"))
            break

        items.extend(data.get("places", []) or [])

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(PAGE_DELAY_SEC)
    return items

# ---- Nearby with pagination (TYPES) ----
def nearby_all_pages_types(included_types):
    """Search with includedTypes (needed for hawker 'food_court')."""
    items = []
    page_token = None
    for _ in range(MAX_PAGES_PER_CHUNK):
        body = {
            "includedTypes": included_types,
            "maxResultCount": PER_PAGE,
            "rankPreference": "POPULARITY",
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": LAT, "longitude": LNG},
                    "radius": float(RADIUS_METERS),
                }
            },
        }
        if page_token:
            body["pageToken"] = page_token

        r = requests.post(NEARBY_URL, headers=_headers(), json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            print(f"Nearby(types) error ({included_types}):", data["error"].get("message"))
            break

        items.extend(data.get("places", []) or [])

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(PAGE_DELAY_SEC)
    return items

def text_search(query):
    body = {
        "textQuery": query,
        "maxResultCount": 20,
        "locationBias": {
            "circle": {
                "center": {"latitude": LAT, "longitude": LNG},
                "radius": float(RADIUS_METERS),
            }
        }
    }
    r = requests.post(TEXT_URL, headers=_headers(), json=body, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        print("TextSearch error:", data["error"].get("message"))
        return []
    return data.get("places", []) or []

def first_photo_url(photos, max_h=480, max_w=720):
    if not photos:
        return None
    name = (photos[0] or {}).get("name")
    if not name:
        return None
    return f"https://places.googleapis.com/v1/{name}/media?maxHeightPx={max_h}&maxWidthPx={max_w}&key={API_KEY}"

def better(a, b):
    ar, br = a.get("userRatingCount") or 0, b.get("userRatingCount") or 0
    if ar != br:
        return a if ar > br else b
    ra, rb = a.get("rating") or 0, b.get("rating") or 0
    return a if ra >= rb else b

def _norm(s: str) -> str:
    return (s or "").strip().lower()

def is_hawker_centre_place(p: dict) -> bool:
    """True only for *centres* (not stalls)."""
    primary = _norm(p.get("primaryType"))
    types = [_norm(t) for t in (p.get("types") or [])]
    name = _norm((p.get("displayName") or {}).get("text") or "")
    return (
        primary == "food_court" or
        "food_court" in types or
        name in HAWKER_NAME_SET
    )

# ---- Fetch & blend per bucket ----
raw_by_id = {}

# 1) Restaurants/Cafes/Bars via includedPrimaryTypes (+ paging) and text queries
for bucket_name, types in BUCKETS.items():
    # split into chunks of <=10 primary types (API limit)
    for i in range(0, len(types), 10):
        sub = types[i:i+10]
        try:
            for p in nearby_all_pages(sub):
                primary = (p.get("primaryType") or "").lower()
                if not is_allowed_primary(primary):
                    continue
                pid = p.get("id")
                if not pid:
                    continue
                raw_by_id[pid] = better(raw_by_id.get(pid, p), p)
        except requests.RequestException as e:
            print(f"Nearby failed for {sub}: {e}")

    # add a few text-search results to diversify
    for tq in TEXT_QUERIES[bucket_name]:
        try:
            for p in text_search(tq):
                primary = (p.get("primaryType") or "").lower()
                if not is_allowed_primary(primary):
                    continue
                pid = p.get("id")
                if not pid:
                    continue
                raw_by_id[pid] = better(raw_by_id.get(pid, p), p)
        except requests.RequestException as e:
            print(f"TextSearch failed for '{tq}': {e}")

# 2) Hawker centres via includedTypes + biased text searches (centres only)
try:
    for p in nearby_all_pages_types(HAWKER_TYPES):
        if not is_hawker_centre_place(p):
            continue
        pid = p.get("id")
        if not pid:
            continue
        raw_by_id[pid] = better(raw_by_id.get(pid, p), p)
except requests.RequestException as e:
    print(f"Nearby(types) failed for hawkers: {e}")

for q in HAWKER_TEXT_QUERIES:
    try:
        for p in text_search(q):
            if not is_hawker_centre_place(p):
                continue
            pid = p.get("id")
            if not pid:
                continue
            raw_by_id[pid] = better(raw_by_id.get(pid, p), p)
    except requests.RequestException as e:
        print(f"TextSearch failed for hawker '{q}': {e}")

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
        "is_hawker_centre": is_hawker_centre_place(p),  # <-- used by frontend filter
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
