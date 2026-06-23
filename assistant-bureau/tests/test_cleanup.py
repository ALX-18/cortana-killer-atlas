"""Test rapide du nettoyage JSON dans process_ai_response."""
import asyncio
import sys
sys.path.insert(0, '.')

from core.intent_engine import process_ai_response

async def main():
    # Test 1: JSON avec accolades imbriquées
    text1 = '{"action": "window_get_active", "params": {}} Voilà ce que je vois'
    r1 = await process_ai_response(text1, {})
    print("Test 1 - message:", repr(r1.get("message")))

    # Test 2: JSON suivi de texte avec retour à la ligne
    text2 = '{"action": "launch_app", "params": {"app_name": "steam"}}\n\nJe lance Steam pour toi.'
    r2 = await process_ai_response(text2, {})
    print("Test 2 - message:", repr(r2.get("message")))

    # Test 3: JSON seul (pas de texte)
    text3 = '{"action": "window_get_active", "params": {}}'
    r3 = await process_ai_response(text3, {})
    print("Test 3 - message:", repr(r3.get("message")))

    # Test 4: Multi-JSON
    text4 = '{"action": "window_get_active", "params": {}}{"action": "launch_app", "params": {"app_name": "steam"}}'
    r4 = await process_ai_response(text4, {})
    print("Test 4 - message:", repr(r4.get("message")))

asyncio.run(main())
