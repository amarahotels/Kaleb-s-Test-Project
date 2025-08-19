# get_featured_attractions.py
import os, json, re, requests
from pathlib import Path
from urllib.parse import urlencode

API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise RuntimeError("GOOGLE_API_KEY is not set")

OUT_JSON = Path("public/data/featured_attractions.json")
IMG_DIR  = Path("public/images/attractions")
IMG_DIR.mkdir(parents=True, exist_ok=True)

# Singapore bias (center & 25km radius)
SG_LAT, SG_LNG = 1.3521, 103.8198
LOCATION_BIAS = f"circle:25000@{SG_LAT},{SG_LNG}"

COMMON_PARAMS = {
    "language": "en",
    "region": "sg",
    "key": API_KEY
}

# Curated list + useful aliases to improve hit-rate
ATTRACTIONS = [
    {"name": "Gardens by the Bay", "aliases": [
        "Gardens by the Bay Singapore"
    ]},
    {"name": "Flower Dome", "aliases": [
        "Flower Dome Gardens by the Bay", "Flower Dome Singapore"
    ]},
    {"name": "Cloud Forest", "aliases": [
        "Cloud Forest Gardens by the Bay", "Cloud Forest Singapore"
    ]},
    {"name": "ArtScience Museum", "aliases": [
        "ArtScience Museum Singapore"
    ]},
    {"name": "Singapore Zoo", "aliases": [
        "Mandai Singapore Zoo", "Singapore Zoo Mandai"
    ]},
    {"name": "Night Safari", "aliases": [
        "Night Safari Singapore", "Mandai Night Safari"
    ]},
    {"name": "River Wonders", "aliases": [
        "River Wonders Singapore", "Mandai River Wonders"
    ]},
    {"name": "Bird Paradise", "aliases": [
        "Bird Paradise Singapore", "Mandai Bird Paradise"
    ]},
    {"name": "Universal Studios Singapore", "aliases": [
        "USS Sentosa", "Universal Studios Sentosa"
    ]},
    {"name": "S.E.A. Aquarium", "aliases": [
        "SEA Aquarium Sentosa", "S.E.A. Aquarium Singapore"
    ]},
    {"name": "Science Centre Singapore", "aliases": []},
    {"name": "Jewel Changi Airport", "aliases": [
        "Jewel Changi", "HSBC Rain Vortex Jewel"
    ]},
    {"name": "Marina Bay Sands SkyPark Observation Deck", "aliases": [
        "MBS SkyPark Observation Deck", "Marina Bay Sands SkyPark"
    ]},
    {"name": "Sentosa", "aliases": [
        "Sentosa Island"
    ]},
]

def http_json(url, params):
    r = requests.get(url, params=params, timeout=20)
    try:
        data = r.json()
    except Exception:
        data = {}
    return r.status_code, data

def find_place(text):
    """Try Find Place; if nothing, try Text Search. Return the best candidate dict or None."""
    # --- 1) Find Place from Text
    fp_params = {
        "input": text,
        "inputtype": "textquery",
        "fields": "place_id,name,formatted_address,geometry,types",
        "locationbias": LOCATION_BIAS,
        **COMMON_PARAMS
    }
    code, data = http_json("https://maps.googleapis.com/maps/api/place/findplacefromtext/json", fp_params)
    status = data.get("status")
    if status == "OK" and data.get("candidates"):
        return data["candidates"][0]
    if status not in ("ZERO_RESULTS", "OK"):
        print(f"  ⚠️ FindPlace error for '{text}': HTTP {code}, status={status}, msg={data.get('error_message')}")

    # --- 2) Fallback: Text Search
    ts_params = {
        "query": text,
        "location": f"{SG_LAT},{SG_LNG}",
        "radius": 30000,
        **COMMON_PARAMS
    }
    code, data = http_json("https://maps.googleapis.com/maps/api/place/textsearch/json", ts_params)
    status = data.get("status")
    if status == "OK" and data.get("results"):
        return data["results"][0]
    if status not in ("ZERO_RESULTS", "OK"):
        print(f"  ⚠️ TextSearch error for '{text}': HTTP {code}, status={status}, msg={data.get('error_message')}")
    return None

def place_details(place_id):
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,website,url,international_phone_number,geometry,photos,types",
        **COMMON_PARAMS
    }
    code, data = http_json("https://maps.googleapis.com/maps/api/place/details/json", params)
    status = data.get("status")
    if status != "OK":
        print(f"  ⚠️ Details error for {place_id}: HTTP {code}, status={status}, msg={data.get('error_message')}")
        return None
    return data.get("result")

def download_photo(photo_ref, slug):
    """Download first photo to public/images/attractions/<slug>.jpg and return relative path."""
    if not photo_ref:
        return ""
    photo_params = {
        "maxwidth": 1600,
        "photo_reference": photo_ref,
        "key": API_KEY
    }
    url = "https://maps.googleapis.com/maps/api/place/photo?" + urlencode(photo_params)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        out = IMG_DIR / f"{slug}.jpg"
        with open(out, "wb") as f:
            f.write(resp.content)
        return f"/images/attractions/{slug}.jpg"
    except Exception as e:
        print(f"  ⚠️ Photo download failed for {slug}: {e}")
        return ""

def slugify(s):
    return re.sub(r"[^a-z0-9]+","-", (s or "").lower()).strip("-")

def main():
    out_items = []

    for item in ATTRACTIONS:
        name = item["name"]
        print(f"🔎 Finding: {name}")
        candidate = find_place(name)

        # Try aliases if main name didn't match
        if not candidate:
            for alias in item.get("aliases", []):
                candidate = find_place(alias)
                if candidate:
                    print(f"   ↳ matched alias: {alias}")
                    break

        if not candidate:
            print(f"  ❌ Couldn't find place for: {name}")
            continue

        pid = candidate.get("place_id")
        details = place_details(pid)
        if not details:
            print(f"  ❌ No details for: {name}")
            continue

        photo_ref = (details.get("photos") or [{}])[0].get("photo_reference")
        slug = slugify(details.get("name") or name)
        photo_url = download_photo(photo_ref, slug)

        maps_url = f"https://www.google.com/maps/place/?q=place_id:{pid}"

        out_items.append({
            "name": details.get("name") or name,
            "address": details.get("formatted_address") or "",
            "website": details.get("website") or "",
            "maps_url": details.get("url") or maps_url,
            "photo_url": photo_url,   # local image when available
            "place_id": pid
        })

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump({"attractions": out_items}, f, ensure_ascii=False, indent=2)

    print(f"✅ Saved {len(out_items)} attractions to {OUT_JSON}")

if __name__ == "__main__":
    main()
