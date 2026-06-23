"""Capture raw LLM response for test 2 to debug parser."""
import json
import httpx

API = "http://127.0.0.1:8550/api"

prompt = "Lance Firefox, ouvre YouTube puis lance une vidéo sur l'espace."

with httpx.Client(timeout=120.0) as client:
    resp = client.post(f"{API}/chat", json={"message": prompt, "history": []})
    data = resp.json()

    print("TYPE:", data.get("type"))
    msg = data.get("message") or ""
    print("MESSAGE RAW (repr):")
    print(repr(msg[:500]))
    print()
    print("TOOLS:", json.dumps(data.get("tool_results", []), indent=2, ensure_ascii=False)[:500])

    # Now test the parser directly
    from core.intent_engine import parse_model_response
    result = parse_model_response(msg)
    print()
    print("PARSER RESULT TYPE:", type(result).__name__)
    if isinstance(result, list):
        print("SEQUENCE LENGTH:", len(result))
        for i, s in enumerate(result):
            print(f"  Step {i+1}: {s.get('tool')}")
    elif isinstance(result, str):
        print("PARSED AS TEXT (first 200):", repr(result[:200]))
