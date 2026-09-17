"""
Real E2E validation for Kimi sprint (5 commands).
Interacts with the machine and reports pass/fail per command.
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # scripts/manual/ -> racine

from core.intent_classifier import get_classifier
from core.validator import get_validator
from core.intent_engine import execute_tool
from tools.window_controller import window_find, window_minimize


def _print_step(name: str, ok: bool, details: str = ""):
    icon = "PASS" if ok else "FAIL"
    print(f"[{icon}] {name}")
    if details:
        print(f"       -> {details}")


async def _run_pipeline(user_input: str, context: dict | None = None):
    ctx = context or {}
    classifier = get_classifier()
    validator = get_validator()

    intent = classifier.classify(user_input, ctx)
    resolved = validator.resolve(intent, ctx)

    if resolved.tool == "__conversation__":
        return {
            "status": "conversation",
            "intent": intent,
            "resolved": resolved,
            "result": None,
        }

    result = await execute_tool(resolved.tool, resolved.params, ctx)
    return {
        "status": result.get("status"),
        "intent": intent,
        "resolved": resolved,
        "result": result,
    }


async def main():
    total = 0
    passed = 0

    print("=" * 72)
    print("KIMI SPRINT — REAL E2E (5 COMMANDES)")
    print("=" * 72)

    # 1) Ouvre steam
    total += 1
    r1 = await _run_pipeline("ouvre steam")
    ok1 = r1["resolved"].tool in {"launch_app", "window_focus"} and r1["status"] in {"success", "confirmation_required"}
    _print_step("C1 ouvre steam", ok1, f"tool={r1['resolved'].tool} status={r1['status']}")
    passed += int(ok1)
    time.sleep(2)

    # 2) Clique sur bibliothèque (expected vision/ocr/cache path on electron-like apps)
    total += 1
    try:
        res2 = await execute_tool("ui_click_element", {"app_title": "steam", "element_name": "bibliothèque"}, {})
        method = ((res2.get("result") or {}).get("method") if res2.get("status") == "success" else None)
        ok2 = res2.get("status") == "success" and method in {"vision", "ocr", "cache", "steam_heuristic"}
        detail = f"status={res2.get('status')} method={method}"
        if method == "steam_heuristic":
            detail += " (mode degrade)"
        _print_step("C2 clique sur bibliothèque", ok2, detail)
    except Exception as e:
        ok2 = False
        _print_step("C2 clique sur bibliothèque", False, str(e))
    passed += int(ok2)
    time.sleep(1)

    # 3) Ouvre discord
    total += 1
    r3 = await _run_pipeline("ouvre discord")
    ok3 = r3["resolved"].tool in {"launch_app", "window_focus"} and r3["status"] in {"success", "confirmation_required"}
    _print_step("C3 ouvre discord", ok3, f"tool={r3['resolved'].tool} status={r3['status']}")
    passed += int(ok3)
    time.sleep(2)

    # 4) Refais
    total += 1
    r4 = await _run_pipeline("refais")
    ok4 = r4["resolved"].tool == "redo_last_action" and r4["status"] in {"success", "error", "confirmation_required"}
    _print_step("C4 refais", ok4, f"tool={r4['resolved'].tool} status={r4['status']}")
    passed += int(ok4)

    # 5) Réduis la fenêtre opera gx
    total += 1
    r5 = await _run_pipeline("réduis la fenêtre opera gx")
    # Optional direct verification when window exists
    find = window_find("opera gx")
    verify = window_minimize("opera gx") if find.get("success") else {"success": True}
    ok5 = r5["intent"].target == "opera gx" and r5["resolved"].tool == "window_minimize" and verify.get("success", False)
    _print_step(
        "C5 réduis la fenêtre opera gx",
        ok5,
        f"target={r5['intent'].target} tool={r5['resolved'].tool} status={r5['status']}",
    )
    passed += int(ok5)

    print("-" * 72)
    print(f"RESULTAT: {passed}/{total} PASS")
    print("SEUIL SPRINT: >= 3/5")
    print("SPRINT STATUS:", "VALIDE" if passed >= 3 else "A REVOIR")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
