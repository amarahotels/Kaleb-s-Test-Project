# process_event_images.py
import os
import requests
import json

EVENTS_PATH = "public/data/events.json"
IMAGE_DIR = "public/data/event_images"

os.makedirs(IMAGE_DIR, exist_ok=True)

with open(EVENTS_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

for i, event in enumerate(data.get("events", [])):
    img_url = event.get("image")
    if not img_url or not img_url.startswith("http"):
        continue

    try:
        img_data = requests.get(img_url, timeout=10).content
        img_name = f"event_{i+1}.jpg"
        full_path = os.path.join(IMAGE_DIR, img_name)

        with open(full_path, "wb") as f:
            f.write(img_data)

        # Update image path in JSON
        event["image"] = f"/data/event_images/{img_name}"

    except Exception as e:
        print(f"❌ Could not fetch {img_url}: {e}")
        event["image"] = ""  # blank it

# Save updated events.json
with open(EVENTS_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ Downloaded images and updated image paths.")
