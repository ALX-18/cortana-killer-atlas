import requests
r = requests.get("http://localhost:8888/search", params={"q": "test python", "format": "json"}, timeout=10)
print("Status:", r.status_code)
if r.status_code == 200:
    data = r.json()
    results = data.get("results", [])
    print(f"Results: {len(results)}")
    for x in results[:3]:
        print(f"  - {x['title'][:60]}")
else:
    print("Error:", r.text[:300])
