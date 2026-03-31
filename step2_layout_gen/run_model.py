"""
run_model.py — Universal runner for all model × prompt combinations
====================================================================
Usage:
  python step2_layout_gen/run_model.py --model qwen --prompt v3_iaa
  python step2_layout_gen/run_model.py --model qwen --prompt v5_two_pass
  python step2_layout_gen/run_model.py --model llava --prompt v1_basic --slides 1,2,3

Arguments:
  --model   : llava | qwen
  --prompt  : v1_basic | v2_semantic | v3_iaa | v4_multimodal | v5_two_pass | ...
  --slides  : optional, comma-separated slide numbers (default: all)
  --input   : path to slides_ready.json (default: data/input/slides_ready.json)

Output:
  step2_layout_gen/outputs/{model}_{prompt}.json

Two-pass detection: if the prompt file has build_prompt_assign() and
build_prompt_position(), two-pass mode is used automatically.
"""

import argparse
import importlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import utils
import ollama

# ── MODEL REGISTRY ─────────────────────────────────────────────────────────────
MODELS = {
    "llava": {
        "name":        "llava:latest",
        "temperature": 0.2,
        "num_predict": 2048,
        "num_ctx":     4096,
        "repeat_penalty": 1.1,
    },
    "qwen": {
        "name":        "qwen3-vl:2b-instruct-q8_0",
        "temperature": 0.0,
        "num_predict": 2048,
        "num_ctx":     6000,
        "repeat_penalty": 1.1,
    },
    "llama32": {
    "name":           "llama3.2-vision:11b",
    "temperature":    0.0,
    "num_predict":    2048,
    "num_ctx":        8192,
    "repeat_penalty": 1.1,
},
}

MAX_RETRIES = 3


# ── LLM CALL ───────────────────────────────────────────────────────────────────
def call_llm(model_cfg: dict, prompt: str, image_paths: list = None) -> str:
    t0 = time.time()
    response = ollama.chat(
        model=model_cfg["name"],
        messages=[{
            "role":    "user",
            "content": prompt,
            "images":  image_paths or [],
        }],
        options={
            "temperature":    model_cfg.get("temperature", 0.0),
            "top_p":          1.0,
            "num_predict":    model_cfg.get("num_predict", 2048),
            "num_ctx":        model_cfg.get("num_ctx", 4096),
            "repeat_penalty": model_cfg.get("repeat_penalty", 1.1),
        },
    )
    elapsed = time.time() - t0
    content = response["message"]["content"]
    print(f"      LLM: {int(elapsed)}s  ({len(content)} chars)")
    return content


# ── PROCESS SLIDE — STANDARD (v1 à v4) ────────────────────────────────────────
def process_slide_standard(slide: dict, model_cfg: dict, prompt_module) -> dict:
    snum       = slide.get("slide_number", "?")
    slide_norm = utils.normalize_slide(slide)
    img_paths  = utils.get_image_paths(slide_norm)
    catalog    = utils.build_element_catalog(slide_norm)

    n_t = len(slide_norm.get("textes", []))
    n_i = len(slide_norm.get("images", []))
    n_f = len(slide_norm.get("formes", []))
    print(f"   slide {snum}: {n_t} texts  {n_i} images  {n_f} shapes")

    result_data = None

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"   attempt {attempt}/{MAX_RETRIES}...")
        prompt = (
            prompt_module.build_prompt(slide_norm, catalog)
            if attempt == 1
            else prompt_module.build_retry_prompt(slide_norm, catalog)
        )
        try:
            raw    = call_llm(model_cfg, prompt, img_paths)
            parsed = utils.extract_json(raw)
        except Exception as e:
            print(f"   error: {e}")
            continue

        if "screens" not in parsed:
            print(f"   missing 'screens'")
            continue

        errors = utils.validate(parsed, slide_norm)
        if errors:
            print(f"   {len(errors)} error(s) → repair")
            for err in errors[:3]:
                print(f"      • {err}")
            parsed = utils.repair(parsed, slide_norm)

        result_data = parsed
        print(f"   ok")
        break

    if result_data is None:
        print(f"   fallback")
        result_data = utils.fallback_layout(slide_norm)

    for sk in ["left", "center", "right"]:
        n = len(result_data["screens"][sk]["elements"])
        print(f"      {sk}: {n} element(s)")

    return result_data


# ── PROCESS SLIDE — TWO PASS (v5+) ────────────────────────────────────────────
def process_slide_two_pass(slide: dict, model_cfg: dict, prompt_module) -> dict:
    snum       = slide.get("slide_number", "?")
    slide_norm = utils.normalize_slide(slide)
    img_paths  = utils.get_image_paths(slide_norm)
    catalog    = utils.build_element_catalog(slide_norm)

    # Index tous les éléments par ID
    all_elements = {}
    for key in ["textes", "images", "formes"]:
        for el in slide_norm.get(key, []):
            if "id" in el:
                all_elements[el["id"]] = el

    all_ids = set(all_elements.keys())
    n_t = len(slide_norm.get("textes", []))
    n_i = len(slide_norm.get("images", []))
    n_f = len(slide_norm.get("formes", []))
    print(f"   slide {snum}: {n_t} texts  {n_i} images  {n_f} shapes  ({len(all_ids)} total)")

    # ── PASS 1 — Assignation sémantique ────────────────────────────────────────
    print(f"   [pass 1] semantic assignment...")
    assignment = {"left": [], "center": [], "right": []}

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"      attempt {attempt}/{MAX_RETRIES}...")
        prompt = (
            prompt_module.build_prompt_assign(slide_norm, catalog)
            if attempt == 1
            else prompt_module.build_prompt_assign_retry(slide_norm, catalog)
        )
        try:
            raw    = call_llm(model_cfg, prompt, img_paths)
            parsed = utils.extract_json(raw)

            if "left" in parsed and "center" in parsed and "right" in parsed:
                assigned_ids = set()
                for sk in ["left", "center", "right"]:
                    for eid in parsed.get(sk, []):
                        if eid in all_elements:
                            assigned_ids.add(eid)
                            assignment[sk].append(eid)

                # IDs non assignés → right
                missing = all_ids - assigned_ids
                if missing:
                    print(f"      {len(missing)} unassigned → right: {missing}")
                    assignment["right"].extend(list(missing))

                print(f"      left:{len(assignment['left'])}  center:{len(assignment['center'])}  right:{len(assignment['right'])}")
                break
            else:
                print(f"      invalid assignment response")

        except Exception as e:
            print(f"      error: {e}")

    else:
        # Fallback assignation
        print(f"      fallback assignment")
        texts  = [el["id"] for el in slide_norm.get("textes", [])]
        images = [el["id"] for el in slide_norm.get("images", [])]
        shapes = [el["id"] for el in slide_norm.get("formes", [])]
        assignment["left"]   = texts[:1]
        assignment["center"] = images[:1] if images else texts[1:2]
        assignment["right"]  = (texts[1:] if images else texts[2:]) + images[1:] + shapes

    # ── PASS 2 — Positionnement par écran ──────────────────────────────────────
    print(f"   [pass 2] positioning...")
    screens = {}

    for sk in ["left", "center", "right"]:
        ids_for_screen     = assignment[sk]
        elements_for_screen = [all_elements[eid] for eid in ids_for_screen if eid in all_elements]

        if not elements_for_screen:
            screens[sk] = {"elements": []}
            continue

        positioned = None

        for attempt in range(1, MAX_RETRIES + 1):
            prompt = (
                prompt_module.build_prompt_position(sk, elements_for_screen, slide.get("id", 0), slide.get("slide_number", 0))
                if attempt == 1
                else prompt_module.build_prompt_position_retry(sk, elements_for_screen)
            )
            try:
                raw    = call_llm(model_cfg, prompt)
                parsed = utils.extract_json_list(raw)

                if parsed and isinstance(parsed, list) and len(parsed) > 0:
                    # Clamp toutes les valeurs
                    clean = []
                    for el in parsed:
                        for field in ["positionX", "positionY", "width", "height"]:
                            v = el.get(field, 0)
                            el[field] = round(max(0.0, min(1.0, float(v))), 4)
                        clean.append(el)
                    positioned = clean
                    break

            except Exception as e:
                print(f"      {sk} attempt {attempt} error: {e}")

        if positioned is None:
            print(f"      {sk}: fallback stack")
            positioned = utils.stack_elements(elements_for_screen)

        screens[sk] = {"elements": positioned}
        print(f"      {sk}: {len(positioned)} element(s)")

    return {
        "id":      slide.get("id", 0),
        "order":   slide.get("slide_number", 0),
        "screens": screens,
    }


# ── MAIN ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="ImmerSlide layout generator")
    parser.add_argument("--model",  required=True, choices=list(MODELS.keys()))
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--slides", default=None)
    parser.add_argument("--input",  default="data/input/slides_ready.json")
    args = parser.parse_args()

    # Charger le module prompt
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{args.prompt}.py")
    if not os.path.exists(prompt_path):
        print(f"Error: prompt not found: {prompt_path}")
        available = [f for f in os.listdir(os.path.join(os.path.dirname(__file__), "prompts"))
                     if f.endswith(".py") and not f.startswith("__")]
        print(f"Available: {available}")
        sys.exit(1)

    spec          = importlib.util.spec_from_file_location("prompt_mod", prompt_path)
    prompt_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prompt_module)

    # Détecter automatiquement le mode two-pass
    is_two_pass = (
        hasattr(prompt_module, "build_prompt_assign") and
        hasattr(prompt_module, "build_prompt_position")
    )

    model_cfg = MODELS[args.model]

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)
    slides = data.get("slides", [])

    if args.slides:
        wanted = {int(x.strip()) for x in args.slides.split(",")}
        slides = [s for s in slides if s.get("slide_number") in wanted]

    mode_label = "[TWO-PASS]" if is_two_pass else "[STANDARD]"
    print(f"\n{'='*60}")
    print(f"Model  : {model_cfg['name']}")
    print(f"Prompt : {args.prompt}  {mode_label}")
    print(f"Slides : {len(slides)}")
    print(f"{'='*60}\n")

    output_file = os.path.join(
        os.path.dirname(__file__),
        "outputs",
        f"{args.model}_{args.prompt}.json"
    )

    immerslides   = []
    used_fallback = []
    t_total       = time.time()

    for slide in slides:
        snum = slide.get("slide_number", "?")
        if is_two_pass:
            result = process_slide_two_pass(slide, model_cfg, prompt_module)
        else:
            result = process_slide_standard(slide, model_cfg, prompt_module)

        immerslides.append(result)

        # Checkpoint après chaque slide
        utils.save_output(immerslides, output_file)

        if (not result["screens"]["left"]["elements"] and
                not result["screens"]["right"]["elements"]):
            used_fallback.append(snum)

    elapsed = int(time.time() - t_total)
    minutes = elapsed // 60
    seconds = elapsed % 60

    print(f"\n{'='*60}")
    print(f"Done   : {len(immerslides)} immerslide(s) in {minutes} min {seconds} sec")
    print(f"Output : {output_file}")
    if used_fallback:
        print(f"Fallback: slides {used_fallback}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()