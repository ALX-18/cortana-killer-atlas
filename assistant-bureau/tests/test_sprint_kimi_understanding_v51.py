import tools.grounding as grounding
from core.intent_classifier import get_classifier
from core.validator import get_validator
from tools.app_launcher import get_app_type


def test_target_extraction_reduce_opera_gx():
    classifier = get_classifier()
    r = classifier.classify("réduis la fenêtre opera gx svp", {})
    assert r.category == "window_mgmt"
    assert r.verb == "minimize"
    assert (r.target or "") == "opera gx"


def test_redo_priority_detection():
    classifier = get_classifier()
    r = classifier.classify("refais", {})
    assert r.category == "memory"
    assert r.verb == "redo"


def test_get_app_type_mapping():
    assert get_app_type("steam") in {"electron", "game"}
    assert get_app_type("notepad") == "win32"


def test_grounding_layer_order_electron_skips_uia():
    layers = grounding._build_layers("electron")
    names = [fn.__name__ for fn in layers]
    assert "_try_uia" not in names
    assert names[0] == "_try_cache"


def test_grounding_layer_order_steam_includes_heuristic():
    # v5.3: vision is OFF by default (Réunion #4). Explicitly test the
    # vision-enabled composition here to verify the layer ordering logic.
    from unittest.mock import patch
    with patch.object(grounding, "_is_vision_enabled", return_value=True):
        layers = grounding._build_layers("electron", "steam")
        names = [fn.__name__ for fn in layers]
        assert "_try_vision" in names
        if grounding._has_local_minicpm():
            assert "_try_steam_nav_heuristic" not in names
        else:
            assert "_try_steam_nav_heuristic" in names
            assert names.index("_try_vision") < names.index("_try_steam_nav_heuristic")


def test_grounding_layer_steam_uses_heuristic_when_vision_disabled():
    # v5.3 — with vision disabled (the new default), Steam falls back to the
    # OCR + nav heuristic stack; vision must not appear.
    from unittest.mock import patch
    with patch.object(grounding, "_is_vision_enabled", return_value=False):
        layers = grounding._build_layers("electron", "steam")
        names = [fn.__name__ for fn in layers]
        assert "_try_vision" not in names
        assert "_try_ocr" in names
        assert "_try_steam_nav_heuristic" in names


def test_vision_parse_json_embedded_text():
    txt = 'Result: {"x": 123, "y": 456, "found": true}'
    parsed = grounding._parse_vision_json(txt)
    assert parsed is not None
    assert parsed["x"] == 123
    assert parsed["found"] is True


def test_normalize_text_handles_accents_for_bibliotheque():
    assert grounding._normalize_text("Bibliothèque") == "bibliotheque"


def test_click_command_extracts_element_and_app_correctly():
    classifier = get_classifier()
    r = classifier.classify("clique sur bibliothèque dans steam", {})
    assert r.category == "interaction"
    assert r.verb == "click"
    assert r.params.get("element_name") == "bibliothèque"
    assert r.params.get("app_title") == "steam"


def test_focus_phrase_not_misclassified_as_schedule():
    classifier = get_classifier()
    r = classifier.classify("mets la fenetre de discord en premier plan", {})
    assert r.category == "window_mgmt"
    assert r.verb == "focus"
    assert "discord" in (r.params.get("title") or "")


def test_click_on_element_uses_foreground_title_when_app_missing():
    classifier = get_classifier()
    validator = get_validator()

    i = classifier.classify("clique sur Tous", {"foreground_window": {"title": "Amis - Discord"}})
    r = validator.resolve(i, {"foreground_window": {"title": "Amis - Discord"}})

    assert r.tool == "ui_click_element"
    assert "discord" in (r.params.get("app_title", "")).lower()


def test_focus_pronoun_marks_last_window_placeholder():
    classifier = get_classifier()
    r = classifier.classify("remets la en premier plan", {})
    assert r.category == "window_mgmt"
    assert r.verb == "focus"
    assert r.params.get("title") == "__last_window__"


def test_point_in_bounds_allows_negative_x_virtual_desktop():
    assert grounding._point_in_bounds(-1502, 80, (-1920, 0, 1920, 1080)) is True


def test_steam_label_aliases_for_library():
    aliases = [grounding._normalize_text(a) for a in grounding._steam_label_aliases("bibliothèque")]
    assert "bibliotheque" in aliases
    assert "library" in aliases
