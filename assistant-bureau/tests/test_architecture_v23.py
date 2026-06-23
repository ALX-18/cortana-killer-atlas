"""
Test Suite v2.3 — Architecture Controlled Loop
23 scénarios : 19 originaux + 4 nouveaux

Tests unitaires déterministes (sans Ollama, sans exécution réelle).
Valident le pipeline : Classifier → Validator → ExecutionEngine routing.
"""

import asyncio
import json
import sys
import os
import time

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PYTHONIOENCODING"] = "utf-8"

from core.intent_classifier import IntentClassifier, IntentResult, get_classifier
from core.validator import Validator, ResolvedAction, get_validator
from core.world_state import WorldState, get_world_state
from core.intent_engine import TOOL_HANDLERS

# --------------------------------------------------------------------------- #
#  Test infrastructure
# --------------------------------------------------------------------------- #

PASS = 0
FAIL = 0
RESULTS = []


def _test(name: str, condition: bool, details: str = ""):
    global PASS, FAIL
    status = "PASS" if condition else "FAIL"
    if condition:
        PASS += 1
    else:
        FAIL += 1
    RESULTS.append({"name": name, "status": status, "details": details})
    icon = "✅" if condition else "❌"
    print(f"  {icon} {name} — {details}" if details else f"  {icon} {name}")


# Mock context for tests
MOCK_CONTEXT = {
    "foreground_window": {
        "title": "Visual Studio Code",
        "process": "Code.exe",
    },
    "cpu_usage": 25.0,
    "ram_usage": 60.0,
    "top_processes": [
        {"name": "Code.exe", "pid": 1234},
        {"name": "opera.exe", "pid": 5678},
        {"name": "explorer.exe", "pid": 9012},
    ],
}


def run_tests():
    global PASS, FAIL

    classifier = IntentClassifier()
    validator = Validator()

    print("\n" + "=" * 70)
    print("  ATLAS v2.3 — Architecture Test Suite (23 scénarios)")
    print("=" * 70)

    # ================================================================== #
    #  BLOC 1 : Classification d'intentions (12 tests)
    # ================================================================== #
    print("\n--- BLOC 1 : Intent Classifier ---\n")

    # S1: Lancer une application
    r = classifier.classify("Ouvre le bloc-notes", MOCK_CONTEXT)
    _test("S01 — Ouvre le bloc-notes",
          r.category == "window_mgmt" and r.verb == "open" and "bloc-notes" in (r.target or "").lower(),
          f"cat={r.category} verb={r.verb} target={r.target} conf={r.confidence:.2f}")

    # S2: Fermer une application
    r = classifier.classify("Ferme Discord", MOCK_CONTEXT)
    _test("S02 — Ferme Discord",
          r.category == "window_mgmt" and r.verb == "close" and "discord" in (r.target or "").lower(),
          f"cat={r.category} verb={r.verb} target={r.target}")

    # S3: Recherche web
    r = classifier.classify("Cherche la météo à Paris", MOCK_CONTEXT)
    _test("S03 — Cherche la météo",
          r.category == "web" and r.verb == "search",
          f"cat={r.category} verb={r.verb} target={r.target}")

    # S4: Taper du texte
    r = classifier.classify("Tape 'bonjour le monde' dans le bloc-notes", MOCK_CONTEXT)
    _test("S04 — Taper du texte",
          r.category == "interaction" and r.verb == "type",
          f"cat={r.category} verb={r.verb} params={r.params}")

    # S5: Raccourci clavier
    r = classifier.classify("Fais Ctrl+S dans VS Code", MOCK_CONTEXT)
    _test("S05 — Raccourci Ctrl+S",
          r.category == "interaction" and r.verb == "hotkey",
          f"cat={r.category} verb={r.verb} params={r.params}")

    # S6: Question pure (conversation)
    r = classifier.classify("C'est quoi Python ?", MOCK_CONTEXT)
    _test("S06 — Question → conversation",
          r.category == "conversation",
          f"cat={r.category} verb={r.verb} conf={r.confidence:.2f}")

    # S7: Navigation web
    r = classifier.classify("Va sur youtube.com", MOCK_CONTEXT)
    _test("S07 — Va sur youtube.com",
          r.category == "web" and r.verb == "navigate",
          f"cat={r.category} verb={r.verb} params={r.params}")

    # S8: Kill process
    r = classifier.classify("Tue le processus Chrome", MOCK_CONTEXT)
    _test("S08 — Kill process",
          r.category == "process" and r.verb == "kill",
          f"cat={r.category} verb={r.verb} target={r.target}")

    # S9: Diagnostic système
    r = classifier.classify("Fais un diagnostic système", MOCK_CONTEXT)
    _test("S09 — Diagnostic",
          r.category == "system" and r.verb == "diagnose",
          f"cat={r.category} verb={r.verb}")

    # S10: URL directe
    r = classifier.classify("Lis https://example.com/article", MOCK_CONTEXT)
    _test("S10 — URL directe → web/read",
          r.category == "web" and r.verb == "read" and "example.com" in (r.target or ""),
          f"cat={r.category} verb={r.verb} target={r.target}")

    # S11: Minimize
    r = classifier.classify("Minimise la fenêtre Discord", MOCK_CONTEXT)
    _test("S11 — Minimise Discord",
          r.category == "window_mgmt" and r.verb == "minimize",
          f"cat={r.category} verb={r.verb} target={r.target}")

    # S12: Multi-step detection
    r = classifier.classify("Ouvre Chrome puis va sur google.com", MOCK_CONTEXT)
    _test("S12 — Multi-step détection",
          r.is_complex,
          f"is_complex={r.is_complex} cat={r.category}")

    # ================================================================== #
    #  BLOC 2 : Validator (6 tests)
    # ================================================================== #
    print("\n--- BLOC 2 : Validator ---\n")

    # S13: Open app → launch_app
    intent = IntentResult(category="window_mgmt", verb="open", target="notepad",
                          params={"name": "notepad"}, confidence=0.95, raw_input="ouvre notepad")
    resolved = validator.resolve(intent, MOCK_CONTEXT)
    _test("S13 — Open → launch_app",
          resolved.tool == "launch_app",
          f"tool={resolved.tool} params={resolved.params}")

    # S14: Open already running app → window_focus
    intent = IntentResult(category="window_mgmt", verb="open", target="Code",
                          params={"name": "Code"}, confidence=0.95, raw_input="ouvre vscode")
    context_with_code = dict(MOCK_CONTEXT)
    resolved = validator.resolve(intent, context_with_code)
    _test("S14 — Open running app → window_focus",
          resolved.tool == "window_focus",
          f"tool={resolved.tool} params={resolved.params}")

    # S15: Close → confirmation required
    intent = IntentResult(category="window_mgmt", verb="close", target="discord",
                          params={"title": "discord"}, confidence=0.95, raw_input="ferme discord")
    resolved = validator.resolve(intent, MOCK_CONTEXT)
    _test("S15 — Close → confirmation",
          resolved.confirmation_required and resolved.tool == "window_close",
          f"tool={resolved.tool} confirm={resolved.confirmation_required}")

    # S16: Search → web_search
    intent = IntentResult(category="web", verb="search", target="météo",
                          params={"query": "météo"}, confidence=0.95, raw_input="cherche la météo")
    resolved = validator.resolve(intent, MOCK_CONTEXT)
    _test("S16 — Search → web_search",
          resolved.tool == "web_search",
          f"tool={resolved.tool} params={resolved.params}")

    # S17: Click → ui_click_element (grounding)
    intent = IntentResult(category="interaction", verb="click", target="Fichier",
                          params={"element_name": "Fichier"}, confidence=0.90,
                          raw_input="clique sur Fichier")
    resolved = validator.resolve(intent, MOCK_CONTEXT)
    _test("S17 — Click → ui_click_element",
          resolved.tool == "ui_click_element",
          f"tool={resolved.tool} params={resolved.params}")

    # S18: Conversation passthrough
    intent = IntentResult(category="conversation", verb="chat", target=None,
                          confidence=0.80, raw_input="c'est quoi python")
    resolved = validator.resolve(intent, MOCK_CONTEXT)
    _test("S18 — Conversation → __conversation__",
          resolved.tool == "__conversation__",
          f"tool={resolved.tool}")

    # ================================================================== #
    #  BLOC 3 : Tool Handlers Registry (3 tests)
    # ================================================================== #
    print("\n--- BLOC 3 : Tool Handlers ---\n")

    # S19: New window tools registered
    new_tools = ["window_close", "window_minimize", "window_maximize",
                 "window_list", "window_snap"]
    missing = [t for t in new_tools if t not in TOOL_HANDLERS]
    _test("S19 — Window tools enregistrés",
          len(missing) == 0,
          f"missing={missing}" if missing else f"all {len(new_tools)} present")

    # S20: Grounding tool registered
    _test("S20 — ui_click_element enregistré",
          "ui_click_element" in TOOL_HANDLERS,
          f"present={'ui_click_element' in TOOL_HANDLERS}")

    # S21: Redo tool registered
    _test("S21 — redo_last_action enregistré",
          "redo_last_action" in TOOL_HANDLERS,
          f"present={'redo_last_action' in TOOL_HANDLERS}")

    # ================================================================== #
    #  BLOC 4 : World State + Integration (2 tests)
    # ================================================================== #
    print("\n--- BLOC 4 : WorldState + Integration ---\n")

    # S22: WorldState update
    ws = WorldState()
    ws.update_from_context(MOCK_CONTEXT)
    ws.update_after_action("launch_app", {"name": "notepad"}, {"success": True}, raw_input="ouvre notepad")
    _test("S22 — WorldState update + redo ready",
          ws.last_action is not None and ws.last_action["tool"] == "launch_app",
          f"last_action={ws.last_action}")

    # S23: Full pipeline — Classifier → Validator consistency
    test_cases = [
        ("Lance Steam", "launch_app"),
        ("Ferme le bloc-notes", "window_close"),
        ("Cherche recette pizza", "web_search"),
        ("Maximise Discord", "window_maximize"),
    ]
    all_correct = True
    failures = []
    for user_input, expected_tool in test_cases:
        intent = classifier.classify(user_input, MOCK_CONTEXT)
        resolved = validator.resolve(intent, MOCK_CONTEXT)
        if resolved.tool != expected_tool:
            all_correct = False
            failures.append(f"{user_input}: got {resolved.tool}, expected {expected_tool}")

    _test("S23 — Pipeline Classifier→Validator (4 cas)",
          all_correct,
          f"failures={failures}" if failures else "all 4 correct")

    # ================================================================== #
    #  Summary
    # ================================================================== #
    print("\n" + "=" * 70)
    total = PASS + FAIL
    pct = (PASS / total * 100) if total > 0 else 0
    print(f"  RÉSULTAT : {PASS}/{total} ({pct:.0f}%)")
    if pct >= 83:
        print("  🎯 OBJECTIF ATTEINT (≥83%)")
    else:
        print(f"  ⚠️ OBJECTIF NON ATTEINT (cible ≥83%, actuel {pct:.0f}%)")
    print("=" * 70)

    return RESULTS


if __name__ == "__main__":
    run_tests()
