"""
STEP 1 — Decode Images
======================
Input  : data/input/input_brute.json
Output : data/input/slides_ready.json
         data/images/image_XXXX.png

Run from project root:
  python step1_decode/decode_images.py
"""

import base64
import json
import os

BASE         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_JSON   = os.path.join(BASE, "data", "input", "input_brute.json")
OUTPUT_JSON  = os.path.join(BASE, "data", "input", "slides_ready.json")
IMAGES_FOLDER = os.path.join(BASE, "data", "images")

os.makedirs(IMAGES_FOLDER, exist_ok=True)

with open(INPUT_JSON, "r", encoding="utf-8") as f:
    data = json.load(f)

counter = 1
decoded = 0
errors  = 0

for slide in data.get("slides", []):
    slide_num = slide.get("slide_number", "?")
    for image in slide.get("images", []):
        b64 = image.get("content")
        if not b64:
            continue
        try:
            raw      = base64.b64decode(b64)
            filename = f"image_{counter:04d}.png"
            filepath = os.path.join(IMAGES_FOLDER, filename)
            with open(filepath, "wb") as img_file:
                img_file.write(raw)
            image["content"]        = filepath
            image["image_filename"] = filename
            counter += 1
            decoded += 1
        except Exception as e:
            print(f"  error slide {slide_num}: {e}")
            errors += 1

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"decoded: {decoded} image(s) → {IMAGES_FOLDER}")
print(f"output : {OUTPUT_JSON}")
if errors:
    print(f"errors : {errors}")
