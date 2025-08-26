# get_featured_attractions.py  (Places API NEW – with ratings)
import os, json, requests
from pathlib import Path
from datetime import datetime

API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise RuntimeError("GOOGLE_API_KEY is not set")

BASE = "https://places.googleapis.com/v1"
HEADERS = {
    "X-Goog-Api-Key": API_KEY,
    # ⬇️ ask for rating + userRatingCount as well
    "X-Goog-FieldMask": (
        "places.displayName,places.id,places.formattedAddress,"
        "places.location,places.googleMapsUri,places.photos,"
        "places.rating,places.userRatingCount"
    ),
}

QUERIES = [
    "Flower Dome Gardens by the Bay",
    "Bird Paradise Singapore",
    "S.E.A. Aquarium",
    "Gardens by the Bay",
    "Jewel Changi Airport HSBC Rain Vortex",
    "Universal Studios Singapore",
    "Cloud Forest Gardens by the Bay",
    "ArtScience Museum",
    "Singapore Zoo",
    "Night Safari",
    "River Wonders",
    "Science Centre Singapore",
    "Sentosa",
]

OUT_JSON = Path("public/data/featured_attractions.json")
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

def search_place(q: str):
    body = {
        "textQuery": f"{q}, Singapore",
        "regionCode": "SG",
        "locationBias": {
            "circle": {
                "center": {"latitude": 1.3521, "longitude": 103.8198},
                "radius": 50000
            }
        },
    }
    r = requests.post(f"{BASE}/places:searchText", json=body, headers=HEADERS, timeout=30)
    r.raise_for_status()
    places = r.json().get("places", []) or []
    return places[0] if places else None

def photo_media_url(place: dict) -> str | None:
    photos = place.get("photos") or []
    if not photos: return None
    name = photos[0].get("name")
    if not name: return None
    return f"{BASE}/{name}/media?maxHeightPx=640&key={API_KEY}"

def normalize(p: dict):
    loc = p.get("location") or {}
    return {
        "title": (p.get("displayName") or {}).get("text"),
        "address": p.get("formattedAddress"),
        "lat": loc.get("latitude"),
        "lng": loc.get("longitude"),
        "maps_url": p.get("googleMapsUri"),
        "photo_url": photo_media_url(p),
        "rating": p.get("rating"),                   # ⬅️ NEW
        "rating_count": p.get("userRatingCount"),    # ⬅️ NEW
        "category": "family_featured",
        "source": "places_api_new",
    }

def main():
    results = []
    for q in QUERIES:
        print(f"🔎 Finding: {q}")
        try:
            p = search_place(q)
            if not p:
                print(f"  ⚠️ No result for {q}")
                continue
            results.append(normalize(p))
            print(f"  ✅ Found: {q}")
        except requests.HTTPError as e:
            print(f"  ❌ HTTP error for {q}: {e.response.text[:200]}")
        except Exception as e:
            print(f"  ❌ {q}: {e}")

    payload = {"generated_at": datetime.utcnow().isoformat() + "Z", "attractions": results}
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Saved {len(results)} attractions to {OUT_JSON}")

if __name__ == "__main__":
    main()
