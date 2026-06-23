import asyncio
import os
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

from core.context_monitor import collect_context
from core.intent_engine import process_ai_response


async def main():
    ctx = collect_context()

    web = await process_ai_response(
        '{"action":"web_search","params":{"query":"météo Paris","max_results":3}}',
        ctx,
    )
    t1 = web["tool_results"][0]
    print("web_search_status=", t1.get("status"), "count=", len(t1.get("result", [])))

    read = await process_ai_response(
        '{"action":"read_url","params":{"url":"https://example.com"}}',
        ctx,
    )
    t2 = read["tool_results"][0]
    r2 = t2.get("result", {}) if isinstance(t2.get("result"), dict) else {}
    print("read_url_status=", t2.get("status"), "success=", r2.get("success"), "has_summary=", bool(r2.get("summary")))


if __name__ == "__main__":
    asyncio.run(main())
