"""
Grounding Stack — Résolution des clics sémantiques en 4 couches.

Couche 1 : UIA / pywinauto (Win32 natif) — apps classiques
Couche 2 : Cache coordonnées (même fenêtre, même élément)
Couche 3 : OCR / tesseract (~50ms) — localisation de texte à l'écran
Couche 4 : MiniCPM-V (~300ms, dernier recours) — vision IA

Détection auto du type d'app :
- Win32 natif → UIA en premier
- Electron/modern → skip UIA, OCR direct
- Jeux/overlays → MiniCPM-V direct
"""

import asyncio
import logging
import math
import time
import json
import re
import base64
import ctypes
import os
from io import BytesIO
import unicodedata
from difflib import SequenceMatcher
from typing import Optional, Any

import pyautogui
import requests

logger = logging.getLogger("atlas.grounding")

_OLLAMA_MODELS_CACHE: list[str] = []
_OLLAMA_MODELS_CACHE_TS = 0.0
_OLLAMA_MODELS_TTL_S = 10.0
_VISION_TIMEOUT_DEFAULT_S = 12.0
_VISION_TIMEOUT_MINICPM_S = 45.0
_DEBUG_IMAGE_DIR = os.path.join("data", "debug")
_OLLAMA_GENERATE_URL = "http://127.0.0.1:11434/api/generate"

_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")


def _is_vision_enabled() -> bool:
    """Read vision_enabled from config/settings.json (default: True for backwards compat)."""
    try:
        with open(_SETTINGS_PATH, encoding="utf-8") as _f:
            _cfg = json.load(_f)
        return bool(_cfg.get("grounding", {}).get("vision_enabled", True))
    except Exception:
        return True


# v5.1 corrective — per-layer hard timeouts and global cap
GROUNDING_LAYER_TIMEOUT = {
    "uia": 3.0,        # 3s — UIA est rapide ou échoue rapide
    "cache": 0.5,      # 0.5s — purement local
    "ocr": 5.0,        # 5s — Tesseract sur fenêtre
    "vision": 8.0,     # 8s — MiniCPM-V hard cap
    "steam_nav_heuristic": 1.0,  # 1s — calcul de coordonnées + clic
}
GROUNDING_TOTAL_TIMEOUT = 20.0  # cap absolu, toutes couches confondues

def _coerce_int(value: Any) -> Optional[int]:
    """Coerce scalar/list-like numeric values to int when possible."""
    try:
        if isinstance(value, list):
            if not value:
                return None
            return _coerce_int(value[0])
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            m = re.search(r"-?\d+", value)
            if m:
                return int(m.group(0))
        return None
    except Exception:
        return None


def _normalize_vision_payload(payload: Optional[dict]) -> Optional[dict]:
    if not payload or not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    x = _coerce_int(normalized.get("x"))
    y = _coerce_int(normalized.get("y"))
    if x is not None:
        normalized["x"] = x
    if y is not None:
        normalized["y"] = y
    return normalized


def _normalize_text(text: str) -> str:
    s = (text or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _get_virtual_screen_bounds() -> tuple[int, int, int, int]:
    """Return virtual desktop bounds (left, top, right, bottom)."""
    try:
        user32 = ctypes.windll.user32
        left = int(user32.GetSystemMetrics(76))
        top = int(user32.GetSystemMetrics(77))
        width = int(user32.GetSystemMetrics(78))
        height = int(user32.GetSystemMetrics(79))
        return left, top, left + width, top + height
    except Exception:
        size = pyautogui.size()
        return 0, 0, int(size.width), int(size.height)


def _point_in_bounds(x: int, y: int, bounds: tuple[int, int, int, int]) -> bool:
    left, top, right, bottom = bounds
    return left <= x < right and top <= y < bottom


def _save_debug_image(img: Any, name: str) -> None:
    """Persist debug screenshots for grounding diagnostics."""
    try:
        os.makedirs(_DEBUG_IMAGE_DIR, exist_ok=True)
        path = os.path.join(_DEBUG_IMAGE_DIR, f"{name}.png")
        img.save(path)
        logger.info("[DEBUG] Image sauvegardee: %s", path)
    except Exception as e:
        logger.debug("[DEBUG] Save image failed: %s", e)


def _steam_nav_crop(img: Any) -> Any:
    """Top-left Steam navigation crop (covers top nav + left section)."""
    w, h = img.size
    nav_w = min(w, max(220, int(w * 0.45)))
    nav_h = min(h, max(120, int(h * 0.30)))
    return img.crop((0, 0, nav_w, nav_h))


def _preprocess_for_ocr(img: Any) -> Any:
    """Simple OCR preprocessing for anti-aliased UI labels."""
    from PIL import ImageEnhance

    gray = img.convert("L")
    enhanced = ImageEnhance.Contrast(gray).enhance(2.0)
    binary = enhanced.point(lambda x: 0 if x < 150 else 255, "1")
    return binary.convert("L")


def _verify_target_near_point(
    img: Any,
    local_x: int,
    local_y: int,
    target_aliases: set[str],
) -> tuple[bool, dict[str, Any]]:
    """Lightweight OCR verification around a predicted point.

    Returns (is_valid, details). This is designed to reject clear decoys like
    "magasin/store" for Steam "bibliotheque/library" clicks.
    """
    try:
        import pytesseract
    except Exception:
        return True, {"status": "ocr_unavailable"}

    w, h = img.size
    cx = max(0, min(w - 1, int(local_x)))
    cy = max(0, min(h - 1, int(local_y)))
    left = max(0, cx - 140)
    top = max(0, cy - 45)
    right = min(w, cx + 140)
    bottom = min(h, cy + 45)
    if right - left <= 8 or bottom - top <= 8:
        return True, {"status": "roi_too_small"}

    roi = img.crop((left, top, right, bottom))
    roi = _preprocess_for_ocr(roi)

    data = pytesseract.image_to_data(roi, output_type=pytesseract.Output.DICT, lang="fra+eng")
    best_text = ""
    best_conf = 0
    best_ratio = 0.0

    for i in range(len(data.get("text", []))):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        conf = int(data["conf"][i]) if data["conf"][i] != "-1" else 0
        txt_norm = _normalize_text(txt)
        if not txt_norm:
            continue
        ratio = max(SequenceMatcher(None, txt_norm, a).ratio() for a in target_aliases)
        if ratio > best_ratio or (ratio == best_ratio and conf > best_conf):
            best_ratio = ratio
            best_conf = conf
            best_text = txt_norm

    details = {
        "status": "ok",
        "best_text": best_text,
        "best_conf": best_conf,
        "best_ratio": round(best_ratio, 3),
    }

    # Strong accept: near exact text match around predicted point.
    if best_ratio >= 0.72:
        return True, details

    # Strong reject: clear decoy labels near the predicted point.
    decoys = {"magasin", "store", "shop"}
    if best_text in decoys and best_ratio < 0.62:
        details["status"] = "decoy_reject"
        return False, details

    # Soft accept to avoid over-blocking if OCR is uncertain.
    details["status"] = "uncertain_accept"
    return True, details


def _log_window_selection(app_title: str, w: Any) -> None:
    """Emit selected window details for debug traces."""
    try:
        proc_name, proc_exe = _get_window_process_info(w)
        logger.info(
            "[WINDOW] app='%s' title='%s' proc='%s' rect=(%s,%s,%s,%s)",
            app_title,
            getattr(w, "title", ""),
            proc_name,
            int(getattr(w, "left", 0)),
            int(getattr(w, "top", 0)),
            int(getattr(w, "width", 0)),
            int(getattr(w, "height", 0)),
        )
        if proc_exe:
            logger.info("[WINDOW] exe='%s'", proc_exe)
    except Exception:
        pass


def _choose_best_window(windows: list[Any], app_title: str = "") -> Optional[Any]:
    """Pick the most relevant window: active match first, then largest visible one."""
    if not windows:
        return None

    title_norm = _normalize_text(app_title)

    try:
        import pygetwindow as gw

        active = gw.getActiveWindow()
        if active is not None:
            active_hwnd = int(getattr(active, "_hWnd", 0))
            candidate_hwnds = {int(getattr(w, "_hWnd", 0)) for w in windows}
            # Only prioritize active window if it is one of the candidate windows.
            if active_hwnd not in candidate_hwnds:
                active = None

        if active is not None:
            active_title = _normalize_text(getattr(active, "title", ""))
            if title_norm and title_norm in active_title:
                return active
    except Exception:
        pass

    candidates = []
    for w in windows:
        try:
            width = int(getattr(w, "width", 0))
            height = int(getattr(w, "height", 0))
            minimized = bool(getattr(w, "isMinimized", False))
            if minimized or width <= 0 or height <= 0:
                continue
            area = width * height
            candidates.append((area, w))
        except Exception:
            continue

    if not candidates:
        return windows[0]

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _get_window_process_info(w: Any) -> tuple[str, str]:
    """Return (process_name, process_exe) for a window when available."""
    try:
        import win32process
        import psutil

        hwnd = int(getattr(w, "_hWnd", 0))
        if hwnd <= 0:
            return "", ""
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        return (proc.name() or "").lower(), (proc.exe() or "").lower()
    except Exception:
        return "", ""


def _is_steam_window(w: Any) -> bool:
    """True for native Steam windows (avoid web tabs that include 'steam' in title)."""
    title = _normalize_text(getattr(w, "title", ""))
    proc_name, proc_exe = _get_window_process_info(w)

    if proc_name in {"steam.exe", "steamwebhelper.exe"}:
        return True
    if "\\steam\\" in proc_exe or proc_exe.endswith("\\steam.exe"):
        return True
    if title == "steam":
        return True
    return False


def _find_candidate_windows(app_title: str) -> list[Any]:
    """Find candidate windows for an app with app-specific filtering."""
    try:
        import pygetwindow as gw

        title_norm = _normalize_text(app_title)
        if "steam" in title_norm:
            all_windows = gw.getAllWindows()
            steam_windows = [w for w in all_windows if _is_steam_window(w)]
            if steam_windows:
                return steam_windows

        return gw.getWindowsWithTitle(app_title)
    except Exception:
        return []


def _capture_window_screenshot(w: Any) -> Optional[tuple[Any, int, int]]:
    """Capture only the visible overlap of a window with the virtual desktop.

    Returns (image, origin_x, origin_y), where origin_* are screen coordinates
    of image top-left, used to remap OCR/vision local coordinates.
    """
    try:
        w_left = int(getattr(w, "left", 0))
        w_top = int(getattr(w, "top", 0))
        w_width = int(getattr(w, "width", 0))
        w_height = int(getattr(w, "height", 0))
        if w_width <= 1 or w_height <= 1:
            return None

        v_left, v_top, v_right, v_bottom = _get_virtual_screen_bounds()
        left = max(w_left, v_left)
        top = max(w_top, v_top)
        right = min(w_left + w_width, v_right)
        bottom = min(w_top + w_height, v_bottom)
        if right - left <= 1 or bottom - top <= 1:
            return None

        from PIL import ImageGrab

        # all_screens=True returns a virtual-desktop image on Windows.
        full = ImageGrab.grab(all_screens=True)
        fx, fy = full.size

        crop_left = max(0, left - v_left)
        crop_top = max(0, top - v_top)
        crop_right = min(fx, right - v_left)
        crop_bottom = min(fy, bottom - v_top)
        if crop_right - crop_left <= 1 or crop_bottom - crop_top <= 1:
            return None

        img = full.crop((crop_left, crop_top, crop_right, crop_bottom))
        return img, left, top
    except Exception as e:
        logger.debug("[CAPTURE] Failed: %s", e)
        return None


def _list_ollama_models() -> list[str]:
    """Return installed model names from local Ollama with a short TTL cache."""
    global _OLLAMA_MODELS_CACHE, _OLLAMA_MODELS_CACHE_TS
    now = time.time()
    if _OLLAMA_MODELS_CACHE and (now - _OLLAMA_MODELS_CACHE_TS) < _OLLAMA_MODELS_TTL_S:
        return _OLLAMA_MODELS_CACHE

    try:
        resp = requests.get("http://127.0.0.1:11434/api/tags", timeout=2.0)
        if resp.status_code != 200:
            return _OLLAMA_MODELS_CACHE
        models = [str(m.get("name", "")).strip().lower() for m in resp.json().get("models", [])]
        models = [m for m in models if m]
        _OLLAMA_MODELS_CACHE = models
        _OLLAMA_MODELS_CACHE_TS = now
        return models
    except Exception:
        return _OLLAMA_MODELS_CACHE


def _preferred_vision_models() -> list[str]:
    """Build an ordered list of vision-capable models available locally."""
    available = _list_ollama_models()
    preferred_prefixes = (
        "minicpm-v",
        "minicpm",
        "llava",
        "qwen2.5vl",
        "qwen2-vl",
    )

    picked = []
    for prefix in preferred_prefixes:
        for model in available:
            if model.startswith(prefix) and model not in picked:
                picked.append(model)

    # Backward-compatible fallbacks only if no explicit vision model is found.
    if not picked:
        for model in ("minicpm-v", "qwen2.5:14b"):
            if model not in picked:
                picked.append(model)

    return picked


def _has_local_minicpm() -> bool:
    return any(m.startswith("minicpm-v") or m.startswith("minicpm") for m in _list_ollama_models())


def _steam_label_aliases(element_name: str) -> list[str]:
    """Return Steam-specific aliases for frequent navigation labels."""
    norm = _normalize_text(element_name)
    if norm in {"bibliotheque", "bibliothèque", "library", "librairie"}:
        return ["bibliotheque", "bibliothèque", "library", "librairie"]
    return [element_name]


# Cooldown tracker: skip disambiguation for 30s after it was triggered for a given (app, element)
_disambiguation_cooldown: dict[str, float] = {}


def _should_check_disambiguation(app_title: str, element_name: str) -> bool:
    key = f"{app_title.lower()}:{element_name.lower()}"
    last = _disambiguation_cooldown.get(key, 0.0)
    return (time.time() - last) > 30.0


def _mark_disambiguation_triggered(app_title: str, element_name: str) -> None:
    key = f"{app_title.lower()}:{element_name.lower()}"
    _disambiguation_cooldown[key] = time.time()


def _check_proximity_disambiguation(
    img: Any,
    local_x: int,
    local_y: int,
    target_aliases: set[str],
    element_name: str,
    app_title: str,
    radius_px: int = 80,
) -> Optional[dict]:
    """
    After vision returns a point, check if other OCR elements are ambiguously close.
    Returns a disambiguation_required dict or None if no ambiguity.
    """
    try:
        import pytesseract
        from uuid import uuid4
        from core.confirmation import store_pending

        w, h = img.size
        left = max(0, local_x - radius_px)
        top = max(0, local_y - radius_px)
        right = min(w, local_x + radius_px)
        bottom = min(h, local_y + radius_px)

        if right - left < 10 or bottom - top < 10:
            return None

        roi = img.crop((left, top, right, bottom))
        data = pytesseract.image_to_data(roi, output_type=pytesseract.Output.DICT, lang="fra+eng")

        seen: set[str] = set()
        candidates: list[dict] = []
        for i in range(len(data.get("text", []))):
            txt = (data["text"][i] or "").strip()
            if not txt:
                continue
            conf = int(data["conf"][i]) if data["conf"][i] != "-1" else 0
            if conf < 25:
                continue
            txt_norm = _normalize_text(txt)
            if not txt_norm or txt_norm in seen:
                continue
            seen.add(txt_norm)
            cx = data["left"][i] + data["width"][i] // 2 + left
            cy = data["top"][i] + data["height"][i] // 2 + top
            dist = math.hypot(cx - local_x, cy - local_y)
            candidates.append({"name": txt, "norm": txt_norm, "distance_px": dist, "conf": conf})

        if len(candidates) < 2:
            return None

        candidates.sort(key=lambda c: c["distance_px"])
        close = [c for c in candidates if c["distance_px"] <= radius_px]

        if len(close) < 2:
            return None

        c0, c1 = close[0], close[1]

        # If the two closest elements are far apart in distance, clear winner
        if abs(c0["distance_px"] - c1["distance_px"]) > 40:
            return None

        # If they're the same text, no ambiguity
        if c0["norm"] == c1["norm"]:
            return None

        # If one of them is clearly the target, no ambiguity
        score0 = max(SequenceMatcher(None, c0["norm"], a).ratio() for a in target_aliases)
        score1 = max(SequenceMatcher(None, c1["norm"], a).ratio() for a in target_aliases)
        if score0 >= 0.8 and (score0 - score1) > 0.3:
            return None

        # Ambiguity confirmed — store and return disambiguation request
        _mark_disambiguation_triggered(app_title, element_name)
        confirmation_id = str(uuid4())[:12]
        message = (
            f"Je vois '{c0['name']}' et '{c1['name']}' proches du point ciblé. "
            f"Tu veux bien '{element_name}' ?"
        )
        store_pending(
            confirmation_id,
            "ui_click_element",
            {"app_title": app_title, "element_name": element_name},
            {
                "reason": message,
                "level": "🟡 DEMANDE",
                "target": element_name,
                "suggestion": "Confirme la cible correcte",
            },
        )
        logger.info("[DISAMBIGUATION] Ambiguité détectée entre '%s' et '%s'", c0["name"], c1["name"])
        return {
            "success": False,
            "type": "disambiguation_required",
            "confirmation_id": confirmation_id,
            "message": message,
            "candidates": [
                {"name": c["name"], "distance_px": int(c["distance_px"])}
                for c in close[:3]
            ],
        }
    except Exception as e:
        logger.debug("[DISAMBIGUATION] Check failed: %s", e)
        return None


async def verify_post_click(
    app_title: str,
    expected_element: str,
    timeout: float = 2.0,
) -> dict:
    """
    After a click, verify the expected UI element is visible in the window.
    Uses OCR on the window screenshot. Returns {"verified": bool, "confidence": float, "method": str}.
    Fails gracefully when OCR is unavailable (returns verified=True to avoid blocking).
    """
    await asyncio.sleep(0.5)

    try:
        windows = _find_candidate_windows(app_title)
        w = _choose_best_window(windows, app_title)
        if w is None:
            return {"verified": False, "confidence": 0.0, "method": "no_window"}

        captured = _capture_window_screenshot(w)
        if captured is None:
            return {"verified": False, "confidence": 0.0, "method": "capture_failed"}

        screenshot, origin_x, origin_y = captured
    except Exception as e:
        logger.debug("[VERIFY] Screenshot failed: %s", e)
        return {"verified": False, "confidence": 0.0, "method": "screenshot_error"}

    try:
        import pytesseract

        title_norm = _normalize_text(app_title)
        is_steam = "steam" in title_norm

        scan_img = _steam_nav_crop(screenshot) if is_steam else screenshot
        aliases = (
            set(_normalize_text(a) for a in _steam_label_aliases(expected_element))
            if is_steam
            else {_normalize_text(expected_element)}
        )

        data = pytesseract.image_to_data(scan_img, output_type=pytesseract.Output.DICT, lang="fra+eng")

        best_score = 0.0
        best_conf = 0
        for i in range(len(data.get("text", []))):
            txt = (data["text"][i] or "").strip()
            if not txt:
                continue
            conf = int(data["conf"][i]) if data["conf"][i] != "-1" else 0
            txt_norm = _normalize_text(txt)
            if not txt_norm:
                continue
            ratio = max(SequenceMatcher(None, txt_norm, a).ratio() for a in aliases)
            contains_boost = 0.15 if any(a in txt_norm or txt_norm in a for a in aliases) else 0.0
            score = ratio + contains_boost + min(conf / 200.0, 0.5)
            if score > best_score:
                best_score = score
                best_conf = conf

        # Steam nav OCR is noisier — use a slightly lower threshold
        threshold = 0.9 if is_steam else 1.0
        verified = best_score >= threshold

        logger.info(
            "[VERIFY] expected='%s' score=%.3f conf=%d verified=%s",
            expected_element, best_score, best_conf, verified,
        )
        return {"verified": verified, "confidence": round(best_score, 3), "method": "ocr"}

    except ImportError:
        logger.debug("[VERIFY] pytesseract indisponible, vérification ignorée")
        return {"verified": True, "confidence": 0.0, "method": "skipped_no_ocr"}
    except Exception as e:
        logger.debug("[VERIFY] OCR failed: %s", e)
        return {"verified": False, "confidence": 0.0, "method": "ocr_error"}


# --------------------------------------------------------------------------- #
#  App type detection
# --------------------------------------------------------------------------- #

_ELECTRON_APPS = {
    "discord", "spotify", "vscode", "code", "slack", "teams",
    "notion", "obsidian", "figma", "postman", "insomnia",
}

_GAME_KEYWORDS = {
    "game", "steam", "epic", "unity", "unreal",
    "helldivers", "valorant", "fortnite", "minecraft",
}


def _detect_app_type(app_title: str) -> str:
    """Retourne 'win32' | 'electron' | 'game' | 'unknown'."""
    title_lower = app_title.lower()
    for kw in _GAME_KEYWORDS:
        if kw in title_lower:
            return "game"
    for app in _ELECTRON_APPS:
        if app in title_lower:
            return "electron"
    return "win32"


# --------------------------------------------------------------------------- #
#  Coordinate cache
# --------------------------------------------------------------------------- #

_coordinate_cache: dict[str, dict[str, dict[str, Any]]] = {}


def _cache_key(app_title: str) -> str:
    return app_title.lower().strip()


def _is_steam_title(app_title: str) -> bool:
    return "steam" in _normalize_text(app_title)


def _get_cached(app_title: str, element_name: str) -> Optional[dict[str, Any]]:
    key = _cache_key(app_title)
    window_cache = _coordinate_cache.get(key, {})
    return window_cache.get(element_name.lower())


def _set_cached(
    app_title: str,
    element_name: str,
    coords: tuple[int, int],
    window_rect: Optional[tuple[int, int, int, int]] = None,
):
    key = _cache_key(app_title)
    if key not in _coordinate_cache:
        _coordinate_cache[key] = {}
    _coordinate_cache[key][element_name.lower()] = {
        "coords": coords,
        "window_rect": window_rect,
        "timestamp": time.time(),
    }


# --------------------------------------------------------------------------- #
#  Couche 1 : UIA / pywinauto
# --------------------------------------------------------------------------- #

async def _try_uia(app_title: str, element_name: str) -> Optional[dict]:
    """Tente de cliquer via pywinauto UI Automation."""
    try:
        from pywinauto import Desktop

        desktop = Desktop(backend="uia")

        # Find the window
        windows = desktop.windows(title_re=f".*{app_title}.*", visible_only=True)
        if not windows:
            logger.debug("[UIA] Fenêtre '%s' non trouvée", app_title)
            return None

        window = windows[0]

        # Try to find the element by name
        try:
            # Try direct child search
            element = window.child_window(title=element_name, control_type="Button")
            if element.exists(timeout=1):
                element.click_input()
                rect = element.rectangle()
                coords = (rect.mid_point().x, rect.mid_point().y)
                _set_cached(app_title, element_name, coords)
                return {
                    "success": True,
                    "method": "uia",
                    "message": f"Clic UIA sur '{element_name}' dans '{app_title}'.",
                    "coords": coords,
                }
        except Exception:
            pass

        # Try with best_match (fuzzy)
        try:
            element = window.child_window(best_match=element_name)
            if element.exists(timeout=1):
                element.click_input()
                rect = element.rectangle()
                coords = (rect.mid_point().x, rect.mid_point().y)
                _set_cached(app_title, element_name, coords)
                return {
                    "success": True,
                    "method": "uia",
                    "message": f"Clic UIA (fuzzy) sur '{element_name}' dans '{app_title}'.",
                    "coords": coords,
                }
        except Exception:
            pass

        # Try menu items
        try:
            menu = window.menu_select(element_name)
            return {
                "success": True,
                "method": "uia_menu",
                "message": f"Menu UIA '{element_name}' sélectionné dans '{app_title}'.",
            }
        except Exception:
            pass

        logger.debug("[UIA] Élément '%s' non trouvé dans '%s'", element_name, app_title)
        return None

    except ImportError:
        logger.warning("[UIA] pywinauto non disponible")
        return None
    except Exception as e:
        logger.debug("[UIA] Erreur : %s", e)
        return None


# --------------------------------------------------------------------------- #
#  Couche 2 : Cache coordonnées
# --------------------------------------------------------------------------- #

async def _try_cache(app_title: str, element_name: str) -> Optional[dict]:
    """Tente de cliquer via les coordonnées en cache."""
    # Steam UI is dynamic; stale absolute coords are a frequent source of false clicks.
    if _is_steam_title(app_title):
        return None

    cached = _get_cached(app_title, element_name)
    if cached is None:
        return None

    # Backward compatibility for old tuple-only cache entries.
    if isinstance(cached, tuple):
        coords = cached
        cached_rect = None
    else:
        coords = tuple(cached.get("coords", ()))
        cached_rect = cached.get("window_rect")

    if len(coords) != 2:
        return None

    x, y = coords

    # Adjust cached point when target window moved since cache insertion.
    try:
        windows = _find_candidate_windows(app_title)
        w = _choose_best_window(windows, app_title)
        if w is not None:
            current_rect = (
                int(getattr(w, "left", 0)),
                int(getattr(w, "top", 0)),
                int(getattr(w, "width", 0)),
                int(getattr(w, "height", 0)),
            )
            if cached_rect and len(cached_rect) == 4:
                x += current_rect[0] - int(cached_rect[0])
                y += current_rect[1] - int(cached_rect[1])

            in_window = (
                current_rect[0] <= x < current_rect[0] + current_rect[2]
                and current_rect[1] <= y < current_rect[1] + current_rect[3]
            )
            if not in_window:
                return None
    except Exception:
        pass

    try:
        pyautogui.click(x=x, y=y)
        return {
            "success": True,
            "method": "cache",
            "message": f"Clic cache sur '{element_name}' à ({x}, {y}).",
            "coords": coords,
        }
    except Exception as e:
        logger.debug("[CACHE] Erreur clic : %s", e)
        return None


# --------------------------------------------------------------------------- #
#  Couche 3 : OCR / tesseract
# --------------------------------------------------------------------------- #

async def _try_ocr(app_title: str, element_name: str) -> Optional[dict]:
    """Screenshot + OCR + clic aux coordonnées trouvées.

    v5.2 Phase A : diagnostic complet — mots détectés, normalisation, lang.
    """
    try:
        import pytesseract
        import pygetwindow as gw

        # Find and screenshot the window
        windows = _find_candidate_windows(app_title)
        w = _choose_best_window(windows, app_title)
        if w is None:
            logger.debug("[OCR] Fenêtre '%s' non trouvée", app_title)
            return None

        _log_window_selection(app_title, w)

        if w.isMinimized:
            w.restore()
            time.sleep(0.3)

        captured = _capture_window_screenshot(w)
        if captured is None:
            logger.debug("[OCR] Capture impossible pour '%s'", app_title)
            return None
        screenshot, origin_x, origin_y = captured

        # v5.2 Phase A — log search target normalization upfront
        _ocr_lang = "fra+eng"
        try:
            tesseract_version = str(pytesseract.get_tesseract_version())
        except Exception:
            tesseract_version = "unknown"
        logger.info(
            "[OCR] Recherche: '%s' (normalisé: '%s') | lang='%s' | tesseract=%s",
            element_name, _normalize_text(element_name), _ocr_lang, tesseract_version,
        )

        # OCR
        data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT, lang="fra+eng")

        element_norm = _normalize_text(element_name)
        best_match = None
        best_score = 0.0
        best_conf = 0

        title_norm = _normalize_text(app_title)
        is_steam = "steam" in title_norm

        aliases = set(_normalize_text(a) for a in _steam_label_aliases(element_name)) if is_steam else {element_norm}

        # Steam nav text can have weaker OCR confidence due to anti-aliasing/theme.
        min_conf = 20 if is_steam else 35
        min_score = 0.95 if is_steam else 1.1

        ocr_passes: list[tuple[Any, int, int, str]] = [(screenshot, origin_x, origin_y, "full")]
        if is_steam:
            nav_img = _steam_nav_crop(screenshot)
            nav_processed = _preprocess_for_ocr(nav_img)
            ocr_passes = [
                (nav_processed, origin_x, origin_y, "steam_nav_preprocessed"),
                (nav_img, origin_x, origin_y, "steam_nav"),
                (screenshot, origin_x, origin_y, "full"),
            ]
            ts = int(time.time() * 1000)
            _save_debug_image(screenshot, f"steam_full_{ts}")
            _save_debug_image(nav_img, f"steam_nav_{ts}")
            _save_debug_image(nav_processed, f"steam_nav_pre_{ts}")

        for pass_img, pass_ox, pass_oy, pass_name in ocr_passes:
            data = pytesseract.image_to_data(pass_img, output_type=pytesseract.Output.DICT, lang=_ocr_lang)
            top_candidates: list[tuple[str, int, float]] = []
            all_detected: list[str] = []  # v5.2 Phase A — full word list for diagnosis

            for i in range(len(data["text"])):
                text = data["text"][i].strip()
                conf = int(data["conf"][i]) if data["conf"][i] != "-1" else 0

                if text:
                    all_detected.append(f"{text}({conf})")

                text_norm = _normalize_text(text)
                if not text_norm:
                    continue

                ratio = max(SequenceMatcher(None, text_norm, a).ratio() for a in aliases)
                contains_boost = 0.15 if any(a in text_norm or text_norm in a for a in aliases) else 0.0
                score = ratio + contains_boost + min(conf / 200.0, 0.5)
                top_candidates.append((text_norm, conf, round(score, 3)))

                if score > best_score and conf >= min_conf:
                    best_score = score
                    best_conf = conf
                    x = data["left"][i] + data["width"][i] // 2
                    y = data["top"][i] + data["height"][i] // 2
                    best_match = (x + pass_ox, y + pass_oy)

            # v5.2 Phase A — log all detected words (top 30) for OCR diagnosis
            logger.info(
                "[OCR] pass=%s detected=%d_words top30=%s",
                pass_name, len(all_detected), all_detected[:30],
            )

            if top_candidates:
                top_candidates.sort(key=lambda it: (it[2], it[1]), reverse=True)
                logger.info("[OCR] pass=%s top_scored=%s", pass_name, top_candidates[:6])

            if best_match and best_score >= min_score:
                break

        if best_match and best_score >= min_score:
            x, y = best_match
            pyautogui.click(x=x, y=y)
            if not is_steam:
                _set_cached(
                    app_title,
                    element_name,
                    best_match,
                    window_rect=(
                        int(getattr(w, "left", 0)),
                        int(getattr(w, "top", 0)),
                        int(getattr(w, "width", 0)),
                        int(getattr(w, "height", 0)),
                    ),
                )
            return {
                "success": True,
                "method": "ocr",
                "message": f"Clic OCR sur '{element_name}' à ({x}, {y}), confiance={best_conf}%.",
                "coords": best_match,
                "ocr_confidence": best_conf,
                "ocr_score": round(best_score, 2),
            }

        logger.debug("[OCR] Texte '%s' non trouvé (best_score=%.2f, conf=%d)", element_name, best_score, best_conf)
        return None

    except ImportError as e:
        logger.warning("[OCR] Dépendance manquante : %s", e)
        return None
    except Exception as e:
        logger.debug("[OCR] Erreur : %s", e)
        return None


# --------------------------------------------------------------------------- #
#  Couche 4 : Vision (MiniCPM-V) — placeholder
# --------------------------------------------------------------------------- #

async def _try_vision(app_title: str, element_name: str) -> Optional[dict]:
    """Screenshot -> MiniCPM-V (or fallback model) -> coordinates.

    v5.2 Phase A : instrumentation détaillée par attempt (model × pass).
    Chaque tentative émet un log [VISION_TIMING] structuré avec capture/prepare/ollama/parse.
    v5.3 : retourne immédiatement si vision_enabled=false dans la config.
    """
    if not _is_vision_enabled():
        logger.info("[VISION] couche désactivée par config (vision_enabled=false) — skip")
        return {"success": False, "method": "vision", "skipped": True,
                "error": "vision_disabled_by_config", "result": "skipped"}

    try:
        import pygetwindow as gw

        capture_start = time.monotonic()

        windows = _find_candidate_windows(app_title)
        w = _choose_best_window(windows, app_title)
        if w is None:
            return None

        _log_window_selection(app_title, w)

        if w.isMinimized:
            w.restore()
            time.sleep(0.2)

        captured = _capture_window_screenshot(w)
        if captured is None:
            logger.debug("[VISION] Capture impossible pour '%s'", app_title)
            return None
        screenshot, origin_x, origin_y = captured
        capture_ms = int((time.monotonic() - capture_start) * 1000)
        try:
            sw_full, sh_full = screenshot.size
        except Exception:
            sw_full, sh_full = (0, 0)
        logger.info(
            "[VISION_CAPTURE] app='%s' size=%dx%d capture_ms=%d",
            app_title, sw_full, sh_full, capture_ms,
        )
        title_norm = _normalize_text(app_title)
        is_steam = "steam" in title_norm

        # Build vision passes: Steam left-nav first, then full image.
        image_passes: list[tuple[Any, int, int, str]] = [(screenshot, origin_x, origin_y, "full")]
        if is_steam:
            sw, sh = screenshot.size
            nav_w = max(220, int(sw * 0.45))
            nav_h = max(120, int(sh * 0.30))
            nav_crop = screenshot.crop((0, 0, min(sw, nav_w), min(sh, nav_h)))
            image_passes = [(nav_crop, origin_x, origin_y, "steam_nav"), (screenshot, origin_x, origin_y, "full")]

        labels = _steam_label_aliases(element_name) if is_steam else [element_name]
        aliases = set(_normalize_text(a) for a in labels)
        labels_hint = ", ".join(dict.fromkeys(labels))

        models = _preferred_vision_models()
        for model in models:
            model_timeout = _VISION_TIMEOUT_MINICPM_S if model.startswith("minicpm") else _VISION_TIMEOUT_DEFAULT_S
            for pass_img, pass_origin_x, pass_origin_y, pass_name in image_passes:
                # v5.2 Phase A — fine-grained timings per (model, pass) attempt
                timings: dict[str, Any] = {
                    "model": model,
                    "pass": pass_name,
                    "capture_ms": capture_ms,
                }
                try:
                    try:
                        pw, ph = pass_img.size
                    except Exception:
                        pw, ph = (0, 0)
                    timings["pass_image_size"] = f"{pw}x{ph}"

                    prepare_start = time.monotonic()
                    image_b64 = _encode_image(pass_img)
                    prompt_hint = ""
                    if pass_name == "steam_nav":
                        prompt_hint = "Focus on the top-left navigation area of Steam where the Library tab usually appears. "
                    payload_dict = {
                        "model": model,
                        "prompt": (
                            f"Find the clickable UI label among these candidate texts: {labels_hint}. "
                            f"{prompt_hint}"
                            "Return strictly and only valid JSON with integer pixel coordinates relative to this screenshot: "
                            "{\"x\": int, \"y\": int, \"found\": bool}. No markdown, no explanation."
                            " Do NOT return arrays for x/y. No markdown, no explanation."
                        ),
                        "images": [image_b64],
                        "stream": False,
                    }
                    timings["prepare_ms"] = int((time.monotonic() - prepare_start) * 1000)
                    timings["image_b64_bytes"] = len(image_b64)
                    timings["payload_size_bytes"] = len(json.dumps(payload_dict))

                    ollama_start = time.monotonic()
                    resp = requests.post(
                        _OLLAMA_GENERATE_URL,
                        json=payload_dict,
                        timeout=model_timeout,
                    )
                    timings["ollama_call_ms"] = int((time.monotonic() - ollama_start) * 1000)
                    timings["http_status"] = resp.status_code

                    if resp.status_code != 200:
                        logger.info("[VISION] model=%s pass=%s http=%s", model, pass_name, resp.status_code)
                        timings["result"] = "http_error"
                        logger.info("[VISION_TIMING] %s", json.dumps(timings, ensure_ascii=False))
                        continue
                    raw = resp.json().get("response", "")
                    logger.info(
                        "[VISION] model=%s pass=%s timeout=%.1fs raw=%s",
                        model,
                        pass_name,
                        model_timeout,
                        raw[:220].replace("\n", " "),
                    )
                    parse_start = time.monotonic()
                    parsed = _normalize_vision_payload(_parse_vision_json(raw))
                    timings["parse_ms"] = int((time.monotonic() - parse_start) * 1000)
                    has_found_flag = bool(parsed and "found" in parsed)
                    if has_found_flag:
                        is_found = bool(parsed.get("found"))
                    else:
                        is_found = bool(parsed and ("x" in parsed and "y" in parsed))
                    if is_found:
                        local_x = int(parsed.get("x", 0))
                        local_y = int(parsed.get("y", 0))

                        effective_img = pass_img
                        effective_origin_x = pass_origin_x
                        effective_origin_y = pass_origin_y

                        # Some MiniCPM responses on steam_nav return coords in full-image space.
                        if pass_name == "steam_nav":
                            pw, ph = pass_img.size
                            sw, sh = screenshot.size
                            in_pass = 0 <= local_x < pw and 0 <= local_y < ph
                            in_full = 0 <= local_x < sw and 0 <= local_y < sh
                            if (not in_pass) and in_full:
                                logger.info(
                                    "[VISION] remap pass=%s local=(%s,%s) interpreted_as=full",
                                    pass_name,
                                    local_x,
                                    local_y,
                                )
                                effective_img = screenshot
                                effective_origin_x = origin_x
                                effective_origin_y = origin_y

                        # For Steam labels, reject obvious decoy points before clicking.
                        if is_steam:
                            ok_point, verify = _verify_target_near_point(effective_img, local_x, local_y, aliases)
                            logger.info("[VISION] verify pass=%s -> %s", pass_name, verify)
                            if not ok_point:
                                timings["result"] = "decoy_reject"
                                logger.info("[VISION_TIMING] %s", json.dumps(timings, ensure_ascii=False))
                                continue

                        # P2: Proximity disambiguation — ask user if two close targets detected
                        if _should_check_disambiguation(app_title, element_name):
                            disamb = _check_proximity_disambiguation(
                                effective_img, local_x, local_y, aliases, element_name, app_title,
                            )
                            if disamb is not None:
                                timings["result"] = "disambiguation_required"
                                logger.info("[VISION_TIMING] %s", json.dumps(timings, ensure_ascii=False))
                                return disamb

                        x = local_x + effective_origin_x
                        y = local_y + effective_origin_y
                        if _point_in_bounds(x, y, _get_virtual_screen_bounds()):
                            pyautogui.click(x=x, y=y)
                            coords = (x, y)
                            if not is_steam:
                                _set_cached(
                                    app_title,
                                    element_name,
                                    coords,
                                    window_rect=(
                                        int(getattr(w, "left", 0)),
                                        int(getattr(w, "top", 0)),
                                        int(getattr(w, "width", 0)),
                                        int(getattr(w, "height", 0)),
                                    ),
                                )
                            timings["result"] = "success"
                            timings["coords"] = [x, y]
                            logger.info("[VISION_TIMING] %s", json.dumps(timings, ensure_ascii=False))
                            return {
                                "success": True,
                                "method": "vision",
                                "message": f"Clic vision sur '{element_name}' à ({x}, {y}) via {model} ({pass_name}).",
                                "coords": coords,
                                "vision_model": model,
                            }
                        else:
                            # Coords out of virtual screen bounds
                            timings["result"] = "out_of_bounds"
                            logger.info("[VISION_TIMING] %s", json.dumps(timings, ensure_ascii=False))
                    else:
                        # Vision returned found=false or no x/y
                        timings["result"] = "not_found"
                        logger.info("[VISION_TIMING] %s", json.dumps(timings, ensure_ascii=False))
                except Exception as inner:
                    timings["result"] = "exception"
                    timings["exception"] = str(inner)[:200]
                    logger.info("[VISION_TIMING] %s", json.dumps(timings, ensure_ascii=False))
                    logger.debug("[VISION] Model %s failed (%s): %s", model, pass_name, inner)
                    continue

        return None
    except Exception as e:
        logger.warning("[VISION] Failed: %s", e)
        return None


async def _try_steam_nav_heuristic(app_title: str, element_name: str) -> Optional[dict]:
    """Steam-specific fallback: click expected nav position for Bibliotheque/Library."""
    element_norm = _normalize_text(element_name)
    if element_norm not in {"bibliotheque", "library", "bibliothèque"}:
        return None

    try:
        import pygetwindow as gw

        windows = _find_candidate_windows(app_title)
        w = _choose_best_window(windows, app_title)
        if w is None:
            return None

        if w.isMinimized:
            w.restore()
            time.sleep(0.2)
        try:
            w.activate()
        except Exception:
            pass

        # Approximate position for Steam top-left nav "Library".
        x = int(w.left + max(120, w.width * 0.22))
        y = int(w.top + max(44, w.height * 0.08))

        # Guard: only click when point is in the chosen window and the virtual desktop.
        if not (int(w.left) <= x < int(w.left + w.width) and int(w.top) <= y < int(w.top + w.height)):
            return None
        if not _point_in_bounds(x, y, _get_virtual_screen_bounds()):
            return None

        pyautogui.click(x=x, y=y)
        coords = (x, y)
        # Do not cache heuristic coordinates: they are approximate and can drift.
        return {
            "success": True,
            "method": "steam_heuristic",
            "message": f"Clic heuristique Steam '{element_name}' à ({x}, {y}).",
            "coords": coords,
        }
    except Exception as e:
        logger.debug("[STEAM_HEURISTIC] Failed: %s", e)
        return None


def _encode_image(img) -> str:
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _parse_vision_json(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    # Markdown code block JSON
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except Exception:
            pass

    # Inline code JSON
    inline = re.search(r"`(\{[\s\S]*?\})`", text)
    if inline:
        try:
            return json.loads(inline.group(1))
        except Exception:
            pass

    # MiniCPM bbox format: <box>x1 y1 x2 y2</box>
    box = re.search(r"<box>\s*(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s*</box>", text, flags=re.IGNORECASE)
    if box:
        x1, y1, x2, y2 = map(int, box.groups())
        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)
        return {"found": True, "x": cx, "y": cy, "box": [x1, y1, x2, y2]}

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        # Last-resort coordinate extraction from loose text
        coord_match = re.search(r'"x"\s*:\s*(-?\d+)[\s\S]*?"y"\s*:\s*(-?\d+)', text)
        if coord_match:
            return {"found": True, "x": int(coord_match.group(1)), "y": int(coord_match.group(2))}
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        coord_match = re.search(r'"x"\s*:\s*(-?\d+)[\s\S]*?"y"\s*:\s*(-?\d+)', match.group(0))
        if coord_match:
            return {"found": True, "x": int(coord_match.group(1)), "y": int(coord_match.group(2))}
        return None


def _build_layers(app_type: str, app_title: str = ""):
    title_norm = _normalize_text(app_title)
    is_steam = "steam" in title_norm
    has_minicpm = _has_local_minicpm()
    vision_on = _is_vision_enabled()

    if app_type == "game":
        if is_steam:
            if vision_on and has_minicpm:
                return [_try_cache, _try_ocr, _try_vision]
            return [_try_cache, _try_ocr, _try_steam_nav_heuristic]
        return [_try_cache] + ([_try_vision] if vision_on else [])
    if app_type == "electron":
        if is_steam:
            if vision_on and has_minicpm:
                return [_try_cache, _try_ocr, _try_vision]
            return [_try_cache, _try_ocr, _try_steam_nav_heuristic]
        return [_try_cache, _try_ocr] + ([_try_vision] if vision_on else [])
    return [_try_uia, _try_cache, _try_ocr] + ([_try_vision] if vision_on else [])


# --------------------------------------------------------------------------- #
#  Interface publique
# --------------------------------------------------------------------------- #

async def find_and_click(
    app_title: str,
    element_name: str,
    exclude_methods: Optional[set[str]] = None,
) -> dict[str, Any]:
    """
    Résout un clic sémantique via le grounding stack (4 couches).
    Retourne le résultat du premier succès.

    exclude_methods: noms de couches à sauter (ex: {"vision"} pour retry sans vision).
    """
    if not element_name:
        return {"success": False, "method": "none", "message": "Pas d'élément spécifié."}

    app_type = _detect_app_type(app_title)
    try:
        from tools.app_launcher import get_app_type

        app_type = get_app_type(app_title) or app_type
    except Exception:
        pass
    logger.info(
        "[GROUNDING] Recherche '%s' dans '%s' (type=%s)",
        element_name, app_title, app_type,
    )

    # Définir l'ordre des couches selon le type d'app, filtrer les méthodes exclues
    layers = _build_layers(app_type, app_title)
    if exclude_methods:
        layers = [l for l in layers if l.__name__.replace("_try_", "") not in exclude_methods]
    attempted_layers: list[str] = []
    layer_attempts: list[dict] = []  # v5.1 corrective — instrumentation détaillée

    overall_start = time.monotonic()

    for layer_fn in layers:
        layer_name = layer_fn.__name__.replace("_try_", "")
        attempted_layers.append(layer_name)

        # v5.1 corrective — global cap check before launching next layer
        elapsed_total = time.monotonic() - overall_start
        if elapsed_total >= GROUNDING_TOTAL_TIMEOUT:
            logger.warning(
                "[GROUNDING] Total timeout %.1fs atteint avant couche %s — abort",
                GROUNDING_TOTAL_TIMEOUT, layer_name,
            )
            layer_attempts.append({
                "layer": layer_name,
                "result": "skipped",
                "latency_ms": 0,
                "error": "global_timeout_reached",
            })
            break

        layer_timeout = GROUNDING_LAYER_TIMEOUT.get(layer_name, 5.0)
        layer_start = time.monotonic()
        layer_result_kind = "failure"
        layer_error: Optional[str] = None
        result: Optional[dict] = None

        try:
            result = await asyncio.wait_for(
                layer_fn(app_title, element_name),
                timeout=layer_timeout,
            )
            if result and result.get("success"):
                layer_result_kind = "success"
            elif result and result.get("type") == "disambiguation_required":
                layer_result_kind = "disambiguation"
            elif result and result.get("skipped"):
                # v5.3 — layer skipped by config (e.g. vision_enabled=false)
                layer_result_kind = "skipped"
                layer_error = result.get("error") or "skipped_by_config"
            elif result is None:
                layer_error = "no_match"
            else:
                layer_error = result.get("message") or "no_match"
        except asyncio.TimeoutError:
            layer_result_kind = "timeout"
            layer_error = f"timeout_{layer_timeout}s"
            logger.warning(
                "[GROUNDING] Couche '%s' timeout après %.1fs", layer_name, layer_timeout,
            )
        except Exception as e:
            layer_result_kind = "failure"
            layer_error = str(e)[:200]
            logger.debug("[GROUNDING] Couche %s échouée : %s", layer_name, e)

        latency_ms = int((time.monotonic() - layer_start) * 1000)
        layer_attempts.append({
            "layer": layer_name,
            "result": layer_result_kind,
            "latency_ms": latency_ms,
            "error": layer_error,
        })

        if layer_result_kind == "success" and result:
            logger.info(
                "[GROUNDING] Succès via %s : '%s' dans '%s' (%dms)",
                layer_name, element_name, app_title, latency_ms,
            )
            result["layer_attempts"] = layer_attempts
            return result

        if layer_result_kind == "disambiguation" and result:
            logger.info("[GROUNDING] Désambiguïsation requise pour '%s'", element_name)
            result["layer_attempts"] = layer_attempts
            return result

    total_latency_ms = int((time.monotonic() - overall_start) * 1000)
    diagnostics = {
        "attempted_layers": attempted_layers,
        "vision_models": _preferred_vision_models(),
        "local_ollama_models": _list_ollama_models(),
        "total_latency_ms": total_latency_ms,
    }

    # Distinguish total-timeout abort from genuine no-match
    if total_latency_ms >= int(GROUNDING_TOTAL_TIMEOUT * 1000):
        msg = (
            f"Recherche visuelle trop lente — timeout {GROUNDING_TOTAL_TIMEOUT:.0f}s. "
            f"Réessaie avec une commande plus précise."
        )
        method = "global_timeout"
    else:
        msg = (
            f"Impossible de trouver '{element_name}' dans '{app_title}'. "
            f"Aucune couche n'a réussi. Tentatives={','.join(attempted_layers)}"
        )
        method = "all_failed"

    return {
        "success": False,
        "method": method,
        "message": msg,
        "diagnostics": diagnostics,
        "layer_attempts": layer_attempts,
    }
