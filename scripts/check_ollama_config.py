"""
Sprint v5.2 — Phase A.4 : Vérification config Ollama / GPU / VRAM

Interroge l'API Ollama locale pour rapporter :
- Modèles installés (`/api/tags`)
- Détails de chaque modèle vision (`/api/show`) : quantization, size,
  modelfile, parameters, family, format
- Modèles actuellement chargés en RAM/VRAM (`/api/ps`)
- État GPU (via nvidia-smi si disponible)

Usage:
    cd assistant-bureau
    python scripts/check_ollama_config.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests

OLLAMA_BASE = "http://127.0.0.1:11434"


def _section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def list_installed_models() -> list[dict]:
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5.0)
        r.raise_for_status()
        return r.json().get("models", []) or []
    except Exception as e:
        print(f"[ERROR] /api/tags : {e}")
        return []


def show_model(name: str) -> dict | None:
    try:
        r = requests.post(f"{OLLAMA_BASE}/api/show", json={"name": name}, timeout=10.0)
        if r.status_code != 200:
            print(f"[WARN] /api/show {name} → HTTP {r.status_code}")
            return None
        return r.json()
    except Exception as e:
        print(f"[ERROR] /api/show {name} : {e}")
        return None


def list_loaded_models() -> list[dict]:
    """`/api/ps` returns models currently loaded in memory (RAM/VRAM)."""
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/ps", timeout=5.0)
        if r.status_code != 200:
            return []
        return r.json().get("models", []) or []
    except Exception as e:
        print(f"[ERROR] /api/ps : {e}")
        return []


def nvidia_smi() -> str | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True, timeout=4.0,
        )
        return out.strip()
    except Exception as e:
        return f"nvidia-smi error: {e}"


def main():
    _section("OLLAMA — modèles installés (/api/tags)")
    installed = list_installed_models()
    if not installed:
        print("Aucun modèle ou Ollama indisponible.")
        sys.exit(2)
    for m in installed:
        name = m.get("name", "?")
        size = m.get("size", 0)
        size_gb = size / (1024 ** 3) if size else 0
        details = m.get("details", {}) or {}
        fam = details.get("family") or details.get("families") or "?"
        quant = details.get("quantization_level", "?")
        params = details.get("parameter_size", "?")
        fmt = details.get("format", "?")
        print(f"  {name}")
        print(f"    size={size_gb:.2f}GB | family={fam} | params={params} | quant={quant} | format={fmt}")

    _section("OLLAMA — modèles vision (/api/show)")
    vision_keywords = ("minicpm-v", "minicpm", "llava", "qwen2.5vl", "qwen2-vl")
    vision_models = [m["name"] for m in installed if any(m["name"].startswith(k) for k in vision_keywords)]
    if not vision_models:
        print("Aucun modèle vision détecté localement.")
    for name in vision_models:
        info = show_model(name)
        if info is None:
            continue
        details = info.get("details", {}) or {}
        modelfile_excerpt = (info.get("modelfile") or "")[:300].replace("\n", " ")
        print(f"  {name}")
        print(f"    family       = {details.get('family') or details.get('families')}")
        print(f"    parameter_sz = {details.get('parameter_size')}")
        print(f"    quantization = {details.get('quantization_level')}")
        print(f"    format       = {details.get('format')}")
        print(f"    template     = {(info.get('template') or '')[:80]!r}")
        print(f"    modelfile[:300] = {modelfile_excerpt!r}")
        # Try to get model_info numeric stats
        mi = info.get("model_info") or {}
        if mi:
            print(f"    model_info keys ({len(mi)}): {list(mi.keys())[:8]}")

    _section("OLLAMA — modèles chargés en mémoire (/api/ps)")
    loaded = list_loaded_models()
    if not loaded:
        print("Aucun modèle actuellement chargé en RAM/VRAM.")
    for m in loaded:
        name = m.get("name", "?")
        size_total = m.get("size", 0) / (1024 ** 3)
        size_vram = m.get("size_vram", 0) / (1024 ** 3) if m.get("size_vram") else 0
        expires = m.get("expires_at", "?")
        gpu_pct = round((size_vram / size_total * 100), 1) if size_total else 0
        print(f"  {name}")
        print(f"    size_total = {size_total:.2f}GB | size_vram = {size_vram:.2f}GB ({gpu_pct}% on GPU)")
        print(f"    expires_at = {expires}")

    _section("GPU — nvidia-smi")
    smi = nvidia_smi()
    if smi is None:
        print("nvidia-smi indisponible (pas de GPU NVIDIA ou utilitaire absent).")
    else:
        print("name | mem.total(MB) | mem.used(MB) | mem.free(MB) | gpu.util(%)")
        print(smi)

    _section("DIAGNOSTIC RAPIDE")
    qwen_loaded = any(m.get("name", "").startswith("qwen") for m in loaded)
    minicpm_loaded = any(m.get("name", "").startswith("minicpm") for m in loaded)
    if qwen_loaded and minicpm_loaded:
        total_vram = sum(m.get("size_vram", 0) for m in loaded) / (1024 ** 3)
        print(f"⚠️  Qwen + MiniCPM chargés simultanément — VRAM totale modèles: {total_vram:.2f}GB")
        print("   Si VRAM système < ce total, un modèle est offload CPU → latence vision élevée.")
    elif minicpm_loaded:
        m = next(m for m in loaded if m["name"].startswith("minicpm"))
        size_vram = m.get("size_vram", 0) / (1024 ** 3)
        size_total = m.get("size", 0) / (1024 ** 3)
        if size_vram < size_total * 0.95:
            print(f"⚠️  MiniCPM partiellement offload CPU ({size_vram:.2f}GB / {size_total:.2f}GB en VRAM)")
        else:
            print(f"✅ MiniCPM entièrement en VRAM ({size_vram:.2f}GB)")
    else:
        print("ℹ️  MiniCPM-V pas chargé en mémoire — premier appel = chargement initial (lent).")
    print()


if __name__ == "__main__":
    main()
