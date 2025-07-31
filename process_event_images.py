import os
import json
import requests
from PIL import Image
from io import BytesIO

IMAGE_DIR = 'public/data/event_images'

# Make sure directory exists
os.makedirs(IMAGE_DIR, exist_ok=True)

# Add .gitkeep file if it's a new folder
gitkeep_path = os.path.join(IMAGE_DIR, '.gitkeep')
if not os.path.exists(gitkeep_path):
    with open(gitkeep_path, 'w') as f:
        f.write('')

# Load the events
with open('public/data/events.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Process images
for idx, event in enumerate(data.get('events', [])):
    img_url = event.get('image')
    if not img_url:
        print(f"🔸 Event {idx+1} has no image URL.")
        continue

    try:
        print(f"🔄 Downloading image: {img_url}")
        response = requests.get(img_url, timeout=10)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content)).convert("RGB")

        filename = f"event_{idx+1}.jpg"
        save_path = os.path.join(IMAGE_DIR, filename)
        img.save(save_path, format="JPEG", quality=90)

        print(f"✅ Saved: {save_path}")
        event['image'] = f"data/event_images/{filename}"
    except Exception as e:
        print(f"❌ Failed to download {img_url}: {e}")


# Save updated events
with open('public/data/events.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
