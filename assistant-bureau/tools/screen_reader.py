"""
Screen Reader — F2 v6.0.

Capture la fenêtre active, extrait le texte par OCR (Tesseract → EasyOCR fallback),
et le résume via Qwen 7B. Couvre les cas d'usage F2 non-clic :
  CU-1 "Lis-moi ce qui est à l'écran"
  CU-3 "Que fais-je actuellement ?"
  CU-4 "Résume cette page"
  CU-5 "Que vois-tu à l'écran ?"
"""

import logging
from typing import Optional

logger = logging.getLogger("atlas.screen_reader")

MAX_OCR_CHARS = 4000


def _capture_foreground():
    """Capture la fenêtre active. Retourne (image, title, process) ou None."""
    try:
        import pygetwindow as gw
        from tools.grounding import _capture_window_screenshot, _get_window_process_info

        w = gw.getActiveWindow()
        if w is None:
            return None
        captured = _capture_window_screenshot(w)
        if captured is None:
            return None
        img, _, _ = captured
        proc_name, _ = _get_window_process_info(w)
        return img, getattr(w, "title", ""), proc_name
    except Exception as e:
        logger.debug("Capture foreground échouée : %s", e)
        return None


def _ocr_text(img) -> str:
    """Extrait tout le texte d'une image (Tesseract, puis EasyOCR en fallback)."""
    # Tesseract d'abord
    try:
        import pytesseract
        txt = pytesseract.image_to_string(img, lang="fra+eng")
        if txt and txt.strip():
            return txt.strip()[:MAX_OCR_CHARS]
    except Exception as e:
        logger.debug("Tesseract full-text échoué : %s", e)

    # EasyOCR fallback
    try:
        import numpy as np
        from tools.grounding import _get_easyocr_reader
        reader = _get_easyocr_reader()
        if reader is not None:
            results = reader.readtext(np.array(img), detail=0)
            return " ".join(results)[:MAX_OCR_CHARS]
    except Exception as e:
        logger.debug("EasyOCR full-text échoué : %s", e)

    return ""


async def read_screen(mode: str = "read", summarize: bool = True) -> dict:
    """
    Lit le contenu de la fenêtre active.

    mode : "read" (résumé du contenu) | "activity" (que fais-je actuellement)
    Retourne {"success", "title", "process", "text", "summary", "message"}.
    """
    cap = _capture_foreground()
    if cap is None:
        return {"success": False, "message": "Impossible de capturer la fenêtre active."}
    img, title, process = cap

    text = _ocr_text(img)

    if mode == "activity":
        base = f"Tu utilises actuellement : {title or process or 'fenêtre inconnue'}."
        if not summarize or not text:
            return {"success": True, "title": title, "process": process,
                    "text": text, "summary": base, "message": base}
        prompt = (
            f"L'utilisateur demande ce qu'il fait actuellement. Fenêtre active : '{title}' "
            f"(processus {process}). Texte visible à l'écran :\n{text[:1500]}\n\n"
            "Réponds en 1-2 phrases : que fait l'utilisateur ?"
        )
    else:
        if not text:
            return {"success": True, "title": title, "process": process, "text": "",
                    "summary": "", "message": "Je ne lis aucun texte exploitable à l'écran."}
        if not summarize:
            return {"success": True, "title": title, "process": process, "text": text,
                    "summary": "", "message": text[:500]}
        prompt = (
            f"Voici le texte extrait par OCR de la fenêtre '{title}' :\n{text}\n\n"
            "Résume en français, en 2-3 phrases, ce qui est affiché à l'écran."
        )

    # Résumé via Qwen
    try:
        from core.ollama_client import chat_full
        summary = await chat_full(user_message=prompt, context={}, history=None)
        summary = (summary or "").strip()
    except Exception as e:
        logger.warning("Résumé LLM échoué : %s", e)
        summary = text[:400]

    return {
        "success": True,
        "title": title,
        "process": process,
        "text": text,
        "summary": summary,
        "message": summary or text[:400],
    }
