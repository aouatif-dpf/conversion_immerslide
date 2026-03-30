"""
PROMPT v4 — Multimodal Cross-linking
======================================
Hypothesis: explicitly asking the LLM to READ the image content (not just know
its path) and then link it to specific text fragments produces the most
semantically coherent layouts. The LLM must describe what it sees in each
image and map it to text before deciding placement.

Key change vs v3:
- LLM is asked to DESCRIBE each image content before layout
- Explicit cross-modal mapping: "image X shows concept Y, text Z explains Y"
- Placement is derived from this mapping, not from element type alone
- Works best with vision models (llava, qwen-vl) that actually see the images

What to observe vs v3:
- Does the LLM correctly identify image content?
- Do image-text pairs that share a concept end up on the same screen?
- Does the layout reflect the visual storytelling of the original slide?

Limitation: requires a vision-capable model. With text-only models,
image descriptions will be hallucinated — watch for this in outputs.
"""

PROMPT_ID = "v4_multimodal"


def build_prompt(slide: dict, catalog: str) -> str:
    import json
    sid  = slide.get("id")
    snum = slide.get("slide_number")

    texts_json  = json.dumps(slide.get("textes", []),  ensure_ascii=False, separators=(",", ":"))
    images_json = json.dumps(slide.get("images", []),  ensure_ascii=False, separators=(",", ":"))
    shapes_json = json.dumps(slide.get("formes", []),  ensure_ascii=False, separators=(",", ":"))

    n_images = len(slide.get("images", []))

    return f"""/no_think
You are an expert in multimodal educational content design.
You MUST use your vision capability to read the images provided.

## Task — 3 phases:

### PHASE 1 — Image reading (mandatory if images present)
For each image ({n_images} image(s) in this slide):
- Describe what you SEE in the image (diagram, chart, photo, schema...)
- Identify the CONCEPT the image illustrates
- Note the image ID for cross-referencing

### PHASE 2 — Cross-modal semantic mapping
For each image concept identified:
- Find the TEXT element(s) that explain, introduce, or label that concept
- These form a SEMANTIC PAIR: they MUST go on the same screen, close together

For text elements with no linked image:
- Are they the slide title? → LEFT screen, top
- Do they expand a concept shown in an image? → same screen as that image
- Are they standalone bullet points? → RIGHT screen

### PHASE 3 — Layout with full positional freedom
Apply this layout logic:
- CENTER: the strongest semantic pair (main image + its explanation text)
          OR the most important concept if no images
          Primary element: positionY ≈ 0.08–0.25, width ≈ 0.88–0.92
- LEFT  : slide title + orientation label
          positionY starts at 0.08
- RIGHT : remaining elements, cascaded vertically
          Secondary semantic pairs also go here if CENTER is taken
- Positions are completely FREE — choose the best layout for comprehension
- Linked elements: positionY difference ≤ 0.10
- All values in [0.0, 1.0]
- Preserve ALL original fields in each element object

## Element catalog — slide {snum}
{catalog}

## Full data:
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
    return f"""/no_think
Cross-modal layout: place {len(all_els)} elements. Linked image+text → same screen, close positionY.
CENTER=main image+caption, LEFT=title, RIGHT=details. All positions free, all values in [0.0,1.0].

Elements:
{catalog}

Full data: {json.dumps(all_els, ensure_ascii=False, separators=(",",":"))}
Return ONLY: {{"id":{sid},"order":{snum},"screens":{{"left":{{"elements":[]}},"center":{{"elements":[]}},"right":{{"elements":[]}}}}}}"""
