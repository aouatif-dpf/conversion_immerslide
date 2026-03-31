"""
utils.py — Shared utilities for ALL layout generation runs
===========================================================
Rule: this file NEVER changes between prompt versions.
Only the prompt files in prompts/ change.
"""

import json
import os
import re

SLIDE_W = 960.0
SLIDE_H = 540.0


# ── NORMALISATION ──────────────────────────────────────────────────────────────
def norm(val, dim: float) -> float:
    v = float(val) if val is not None else 0.0
    return round(v / dim if v > 1.0 else v, 4)

def normalize_element(el: dict) -> dict:
    e = dict(el)
    e["positionX"] = norm(e.get("positionX", 0), SLIDE_W)
    e["positionY"] = norm(e.get("positionY", 0), SLIDE_H)
    e["width"]     = norm(e.get("width",     0), SLIDE_W)
    e["height"]    = norm(e.get("height",    0), SLIDE_H)
    return e

def normalize_slide(slide: dict) -> dict:
    s = dict(slide)
    s["textes"] = [normalize_element(t) for t in slide.get("textes", [])]
    s["images"] = [normalize_element(i) for i in slide.get("images", [])]
    s["formes"] = [normalize_element(f) for f in slide.get("formes", [])]
    return s


# ── JSON EXTRACTION ────────────────────────────────────────────────────────────
def extract_json(text: str) -> dict:
    """Robustly extract first valid JSON object from LLM output."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        try:
            obj, _ = decoder.raw_decode(text[idx:])
            return obj
        except json.JSONDecodeError:
            nxt = text.find("{", idx + 1)
            if nxt == -1:
                break
            idx = nxt
    raise ValueError("No valid JSON found in LLM output.")


# ── CLAMP ONLY — no forced repositioning ──────────────────────────────────────
# Philosophy: the LLM decides ALL positions based on semantics.
# We only clamp values outside [0,1] to avoid rendering crashes.
# We do NOT reorder or push elements — that would override the LLM's decisions.
def clamp_element(el: dict) -> dict:
    e = dict(el)
    for field in ["positionX", "positionY", "width", "height"]:
        v = e.get(field)
        if v is not None:
            e[field] = round(max(0.0, min(1.0, float(v))), 4)
    if e.get("positionX", 0) + e.get("width", 0) > 1.0:
        e["width"] = round(1.0 - e["positionX"], 4)
    if e.get("positionY", 0) + e.get("height", 0) > 1.0:
        e["height"] = round(1.0 - e["positionY"], 4)
    return e


# ── VALIDATION ─────────────────────────────────────────────────────────────────
def get_source_ids(slide: dict) -> set:
    ids = set()
    for key in ["textes", "images", "formes"]:
        for el in slide.get(key, []):
            if "id" in el:
                ids.add(el["id"])
    return ids

def get_output_ids(result: dict) -> set:
    ids = set()
    for screen in result.get("screens", {}).values():
        for el in screen.get("elements", []):
            if "id" in el:
                ids.add(el["id"])
    return ids

def validate(result: dict, slide: dict) -> list:
    errors = []
    for sk in ["left", "center", "right"]:
        if sk not in result.get("screens", {}):
            errors.append(f"Missing screen: {sk}")
            continue
        for el in result["screens"][sk].get("elements", []):
            for field in ["positionX", "positionY", "width", "height"]:
                v = el.get(field)
                if v is not None and not (0.0 <= float(v) <= 1.0):
                    errors.append(f"[{sk}] id={el.get('id')} {field}={v} out of [0,1]")
    missing = get_source_ids(slide) - get_output_ids(result)
    if missing:
        errors.append(f"Missing IDs: {missing}")
    return errors


# ── REPAIR — clamp + re-inject missing, preserve LLM decisions ────────────────
def repair(result: dict, slide: dict) -> dict:
    screens = result.setdefault("screens", {})
    for sk in ["left", "center", "right"]:
        screens.setdefault(sk, {"elements": []})

    # Clamp all positions — do NOT reorder
    for screen in screens.values():
        screen["elements"] = [clamp_element(el) for el in screen.get("elements", [])]

    # Re-inject truly missing elements into right screen
    src_ids = get_source_ids(slide)
    out_ids = get_output_ids(result)
    missing = src_ids - out_ids
    if missing:
        all_els = {
            el["id"]: normalize_element(el)
            for key in ["textes", "images", "formes"]
            for el in slide.get(key, []) if "id" in el
        }
        right = screens["right"]["elements"]
        y = max((e.get("positionY", 0) + e.get("height", 0.1) for e in right), default=0.05)
        for mid in missing:
            el = dict(all_els.get(mid, {"id": mid}))
            el["positionX"] = 0.05
            el["positionY"] = round(min(y + 0.04, 0.90), 4)
            el["width"]     = 0.90
            el["height"]    = round(min(el.get("height", 0.12), 0.25), 4)
            right.append(el)
            y = el["positionY"] + el["height"]
            print(f"     repair: id={mid} re-injected into right")
    return result


# ── FALLBACK — deterministic, all into center, last resort only ────────────────
def fallback_layout(slide: dict) -> dict:
    all_els = (
        [normalize_element(t) for t in slide.get("textes", [])] +
        [normalize_element(i) for i in slide.get("images", [])] +
        [normalize_element(f) for f in slide.get("formes", [])]
    )
    y = 0.03
    for el in all_els:
        el["positionX"] = 0.05
        el["positionY"] = round(y, 4)
        el["width"]     = 0.90
        h = min(el.get("height", 0.15), 0.28)
        el["height"]    = h
        y = round(y + h + 0.03, 4)
        if y > 0.95:
            y = 0.03
    return {
        "id":    slide.get("id", 0),
        "order": slide.get("slide_number", 0),
        "screens": {
            "left":   {"elements": []},
            "center": {"elements": all_els},
            "right":  {"elements": []},
        }
    }


# ── IMAGE PATHS ────────────────────────────────────────────────────────────────
def get_image_paths(slide: dict) -> list:
    paths = []
    for img in slide.get("images", []):
        path = img.get("content", "").replace("\\", "/")
        if path and os.path.exists(path):
            paths.append(path)
        else:
            print(f"  warning: image not found: {path}")
    return paths


# ── ELEMENT CATALOG (readable summary for prompts) ────────────────────────────
def build_element_catalog(slide: dict) -> str:
    """
    Builds a human-readable catalog of ALL elements with semantic hints.
    Used by prompts to feed the LLM a compact but rich view of the content.
    """
    lines = []
    texts = sorted(slide.get("textes", []), key=lambda t: t.get("font_size", 12), reverse=True)
    for rank, t in enumerate(texts):
        fs    = t.get("font_size", 12)
        bold  = t.get("bold", False)
        role  = "TITLE" if (rank == 0 or bold or fs >= 20) else "BODY"
        content = t.get("content", "").strip().replace("\n", " ")[:120]
        lines.append(f"  [{role}] id={t['id']} fs={fs} bold={bold} → \"{content}\"")

    for img in slide.get("images", []):
        w = img.get("width", 0)
        h = img.get("height", 0)
        lines.append(f"  [IMAGE] id={img['id']} size={w:.2f}x{h:.2f} → \"{img.get('content','')}\"")

    for f in slide.get("formes", []):
        lines.append(f"  [SHAPE] id={f['id']} name=\"{f.get('name','')}\" fill={f.get('fill_color','')}")

    return "\n".join(lines) if lines else "  (empty slide)"


# ── SAVE ───────────────────────────────────────────────────────────────────────
def save_output(immerslides: list, output_file: str):
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({"immerslides": immerslides}, f, indent=2, ensure_ascii=False)
    print(f"  saved {len(immerslides)} immerslide(s) → {output_file}")


# ── EXTRACT JSON LIST (pour pass 2 qui retourne une liste) ────────────────────
def extract_json_list(text: str) -> list:
    """Extract first valid JSON array from LLM output."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()

    # Chercher d'abord un tableau JSON
    idx = 0
    while idx < len(text):
        start = text.find("[", idx)
        if start == -1:
            break
        try:
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(text[start:])
            if isinstance(obj, list):
                return obj
        except json.JSONDecodeError:
            pass
        idx = start + 1

    # Fallback : chercher un objet avec "elements"
    try:
        obj = extract_json(text)
        if "elements" in obj:
            return obj["elements"]
    except Exception:
        pass

    raise ValueError("No valid JSON array found.")


# ── STACK ELEMENTS — fallback déterministe pour pass 2 ───────────────────────
def stack_elements(elements: list) -> list:
    """
    Deterministic vertical stack — used when pass 2 LLM fails.
    Gives every element full width and stacks them from top to bottom.
    """
    result = []
    y = 0.05
    gap = 0.04

    for el in elements:
        e = dict(el)
        content = e.get("content", "")
        is_img = any(ext in content.lower() for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"])

        if is_img:
            h = 0.42
        elif e.get("font_family") or e.get("font_size"):
            # Texte : hauteur selon longueur
            text_len = len(content.strip())
            if text_len == 0 or content.strip() == "\n":
                continue  # ignorer textes vides
            h = 0.18 if text_len > 60 else 0.12
        else:
            # Forme
            if not e.get("fill_color"):
                continue  # ignorer formes invisibles
            h = 0.06

        if y + h > 0.95:
            break  # plus de place

        e["positionX"] = 0.04
        e["positionY"] = round(y, 4)
        e["width"]     = 0.92
        e["height"]    = round(h, 4)
        result.append(e)
        y = round(y + h + gap, 4)

    return result