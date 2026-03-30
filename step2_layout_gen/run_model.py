"""
run_model.py — Universal runner for all model × prompt combinations
====================================================================
Usage:
  python step2_layout_gen/run_model.py --model qwen --prompt v3_iaa
  python step2_layout_gen/run_model.py --model llava --prompt v1_basic
  python step2_layout_gen/run_model.py --model qwen --prompt v2_semantic --slides 1,2,3

Arguments:
  --model   : llava | qwen          (which Ollama model to use)
  --prompt  : v1_basic | v2_semantic | v3_iaa | v4_multimodal
  --slides  : optional, comma-separated slide numbers to process (default: all)
  --input   : path to slides_ready.json (default: data/input/slides_ready.json)

Output:
  step2_layout_gen/outputs/{model}_{prompt}_{timestamp}.json

This is the ONLY file you run. You never edit it.
To test a new prompt: create prompts/v5_xxx.py and pass --prompt v5_xxx.
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
        "no_think":    False,
    },
    "qwen": {
        "name":        "qwen3-vl:2b-instruct-q8_0",
        "temperature": 0.0,
        "num_predict": 3000,
        "num_ctx":     6000,
        "no_think":    True,   # /no_think prefix handled in prompts
    },
}

MAX_RETRIES = 3


# ── LLM CALL ───────────────────────────────────────────────────────────────────
def call_llm(model_cfg: dict, prompt: str, image_paths: list) -> str:
    t0 = time.time()
    response = ollama.chat(
        model=model_cfg["name"],
        messages=[{
            "role":    "user",
            "content": prompt,
            "images":  image_paths,
        }],
        options={
            "temperature":    model_cfg["temperature"],
            "top_p":          1.0,
            "num_predict":    model_cfg["num_predict"],
            "num_ctx":        model_cfg["num_ctx"],
            "repeat_penalty": 1.1,
        },
    )
    elapsed = time.time() - t0
    print(f"      LLM: {elapsed:.1f}s  ({len(response['message']['content'])} chars)")
    return response["message"]["content"]


# ── PROCESS ONE SLIDE ──────────────────────────────────────────────────────────
def process_slide(slide: dict, model_cfg: dict, prompt_module) -> dict:
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
            print(f"   missing 'screens' key")
            continue

        errors = utils.validate(parsed, slide_norm)
        if errors:
            print(f"   {len(errors)} validation error(s) → repair")
            for err in errors[:3]:
                print(f"      • {err}")
            parsed = utils.repair(parsed, slide_norm)

        result_data = parsed
        print(f"   ok")
        break

    if result_data is None:
        print(f"   fallback layout")
        result_data = utils.fallback_layout(slide_norm)

    for sk in ["left", "center", "right"]:
        n = len(result_data["screens"][sk]["elements"])
        print(f"      {sk}: {n} element(s)")

    return result_data


# ── MAIN ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="ImmerSlide layout generator")
    parser.add_argument("--model",  required=True, choices=list(MODELS.keys()),
                        help="Model to use: llava or qwen")
    parser.add_argument("--prompt", required=True,
                        help="Prompt version: v1_basic, v2_semantic, v3_iaa, v4_multimodal, ...")
    parser.add_argument("--slides", default=None,
                        help="Comma-separated slide numbers to process (default: all)")
    parser.add_argument("--input",  default="data/input/slides_ready.json",
                        help="Path to input JSON")
    args = parser.parse_args()

    # Load prompt module dynamically
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{args.prompt}.py")
    if not os.path.exists(prompt_path):
        print(f"Error: prompt file not found: {prompt_path}")
        print(f"Available prompts: {os.listdir(os.path.join(os.path.dirname(__file__), 'prompts'))}")
        sys.exit(1)

    spec   = importlib.util.spec_from_file_location("prompt_mod", prompt_path)
    prompt_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prompt_module)

    model_cfg = MODELS[args.model]

    # Load slides
    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)
    slides = data.get("slides", [])

    # Filter slides if requested
    if args.slides:
        wanted = {int(x.strip()) for x in args.slides.split(",")}
        slides = [s for s in slides if s.get("slide_number") in wanted]

    print(f"\n{'='*60}")
    print(f"Model  : {model_cfg['name']}")
    print(f"Prompt : {args.prompt}")
    print(f"Slides : {len(slides)}")
    print(f"{'='*60}\n")

    # Output filename includes model + prompt + timestamp
    timestamp   = time.strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(
        os.path.dirname(__file__),
        "outputs",
        f"{args.model}_{args.prompt}_{timestamp}.json"
    )

    immerslides   = []
    used_fallback = []
    t_total       = time.time()

    for slide in slides:
        snum   = slide.get("slide_number", "?")
        result = process_slide(slide, model_cfg, prompt_module)
        immerslides.append(result)
        # Track fallbacks (all elements in center = fallback)
        if (not result["screens"]["left"]["elements"] and
                not result["screens"]["right"]["elements"]):
            used_fallback.append(snum)

    utils.save_output(immerslides, output_file)

    print(f"\n{'='*60}")
    print(f"Done: {len(immerslides)} immerslide(s) in {time.time()-t_total:.1f}s")
    print(f"Output: {output_file}")
    if used_fallback:
        print(f"Fallback used for slides: {used_fallback}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
