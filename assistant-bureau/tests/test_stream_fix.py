"""Test rapide du fix streaming JSON."""
import requests
import json

STREAM_API = "http://localhost:8550/api/chat/stream"

tests = [
    ("Ouvre steam", "Action tool-call"),
    ("Salut ca va ?", "Texte simple"),
    ("Cherche Python sur internet", "Recherche web"),
]

for prompt, label in tests:
    print(f"\n{'='*60}")
    print(f"[{label}] {prompt}")
    print('='*60)
    
    r = requests.post(STREAM_API, json={"message": prompt, "history": []}, timeout=90, stream=True)
    
    events = []
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data = line[6:].strip()
        if data == "[DONE]":
            break
        try:
            parsed = json.loads(data)
            events.append(parsed)
            etype = parsed.get("type", "?")
            content = parsed.get("content", "")
            if etype == "token":
                pass  # Don't print each token
            elif etype == "thinking":
                print(f"  [THINKING] {content}")
            elif etype == "result":
                msg = content.get("message", "") if isinstance(content, dict) else str(content)
                print(f"  [RESULT] message={msg[:120]!r}")
            elif etype == "step":
                print(f"  [STEP] {content}")
            else:
                print(f"  [{etype}] {str(content)[:100]}")
        except:
            pass
    
    # Analyse
    token_events = [e for e in events if e.get("type") == "token"]
    thinking_events = [e for e in events if e.get("type") == "thinking"]
    result_events = [e for e in events if e.get("type") == "result"]
    
    tokens_text = "".join(e.get("content", "") for e in token_events)
    json_in_tokens = '{"action"' in tokens_text or '{"sequence"' in tokens_text
    
    if json_in_tokens:
        print(f"  ❌ JSON BRUT DANS LES TOKENS: {tokens_text[:100]!r}")
    elif thinking_events:
        print(f"  ✅ JSON masqué, indicateur thinking envoyé")
    elif token_events:
        print(f"  ✅ Tokens texte normaux ({len(token_events)} tokens)")
    
    if result_events:
        print(f"  ✅ Event result reçu")
