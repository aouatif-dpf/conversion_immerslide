"""
PROMPT v3 — Information Architecture & Attention (IAA)
========================================================
Hypothesis: grounding the prompt in real IA/UX principles (visual hierarchy,
F-pattern reading, proximity, figure-ground) produces layouts that are not just
semantically correct but also visually readable and pedagogically effective.

Key change vs v2:
- Explicit IA principles injected: proximity, hierarchy, figure-ground
- F-pattern reading direction used to guide element placement
- Element "weight" concept: title=heavy, body=medium, detail=light
- LLM asked to reason about a student's attention flow, not just content type

Theoretical basis:
  - Gestalt proximity law: related elements placed close together
  - F-pattern (Nielsen): heavy content top-left, scannable right column
  - Information hierarchy: 1 primary, 2-3 secondary, rest supporting
  - Figure-ground: main visual (figure) isolated on center, context as ground

What to observe vs v2:
- Does the LLM produce a real visual hierarchy (not just categorize)?
- Do elements have varied sizes reflecting their importance?
- Is the resulting layout more readable from a student's perspective?
"""

PROMPT_ID = "v3_iaa"


def build_prompt(slide: dict, catalog: str) -> str:
    import json
    sid  = slide.get("id")
    snum = slide.get("slide_number")

    texts_json  = json.dumps(slide.get("textes", []),  ensure_ascii=False, separators=(",", ":"))
    images_json = json.dumps(slide.get("images", []),  ensure_ascii=False, separators=(",", ":"))
    shapes_json = json.dumps(slide.get("formes", []),  ensure_ascii=False, separators=(",", ":"))

    return f"""/no_think
You are an expert in Information Architecture and immersive educational display design.
You apply proven IA and UX principles to arrange presentation content across 3 screens.

## Context
A student sits in front of 3 large screens (left, center, right).
The student's gaze naturally starts at CENTER, then scans LEFT, then RIGHT.
You must design the layout so the student understands the content intuitively,
without needing to read everything in order.

## IA Principles to apply (mandatory)

### 1. Visual hierarchy
Every screen must have exactly ONE primary element (largest, most prominent).
Secondary elements are smaller. Supporting elements are smallest.
Never place two elements of equal visual weight at the same Y position.

### 2. Proximity (Gestalt law)
Elements that are semantically linked MUST be placed close together (same screen,
positionY within 0.08 of each other). An image and its caption = proximity group.
A concept title and its explanation = proximity group.

### 3. Figure-ground
The CENTER screen is the "figure" — the main concept stands alone, with visual breathing room.
The LEFT and RIGHT screens are "ground" — supporting context.
The primary visual or core concept of the slide always goes to CENTER.

### 4. F-pattern reading
On LEFT screen: most important element at positionY ≈ 0.10–0.20 (top-left anchor for the eye).
On CENTER screen: primary element at positionY ≈ 0.15–0.30.
On RIGHT screen: first element at positionY ≈ 0.10, then cascade down.

### 5. Information weight assignment
Before placing, assign a WEIGHT to each element:
- WEIGHT 5 (primary)   : main title, largest image, core concept
- WEIGHT 3 (secondary) : body text, supporting image, key bullet
- WEIGHT 1 (tertiary)  : decorative shape, footnote, secondary label

Weight → size mapping:
- weight 5: width ≈ 0.85–0.92, height ≈ 0.25–0.45 (images) or 0.10–0.18 (text)
- weight 3: width ≈ 0.75–0.88, height ≈ 0.08–0.14 (text) or 0.20–0.35 (images)
- weight 1: width ≈ 0.60–0.80, height ≈ 0.05–0.10

## Screen assignment
- LEFT   : slide anchor (WEIGHT 5 title or section label) + orientation context
- CENTER : primary semantic unit = WEIGHT 5 main concept + its WEIGHT 5 image if linked
- RIGHT  : WEIGHT 3 and 1 elements — bullets, details, complementary visuals

## Element catalog — slide {snum}
{catalog}

## Full element data (preserve ALL fields exactly):
TEXTS : {texts_json}
IMAGES: {images_json}
SHAPES: {shapes_json}

Return ONLY valid JSON — no explanation, no markdown:
{{"id":{sid},"order":{snum},"screens":{{"left":{{"elements":[]}},"center":{{"elements":[]}},"right":{{"elements":[]}}}}}}"""


def build_retry_prompt(slide: dict, catalog: str) -> str:
    import json
    sid  = slide.get("id")
    snum = slide.get("slide_number")
    all_els = slide.get("textes", []) + slide.get("images", []) + slide.get("formes", [])
    return f"""/no_think
Apply IA principles to place {len(all_els)} elements on 3 screens.
- LEFT: title anchor (top, large)
- CENTER: primary concept + linked image (figure-ground isolation)
- RIGHT: supporting details (cascade down)
- Proximity: linked elements within positionY 0.08 of each other
- All positions FROM SCRATCH, all values in [0.0, 1.0]

Elements:
{catalog}

Full data: {json.dumps(all_els, ensure_ascii=False, separators=(",",":"))}
Return ONLY: {{"id":{sid},"order":{snum},"screens":{{"left":{{"elements":[]}},"center":{{"elements":[]}},"right":{{"elements":[]}}}}}}"""
