import json
import httpx

payload = {
    "message": "Réponds UNIQUEMENT avec ce JSON exact: {\"action\":\"web_search\",\"params\":{\"query\":\"météo Paris\",\"max_results\":3},\"confirmation_required\":false,\"reason\":\"test\"}",
    "history": [],
}

with httpx.Client(timeout=120.0) as client:
    resp = client.post("http://127.0.0.1:8550/api/chat", json=payload)
    resp.raise_for_status()
    data = resp.json()

print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
