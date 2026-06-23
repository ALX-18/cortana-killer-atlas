"""Test rapide via l'API /api/chat pour verifier le nettoyage."""
import requests
import json

url = "http://localhost:8550/api/chat"

tests = [
    "tu vois quoi sur mon ecran ?",
    "ouvre steam",
]

for prompt in tests:
    print(f"\n{'='*60}")
    print(f"PROMPT: {prompt}")
    print('='*60)
    r = requests.post(url, json={"message": prompt, "history": []}, timeout=60)
    data = r.json()
    print(f"Type: {data.get('type')}")
    print(f"Message: {data.get('message')!r}")
    if data.get('tool_results'):
        for tr in data['tool_results']:
            print(f"  Tool: {tr.get('tool')} -> status={tr.get('status')}")
            if tr.get('result'):
                print(f"  Result: {tr['result'].get('message', '')[:100]}")
