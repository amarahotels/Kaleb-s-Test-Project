import os
import json
import math
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
LAT, LNG = 1.2765, 103.8456     # Amara / Tanjong Pagar area
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
    "places.location",            # <-- needed for distance
    "nextPageToken",
])

def _headers():
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }

# ---------------- Buckets (includedTypes) ----------------
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
    "bookstores": [
        "book_store"                # keep it tight to avoid generic "store"
    ]
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
    "bookstores": [
        "bookstore near Tanjong Pagar",
        "indie bookstore Tanjong Pagar",
        "comic shop near Tanjong Pagar",
        "manga bookstore near Tanjong Pagar"
    ]
}

# --- Hawker config ---
HAWKER_TYPES = ["food_court"]
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

HAWKER_NAME_TOKENS = (
    "lau pa sat",
    "maxwell food centre",
    "maxwell food center",
    "amoy street food centre",
    "amoy street food center",
    "chinatown complex",
    "chinatown hawker centre",
    "chinatown hawker center",
    "market street hawker centre",
    "people's park food centre",
)

HAWKER_NAME_KEYWORDS = (
    "hawker centre", "hawker center",
    "food centre", "food center",
    "food court", "market",
)

EXCLUDED_PRIMARY = {"lodging"}   # and anything containing "hotel"}

def is_allowed_primary(primary: str) -> bool:
    p = (primary or "").lower()
    if p in EXCLUDED_PRIMARY or "hotel" in p:
        return False
    return True

# Per-bucket primaryType restriction (None => no extra restriction)
ALLOWED_PRIMARY = {
    "bookstores": {"book_store"},   # STRICT: only true bookstores
    "restaurants": None,
    "cafes": None,
    "bars": None,
}

# --- Haversine distance (meters) ---
def haversine_m(lat1, lon1, lat2, lon2):
    if lat2 is None or lon2 is None:
        return None
    R = 6371000.0
    ph1, ph2 = math.radians(lat1), math.radians(lat2)
    dph = math.radians(lat2 - lat1)
    dl  = math.radians(lon2 - lon1)
    a = math.sin(dph/2)**2 + math.cos(ph1)*math.cos(ph2)*math.sin(dl/2)**2
    c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# --- Nearby with pagination (includedTypes) ---
MAX_PAGES_PER_CHUNK = 3
PAGE_DELAY_SEC = 2.0
PER_PAGE = 20

def nearby_all_pages(included_types):
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
            print(f"Nearby error ({included_types}):", data["error"].get("message"))
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
    primary = _norm(p.get("primaryType"))
    types = [_norm(t) for t in (p.get("types") or [])]
    name = _norm((p.get("displayName") or {}).get("text") or "")

    if primary == "food_court":
        return True
    if any(tok in name for tok in HAWKER_NAME_TOKENS):
        return True
    if "food_court" in types and any(k in name for k in HAWKER_NAME_KEYWORDS):
        return True
    return False

# --- Fetch & blend ---
raw_by_id = {}

# 1) Restaurants/Cafes/Bars/Bookstores
for bucket_name, types in BUCKETS.items():
    allowed_primary_for_bucket = ALLOWED_PRIMARY.get(bucket_name)

    # Nearby search
    for i in range(0, len(types), 10):  # API allows up to 10 types per call
        sub = types[i:i+10]
        try:
            for p in nearby_all_pages(sub):
                primary = (p.get("primaryType") or "").lower()

                # Global exclusions (lodging/hotel)
                if not is_allowed_primary(primary):
                    continue
                # Bucket-specific restriction (e.g., bookstores must be exactly book_store)
                if allowed_primary_for_bucket and primary not in allowed_primary_for_bucket:
                    continue

                pid = p.get("id")
                if not pid:
                    continue
                raw_by_id[pid] = better(raw_by_id.get(pid, p), p)
        except requests.RequestException as e:
            print(f"Nearby failed for {sub}: {e}")

    # Text search
    for tq in TEXT_QUERIES[bucket_name]:
        try:
            for p in text_search(tq):
                primary = (p.get("primaryType") or "").lower()

                if not is_allowed_primary(primary):
                    continue
                if allowed_primary_for_bucket and primary not in allowed_primary_for_bucket:
                    continue

                pid = p.get("id")
                if not pid:
                    continue
                raw_by_id[pid] = better(raw_by_id.get(pid, p), p)
        except requests.RequestException as e:
            print(f"TextSearch failed for '{tq}': {e}")

# 2) Hawkers
try:
    for p in nearby_all_pages(HAWKER_TYPES):
        if not is_hawker_centre_place(p):
            continue
        pid = p.get("id")
        if not pid:
            continue
        raw_by_id[pid] = better(raw_by_id.get(pid, p), p)
except requests.RequestException as e:
    print(f"Nearby failed for hawkers: {e}")

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

# --- Transform for frontend ---
places = []
for p in raw_by_id.values():
    rating = p.get("rating")
    if rating is None or rating <= 3.5:
        continue

    display = p.get("displayName") or {}
    photo_url = first_photo_url(p.get("photos"))

    # ✅ Skip anything without a usable image
    if not photo_url:
        continue

    # Pull lat/lng to compute distance
    loc = p.get("location") or {}
    plat = loc.get("latitude")
    plng = loc.get("longitude")
    dist_m = haversine_m(LAT, LNG, plat, plng)

    places.append({
        "name": display.get("text"),
        "rating": rating,
        "rating_count": p.get("userRatingCount"),
        "address": p.get("formattedAddress"),
        "place_id": p.get("id"),
        "maps_url": p.get("googleMapsUri"),
        "photo_url": photo_url,
        "types": p.get("types", []),
        "primary_type": p.get("primaryType"),
        "lat": plat,
        "lng": plng,
        "distance_m": round(dist_m) if dist_m is not None else None,
        "is_hawker_centre": is_hawker_centre_place(p),
    })

# Sort by rating then rating_count
places.sort(key=lambda x: ((x.get("rating") or 0), (x.get("rating_count") or 0)), reverse=True)

# --- Write JSON ---
Path("public/data").mkdir(parents=True, exist_ok=True)
meta = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "origin": {"lat": LAT, "lng": LNG}
}
out = {"meta": meta, "places": places}

with open("public/data/places.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"Wrote {len(places)} places to public/data/places.json (with metadata)")
