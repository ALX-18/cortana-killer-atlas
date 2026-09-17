import json
import httpx

API = "http://127.0.0.1:8550/api"

SCENARIOS = [
    {
        "id": 1,
        "name": "Steam + WorldBox",
        "prompt": "Lance Steam puis lance WorldBox sur la plateforme Steam.",
    },
    {
        "id": 2,
        "name": "Firefox + YouTube + vidéo",
        "prompt": "Lance Firefox, ouvre YouTube puis lance une vidéo sur l'espace.",
    },
    {
        "id": 3,
        "name": "Question historique web",
        "prompt": "Donne-moi des dates historiques importantes de la Révolution française avec sources web.",
    },
    {
        "id": 4,
        "name": "Systèmes/processus en cours",
        "prompt": "Quels systèmes et processus tournent actuellement sur le PC ?",
    },
    {
        "id": 5,
        "name": "Test libre style utilisateur",
        "prompt": "Cherche les 3 dernières avancées majeures en IA en 2025 et résume-les en français.",
    },
]


def compact_tool_result(tr: dict) -> dict:
    out = {
        "tool": tr.get("tool"),
        "status": tr.get("status"),
    }
    if tr.get("status") == "confirmation_required":
        out["reason"] = tr.get("reason")
        out["confirmation_id"] = tr.get("confirmation_id")
    if tr.get("status") == "success":
        res = tr.get("result")
        if isinstance(res, dict):
            out["result_message"] = res.get("message")
            if "success" in res:
                out["result_success"] = res.get("success")
            if "url" in res:
                out["url"] = res.get("url")
            if "summary" in res:
                out["has_summary"] = bool(res.get("summary"))
        elif isinstance(res, list):
            out["result_count"] = len(res)
            if res and isinstance(res[0], dict):
                out["first_source"] = res[0].get("source")
                out["first_title"] = res[0].get("title")
    if tr.get("status") == "error":
        out["error"] = tr.get("message")
    return out


def run():
    history = []
    with httpx.Client(timeout=240.0) as client:
        for s in SCENARIOS:
            payload = {"message": s["prompt"], "history": history[-20:]}
            resp = client.post(f"{API}/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

            print("\n" + "=" * 80)
            print(f"TEST {s['id']} — {s['name']}")
            print("PROMPT:", s["prompt"])
            print("TYPE:", data.get("type"))
            msg = data.get("message")
            if msg:
                print("MESSAGE:", (msg[:280] + "...") if len(msg) > 280 else msg)

            tool_results = data.get("tool_results", [])
            if not tool_results:
                print("TOOLS: none")
            else:
                print("TOOLS:")
                for tr in tool_results:
                    print(json.dumps(compact_tool_result(tr), ensure_ascii=False, indent=2))

                # Auto-confirm if needed, then print confirm execution result
                first = tool_results[0]
                if first.get("status") == "confirmation_required" and first.get("confirmation_id"):
                    confirm_payload = {
                        "confirmation_id": first["confirmation_id"],
                        "accepted": True,
                    }
                    c = client.post(f"{API}/confirm", json=confirm_payload)
                    c.raise_for_status()
                    cdata = c.json()
                    print("CONFIRM_RESULT:")
                    print(json.dumps(cdata, ensure_ascii=False, indent=2)[:1000])

            # update history
            history.append({"role": "user", "content": s["prompt"]})
            assistant_text = data.get("message") or ""
            history.append({"role": "assistant", "content": assistant_text})


if __name__ == "__main__":
    run()
