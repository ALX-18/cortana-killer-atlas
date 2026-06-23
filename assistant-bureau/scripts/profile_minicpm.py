"""
Sprint v5.2 — Phase A.2 : Profiling MiniCPM-V isolé

Capture un screenshot de la fenêtre Steam et envoie 5 fois la même requête
à Ollama directement (sans passer par le grounding stack). Mesure la latence
de chaque appel pour distinguer "lenteur Ollama" de "lenteur Atlas".

Usage:
    cd assistant-bureau
    python scripts/profile_minicpm.py [--app "Steam"] [--element "Bibliothèque"] [--n 5]

Sortie:
    - Latence par appel (capture, encode, ollama, parse)
    - Stats agrégées : min, max, médiane, écart-type
    - Réponses brutes (200 premiers chars)
"""

from __future__ import annotations

import argparse
import base64
import json
import statistics
import sys
import time
from io import BytesIO
from pathlib import Path

# Allow running from project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests

from tools.grounding import (
    _capture_window_screenshot,
    _choose_best_window,
    _find_candidate_windows,
    _preferred_vision_models,
    _steam_label_aliases,
    _steam_nav_crop,
    _OLLAMA_GENERATE_URL,
    _VISION_TIMEOUT_DEFAULT_S,
    _VISION_TIMEOUT_MINICPM_S,
)


def _b64(img) -> str:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def capture(app_title: str):
    windows = _find_candidate_windows(app_title)
    w = _choose_best_window(windows, app_title)
    if w is None:
        raise RuntimeError(f"Fenêtre '{app_title}' introuvable. Ouvre l'app et relance.")
    if getattr(w, "isMinimized", False):
        try:
            w.restore()
        except Exception:
            pass
        time.sleep(0.3)
    captured = _capture_window_screenshot(w)
    if captured is None:
        raise RuntimeError("Capture impossible (fenêtre invisible ?).")
    return captured  # (img, origin_x, origin_y)


def build_payload(model: str, img, element_name: str, app_title: str):
    is_steam = "steam" in app_title.lower()
    use_img = _steam_nav_crop(img) if is_steam else img
    labels = _steam_label_aliases(element_name) if is_steam else [element_name]
    labels_hint = ", ".join(dict.fromkeys(labels))
    image_b64 = _b64(use_img)
    payload = {
        "model": model,
        "prompt": (
            f"Find the clickable UI label among these candidate texts: {labels_hint}. "
            "Return strictly and only valid JSON with integer pixel coordinates relative to this screenshot: "
            "{\"x\": int, \"y\": int, \"found\": bool}. No markdown, no explanation."
            " Do NOT return arrays for x/y. No markdown, no explanation."
        ),
        "images": [image_b64],
        "stream": False,
    }
    return payload, len(image_b64), use_img.size


def run_once(model: str, payload: dict, timeout_s: float) -> dict:
    t0 = time.monotonic()
    try:
        resp = requests.post(_OLLAMA_GENERATE_URL, json=payload, timeout=timeout_s)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return {
            "ok": resp.status_code == 200,
            "status": resp.status_code,
            "elapsed_ms": elapsed_ms,
            "response": resp.json().get("response", "") if resp.status_code == 200 else "",
            "error": None,
        }
    except requests.Timeout:
        return {
            "ok": False,
            "status": -1,
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
            "response": "",
            "error": f"timeout({timeout_s}s)",
        }
    except Exception as e:
        return {
            "ok": False,
            "status": -1,
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
            "response": "",
            "error": str(e)[:200],
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default="Steam", help="Titre de fenêtre (default: Steam)")
    ap.add_argument("--element", default="Bibliothèque", help="Nom élément (default: Bibliothèque)")
    ap.add_argument("--n", type=int, default=5, help="Nombre d'appels (default: 5)")
    ap.add_argument("--model", default=None, help="Modèle vision spécifique (default: auto)")
    args = ap.parse_args()

    print(f"=== Profiling MiniCPM-V — app='{args.app}' element='{args.element}' n={args.n} ===")

    # Choose model
    if args.model:
        model = args.model
    else:
        models = _preferred_vision_models()
        if not models:
            print("[ERROR] Aucun modèle vision détecté localement. Vérifie 'ollama list'.")
            sys.exit(2)
        model = models[0]
    print(f"Model: {model}")

    timeout = _VISION_TIMEOUT_MINICPM_S if model.startswith("minicpm") else _VISION_TIMEOUT_DEFAULT_S
    print(f"HTTP timeout: {timeout}s")

    # Capture once
    print("Capture...")
    cap_start = time.monotonic()
    img, ox, oy = capture(args.app)
    cap_ms = int((time.monotonic() - cap_start) * 1000)
    print(f"Capture: {img.size[0]}x{img.size[1]} en {cap_ms}ms")

    # Build payload once (same image, same prompt, N calls)
    prep_start = time.monotonic()
    payload, b64_size, used_size = build_payload(model, img, args.element, args.app)
    prep_ms = int((time.monotonic() - prep_start) * 1000)
    print(f"Prepare: {prep_ms}ms | image_b64={b64_size} bytes | payload={len(json.dumps(payload))} bytes | crop_size={used_size[0]}x{used_size[1]}")

    # N calls
    print(f"\n--- {args.n} appels Ollama ---")
    latencies: list[int] = []
    successes = 0
    for i in range(args.n):
        result = run_once(model, payload, timeout)
        latencies.append(result["elapsed_ms"])
        if result["ok"]:
            successes += 1
        flag = "OK" if result["ok"] else f"FAIL({result.get('error') or result.get('status')})"
        raw_preview = (result.get("response") or "")[:200].replace("\n", " ")
        print(f"  Call {i+1}/{args.n}: {result['elapsed_ms']}ms  [{flag}]  raw='{raw_preview}'")

    # Stats
    print("\n--- Stats latence (ms) ---")
    print(f"  successes : {successes}/{args.n}")
    print(f"  min       : {min(latencies)}")
    print(f"  max       : {max(latencies)}")
    print(f"  median    : {int(statistics.median(latencies))}")
    print(f"  mean      : {int(statistics.mean(latencies))}")
    if len(latencies) > 1:
        print(f"  stdev     : {int(statistics.stdev(latencies))}")
    print()


if __name__ == "__main__":
    main()
