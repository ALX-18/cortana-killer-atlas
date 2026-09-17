import json
import sys
import httpx

API = "http://127.0.0.1:8550/api"

if len(sys.argv) < 2:
    print("Usage: python tests/run_one_prompt.py \"prompt\"")
    raise SystemExit(1)

prompt = " ".join(sys.argv[1:])
payload = {"message": prompt, "history": []}

with httpx.Client(timeout=240.0) as client:
    resp = client.post(f"{API}/chat", json=payload)
    resp.raise_for_status()
    data = resp.json()

print(json.dumps({
    "prompt": prompt,
    "type": data.get("type"),
    "message": (data.get("message")[:300] if isinstance(data.get("message"), str) else data.get("message")),
    "tool_results": data.get("tool_results", []),
}, ensure_ascii=False, indent=2)[:6000])

trs = data.get("tool_results", [])
if trs and trs[0].get("status") == "confirmation_required" and trs[0].get("confirmation_id"):
    with httpx.Client(timeout=180.0) as client:
        c = client.post(f"{API}/confirm", json={"confirmation_id": trs[0]["confirmation_id"], "accepted": True})
        c.raise_for_status()
        print("\nCONFIRM:")
        print(json.dumps(c.json(), ensure_ascii=False, indent=2)[:3000])
