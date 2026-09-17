"""Quick validation tests for sprint 1.2 changes."""
import json
import os
import sys
import sqlite3
import pathlib

# Ensure we're in the right dir
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

def test_parser():
    from core.intent_engine import parse_model_response
    
    # Test 1: New format
    r = parse_model_response('{"action": "launch_app", "params": {"name": "discord"}, "confirmation_required": false, "reason": "Lancement"}')
    assert isinstance(r, dict) and r["tool"] == "launch_app", f"FAIL new format: {r}"
    print("  Parser test 1 (new format): PASS")
    
    # Test 2: Legacy format
    r = parse_model_response('{"tool": "kill_process", "args": {"name": "chrome"}}')
    assert isinstance(r, dict) and r["tool"] == "kill_process", f"FAIL legacy: {r}"
    print("  Parser test 2 (legacy): PASS")
    
    # Test 3: Plain text
    r = parse_model_response("Bonjour ! Comment puis-je vous aider ?")
    assert isinstance(r, str), f"FAIL text: {r}"
    print("  Parser test 3 (text): PASS")
    
    # Test 4: Malformed JSON
    r = parse_model_response('{"action": "launch_app, broken')
    assert isinstance(r, str), f"FAIL malformed: {r}"
    print("  Parser test 4 (malformed): PASS")
    
    # Test 5: Code block
    r = parse_model_response('Voici:\n```json\n{"action": "get_diagnostics", "params": {}}\n```')
    assert isinstance(r, dict) and r["tool"] == "get_diagnostics", f"FAIL code block: {r}"
    print("  Parser test 5 (code block): PASS")
    
    # Test 6: Unknown action → returns text
    r = parse_model_response('{"action": "hack_pentagon", "params": {}}')
    assert isinstance(r, str), f"FAIL unknown action: {r}"
    print("  Parser test 6 (unknown action): PASS")


def test_powershell_security():
    from tools.system_config import _check_powershell_security
    
    # Allowed
    ok, _ = _check_powershell_security("Get-Process | Select-Object Name, CPU")
    assert ok, "Should allow Get-Process"
    print("  Security test 1 (allow): PASS")
    
    # Denied
    ok, reason = _check_powershell_security("Remove-Item C:\\important -Recurse")
    assert not ok, "Should block Remove-Item"
    print(f"  Security test 2 (deny): PASS — {reason}")
    
    # No allowlist match
    ok, reason = _check_powershell_security("SomeRandomCommand")
    assert not ok, "Should block unknown commands"
    print(f"  Security test 3 (no allowlist): PASS — {reason}")
    
    # Denied takes priority
    ok, reason = _check_powershell_security("Get-Process | Invoke-Expression")
    assert not ok, "Denylist should override allowlist"
    print(f"  Security test 4 (deny priority): PASS — {reason}")


def test_sqlite_habits():
    from core.context_monitor import _init_db, _persist_habit, _DB_PATH
    
    _init_db()
    assert _DB_PATH.exists(), f"DB should exist at {_DB_PATH}"
    print(f"  SQLite test 1 (created): PASS — {_DB_PATH}")
    
    # Insert a test habit
    _persist_habit("test_process.exe", 5)
    
    conn = sqlite3.connect(str(_DB_PATH))
    row = conn.execute("SELECT * FROM process_habits WHERE process_name = 'test_process.exe'").fetchone()
    conn.close()
    
    assert row is not None, "Should find test habit"
    assert row[1] == 5, f"Count should be 5, got {row[1]}"
    print(f"  SQLite test 2 (persist): PASS — count={row[1]}")
    
    # Cleanup test row
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("DELETE FROM process_habits WHERE process_name = 'test_process.exe'")
    conn.commit()
    conn.close()
    print("  SQLite test 3 (cleanup): PASS")


def test_audit_log():
    from tools.system_config import _audit_log, _AUDIT_LOG_PATH
    
    _audit_log("Get-Process TEST", "executed", "test entry")
    assert _AUDIT_LOG_PATH.exists(), f"Audit log should exist at {_AUDIT_LOG_PATH}"
    
    with open(_AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    last = json.loads(lines[-1])
    assert last["command"] == "Get-Process TEST", f"Last entry should be test: {last}"
    assert last["status"] == "executed"
    print(f"  Audit log test: PASS — {len(lines)} entries, path={_AUDIT_LOG_PATH}")


def test_lifespan():
    import main
    assert main.app.version in {"3.0.0", "3.1.0", "4.0.0"}
    # Check no on_event handlers
    assert not hasattr(main, 'on_startup'), "on_startup should not exist"
    print(f"  Lifespan test: PASS — version={main.app.version}")


if __name__ == "__main__":
    # Sprint B-minimal : mêmes redirections que la suite pytest, aucune écriture dans le vrai data/.
    import shutil
    from tests.conftest import _isolate_data

    test_root = _isolate_data()
    print(f"(données de test : {test_root})")
    try:
        print("=== Sprint 1.2 Validation ===\n")
    
        print("[P2.2] Parser tool-calls strict:")
        test_parser()
    
        print("\n[P3] Sécurité PowerShell:")
        test_powershell_security()
    
        print("\n[P2.1] SQLite habits:")
        test_sqlite_habits()
    
        print("\n[P3] Audit log:")
        test_audit_log()
    
        print("\n[P1.2] Lifespan migration:")
        test_lifespan()
    
        print("\n=== ALL TESTS PASSED ===")
    finally:
        shutil.rmtree(test_root, ignore_errors=True)
