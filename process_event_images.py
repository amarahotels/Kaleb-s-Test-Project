# process_event_images.py
import os
import json
import requests
from PIL import Image
from io import BytesIO

# Create folders
original_dir = "public/data/event_images/original"
resized_dir = "public/data/event_images/resized"
os.makedirs(original_dir, exist_ok=True)
os.makedirs(resized_dir, exist_ok=True)

# Load events
with open("public/data/events.json", "r", encoding="utf-8") as f:
    events = json.load(f)["events"]

for idx, event in enumerate(events):
    url = event.get("image")
    if not url:
        continue

    try:
        response = requests.get(url, timeout=10)
        img = Image.open(BytesIO(response.content)).convert("RGB")

        # Save original
        original_path = os.path.join(original_dir, f"event_{idx+1}.jpg")
        img.save(original_path)

        # Save resized
        resized = img.resize((400, 250))
        resized_path = os.path.join(resized_dir, f"event_{idx+1}.jpg")
        resized.save(resized_path)

        print(f"✅ Processed event_{idx+1}.jpg")
    except Exception as e:
        print(f"❌ Failed for {url}: {e}")
