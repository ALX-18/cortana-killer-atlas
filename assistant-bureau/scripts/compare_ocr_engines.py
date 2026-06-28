"""
Sprint v6.0 — F2 : Comparatif Tesseract vs EasyOCR.

Génère des images de libellés UI typiques (français, anti-aliasing simulé) et
compare les deux moteurs OCR sur précision + latence.

Usage:
    cd assistant-bureau
    python scripts/compare_ocr_engines.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Libellés UI typiques (Steam/Discord/Electron)
LABELS = [
    "Bibliothèque", "Magasin", "Communauté", "Paramètres",
    "Accueil", "Contacts", "Réglages", "Nouveautés",
]


def _make_label_image(text: str, size=(300, 70)):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", size, (30, 33, 40))  # fond sombre type Steam/Discord
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("segoeui.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
    draw.text((14, 18), text, fill=(220, 222, 226), font=font)
    return img


def _norm(s: str) -> str:
    import unicodedata
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def run_tesseract(img) -> str:
    import pytesseract
    return pytesseract.image_to_string(img, lang="fra+eng").strip()


def run_easyocr(reader, img) -> str:
    import numpy as np
    res = reader.readtext(np.array(img), detail=0)
    return " ".join(res).strip()


def main():
    print("=== Comparatif Tesseract vs EasyOCR (libellés UI FR) ===\n")
    imgs = [(lbl, _make_label_image(lbl)) for lbl in LABELS]

    # Tesseract
    print("Chargement Tesseract... ", end="", flush=True)
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        print("OK")
    except Exception as e:
        print(f"INDISPONIBLE ({e})")
        return

    # EasyOCR
    print("Chargement EasyOCR (peut télécharger les modèles au 1er run)... ", end="", flush=True)
    try:
        import easyocr
        t0 = time.monotonic()
        reader = easyocr.Reader(["fr", "en"], verbose=False)
        print(f"OK ({time.monotonic()-t0:.1f}s)")
    except Exception as e:
        print(f"INDISPONIBLE ({e})")
        reader = None

    tess_hits = easy_hits = 0
    tess_total = easy_total = 0.0
    print(f"\n{'Libellé':<16}{'Tesseract':<28}{'EasyOCR':<28}")
    print("-" * 72)
    for lbl, img in imgs:
        t0 = time.monotonic()
        t_out = run_tesseract(img)
        t_lat = (time.monotonic() - t0) * 1000
        tess_total += t_lat
        t_ok = _norm(lbl) in _norm(t_out)
        tess_hits += t_ok

        if reader is not None:
            t0 = time.monotonic()
            e_out = run_easyocr(reader, img)
            e_lat = (time.monotonic() - t0) * 1000
            easy_total += e_lat
            e_ok = _norm(lbl) in _norm(e_out)
            easy_hits += e_ok
        else:
            e_out, e_lat, e_ok = "-", 0, False

        print(f"{lbl:<16}{t_out[:18]+' '+('✓' if t_ok else '✗'):<28}"
              f"{(e_out[:18]+' '+('✓' if e_ok else '✗')):<28}")

    n = len(imgs)
    print("-" * 72)
    print(f"\nPrécision  : Tesseract {tess_hits}/{n}   EasyOCR {easy_hits}/{n}")
    print(f"Latence moy: Tesseract {tess_total/n:.0f}ms   EasyOCR {easy_total/n if reader else 0:.0f}ms")
    print("\nNote : Tesseract = rapide, EasyOCR = robuste sur anti-aliasing/glyphes difficiles.")
    print("Atlas utilise Tesseract en couche 3, EasyOCR en fallback couche 3.5.")


if __name__ == "__main__":
    main()
