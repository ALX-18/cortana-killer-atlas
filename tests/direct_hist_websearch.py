import asyncio
import os
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

from tools.web_search import search

async def main():
    results = await search("dates importantes Révolution française", max_results=5)
    print("count=", len(results))
    if results:
        print("first_title=", results[0].get("title"))
        print("first_source=", results[0].get("source"))

if __name__ == "__main__":
    asyncio.run(main())
