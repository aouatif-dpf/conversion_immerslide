"""
PROMPT v6 — Visual Quality
===========================
Strategy: content-adaptive sizing + visual balance across 3 screens.

Key difference vs v5:
- Pass 1 same as v5 (semantic assignment)
- Pass 2 completely different: instead of fixed rules,
  the model is asked to READ each element and decide its size
  based on its actual content importance and length.

Sizing logic given to the model:
  - Title (bold, large font) → height 0.14, font displayed big
  - Long body text (>80 chars) → height 0.22
  - Short body text (<80 chars) → height 0.12
  - Key image (main visual) → height 0.50, centered
  - Secondary image → height 0.32
  - Decorative shape → height 0.05 or skip if empty

Visual balance rules:
  - CENTER screen: max 2 elements, lots of breathing room (gap=0.08)
  - LEFT screen: compact, title at top (positionY=0.05)
  - RIGHT screen: cascade, smaller gaps (gap=0.04)
  - No element smaller than height=0.08 (unreadable)
  - No element with positionY+height > 0.93

What to observe vs v5:
  - Do titles appear larger than body text?
  - Do important images take more space than secondary ones?
  - Does CENTER feel visually balanced and breathable?
"""

PROMPT_ID = "v6_visual_quality"


# ── PASS 1 — SEMANTIC ASSIGNMENT (identique à v5) ─────────────────────────────
def build_prompt_assign(slide: dict, catalog: str) -> str:
    all_ids = []
    for key in ["textes", "images", "formes"]:
        for el in slide.get(key, []):
            if "id" in el:
                all_ids.append(el["id"])

    snum = slide.get("slide_number", "?")

    return f"""/no_think
You are a 3-screen presentation layout expert.

Assign each element to exactly one screen:
- LEFT  : slide title or short orienting label (1-2 elements max)
- CENTER: the single most important element — main image OR key concept (1-2 elements max)
- RIGHT : everything else — details, bullets, secondary images, shapes

Rules:
- Every ID must appear exactly once
- Image + its caption → same screen
- All {len(all_ids)} IDs must be assigned: {all_ids}

Elements:
{catalog}

Return ONLY:
{{"left":[...ids...],"center":[...ids...],"right":[...ids...]}}"""


def build_prompt_assign_retry(slide: dict, catalog: str) -> str:
    all_ids = []
    for key in ["textes", "images", "formes"]:
        for el in slide.get(key, []):
            if "id" in el:
                all_ids.append(el["id"])
    return f"""/no_think
Assign {len(all_ids)} IDs to 3 screens.
LEFT=title(1-2), CENTER=main(1-2), RIGHT=rest.
All IDs: {all_ids}
Elements: {catalog}
Return ONLY: {{"left":[...],"center":[...],"right":[...]}}"""


# ── PASS 2 — VISUAL QUALITY POSITIONING ───────────────────────────────────────
def build_prompt_position(screen_name: str, elements: list, slide_id: int, order: int) -> str:
    import json
    n = len(elements)

    # Analyser chaque élément pour donner des hints visuels au modèle
    hints = []
    for el in elements:
        content = el.get("content", "")
        eid     = el["id"]
        is_img  = any(ext in content.lower() for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"])
        fs      = el.get("font_size", 12)
        bold    = el.get("bold", False)
        length  = len(content.strip())

        if is_img:
            fname = content.replace("\\", "/").split("/")[-1]
            if screen_name == "center":
                hint = f"id={eid} [MAIN IMAGE {fname}] → recommend height=0.50 (dominant visual)"
            else:
                hint = f"id={eid} [IMAGE {fname}] → recommend height=0.32"
        elif bold or fs >= 20:
            hint = f"id={eid} [TITLE fs={fs} bold] → recommend height=0.14 (prominent)"
        elif length > 80:
            hint = f"id={eid} [LONG TEXT {length} chars] → recommend height=0.22"
        elif length > 0:
            hint = f"id={eid} [TEXT {length} chars] → recommend height=0.12"
        else:
            hint = f"id={eid} [SHAPE/EMPTY] → recommend height=0.05 or skip"

        hints.append(hint)

    hints_block  = "\n".join(hints)
    elements_json = json.dumps(elements, ensure_ascii=False, separators=(",", ":"))

    # Gap selon l'écran
    gap = 0.08 if screen_name == "center" else 0.04

    return f"""/no_think
Position {n} elements on the {screen_name.upper()} screen with VISUAL QUALITY in mind.

## Sizing recommendations (based on content analysis)
{hints_block}

## Layout rules for {screen_name.upper()}
- positionX = 0.04 for all elements
- width = 0.92 for all elements
- Stack vertically top to bottom, starting at positionY = 0.05
- Gap between elements = {gap} ({"generous breathing room" if screen_name == "center" else "compact"})
- positionY + height must never exceed 0.93
- Use recommended heights above — adjust slightly if needed to fit
- Skip shapes with no fill_color (invisible anyway)
- Preserve ALL original fields of each element

## Full element data
{elements_json}

Return ONLY the positioned elements list:
[{{...element with positionX, positionY, width, height added...}}, ...]"""


def build_prompt_position_retry(screen_name: str, elements: list) -> str:
    import json

    # Calculer les positions automatiquement comme exemple
    y   = 0.05
    gap = 0.08 if screen_name == "center" else 0.04
    example_lines = []

    for el in elements:
        content = el.get("content", "")
        is_img  = any(ext in content.lower() for ext in [".png", ".jpg", ".jpeg", ".gif"])
        bold    = el.get("bold", False)
        fs      = el.get("font_size", 12)
        length  = len(content.strip())

        if is_img:
            h = 0.50 if screen_name == "center" else 0.32
        elif bold or fs >= 20:
            h = 0.14
        elif length > 80:
            h = 0.22
        elif length > 0:
            h = 0.12
        else:
            continue

        if y + h > 0.93:
            break

        example_lines.append(
            f"id={el['id']} → positionX=0.04 positionY={round(y,4)} width=0.92 height={h}"
        )
        y = round(y + h + gap, 4)

    return f"""/no_think
Position elements on {screen_name.upper()} screen. Follow this exact layout:

{chr(10).join(example_lines)}

Full data: {json.dumps(elements, ensure_ascii=False, separators=(",",":"))}
Return ONLY: [{{...element with positionX positionY width height...}}]"""


# ── COMPAT v1-v4 ──────────────────────────────────────────────────────────────
def build_prompt(slide: dict, catalog: str) -> str:
    return build_prompt_assign(slide, catalog)

def build_retry_prompt(slide: dict, catalog: str) -> str:
    return build_prompt_assign_retry(slide, catalog)