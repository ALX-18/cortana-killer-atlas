import json
import httpx

payload = {
    "message": "Réponds UNIQUEMENT avec ce JSON exact: {\"action\":\"web_search\",\"params\":{\"query\":\"météo Paris\",\"max_results\":3},\"confirmation_required\":false,\"reason\":\"test web search\"}",
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
    "result_count": len(tool.get("result", [])),
    "source": (tool.get("result", [{}])[0].get("source") if tool.get("result") else None),
}, ensure_ascii=False, indent=2))
