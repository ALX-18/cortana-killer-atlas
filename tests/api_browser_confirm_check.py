import json
import httpx

payload = {
    "message": "Réponds UNIQUEMENT avec ce JSON exact: {\"action\":\"browser_open\",\"params\":{\"url\":\"https://youtube.com\"},\"confirmation_required\":true,\"reason\":\"test browser confirm\"}",
    "history": [],
}

with httpx.Client(timeout=120.0) as client:
    resp = client.post("http://127.0.0.1:8550/api/chat", json=payload)
    resp.raise_for_status()
    data = resp.json()

tool = data["tool_results"][0]
print(json.dumps({
    "status": tool.get("status"),
    "tool": tool.get("tool"),
    "has_confirmation_id": bool(tool.get("confirmation_id")),
    "reason": tool.get("reason"),
}, ensure_ascii=False, indent=2))
