"""
PROMPT v5 — Two-Pass (niveau 2)
================================
Hypothesis: separating semantic assignment (pass 1) from positioning (pass 2)
produces both correct distribution AND valid coordinates.

Pass 1 — Semantic assignment:
  Input : element catalog (short, readable)
  Output: {"left":[ids], "center":[ids], "right":[ids]}
  → Model only decides WHO goes WHERE — no coordinates, no JSON complexity

Pass 2 — Positioning:
  Input : elements assigned to each screen + strict layout rules
  Output: full immerslide JSON with valid coordinates
  → Model only decides positions — semantic decision already made

Why this works for 2B models:
  - Each pass is ONE simple task
  - Pass 1 has no coordinate math → model focuses on semantics
  - Pass 2 has strict rules → model can't produce out-of-bounds values
  - Total tokens per pass is much lower than a single combined prompt
"""

PROMPT_ID = "v5_two_pass"


# ── PASS 1 — SEMANTIC ASSIGNMENT ──────────────────────────────────────────────
def build_prompt_assign(slide: dict, catalog: str) -> str:
    """
    Ask the model only: which element goes on which screen?
    Returns only IDs — no coordinates.
    """
    all_ids = []
    for key in ["textes", "images", "formes"]:
        for el in slide.get(key, []):
            if "id" in el:
                all_ids.append(el["id"])

    snum = slide.get("slide_number", "?")

    return f"""/no_think
You are a 3-screen presentation layout expert.

Assign each element to exactly one screen:
- LEFT  : slide title, section label, short orienting text (1-2 elements max)
- CENTER: the most important element — main image OR key concept (1-2 elements max)
- RIGHT : everything else — details, secondary text, shapes, extra images

Rules:
- Every ID must appear exactly once
- Semantically linked elements (image + its caption) → same screen
- All {len(all_ids)} IDs must be assigned: {all_ids}

Elements:
{catalog}

Return ONLY this JSON, no explanation:
{{"left":[...ids...],"center":[...ids...],"right":[...ids...]}}"""


def build_prompt_assign_retry(slide: dict, catalog: str) -> str:
    all_ids = []
    for key in ["textes", "images", "formes"]:
        for el in slide.get(key, []):
            if "id" in el:
                all_ids.append(el["id"])

    return f"""/no_think
Assign {len(all_ids)} element IDs to 3 screens.
LEFT=title(1-2), CENTER=main image or concept(1-2), RIGHT=rest.
All IDs: {all_ids}
Elements: {catalog}
Return ONLY: {{"left":[...],"center":[...],"right":[...]}}"""


# ── PASS 2 — POSITIONING ───────────────────────────────────────────────────────
def build_prompt_position(screen_name: str, elements: list, slide_id: int, order: int) -> str:
    """
    Ask the model to assign coordinates to elements on ONE screen.
    Rules are strict and simple — no ambiguity.
    """
    import json
    n = len(elements)

    # Build a minimal catalog of just these elements
    lines = []
    for el in elements:
        content = el.get("content", "")
        is_img  = any(ext in content.lower() for ext in [".png", ".jpg", ".jpeg", ".gif"])
        if is_img:
            fname = content.replace("\\", "/").split("/")[-1]
            lines.append(f"  id={el['id']} [IMAGE] file={fname}")
        elif el.get("font_family"):
            preview = content.strip().replace("\n", " ")[:60]
            fs = el.get("font_size", 12)
            bold = el.get("bold", False)
            lines.append(f"  id={el['id']} [TEXT] fs={fs} bold={bold} → \"{preview}\"")
        else:
            lines.append(f"  id={el['id']} [SHAPE] name={el.get('name', '')}")

    catalog = "\n".join(lines)
    elements_json = json.dumps(elements, ensure_ascii=False, separators=(",", ":"))

    return f"""/no_think
Position {n} elements on the {screen_name.upper()} screen.

STRICT RULES — follow exactly:
1. positionX = 0.04 for all elements
2. width = 0.92 for all elements
3. Stack vertically from top to bottom:
   - First element: positionY = 0.05
   - Each next element: positionY = previous positionY + previous height + 0.04
4. Height by type:
   - IMAGE → height = 0.42
   - TEXT  → height = 0.12 (short text) or 0.18 (long text > 60 chars)
   - SHAPE with fill_color → height = 0.06
   - SHAPE without fill_color → height = 0.04
5. positionY + height must never exceed 0.95
6. Preserve ALL original fields of each element

Elements on this screen:
{catalog}

Full element data:
{elements_json}

Return ONLY the elements list with positions added:
[{{...element with positionX, positionY, width, height...}}, ...]"""


def build_prompt_position_retry(screen_name: str, elements: list) -> str:
    import json
    ids = [el["id"] for el in elements]
    result = []
    y = 0.05
    # Give a concrete example of what we expect
    for el in elements:
        content = el.get("content", "")
        is_img = any(ext in content.lower() for ext in [".png", ".jpg", ".jpeg"])
        h = 0.42 if is_img else (0.18 if len(content.strip()) > 60 else 0.12)
        if not el.get("font_family") and not is_img:
            h = 0.06 if el.get("fill_color") else 0.04
        result.append(f"id={el['id']} → positionX=0.04 positionY={round(y,4)} width=0.92 height={h}")
        y = round(y + h + 0.04, 4)

    return f"""/no_think
Add positions to {len(elements)} elements. IDs: {ids}
Rules: positionX=0.04, width=0.92, stack vertically gap=0.04, max positionY+height=0.95

Expected format:
{chr(10).join(result)}

Full data: {json.dumps(elements, ensure_ascii=False, separators=(",",":"))}
Return ONLY: [{{...element with positionX positionY width height...}}]"""


# ── MAIN PROMPTS (requis par run_model.py pour compatibilité) ─────────────────
# Ces fonctions ne sont pas utilisées pour v5 — run_model.py appelle
# directement build_prompt_assign et build_prompt_position
# Elles sont là pour que run_model.py ne plante pas si appelé en mode v1-v4

def build_prompt(slide: dict, catalog: str) -> str:
    return build_prompt_assign(slide, catalog)

def build_retry_prompt(slide: dict, catalog: str) -> str:
    return build_prompt_assign_retry(slide, catalog)