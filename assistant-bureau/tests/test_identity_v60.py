"""
Sprint v6.0 — Identity Card Atlas (quick win)
Vérifie que le system prompt contient l'identité cohérente.
Les 5 Q/R réelles sont consignées en section 6 du rapport (test terrain).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.ollama_client import build_system_prompt, SYSTEM_PROMPT_IDENTITY

CTX = {
    "foreground_window": {"title": "Steam", "process": "steam.exe"},
    "cpu_usage": 5,
    "ram_usage": 30,
}


class TestIdentityCard:
    def test_identity_constant_has_creator(self):
        assert "Alexis Redaud" in SYSTEM_PROMPT_IDENTITY

    def test_identity_constant_has_project_name(self):
        assert "Cortana Killer" in SYSTEM_PROMPT_IDENTITY

    def test_identity_constant_has_philosophy(self):
        assert "100% local" in SYSTEM_PROMPT_IDENTITY
        assert "zéro cloud" in SYSTEM_PROMPT_IDENTITY

    def test_identity_constant_has_team(self):
        for member in ("Alexis", "Claude", "GPT", "Kimi"):
            assert member in SYSTEM_PROMPT_IDENTITY

    def test_identity_constant_enforces_french(self):
        assert "français" in SYSTEM_PROMPT_IDENTITY.lower()

    def test_identity_injected_in_built_prompt(self):
        p = build_system_prompt(CTX, memories=None)
        assert "Alexis Redaud" in p
        assert "Cortana Killer" in p
        assert "controlled loop" in p.lower()

    def test_identity_coexists_with_context_and_memories(self):
        p = build_system_prompt(CTX, memories=["L'utilisateur préfère le mode sombre"])
        # Identity + world state + memory all present
        assert "Alexis Redaud" in p
        assert "Steam" in p
        assert "mode sombre" in p

    def test_identity_first_in_prompt(self):
        # Identity should lead the prompt (Atlas knows who it is upfront)
        p = build_system_prompt(CTX, memories=None)
        assert p.lstrip().startswith("Tu es Atlas")
