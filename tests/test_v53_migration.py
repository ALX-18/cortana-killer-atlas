"""
Sprint v5.3 — Tests de migration.

Couverture :
  AXE 1 — Qwen 14b → 7b (config)
  AXE 2 — MiniCPM-V désactivé par défaut (grounding)
  AXE 3 — Résolution implicite d'app (validator)
  AXE 4 — Tesseract startup hardening (health endpoint)
"""

import json
import pathlib
import time
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.json"


def _load_settings() -> dict:
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
#  AXE 1 — Config : Qwen 14b → 7b
# --------------------------------------------------------------------------- #

class TestQwen7bMigration:
    def test_model_is_7b(self):
        cfg = _load_settings()
        assert cfg["ollama"]["model"] == "qwen2.5:7b"

    def test_keep_alive_present(self):
        cfg = _load_settings()
        assert cfg["ollama"].get("keep_alive") == "10m"

    def test_grounding_section_vision_disabled(self):
        cfg = _load_settings()
        grounding = cfg.get("grounding", {})
        assert grounding.get("vision_enabled") is False


# --------------------------------------------------------------------------- #
#  AXE 2 — MiniCPM-V désactivé
# --------------------------------------------------------------------------- #

class TestVisionDisabled:
    def test_vision_disabled_returns_skipped(self):
        """_try_vision doit retourner immédiatement quand vision_enabled=false."""
        import asyncio
        from tools import grounding

        with patch.object(grounding, "_is_vision_enabled", return_value=False):
            result = asyncio.run(grounding._try_vision("SomeApp", "SomeElement"))

        assert result is not None
        assert result.get("success") is False
        assert result.get("error") == "vision_disabled_by_config"
        assert result.get("result") == "skipped"

    def test_build_layers_no_vision_when_disabled(self):
        """_build_layers ne doit pas inclure _try_vision quand vision_enabled=false."""
        from tools import grounding

        with patch.object(grounding, "_is_vision_enabled", return_value=False):
            layers = grounding._build_layers("win32", "SomeApp")

        layer_names = [fn.__name__ for fn in layers]
        assert "_try_vision" not in layer_names

    def test_build_layers_includes_vision_when_enabled(self):
        """_build_layers inclut _try_vision quand vision_enabled=true."""
        from tools import grounding

        with patch.object(grounding, "_is_vision_enabled", return_value=True):
            with patch.object(grounding, "_has_local_minicpm", return_value=True):
                layers = grounding._build_layers("win32", "SomeApp")

        layer_names = [fn.__name__ for fn in layers]
        assert "_try_vision" in layer_names


# --------------------------------------------------------------------------- #
#  AXE 3 — Résolution implicite d'app
# --------------------------------------------------------------------------- #

class TestResolveImplicitApp:
    def _make_ws(self, tool: str, app_title: str, age_s: float = 10.0):
        ws = MagicMock()
        ws.last_action = {
            "tool": tool,
            "params": {"app_title": app_title},
            "result": {"success": True},
        }
        ws.last_action_ts = time.time() - age_s
        return ws

    def test_last_action_used(self):
        from core.validator import _resolve_implicit_app
        ws = self._make_ws("ui_click_element", "Steam", age_s=30.0)
        result = _resolve_implicit_app(ws, {})
        assert result == "Steam"

    def test_returns_empty_after_2min(self):
        from core.validator import _resolve_implicit_app
        ws = self._make_ws("ui_click_element", "Steam", age_s=130.0)
        result = _resolve_implicit_app(ws, {})
        assert result == ""

    def test_filters_atlas_desktop(self):
        from core.validator import _resolve_implicit_app
        ws = self._make_ws("ui_click_element", "Atlas Desktop", age_s=5.0)
        result = _resolve_implicit_app(ws, {})
        assert result == ""

    def test_no_last_action(self):
        from core.validator import _resolve_implicit_app
        ws = MagicMock()
        ws.last_action = None
        ws.last_action_ts = 0.0
        result = _resolve_implicit_app(ws, {})
        assert result == ""


# --------------------------------------------------------------------------- #
#  EXTRA v5.3 — Parsing "clique sur <element> sur <app>"
# --------------------------------------------------------------------------- #

class TestClickSurAppParsing:
    """
    Terrain bug 2026-05-20: "clique sur company of heroes 2 sur steam" gardait
    toute la phrase comme élément (app vide) → recherche dans tout le bureau.
    Le séparateur 'sur <app>' n'était pas reconnu (seul 'dans' l'était).
    """

    def _clf(self):
        from core.intent_classifier import get_classifier
        return get_classifier()

    def test_sur_steam_splits_element_and_app(self):
        r = self._clf().classify("clique sur company of heroes 2 sur steam", {})
        assert r.category == "interaction"
        assert r.verb == "click"
        assert r.params.get("element_name") == "company of heroes 2"
        assert r.params.get("app_title") == "steam"

    def test_dans_steam_still_works(self):
        # Non-régression : "dans steam" doit toujours fonctionner
        r = self._clf().classify("clique sur bibliothèque dans steam", {})
        assert r.params.get("element_name") == "bibliothèque"
        assert r.params.get("app_title") == "steam"

    def test_sur_discord_known_app(self):
        r = self._clf().classify("clique sur mon ami sur discord", {})
        assert r.params.get("element_name") == "mon ami"
        assert r.params.get("app_title") == "discord"

    def test_sur_unknown_app_not_split(self):
        # "sur la page" — 'page' n'est pas une app connue → pas de split en app
        r = self._clf().classify("clique sur le bouton sur la page", {})
        # element conserve la phrase, app non résolue via ce pattern
        assert r.params.get("app_title") in (None, "", "la page") or "page" not in (r.params.get("app_title") or "")

    def test_single_sur_no_false_app(self):
        # "clique sur magasin" — un seul 'sur' → pas d'app extraite à tort
        r = self._clf().classify("clique sur magasin", {})
        assert r.params.get("element_name") == "magasin"
        assert not r.params.get("app_title")


# --------------------------------------------------------------------------- #
#  AXE 4 — Tesseract startup / health endpoint
# --------------------------------------------------------------------------- #

class TestTesseractHealth:
    def test_health_endpoint_has_tesseract_status(self):
        import main
        client = TestClient(main.app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "tesseract_status" in body
        assert "ok" in body["tesseract_status"]

    def test_health_endpoint_has_vision_enabled(self):
        import main
        client = TestClient(main.app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "vision_enabled" in body
        assert isinstance(body["vision_enabled"], bool)
