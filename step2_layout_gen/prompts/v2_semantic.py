"""
PROMPT v2 — Semantic
=====================
Hypothesis: telling the LLM to understand semantic relationships between
elements (image explains text, text is title of image, etc.) produces
better spatial distribution than simple role assignment.

Key change vs v1:
- LLM is asked to IDENTIFY semantic links between elements first
- Then place linked elements on the SAME screen or adjacent zones
- Image understanding explicitly requested

What to observe vs v1:
- Do image+caption pairs end up on the same screen?
- Does the LLM place context text near its related visual?
- Does distribution quality improve even if JSON compliance drops?
"""

PROMPT_ID = "v2_semantic"


def build_prompt(slide: dict, catalog: str) -> str:
    import json
    sid  = slide.get("id")
    snum = slide.get("slide_number")

    texts_json  = json.dumps(slide.get("textes", []),  ensure_ascii=False, separators=(",", ":"))
    images_json = json.dumps(slide.get("images", []),  ensure_ascii=False, separators=(",", ":"))
    shapes_json = json.dumps(slide.get("formes", []),  ensure_ascii=False, separators=(",", ":"))

    return f"""/no_think
You are an expert in immersive 3-screen educational presentation design.

## Your task — TWO steps:

### STEP 1 — Semantic analysis (think, don't output yet)
Before placing any element, identify:
- Which TEXT is the main TITLE of this slide?
- Which TEXT elements are body explanations vs bullet points?
- Which IMAGE is the most important visual?
- Are any IMAGE and TEXT semantically linked? (image illustrates text, or text is the caption of image)
- Are any TEXT elements complementary to each other? (same concept, continuation)

### STEP 2 — Semantic layout on 3 screens
Apply these principles:
1. LINKED elements (image + its caption, concept + its visual) → SAME screen, close positionY
2. CENTER screen = the most important semantic unit (main concept + its key visual if linked)
3. LEFT screen = orientation elements (title, slide number, short label, section context)
4. RIGHT screen = supporting details (secondary bullets, complementary visuals, shapes)
5. Each element in exactly ONE screen
6. Choose positionX, positionY, width, height FROM SCRATCH based on semantic importance
   - Important elements → larger size, higher on screen (lower positionY)
   - Secondary elements → smaller, lower
   - Linked elements → same positionY zone (within 0.1 of each other)
7. All coordinates in [0.0, 1.0]

## Element catalog — slide {snum}
{catalog}

## Full element data (preserve ALL fields exactly):
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
Place {len(all_els)} elements across 3 screens. Semantically linked elements go on same screen.
LEFT=title/context, CENTER=main concept+visual, RIGHT=details.
Choose ALL positions FROM SCRATCH. All values in [0.0, 1.0].

Elements:
{catalog}

Full data: {json.dumps(all_els, ensure_ascii=False, separators=(",",":"))}

Return ONLY: {{"id":{sid},"order":{snum},"screens":{{"left":{{"elements":[]}},"center":{{"elements":[]}},"right":{{"elements":[]}}}}}}"""
