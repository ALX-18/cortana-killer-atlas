"""
Sprint v6.0.1 — Patches terrain.
P1 : heuristiques Electron settings déclenchement
P2 : dérive linguistique L7-7 (post-filtrage CJK)
P3 : faux positif intent action sur questions
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.intent_classifier import get_classifier
from core.validator import get_validator
from core.ollama_client import contains_non_latin_script, LANG_FALLBACK_MESSAGE
import core.ollama_client as oc
import tools.electron_heuristics as eh


CTX = {"foreground_window": {"title": "Discord"}}


# --------------------------------------------------------------------------- #
#  P1 — Settings → ui_click_element
# --------------------------------------------------------------------------- #

class TestP1SettingsRouting:
    def setup_method(self):
        self.clf = get_classifier()
        self.val = get_validator()

    def _route(self, cmd, ctx=CTX):
        i = self.clf.classify(cmd, ctx)
        return i, self.val.resolve(i, ctx)

    @pytest.mark.parametrize("cmd", [
        "va dans les paramètres de Discord",
        "ouvre les réglages de discord",
        "paramètres Discord",
        "réglages Discord",
        "configuration Discord",
    ])
    def test_settings_routes_to_click(self, cmd):
        i, r = self._route(cmd)
        assert i.category == "interaction" and i.verb == "click"
        assert r.tool == "ui_click_element"
        assert r.params.get("app_title") == "discord"
        assert "param" in r.params.get("element_name", "").lower()

    def test_yaml_settings_aliases_present(self):
        eh.load_config(force=True)
        pt = eh.resolve_icon_point("Discord", "configuration", (0, 0, 1000, 700))
        assert pt is not None and pt["icon"] == "parametres"

    def test_settings_via_foreground_when_app_implicit(self):
        # "ouvre les paramètres" sans nommer l'app → app via foreground Discord
        i, r = self._route("ouvre les paramètres", {"foreground_window": {"title": "Discord"}})
        assert r.tool == "ui_click_element"
        assert r.params.get("app_title") == "discord"


# --------------------------------------------------------------------------- #
#  P2 — Dérive linguistique
# --------------------------------------------------------------------------- #

class TestP2LanguageDrift:
    def test_detector_chinese(self):
        assert contains_non_latin_script("Bonjour 你好 le monde") is True

    def test_detector_japanese(self):
        assert contains_non_latin_script("テスト test") is True

    def test_detector_korean(self):
        assert contains_non_latin_script("안녕 hello") is True

    def test_detector_cyrillic(self):
        assert contains_non_latin_script("Привет salut") is True

    def test_detector_pure_french_ok(self):
        assert contains_non_latin_script("Bonjour, je suis Atlas. Ça va très bien !") is False

    def test_detector_french_accents_ok(self):
        assert contains_non_latin_script("Réglages, paramètres, à côté, où, ça") is False

    @pytest.mark.asyncio
    async def test_chat_full_retries_on_drift(self, monkeypatch):
        calls = {"n": 0}

        async def fake_raw(user_message, context, history=None, memories=None, system_prompt=None):
            calls["n"] += 1
            return "réponse 你好 polluée" if calls["n"] == 1 else "réponse propre en français"

        monkeypatch.setattr(oc, "_chat_full_raw", fake_raw)
        out = await oc.chat_full("question", {})
        assert calls["n"] == 2
        assert out == "réponse propre en français"

    @pytest.mark.asyncio
    async def test_chat_full_fallback_after_persistent_drift(self, monkeypatch):
        async def fake_raw(user_message, context, history=None, memories=None, system_prompt=None):
            return "toujours pollué 你好 测试"

        monkeypatch.setattr(oc, "_chat_full_raw", fake_raw)
        out = await oc.chat_full("question", {})
        assert out == LANG_FALLBACK_MESSAGE

    @pytest.mark.asyncio
    async def test_chat_full_no_retry_when_clean(self, monkeypatch):
        calls = {"n": 0}

        async def fake_raw(user_message, context, history=None, memories=None, system_prompt=None):
            calls["n"] += 1
            return "réponse parfaitement française"

        monkeypatch.setattr(oc, "_chat_full_raw", fake_raw)
        out = await oc.chat_full("question", {})
        assert calls["n"] == 1
        assert "française" in out

    def test_identity_prompt_has_language_constraint(self):
        from core.ollama_client import SYSTEM_PROMPT_IDENTITY
        assert "CONTRAINTE LINGUISTIQUE" in SYSTEM_PROMPT_IDENTITY
        assert "non-latin" in SYSTEM_PROMPT_IDENTITY


# --------------------------------------------------------------------------- #
#  P3 — Faux positif intent action
# --------------------------------------------------------------------------- #

class TestP3FalsePositive:
    def setup_method(self):
        self.clf = get_classifier()

    @pytest.mark.parametrize("cmd", [
        "Tu penses que c'est réalisable ?",
        "que penses-tu de ça ?",
        "tu crois que ça marche ?",
        "penses-tu pouvoir le faire ?",
        "tu trouves ça bien ?",
        "qu'est-ce que tu en penses ?",
    ])
    def test_opinion_questions_are_conversation(self, cmd):
        i = self.clf.classify(cmd, CTX)
        assert i.category == "conversation", f"{cmd} → {i.category}/{i.verb}"

    def test_real_action_still_routes(self):
        # P3 ne doit pas avaler les vraies actions
        i = self.clf.classify("ouvre le bloc-notes", CTX)
        assert i.category == "window_mgmt"

    def test_screen_read_question_still_works(self):
        # "que fais-je" reste lecture d'écran, pas conversation
        i = self.clf.classify("que fais-je actuellement ?", CTX)
        assert i.category == "vision"
