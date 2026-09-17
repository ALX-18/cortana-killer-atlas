"""
Test d'intégration RÉEL v2.3 — Exécution sur le PC

Ce script exécute VRAIMENT les actions sur la machine :
- Lance des applications
- Tape du texte
- Envoie des raccourcis clavier
- Minimise / maximise / ferme des fenêtres
- Liste les fenêtres actives
- Recherche web
- Teste le pipeline complet Classifier → Validator → Tool

⚠️  Ce script VA interagir avec votre PC en temps réel.
"""

import sys
import os
import time
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PYTHONIOENCODING"] = "utf-8"

from tools.app_launcher import launch_app
from tools.window_controller import (
    window_find, window_focus, window_type, window_hotkey,
    window_get_active, window_close, window_minimize,
    window_maximize, window_list, window_snap,
)
from core.intent_classifier import get_classifier
from core.validator import get_validator
from core.intent_engine import TOOL_HANDLERS, execute_tool

# --------------------------------------------------------------------------- #
PASS = 0
FAIL = 0
RESULTS = []


def _test(name, condition, details=""):
    global PASS, FAIL
    status = "PASS" if condition else "FAIL"
    if condition:
        PASS += 1
    else:
        FAIL += 1
    RESULTS.append({"name": name, "status": status, "details": details})
    icon = "\u2705" if condition else "\u274c"
    print(f"  {icon} {name}")
    if details:
        print(f"      \u2192 {details}")


def _pause(seconds=2):
    """Pause visible entre les actions."""
    time.sleep(seconds)


# --------------------------------------------------------------------------- #
#  Pipeline helper: classifier → validator → execute
# --------------------------------------------------------------------------- #
async def _run_pipeline(user_input: str, context: dict) -> dict:
    """Execute le pipeline v2.3 complet pour un input donné."""
    classifier = get_classifier()
    validator = get_validator()

    intent = classifier.classify(user_input, context)
    resolved = validator.resolve(intent, context)

    if resolved.tool == "__conversation__":
        return {"status": "conversation", "tool": "__conversation__"}

    result = await execute_tool(resolved.tool, resolved.params, context)
    return {"tool": resolved.tool, "params": resolved.params, **result}


def run_pipeline(user_input: str, context: dict = None) -> dict:
    """Wrapper synchrone."""
    ctx = context or {}
    return asyncio.run(_run_pipeline(user_input, ctx))


# ========================================================================== #
#   TESTS RÉELS
# ========================================================================== #

def run_all_tests():
    global PASS, FAIL

    print()
    print("=" * 70)
    print("  ATLAS v2.3 — TESTS D'INTÉGRATION RÉELS")
    print("  \u26a0\ufe0f  Ce script interagit avec votre PC en temps réel")
    print("=" * 70)

    # ------------------------------------------------------------------ #
    #  TEST 1 : Lancer le Bloc-notes
    # ------------------------------------------------------------------ #
    print("\n--- TEST 1 : Lancer le Bloc-notes ---")
    result = launch_app(name="notepad")
    _test("T01 — Lancer Bloc-notes",
          result.get("success", False),
          result.get("message", ""))
    _pause(3)

    # Vérifier que la fenêtre existe
    find_result = window_find("Notepad")
    # Sur Windows FR, le titre peut être "Bloc-notes" ou "Notepad"
    if not find_result.get("success"):
        find_result = window_find("Bloc-notes")
    _test("T02 — Fenêtre Bloc-notes détectée",
          find_result.get("success", False) and find_result.get("count", 0) > 0,
          f"Fenêtres trouvées: {find_result.get('count', 0)}")

    # ------------------------------------------------------------------ #
    #  TEST 2 : Taper du texte dans le Bloc-notes
    # ------------------------------------------------------------------ #
    print("\n--- TEST 2 : Taper du texte ---")
    # Focus d'abord
    focus_r = window_focus("Notepad")
    if not focus_r.get("success"):
        focus_r = window_focus("Bloc-notes")
    _pause(1)

    type_result = window_type("Bonjour Atlas v2.3 !", target=None, use_clipboard=True)
    _test("T03 — Taper 'Bonjour Atlas v2.3 !'",
          type_result.get("success", False),
          type_result.get("message", ""))
    _pause(1)

    # ------------------------------------------------------------------ #
    #  TEST 3 : Raccourci clavier (sélectionner tout)
    # ------------------------------------------------------------------ #
    print("\n--- TEST 3 : Raccourci clavier Ctrl+A ---")
    hotkey_result = window_hotkey("ctrl", "a")
    _test("T04 — Raccourci Ctrl+A (sélectionner tout)",
          hotkey_result.get("success", False),
          hotkey_result.get("message", ""))
    _pause(1)

    # ------------------------------------------------------------------ #
    #  TEST 4 : Minimiser la fenêtre
    # ------------------------------------------------------------------ #
    print("\n--- TEST 4 : Minimiser le Bloc-notes ---")
    min_result = window_minimize("Notepad")
    if not min_result.get("success"):
        min_result = window_minimize("Bloc-notes")
    _test("T05 — Minimiser Bloc-notes",
          min_result.get("success", False),
          min_result.get("message", ""))
    _pause(2)

    # ------------------------------------------------------------------ #
    #  TEST 5 : Maximiser la fenêtre
    # ------------------------------------------------------------------ #
    print("\n--- TEST 5 : Maximiser le Bloc-notes ---")
    max_result = window_maximize("Notepad")
    if not max_result.get("success"):
        max_result = window_maximize("Bloc-notes")
    _test("T06 — Maximiser Bloc-notes",
          max_result.get("success", False),
          max_result.get("message", ""))
    _pause(2)

    # ------------------------------------------------------------------ #
    #  TEST 6 : Lister les fenêtres
    # ------------------------------------------------------------------ #
    print("\n--- TEST 6 : Lister les fenêtres actives ---")
    list_result = window_list()
    count = list_result.get("count", 0)
    _test("T07 — Lister fenêtres",
          list_result.get("success", False) and count > 0,
          f"{count} fenêtres visibles")

    # ------------------------------------------------------------------ #
    #  TEST 7 : Fenêtre active
    # ------------------------------------------------------------------ #
    print("\n--- TEST 7 : Info fenêtre active ---")
    active_result = window_get_active()
    _test("T08 — Fenêtre active détectée",
          active_result.get("success", False),
          f"Titre: {active_result.get('title', '?')}")

    # ------------------------------------------------------------------ #
    #  TEST 8 : Snap fenêtre à gauche
    # ------------------------------------------------------------------ #
    print("\n--- TEST 8 : Snap Bloc-notes à gauche ---")
    snap_result = window_snap("Notepad", "left")
    if not snap_result.get("success"):
        snap_result = window_snap("Bloc-notes", "left")
    _test("T09 — Snap gauche",
          snap_result.get("success", False),
          snap_result.get("message", ""))
    _pause(2)

    # ------------------------------------------------------------------ #
    #  TEST 9 : Fermer le Bloc-notes (sans sauvegarder)
    # ------------------------------------------------------------------ #
    print("\n--- TEST 9 : Fermer le Bloc-notes ---")
    close_result = window_close("Notepad")
    if not close_result.get("success"):
        close_result = window_close("Bloc-notes")
    _test("T10 — Fermer Bloc-notes",
          close_result.get("success", False),
          close_result.get("message", ""))
    _pause(2)
    # Gérer le popup "Voulez-vous enregistrer ?" en appuyant sur "Ne pas enregistrer"
    # Sur Windows FR c'est Alt+N ou Tab+Enter
    try:
        import pyautogui
        # Tenter de fermer le dialogue de sauvegarde s'il apparaît
        _pause(1)
        dialog = window_find("Bloc-notes")
        if not dialog.get("success"):
            dialog = window_find("Notepad")
        if dialog.get("success") and dialog.get("count", 0) > 0:
            pyautogui.hotkey("alt", "n")  # "Ne pas enregistrer" en français
            _pause(0.5)
            # Fallback anglais
            still_there = window_find("Notepad")
            if still_there.get("success") and still_there.get("count", 0) > 0:
                pyautogui.hotkey("alt", "d")  # "Don't Save" en anglais
                _pause(0.5)
    except Exception:
        pass

    # Vérifier que la fenêtre est bien fermée
    _pause(1)
    verify_close = window_find("Notepad")
    notepad_gone = not verify_close.get("success") or verify_close.get("count", 0) == 0
    if not notepad_gone:
        verify_close = window_find("Bloc-notes")
        notepad_gone = not verify_close.get("success") or verify_close.get("count", 0) == 0
    _test("T11 — Bloc-notes bien fermé",
          notepad_gone,
          "Fenêtre disparue" if notepad_gone else "Encore visible!")

    # ------------------------------------------------------------------ #
    #  TEST 10 : Pipeline complet — "Ouvre le bloc-notes" via classifier
    # ------------------------------------------------------------------ #
    print("\n--- TEST 10 : Pipeline complet Classifier→Validator→Execute ---")
    pipeline_result = run_pipeline("Ouvre le bloc-notes")
    _test("T12 — Pipeline: 'Ouvre le bloc-notes'",
          pipeline_result.get("status") == "success",
          f"tool={pipeline_result.get('tool')} → {pipeline_result.get('result', {}).get('message', '')}")
    _pause(3)

    # Vérifier
    find2 = window_find("Notepad")
    if not find2.get("success"):
        find2 = window_find("Bloc-notes")
    _test("T13 — Pipeline: Bloc-notes ouvert confirmé",
          find2.get("success", False) and find2.get("count", 0) > 0,
          f"Fenêtres: {find2.get('count', 0)}")

    # Nettoyer : fermer le bloc-notes
    window_close("Notepad")
    _pause(1)
    window_close("Bloc-notes")
    _pause(1)
    try:
        import pyautogui
        pyautogui.hotkey("alt", "n")
        _pause(0.5)
        pyautogui.hotkey("alt", "d")
    except Exception:
        pass

    # ------------------------------------------------------------------ #
    #  TEST 11 : Pipeline — "Cherche la météo"
    # ------------------------------------------------------------------ #
    print("\n--- TEST 11 : Pipeline — Recherche web ---")
    search_result = run_pipeline("Cherche la météo à Paris")
    search_ok = search_result.get("status") == "success"
    search_msg = ""
    if search_ok:
        res = search_result.get("result", {})
        if isinstance(res, dict):
            results_list = res.get("results", [])
            search_msg = f"{len(results_list)} résultats" if results_list else res.get("message", "")
        else:
            search_msg = str(res)[:100]
    else:
        search_msg = search_result.get("message", "erreur")
    _test("T14 — Pipeline: 'Cherche la météo'",
          search_result.get("tool") == "web_search",
          f"tool={search_result.get('tool')} → {search_msg}")

    # ------------------------------------------------------------------ #
    #  TEST 12 : Lancer la calculatrice (UWP)
    # ------------------------------------------------------------------ #
    print("\n--- TEST 12 : Lancer la Calculatrice (UWP) ---")
    calc_result = launch_app(name="calculator")
    _test("T15 — Lancer Calculatrice",
          calc_result.get("success", False),
          calc_result.get("message", ""))
    _pause(3)

    # Fermer la calculatrice
    calc_close = window_close("Calculatrice")
    if not calc_close.get("success"):
        calc_close = window_close("Calculator")
    _pause(1)
    _test("T16 — Fermer Calculatrice",
          calc_close.get("success", False),
          calc_close.get("message", ""))

    # ================================================================== #
    #  RÉSUMÉ
    # ================================================================== #
    print()
    print("=" * 70)
    total = PASS + FAIL
    pct = (PASS / total * 100) if total > 0 else 0
    print(f"  RÉSULTAT RÉEL : {PASS}/{total} ({pct:.0f}%)")

    failed = [r for r in RESULTS if r["status"] == "FAIL"]
    if failed:
        print(f"\n  Échecs ({len(failed)}) :")
        for f in failed:
            print(f"    - {f['name']}: {f['details']}")

    if pct >= 80:
        print(f"\n  \U0001f3af SUCCÈS — Atlas fonctionne réellement sur ce PC")
    else:
        print(f"\n  \u26a0\ufe0f  Certains tests ont échoué — voir les détails ci-dessus")
    print("=" * 70)


if __name__ == "__main__":
    run_all_tests()
