"""Quick parser debug for code-block wrapped sequences."""
import json
import sys
sys.path.insert(0, ".")

from core.intent_engine import parse_model_response

# Test 1: Pure JSON sequence (no code block)
raw1 = '''{"sequence": [{"action": "launch_app", "params": {"name": "Steam"}, "confirmation_required": false, "reason": "test", "wait_for_completion": true}], "description": "test"}'''
r1 = parse_model_response(raw1)
print("Test 1 (pure JSON):", type(r1).__name__, "is_list:", isinstance(r1, list))

# Test 2: Code block wrapped sequence
raw2 = '```json\n{"sequence": [{"action": "launch_app", "params": {"name": "Steam"}, "confirmation_required": false, "reason": "test", "wait_for_completion": true}], "description": "test"}\n```'
r2 = parse_model_response(raw2)
print("Test 2 (code block):", type(r2).__name__, "is_list:", isinstance(r2, list))

# Test 3: Code block with leading space (like LLM output)
raw3 = ' ```json\n{"sequence": [{"action": "launch_app", "params": {"name": "Steam"}, "confirmation_required": false, "reason": "test", "wait_for_completion": true}], "description": "test"}\n```'
r3 = parse_model_response(raw3)
print("Test 3 (space + code):", type(r3).__name__, "is_list:", isinstance(r3, list))

# Test 4: Multi-line with nested objects
raw4 = '''```json
{
  "sequence": [
    {
      "action": "launch_app",
      "params": {"name": "Steam"},
      "confirmation_required": false,
      "reason": "Lancer Steam",
      "wait_for_completion": true
    },
    {
      "action": "launch_app",
      "params": {"name": "Helldivers"},
      "confirmation_required": false,
      "reason": "Lancer Helldivers",
      "wait_for_completion": false
    }
  ],
  "description": "Steam puis Helldivers"
}
```'''
r4 = parse_model_response(raw4)
print("Test 4 (multi-line nested):", type(r4).__name__, "is_list:", isinstance(r4, list))
if isinstance(r4, list):
    print("  Steps:", len(r4))
    for i, s in enumerate(r4):
        print(f"  Step {i+1}: {s.get('tool')}")
elif isinstance(r4, str):
    print("  TEXT (first 100):", repr(r4[:100]))

# Test 5: Text before code block
raw5 = '''Voici les actions à effectuer :

```json
{
  "sequence": [
    {"action": "launch_app", "params": {"name": "Steam"}, "confirmation_required": false, "reason": "Lancer Steam", "wait_for_completion": true},
    {"action": "launch_app", "params": {"name": "Helldivers"}, "confirmation_required": false, "reason": "Lancer Helldivers", "wait_for_completion": false}
  ],
  "description": "Steam puis Helldivers"
}
```'''
r5 = parse_model_response(raw5)
print("Test 5 (text + code):", type(r5).__name__, "is_list:", isinstance(r5, list))
