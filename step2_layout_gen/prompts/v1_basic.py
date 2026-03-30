"""
PROMPT v1 — Basic
==================
Hypothesis: a minimal prompt is enough to get a valid 3-screen JSON.
No semantic reasoning asked. No image understanding. Pure structure.

What to observe:
- Does the LLM produce valid JSON reliably?
- Does it distribute elements at all or dump everything in center?
- Baseline to compare all other versions against.
"""

PROMPT_ID = "v1_basic"


def build_prompt(slide: dict, catalog: str) -> str:
    sid  = slide.get("id")
    snum = slide.get("slide_number")

    import json
    texts_json  = json.dumps(slide.get("textes", []),  ensure_ascii=False, separators=(",", ":"))
    images_json = json.dumps(slide.get("images", []),  ensure_ascii=False, separators=(",", ":"))
    shapes_json = json.dumps(slide.get("formes", []),  ensure_ascii=False, separators=(",", ":"))

    return f"""You are a 3-screen presentation designer.

Distribute the elements of slide {snum} across 3 screens:
- LEFT   : title, slide number, short label
- CENTER : main content, most important element
- RIGHT  : details, secondary text, shapes

Rules:
- Each element in exactly ONE screen
- positionX, positionY, width, height all in [0.0, 1.0]
- No element outside bounds

TEXTS : {texts_json}
IMAGES: {images_json}
SHAPES: {shapes_json}

Return ONLY valid JSON:
{{"id":{sid},"order":{snum},"screens":{{"left":{{"elements":[]}},"center":{{"elements":[]}},"right":{{"elements":[]}}}}}}"""


def build_retry_prompt(slide: dict, catalog: str) -> str:
    import json
    sid  = slide.get("id")
    snum = slide.get("slide_number")
    all_els = slide.get("textes", []) + slide.get("images", []) + slide.get("formes", [])
    return f"""Distribute {len(all_els)} elements across left/center/right screens.
Elements: {json.dumps(all_els, ensure_ascii=False, separators=(",",":"))}
Return ONLY: {{"id":{sid},"order":{snum},"screens":{{"left":{{"elements":[]}},"center":{{"elements":[]}},"right":{{"elements":[]}}}}}}"""
