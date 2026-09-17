import json
import httpx

payload = {
    "message": "Réponds UNIQUEMENT avec ce JSON exact: {\"action\":\"read_url\",\"params\":{\"url\":\"https://example.com\"},\"confirmation_required\":false,\"reason\":\"test read url\"}",
    "history": [],
}

with httpx.Client(timeout=180.0) as client:
    resp = client.post("http://127.0.0.1:8550/api/chat", json=payload)
    resp.raise_for_status()
    data = resp.json()

tool = data["tool_results"][0]
res = tool.get("result", {})
print(json.dumps({
    "status": tool.get("status"),
    "tool": tool.get("tool"),
    "success": res.get("success"),
    "has_title": bool(res.get("title")),
    "has_summary": bool(res.get("summary")),
}, ensure_ascii=False, indent=2))
