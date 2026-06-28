"""
Sprint v6.0.1 — Extraction core_conversational (cross-platform).

Vérifie : zéro dépendance Windows, IdentityCard + persona overlay, garde
linguistique, embeddings, classifieur minimal, mémoire conversationnelle (live).
Ces tests doivent passer sur Windows ET Mac/Linux.
"""

import ast
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PKG_DIR = os.path.join(os.path.dirname(__file__), "..", "core_conversational")


# --------------------------------------------------------------------------- #
#  Pureté cross-platform : aucune dépendance Windows
# --------------------------------------------------------------------------- #

class TestNoWindowsDeps:
    FORBIDDEN = {
        "win32api", "win32gui", "win32process", "win32con", "pywinauto",
        "comtypes", "pycaw", "wmi", "pygetwindow", "pyautogui", "ctypes",
        "msvcrt", "pytesseract", "easyocr",
    }
    FORBIDDEN_LOCAL = {"grounding", "window_controller", "app_launcher",
                       "electron_heuristics", "screen_reader"}

    def _imports(self, path):
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    mods.add(n.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mods.add(node.module.split(".")[0])
                    # also catch "from core.grounding import ..."
                    mods.add(node.module)
        return mods

    def test_no_windows_imports(self):
        for fname in os.listdir(PKG_DIR):
            if not fname.endswith(".py"):
                continue
            mods = self._imports(os.path.join(PKG_DIR, fname))
            bad = mods & self.FORBIDDEN
            assert not bad, f"{fname} importe Windows dep: {bad}"
            bad_local = {m for m in mods for f in self.FORBIDDEN_LOCAL if f in m}
            assert not bad_local, f"{fname} importe outil Atlas Windows: {bad_local}"


# --------------------------------------------------------------------------- #
#  IdentityCard + persona overlay
# --------------------------------------------------------------------------- #

class TestIdentityCard:
    def test_atlas_default_no_overlay(self):
        from core_conversational import atlas_identity
        p = atlas_identity().build_system_prompt()
        assert "Atlas" in p and "Alexis Redaud" in p
        assert "PERSONA SPÉCIFIQUE" not in p

    def test_persona_overlay_appended(self):
        from core_conversational import IdentityCard, ATLAS_BASE_IDENTITY
        card = IdentityCard(ATLAS_BASE_IDENTITY, persona_overlay="Tu es chaleureuse, tu dis 'ma star'.")
        p = card.build_system_prompt()
        assert "PERSONA SPÉCIFIQUE" in p
        assert "ma star" in p

    def test_manman_mock_persona(self):
        from core_conversational import IdentityCard
        manman = IdentityCard(
            base_identity="Tu es une assistante conversationnelle.",
            persona_overlay="Tu es Manman, l'assistante d'Émilie. Tu la tutoies.",
        )
        p = manman.build_system_prompt()
        assert "Manman" in p and "Émilie" in p

    def test_language_constraint_in_base(self):
        from core_conversational import ATLAS_BASE_IDENTITY
        assert "CONTRAINTE LINGUISTIQUE" in ATLAS_BASE_IDENTITY


# --------------------------------------------------------------------------- #
#  Garde linguistique
# --------------------------------------------------------------------------- #

class TestLanguageGuard:
    def test_detect_chinese(self):
        from core_conversational import contains_non_latin_script
        assert contains_non_latin_script("Bonjour 你好") is True

    def test_clean_french(self):
        from core_conversational import contains_non_latin_script
        assert contains_non_latin_script("Bonjour, ça va ? Réglages à côté.") is False

    @pytest.mark.asyncio
    async def test_llm_client_retries_on_drift(self, monkeypatch):
        from core_conversational import LLMClient
        client = LLMClient()
        calls = {"n": 0}

        async def fake_raw(system_prompt, user_message, history=None):
            calls["n"] += 1
            return "你好 pollué" if calls["n"] == 1 else "réponse française propre"

        monkeypatch.setattr(client, "_complete_raw", fake_raw)
        out = await client.complete("sys", "question")
        assert calls["n"] == 2 and out == "réponse française propre"

    @pytest.mark.asyncio
    async def test_llm_client_fallback(self, monkeypatch):
        from core_conversational import LLMClient, LANG_FALLBACK_MESSAGE
        client = LLMClient()

        async def fake_raw(system_prompt, user_message, history=None):
            return "toujours 你好 测试"

        monkeypatch.setattr(client, "_complete_raw", fake_raw)
        assert await client.complete("sys", "q") == LANG_FALLBACK_MESSAGE


# --------------------------------------------------------------------------- #
#  Classifieur minimal
# --------------------------------------------------------------------------- #

class TestMinimalClassifier:
    def setup_method(self):
        from core_conversational import MinimalClassifier
        self.clf = MinimalClassifier()

    def test_conversation_default(self):
        assert self.clf.classify("salut, comment ça va ?").category in ("conversation", "question")

    def test_memory_save(self):
        assert self.clf.classify("souviens-toi que j'aime le thé").category == "memory_save"

    def test_memory_recall(self):
        assert self.clf.classify("tu te souviens de ce que j'ai dit ?").category == "memory_recall"

    def test_opinion_question(self):
        assert self.clf.classify("que penses-tu de ça ?").category == "question"


# --------------------------------------------------------------------------- #
#  Embeddings + mémoire (embeddings unit ; mémoire live si ChromaDB)
# --------------------------------------------------------------------------- #

class TestMemoryCore:
    def test_embeddings_available(self):
        from core_conversational import embeddings_available, embed_query, EMBED_DIM
        assert embeddings_available() is True
        v = embed_query("bonjour")
        assert len(v) == EMBED_DIM

    def test_atlas_embeddings_facade_delegates(self):
        # Atlas core/embeddings doit déléguer au package
        from core import embeddings as atlas_emb
        assert atlas_emb.is_available() is True
        assert atlas_emb.EMBED_DIM == 768
