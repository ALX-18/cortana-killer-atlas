import asyncio
from pathlib import Path


def test_file_indexer_run_once_and_search(tmp_path, monkeypatch):
    import core.file_indexer as fi

    root = tmp_path / "data"
    root.mkdir(parents=True, exist_ok=True)
    (root / "rapport_atlas.txt").write_text("hello", encoding="utf-8")
    (root / "notes.md").write_text("hi", encoding="utf-8")

    idx = fi.FileIndexer()
    idx._cfg = {
        "enabled": True,
        "scan_interval_seconds": 600,
        "max_files_per_scan": 100,
        "scan_roots": [str(root)],
        "exclude_dirs": [],
    }

    status = asyncio.run(idx.run_once())
    assert status["count"] >= 2

    results = asyncio.run(idx.search("atlas", limit=10))
    assert any("rapport_atlas.txt" in r["name"] for r in results)


def test_file_indexer_status_keys():
    import core.file_indexer as fi

    idx = fi.FileIndexer()
    s = idx.status()
    assert "enabled" in s
    assert "running" in s
    assert "count" in s
