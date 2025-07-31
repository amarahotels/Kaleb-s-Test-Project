import os
import requests
from PIL import Image
from io import BytesIO
import json

EVENT_JSON_PATH = "public/data/events.json"
OUTPUT_DIR = "public/data/event_images"
ORIGINAL_DIR = "public/data/event_images_original"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ORIGINAL_DIR, exist_ok=True)

with open(EVENT_JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

events = data.get("events", [])

for idx, event in enumerate(events):
    image_url = event.get("image")
    if not image_url:
        continue

    try:
        res = requests.get(image_url, timeout=10)
        res.raise_for_status()
        original_img = Image.open(BytesIO(res.content))

        # Save original
        original_path = os.path.join(ORIGINAL_DIR, f"event_{idx + 1}.jpg")
        original_img.save(original_path, "JPEG", quality=95)

        # Resize to 300x200 and save
        resized_img = original_img.resize((300, 200))
        resized_path = os.path.join(OUTPUT_DIR, f"event_{idx + 1}.jpg")
        resized_img.save(resized_path, "JPEG", quality=85)

        # Optional: update the event JSON reference
        event["image"] = f"data/event_images/event_{idx + 1}.jpg"

    except Exception as e:
        print(f"⚠️ Failed to process image {idx+1}: {e}")

# Save updated JSON
with open(EVENT_JSON_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"✅ Processed {len(events)} event images.")
