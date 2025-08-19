# get_featured_attractions.py
import os, json, re, time, requests
from pathlib import Path

API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
if not API_KEY:
    raise RuntimeError("GOOGLE_MAPS_API_KEY is not set")

OUT_JSON = Path("public/data/featured_attractions.json")
IMG_DIR  = Path("public/images/attractions")
IMG_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

# ---- Curate your attractions here ----
# If you know place_id, include it. If not, just set text and we’ll Find Place.
ATTRACTIONS = [
    {"text": "Gardens by the Bay"},
    {"text": "Flower Dome Gardens by the Bay"},
    {"text": "Cloud Forest Gardens by the Bay"},
    {"text": "ArtScience Museum"},
    {"text": "Singapore Zoo"},
    {"text": "Night Safari"},
    {"text": "River Wonders"},
    {"text": "Bird Paradise Singapore"},
    {"text": "Universal Studios Singapore"},
    {"text": "S.E.A. Aquarium"},
    {"text": "Science Centre Singapore"},
    {"text": "Jewel Changi Airport"},
    {"text": "Marina Bay Sands SkyPark Observation Deck"},
    {"text": "Sentosa"},
]

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-{2,}", "-", s).strip("-") or "image"

def find_place(text: str):
    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        "input": text, "inputtype": "textquery",
        "fields": "place_id",
        "key": API_KEY, "language": "en", "region": "sg"
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    c = r.json()
    cand = (c.get("candidates") or [])
    return cand[0]["place_id"] if cand else None

def place_details(place_id: str):
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,geometry,photos,url,website",
        "key": API_KEY, "language": "en"
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return (r.json() or {}).get("result") or {}

def download_photo(photo_ref: str, fname_base: str) -> str | None:
    # Save a 1200px-wide image locally so the API key is never exposed publicly.
    url = "https://maps.googleapis.com/maps/api/place/photo"
    params = {"maxwidth": 1200, "photo_reference": photo_ref, "key": API_KEY}
    dst = IMG_DIR / f"{fname_base}.jpg"
    try:
        with requests.get(url, params=params, timeout=60, stream=True) as resp:
            resp.raise_for_status()
            with open(dst, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
        return f"images/attractions/{dst.name}"
    except Exception as e:
        print(f"⚠️  Photo download failed for {fname_base}: {e}")
        return None

def maybe_recent(path: Path, days=14) -> bool:
    if not path.exists(): return False
    age = time.time() - path.stat().st_mtime
    return age < days * 86400

def main():
    items = []
    for a in ATTRACTIONS:
        place_id = a.get("place_id") or find_place(a["text"])
        if not place_id:
            print(f"❌ Couldn’t find place for: {a['text']}")
            continue

        det = place_details(place_id)
        name = det.get("name") or a["text"]
        addr = det.get("formatted_address") or ""
        geo  = (det.get("geometry") or {}).get("location") or {}
        maps_url = det.get("url") or ""
        website  = det.get("website") or ""

        # choose a photo
        photos = det.get("photos") or []
        photo_url = ""
        if photos:
            ref = photos[0].get("photo_reference")
            base = slugify(name)
            local = IMG_DIR / f"{base}.jpg"
            if not maybe_recent(local):
                photo_url = download_photo(ref, base) or ""
            else:
                photo_url = f"images/attractions/{local.name}"

        items.append({
            "name": name,
            "address": addr,
            "lat": geo.get("lat"),
            "lng": geo.get("lng"),
            "place_id": place_id,
            "maps_url": maps_url or website,
            "photo_url": photo_url,              # local relative path
            "category": "attraction",
            "ongoing": True
        })

    payload = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "source": "google_places",
               "attractions": items}

    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Saved {len(items)} attractions to {OUT_JSON}")

if __name__ == "__main__":
    main()
