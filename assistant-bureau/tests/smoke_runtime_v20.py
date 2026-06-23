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
    context = collect_context()

    r1 = await process_ai_response(
        '{"action":"web_search","params":{"query":"météo Paris","max_results":3}}',
        context,
    )
    print("web_search:", r1["tool_results"][0]["status"])

    r2 = await process_ai_response(
        '{"action":"read_url","params":{"url":"https://example.com"}}',
        context,
    )
    print("read_url:", r2["tool_results"][0]["status"])

    r3 = await process_ai_response(
        '{"action":"browser_open","params":{"url":"https://youtube.com"}}',
        context,
    )
    tr = r3["tool_results"][0]
    print("browser_open:", tr["status"], "confirmation_id=", tr.get("confirmation_id"))


if __name__ == "__main__":
    asyncio.run(main())
