"""
Electron Heuristics — F2 v6.0.

Résolution d'icônes sans texte pour les apps Electron (Discord, Slack, VSCode)
où l'OCR échoue. Les positions sont définies dans electron_heuristics.yaml,
relativement à la fenêtre cible (ancre + offset).

Activation : couche grounding conditionnelle, après échec OCR, si le process de
l'app est listé dans le YAML.
"""

import logging
import os
import unicodedata
from typing import Any, Optional

logger = logging.getLogger("atlas.electron_heuristics")

_YAML_PATH = os.path.join(os.path.dirname(__file__), "electron_heuristics.yaml")
_config: Optional[dict] = None


def _normalize(text: str) -> str:
    s = (text or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch)).strip()


def load_config(force: bool = False) -> dict:
    """Charge (et cache) la config YAML des heuristiques."""
    global _config
    if _config is not None and not force:
        return _config
    try:
        import yaml
        with open(_YAML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        # Normalise : ignore les sections sans icônes utiles
        _config = {}
        for app, spec in data.items():
            if not isinstance(spec, dict):
                continue
            icons = spec.get("icons") or {}
            if not isinstance(icons, dict):
                icons = {}
            # purge les entrées vides ({})
            icons = {k: v for k, v in icons.items() if isinstance(v, dict) and v}
            _config[_normalize(app)] = {
                "process_name": spec.get("process_name", ""),
                "icons": icons,
            }
        logger.info("Heuristiques Electron chargées : %s", list(_config.keys()))
    except Exception as e:
        logger.warning("Chargement heuristiques Electron échoué : %s", e)
        _config = {}
    return _config


def supported_apps() -> list[str]:
    return list(load_config().keys())


def _match_app(app_title: str) -> Optional[str]:
    """Retourne la clé d'app heuristique correspondant au titre/processus."""
    cfg = load_config()
    norm = _normalize(app_title)
    for key, spec in cfg.items():
        if key in norm:
            return key
        proc = _normalize(spec.get("process_name", "").replace(".exe", ""))
        if proc and proc in norm:
            return key
    return None


def _match_icon(app_key: str, element_name: str) -> Optional[tuple[str, dict]]:
    """Trouve l'icône demandée par nom ou alias."""
    cfg = load_config()
    spec = cfg.get(app_key, {})
    icons = spec.get("icons", {})
    target = _normalize(element_name)
    for icon_name, icon_spec in icons.items():
        if _normalize(icon_name) == target:
            return icon_name, icon_spec
        aliases = [_normalize(a) for a in icon_spec.get("aliases", [])]
        if target in aliases or any(target in a or a in target for a in aliases):
            return icon_name, icon_spec
    return None


def resolve_icon_point(
    app_title: str,
    element_name: str,
    window_rect: tuple[int, int, int, int],
) -> Optional[dict]:
    """
    Résout les coordonnées écran absolues d'une icône heuristique.

    window_rect : (left, top, width, height) de la fenêtre cible.
    Retourne {"x", "y", "icon", "app"} ou None si non résolu.
    """
    app_key = _match_app(app_title)
    if app_key is None:
        return None
    matched = _match_icon(app_key, element_name)
    if matched is None:
        return None
    icon_name, spec = matched

    left, top, width, height = window_rect
    anchor = (spec.get("anchor") or "top-left").lower()
    ox = int(spec.get("offset_x", 0))
    oy = int(spec.get("offset_y", 0))

    if anchor == "top-left":
        bx, by = left, top
    elif anchor == "top-right":
        bx, by = left + width, top
    elif anchor == "bottom-left":
        bx, by = left, top + height
    elif anchor == "bottom-right":
        bx, by = left + width, top + height
    elif anchor == "center":
        bx, by = left + width // 2, top + height // 2
    else:
        bx, by = left, top

    return {"x": bx + ox, "y": by + oy, "icon": icon_name, "app": app_key}


def is_electron_heuristic_app(app_title: str) -> bool:
    """True si l'app a des heuristiques Electron disponibles."""
    return _match_app(app_title) is not None
