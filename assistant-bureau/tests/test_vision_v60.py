"""
Sprint v6.0 — F2 Vision OCR Consolidé.

Couvre : couche EasyOCR (fallback), heuristiques Electron, lecture d'écran (CU),
composition du grounding stack, routage classifier/validator.
Décision Réunion #5 : OCR-only, pas de VLM. MiniCPM-V gated off.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import grounding
from tools import electron_heuristics as eh
from core.intent_classifier import get_classifier
from core.validator import get_validator


# --------------------------------------------------------------------------- #
#  Heuristiques Electron
# --------------------------------------------------------------------------- #

class TestElectronHeuristics:
    def test_config_loads(self):
        cfg = eh.load_config(force=True)
        assert "discord" in cfg

    def test_supported_apps(self):
        apps = eh.supported_apps()
        assert "discord" in apps and "slack" in apps and "vscode" in apps

    def test_resolve_discord_settings(self):
        pt = eh.resolve_icon_point("Discord", "paramètres", (100, 50, 1200, 800))
        assert pt is not None
        assert pt["icon"] == "parametres"
        assert pt["app"] == "discord"

    def test_resolve_via_alias_engrenage(self):
        pt = eh.resolve_icon_point("Discord", "engrenage", (100, 50, 1200, 800))
        assert pt is not None and pt["icon"] == "parametres"

    def test_resolve_via_alias_settings_en(self):
        pt = eh.resolve_icon_point("Discord", "settings", (0, 0, 1000, 700))
        assert pt is not None and pt["icon"] == "parametres"

    def test_bottom_left_anchor_math(self):
        # discord paramètres : bottom-left + (220, -18)
        pt = eh.resolve_icon_point("Discord", "paramètres", (100, 50, 1200, 800))
        # left=100, top+height=850 → x=100+220=320, y=850-18=832
        assert pt["x"] == 320
        assert pt["y"] == 832

    def test_top_left_anchor_math(self):
        pt = eh.resolve_icon_point("Discord", "accueil", (200, 100, 1000, 600))
        # top-left + (36, 40) → x=236, y=140
        assert pt["x"] == 236 and pt["y"] == 140

    def test_unknown_app_returns_none(self):
        assert eh.resolve_icon_point("Firefox", "engrenage", (0, 0, 800, 600)) is None

    def test_unknown_icon_returns_none(self):
        assert eh.resolve_icon_point("Discord", "licorne_magique", (0, 0, 800, 600)) is None

    def test_is_electron_heuristic_app(self):
        assert eh.is_electron_heuristic_app("Discord") is True
        assert eh.is_electron_heuristic_app("Discord - #général") is True
        assert eh.is_electron_heuristic_app("Notepad") is False

    def test_empty_sections_ignored(self):
        # slack/vscode ont des icons vides ({}) → pas d'icône résolue, mais app reconnue
        assert eh.is_electron_heuristic_app("Slack") is True
        assert eh.resolve_icon_point("Slack", "n_importe", (0, 0, 800, 600)) is None


# --------------------------------------------------------------------------- #
#  Grounding stack composition (F2)
# --------------------------------------------------------------------------- #

class TestGroundingStackF2:
    def test_easyocr_timeout_defined(self):
        assert grounding.GROUNDING_LAYER_TIMEOUT["easyocr"] == 4.0
        assert grounding.GROUNDING_LAYER_TIMEOUT["electron_heuristics"] == 0.5

    def test_easyocr_in_win32_stack(self):
        from unittest.mock import patch
        with patch.object(grounding, "_is_vision_enabled", return_value=False):
            layers = grounding._build_layers("win32", "Notepad")
        names = [l.__name__ for l in layers]
        assert "_try_easyocr" in names
        assert "_try_vision" not in names  # vision gated off

    def test_electron_heuristics_in_discord_stack(self):
        from unittest.mock import patch
        with patch.object(grounding, "_is_vision_enabled", return_value=False):
            layers = grounding._build_layers("electron", "Discord")
        names = [l.__name__ for l in layers]
        assert "_try_ocr" in names
        assert "_try_easyocr" in names
        assert "_try_electron_heuristics" in names
        # heuristics after OCR layers
        assert names.index("_try_electron_heuristics") > names.index("_try_easyocr")

    def test_no_electron_heuristics_for_unknown_app(self):
        from unittest.mock import patch
        with patch.object(grounding, "_is_vision_enabled", return_value=False):
            layers = grounding._build_layers("electron", "Figma")
        names = [l.__name__ for l in layers]
        assert "_try_electron_heuristics" not in names

    @pytest.mark.asyncio
    async def test_easyocr_graceful_when_reader_unavailable(self, monkeypatch):
        monkeypatch.setattr(grounding, "_get_easyocr_reader", lambda: None)
        result = await grounding._try_easyocr("Notepad", "fichier")
        assert result is None

    @pytest.mark.asyncio
    async def test_electron_heuristics_skips_unknown_app(self):
        # Firefox n'a pas d'heuristiques → None immédiat
        result = await grounding._try_electron_heuristics("Firefox", "engrenage")
        assert result is None


# --------------------------------------------------------------------------- #
#  Lecture d'écran (CU-1/3/4/5) — routage
# --------------------------------------------------------------------------- #

class TestScreenReadRouting:
    def setup_method(self):
        self.clf = get_classifier()
        self.val = get_validator()

    def _resolve(self, cmd):
        i = self.clf.classify(cmd, {})
        return i, self.val.resolve(i, {"foreground_window": {"title": "Discord"}})

    def test_cu1_lis_moi_ecran(self):
        i, r = self._resolve("lis-moi ce qui est à l'écran")
        assert i.category == "vision" and i.verb == "read_screen"
        assert r.tool == "screen_read" and r.params["mode"] == "read"

    def test_cu3_que_fais_je(self):
        i, r = self._resolve("que fais-je actuellement ?")
        assert r.tool == "screen_read" and r.params["mode"] == "activity"

    def test_cu4_resume_page(self):
        i, r = self._resolve("résume cette page")
        assert r.tool == "screen_read" and r.params["mode"] == "read"

    def test_cu5_que_vois_tu(self):
        i, r = self._resolve("que vois-tu à l'écran ?")
        assert r.tool == "screen_read"

    def test_cu2_engrenage_discord_is_click(self):
        # CU-2 reste un clic (heuristiques Electron), pas une lecture d'écran
        i, r = self._resolve("clique sur engrenage dans discord")
        assert i.category == "interaction" and i.verb == "click"
        assert r.tool == "ui_click_element"

    def test_screen_read_registered_in_handlers(self):
        from core.intent_engine import TOOL_HANDLERS
        assert "screen_read" in TOOL_HANDLERS


# --------------------------------------------------------------------------- #
#  Screen reader — comportement sans capture
# --------------------------------------------------------------------------- #

class TestScreenReader:
    @pytest.mark.asyncio
    async def test_read_screen_no_capture(self, monkeypatch):
        from tools import screen_reader
        monkeypatch.setattr(screen_reader, "_capture_foreground", lambda: None)
        result = await screen_reader.read_screen()
        assert result["success"] is False
        assert "capturer" in result["message"].lower()
