"""Test SQLite habit persistence across simulated restarts."""
import sqlite3
import os
import sys

os.chdir(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.getcwd())

from core.context_monitor import _init_db, _persist_habit, _DB_PATH
import core.context_monitor as cm

# Init and persist a test habit
_init_db()
_persist_habit("test_persist.exe", 4)
print(f"1. Persisted: count={cm._process_session_counts.get('test_persist.exe', 'N/A')}")

# Simulate restart: clear RAM
cm._process_session_counts.clear()
cm._db_initialized = False
print(f"2. After clearing RAM: count={cm._process_session_counts.get('test_persist.exe', 'N/A')}")

# Re-init (like after restart)
cm._init_db()
reloaded = cm._process_session_counts.get("test_persist.exe", "N/A")
print(f"3. After re-loading from SQLite: count={reloaded}")

assert reloaded == 4, f"Expected 4, got {reloaded}"
print("PASS: Habits survived simulated restart!")

# Cleanup
conn = sqlite3.connect(str(_DB_PATH))
conn.execute("DELETE FROM process_habits WHERE process_name = 'test_persist.exe'")
conn.commit()
conn.close()
print("Cleanup done.")
