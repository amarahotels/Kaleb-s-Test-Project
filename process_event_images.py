import os
import json
import requests
from bs4 import BeautifulSoup

# Input JSON
EVENTS_PATH = "public/data/events.json"
# Output images
IMAGES_DIR = "public/data/event_images"
# Save original low-quality fallback image too (optional)
SAVE_LOW_RES = True

os.makedirs(IMAGES_DIR, exist_ok=True)

with open(EVENTS_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

events = data.get("events", [])

for idx, event in enumerate(events):
    event_url = event.get("url")
    fallback_img = event.get("image")  # Optional

    img_url = None

    if event_url:
        try:
            resp = requests.get(event_url, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            meta_img = soup.find("meta", property="og:image")
            if meta_img and meta_img.get("content"):
                img_url = meta_img["content"]
        except Exception as e:
            print(f"[{idx}] Failed to fetch og:image from {event_url}: {e}")

    if not img_url and fallback_img and SAVE_LOW_RES:
        img_url = fallback_img

    if img_url:
        try:
            img_ext = os.path.splitext(img_url.split("?")[0])[-1]
            img_ext = img_ext if img_ext in [".jpg", ".jpeg", ".png"] else ".jpg"
            img_path = f"{IMAGES_DIR}/event_{idx+1}{img_ext}"

            img_data = requests.get(img_url, timeout=10).content
            with open(img_path, "wb") as f:
                f.write(img_data)

            # Update the event with local path
            event["image"] = f"data/event_images/event_{idx+1}{img_ext}"
        except Exception as e:
            print(f"[{idx}] Failed to save image from {img_url}: {e}")
    else:
        print(f"[{idx}] No image available for {event.get('title')}")

# Save updated JSON
with open(EVENTS_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
