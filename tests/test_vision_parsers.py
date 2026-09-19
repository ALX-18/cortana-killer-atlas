"""
Tests unitaires — Parseurs vision (tools/grounding.py)
Sprint v5.1 — P4 (parseurs vision)
Sprint v5.1 corrective — timeouts grounding + instrumentation layer_attempts
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from tools import grounding
from tools.grounding import (
    _parse_vision_json,
    _normalize_vision_payload,
    _steam_label_aliases,
    _point_in_bounds,
    _normalize_text,
    find_and_click,
    GROUNDING_LAYER_TIMEOUT,
    GROUNDING_TOTAL_TIMEOUT,
)


# --------------------------------------------------------------------------- #
#  _parse_vision_json
# --------------------------------------------------------------------------- #

class TestParseVisionJson:
    def test_direct_json_found_true(self):
        result = _parse_vision_json('{"x": 123, "y": 456, "found": true}')
        assert result == {"x": 123, "y": 456, "found": True}

    def test_found_false(self):
        result = _parse_vision_json('{"found": false}')
        assert result is not None
        assert result.get("found") is False

    def test_markdown_fenced_json(self):
        text = '```json\n{"x": 100, "y": 200}\n```'
        result = _parse_vision_json(text)
        assert result == {"x": 100, "y": 200}

    def test_markdown_fenced_no_lang(self):
        text = '```\n{"x": 50, "y": 75, "found": true}\n```'
        result = _parse_vision_json(text)
        assert result is not None
        assert result.get("x") == 50
        assert result.get("y") == 75

    def test_bbox_format_center(self):
        result = _parse_vision_json("<box>50 60 150 160</box>")
        assert result is not None
        assert result.get("x") == 100   # (50+150)//2
        assert result.get("y") == 110   # (60+160)//2
        assert result.get("found") is True

    def test_bbox_format_asymmetric(self):
        result = _parse_vision_json("<box>0 0 200 100</box>")
        assert result is not None
        assert result.get("x") == 100
        assert result.get("y") == 50

    def test_loose_coordinate_extraction(self):
        text = 'The element is at "x": 300, stuff "y": 400 here'
        result = _parse_vision_json(text)
        assert result is not None
        assert result.get("x") == 300
        assert result.get("y") == 400

    def test_inline_backtick_json(self):
        text = 'Here is the result: `{"x": 200, "y": 300, "found": true}`'
        result = _parse_vision_json(text)
        assert result is not None
        assert result.get("x") == 200

    def test_bare_json_in_prose(self):
        text = 'The coordinates are {"x": 77, "y": 88} in the image.'
        result = _parse_vision_json(text)
        assert result is not None
        assert result.get("x") == 77

    def test_garbage_returns_none(self):
        result = _parse_vision_json("garbage texte cassé {{{")
        assert result is None

    def test_empty_string_returns_none(self):
        result = _parse_vision_json("")
        assert result is None

    def test_only_whitespace_returns_none(self):
        result = _parse_vision_json("   ")
        assert result is None

    def test_pure_text_no_coords(self):
        result = _parse_vision_json("Je ne trouve pas l'élément dans l'image.")
        assert result is None

    def test_found_false_no_coords(self):
        result = _parse_vision_json('{"found": false, "message": "not found"}')
        assert result is not None
        assert result.get("found") is False


# --------------------------------------------------------------------------- #
#  _normalize_vision_payload  (x/y coercion)
# --------------------------------------------------------------------------- #

class TestNormalizeVisionPayload:
    def test_list_xy_takes_first_element(self):
        result = _normalize_vision_payload({"x": [100], "y": [200], "found": True})
        assert result is not None
        assert result["x"] == 100
        assert result["y"] == 200

    def test_string_xy_to_int(self):
        result = _normalize_vision_payload({"x": "150", "y": "250"})
        assert result is not None
        assert result["x"] == 150
        assert result["y"] == 250

    def test_float_xy_truncated(self):
        result = _normalize_vision_payload({"x": 1.9, "y": 2.1})
        assert result is not None
        assert result["x"] == 1
        assert result["y"] == 2

    def test_none_payload_passthrough(self):
        assert _normalize_vision_payload(None) is None

    def test_non_dict_passthrough(self):
        result = _normalize_vision_payload("not a dict")
        assert result == "not a dict"

    def test_empty_list_xy_unchanged(self):
        # _coerce_int([]) returns None, so the field is NOT overwritten — stays as []
        result = _normalize_vision_payload({"x": [], "y": []})
        assert result is not None
        assert result.get("x") == []
        assert result.get("y") == []

    def test_missing_xy_fields_unchanged(self):
        result = _normalize_vision_payload({"found": False})
        assert result == {"found": False}


# --------------------------------------------------------------------------- #
#  _steam_label_aliases
# --------------------------------------------------------------------------- #

class TestSteamLabelAliases:
    def test_bibliotheque_accented(self):
        aliases = _steam_label_aliases("Bibliothèque")
        assert "bibliotheque" in aliases
        assert "library" in aliases

    def test_bibliotheque_no_accent(self):
        aliases = _steam_label_aliases("bibliotheque")
        assert "bibliotheque" in aliases
        assert "library" in aliases

    def test_library_english(self):
        aliases = _steam_label_aliases("library")
        assert "bibliotheque" in aliases
        assert "library" in aliases

    def test_librairie_variant(self):
        aliases = _steam_label_aliases("librairie")
        assert "library" in aliases

    def test_unknown_element_passthrough(self):
        aliases = _steam_label_aliases("Store")
        assert "Store" in aliases
        assert len(aliases) == 1

    def test_returns_list(self):
        aliases = _steam_label_aliases("Bibliothèque")
        assert isinstance(aliases, list)


# --------------------------------------------------------------------------- #
#  _point_in_bounds
# --------------------------------------------------------------------------- #

class TestPointInBounds:
    STANDARD = (0, 0, 1920, 1080)

    def test_center_in_bounds(self):
        assert _point_in_bounds(960, 540, self.STANDARD) is True

    def test_origin_in_bounds(self):
        assert _point_in_bounds(0, 0, self.STANDARD) is True

    def test_exact_right_edge_out(self):
        # Bounds are exclusive on the right
        assert _point_in_bounds(1920, 540, self.STANDARD) is False

    def test_exact_bottom_edge_out(self):
        assert _point_in_bounds(960, 1080, self.STANDARD) is False

    def test_negative_x_virtual_desktop(self):
        virtual = (-1920, 0, 1920, 1080)
        assert _point_in_bounds(-5, 300, virtual) is True

    def test_negative_out_of_virtual(self):
        virtual = (-1920, 0, 1920, 1080)
        assert _point_in_bounds(-2000, 300, virtual) is False

    def test_completely_outside(self):
        assert _point_in_bounds(3000, 3000, self.STANDARD) is False


# --------------------------------------------------------------------------- #
#  _normalize_text
# --------------------------------------------------------------------------- #

class TestNormalizeText:
    def test_accent_removal_bibliotheque(self):
        assert _normalize_text("Bibliothèque") == "bibliotheque"

    def test_uppercase_lowercased(self):
        assert _normalize_text("STORE") == "store"

    def test_whitespace_collapsed(self):
        assert _normalize_text("  bloc  notes  ") == "bloc notes"

    def test_empty_string(self):
        assert _normalize_text("") == ""

    def test_multiple_accents(self):
        assert _normalize_text("Médiathèque") == "mediatheque"

    def test_e_accented_variants(self):
        result = _normalize_text("Éléments")
        assert result == "elements"

    def test_already_normalized(self):
        assert _normalize_text("steam") == "steam"


# --------------------------------------------------------------------------- #
#  v5.1 corrective — Timeouts + instrumentation grounding
# --------------------------------------------------------------------------- #

class TestGroundingTimeoutEnforced:
    """Verify that find_and_click enforces per-layer and global timeouts."""

    def test_timeout_constants_present(self):
        assert "vision" in GROUNDING_LAYER_TIMEOUT
        assert GROUNDING_LAYER_TIMEOUT["vision"] == 8.0
        assert GROUNDING_LAYER_TIMEOUT["ocr"] == 5.0
        assert GROUNDING_LAYER_TIMEOUT["uia"] == 3.0
        assert GROUNDING_LAYER_TIMEOUT["cache"] == 0.5
        assert GROUNDING_TOTAL_TIMEOUT == 20.0

    @staticmethod
    def _named(name: str, coro_fn):
        """Wrap an async function so its __name__ matches the expected layer key."""
        coro_fn.__name__ = name
        return coro_fn

    @pytest.mark.asyncio
    async def test_layer_timeout_aborts_slow_layer(self, monkeypatch):
        """A layer that hangs longer than its timeout must be aborted as 'timeout'."""

        async def _slow(app, elem):
            await asyncio.sleep(10.0)
            return {"success": True, "method": "uia"}

        async def _fail(app, elem):
            return None

        monkeypatch.setattr(grounding, "_try_uia", self._named("_try_uia", _slow))
        monkeypatch.setattr(grounding, "_try_cache", self._named("_try_cache", _fail))
        monkeypatch.setattr(grounding, "_try_ocr", self._named("_try_ocr", _fail))
        monkeypatch.setattr(grounding, "_try_vision", self._named("_try_vision", _fail))

        # Force win32 path so UIA is the first layer
        # B1 : find_and_click exige désormais une fenêtre existante pour la cible.
        monkeypatch.setattr(grounding, "_find_candidate_windows", lambda t: ["fenêtre simulée"])

        async def _no_easyocr(app, elem):
            return None
        _no_easyocr.__name__ = "_try_easyocr"
        monkeypatch.setattr(grounding, "_try_easyocr", _no_easyocr)
        monkeypatch.setattr(grounding, "_detect_app_type", lambda t: "win32")
        monkeypatch.setattr(grounding, "_has_local_minicpm", lambda: True)

        start = asyncio.get_event_loop().time()
        result = await find_and_click("notepad", "fichier")
        elapsed = asyncio.get_event_loop().time() - start

        # UIA timeout is 3.0s; assert we abort well before the 10s sleep would finish.
        # Margin of 6s accounts for asyncio.wait_for cancellation overhead on Windows.
        assert elapsed < 6.0, f"find_and_click took {elapsed:.1f}s — UIA 3s timeout not enforced"
        assert result["success"] is False

        attempts = result.get("layer_attempts", [])
        uia_attempts = [a for a in attempts if a["layer"] == "uia"]
        assert len(uia_attempts) == 1
        assert uia_attempts[0]["result"] == "timeout"
        assert "timeout" in (uia_attempts[0]["error"] or "").lower()

    @pytest.mark.asyncio
    async def test_layer_attempts_returned_on_failure(self, monkeypatch):
        """find_and_click must always return layer_attempts list (success or failure)."""

        async def _fail(app, elem):
            return None

        monkeypatch.setattr(grounding, "_try_uia", self._named("_try_uia", _fail))
        # Each layer needs a distinct function object since we override __name__
        async def _fail_cache(app, elem):
            return None
        async def _fail_ocr(app, elem):
            return None
        async def _fail_vision(app, elem):
            return None
        monkeypatch.setattr(grounding, "_try_cache", self._named("_try_cache", _fail_cache))
        monkeypatch.setattr(grounding, "_try_ocr", self._named("_try_ocr", _fail_ocr))
        monkeypatch.setattr(grounding, "_try_vision", self._named("_try_vision", _fail_vision))
        monkeypatch.setattr(grounding, "_find_candidate_windows", lambda t: ["fenêtre simulée"])

        async def _no_easyocr(app, elem):
            return None
        _no_easyocr.__name__ = "_try_easyocr"
        monkeypatch.setattr(grounding, "_try_easyocr", _no_easyocr)
        monkeypatch.setattr(grounding, "_detect_app_type", lambda t: "win32")
        monkeypatch.setattr(grounding, "_has_local_minicpm", lambda: True)
        # v5.3: vision is OFF by default; force it ON to exercise the full 4-layer stack
        monkeypatch.setattr(grounding, "_is_vision_enabled", lambda: True)

        result = await find_and_click("notepad", "fichier")
        assert result["success"] is False
        assert "layer_attempts" in result
        attempts = result["layer_attempts"]
        layer_names = [a["layer"] for a in attempts]
        assert "uia" in layer_names
        assert "cache" in layer_names
        assert "ocr" in layer_names
        assert "vision" in layer_names
        for a in attempts:
            assert isinstance(a["latency_ms"], int)
            assert a["latency_ms"] >= 0
            assert "result" in a

    @pytest.mark.asyncio
    async def test_layer_attempts_returned_on_success(self, monkeypatch):
        """On success, layer_attempts must include the successful layer."""

        async def _fail_uia(app, elem):
            return None
        async def _fail_cache(app, elem):
            return None
        async def _ok_ocr(app, elem):
            return {"success": True, "method": "ocr", "coords": (100, 200)}
        async def _fail_vision(app, elem):
            return None

        monkeypatch.setattr(grounding, "_try_uia", self._named("_try_uia", _fail_uia))
        monkeypatch.setattr(grounding, "_try_cache", self._named("_try_cache", _fail_cache))
        monkeypatch.setattr(grounding, "_try_ocr", self._named("_try_ocr", _ok_ocr))
        monkeypatch.setattr(grounding, "_try_vision", self._named("_try_vision", _fail_vision))
        monkeypatch.setattr(grounding, "_find_candidate_windows", lambda t: ["fenêtre simulée"])

        async def _no_easyocr(app, elem):
            return None
        _no_easyocr.__name__ = "_try_easyocr"
        monkeypatch.setattr(grounding, "_try_easyocr", _no_easyocr)
        monkeypatch.setattr(grounding, "_detect_app_type", lambda t: "win32")
        monkeypatch.setattr(grounding, "_has_local_minicpm", lambda: True)

        result = await find_and_click("notepad", "fichier")
        assert result["success"] is True
        assert result["method"] == "ocr"
        assert "layer_attempts" in result
        ocr_attempts = [a for a in result["layer_attempts"] if a["layer"] == "ocr"]
        assert len(ocr_attempts) == 1
        assert ocr_attempts[0]["result"] == "success"
