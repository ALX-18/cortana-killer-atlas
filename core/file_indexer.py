"""
File Indexer — passive local indexing when Atlas is running.

Purpose:
- Build a lightweight file map so Atlas can resolve user targets more precisely.
- Run only when enabled in config and with conservative limits.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import time
from typing import Any

logger = logging.getLogger("atlas.file_indexer")

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
INDEX_FILE = DATA_DIR / "file_index.json"
CONFIG_FILE = pathlib.Path(__file__).resolve().parent.parent / "config" / "settings.json"


class FileIndexer:
    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None
        self._index: dict[str, Any] = {
            "generated_at": None,
            "count": 0,
            "files": [],
            "roots": [],
        }
        self._cfg = self._load_cfg()
        self._load_index_from_disk()

    @staticmethod
    def _load_cfg() -> dict:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("filesystem_assistant", {})

    def enabled(self) -> bool:
        return bool(self._cfg.get("enabled", False))

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled(),
            "running": self._running,
            "generated_at": self._index.get("generated_at"),
            "count": self._index.get("count", 0),
            "roots": self._index.get("roots", []),
        }

    async def start(self):
        if self._running or not self.enabled():
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("📂 FileIndexer started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("📂 FileIndexer stopped")

    async def run_once(self) -> dict[str, Any]:
        idx = await asyncio.to_thread(self._scan_files)
        self._index = idx
        self._save_index_to_disk()
        return self.status()

    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        q = (query or "").strip().lower()
        if not q:
            return []
        files = self._index.get("files", [])
        matches = [f for f in files if q in f.get("name", "").lower() or q in f.get("path", "").lower()]
        return matches[: max(1, min(limit, 200))]

    async def _loop(self):
        interval = int(self._cfg.get("scan_interval_seconds", 600))
        while self._running:
            try:
                await self.run_once()
            except Exception as e:
                logger.warning("FileIndexer scan failed: %s", e)
            await asyncio.sleep(max(60, interval))

    def _scan_files(self) -> dict[str, Any]:
        roots = self._resolve_roots(self._cfg.get("scan_roots", []))
        excluded = [str(pathlib.Path(p).expanduser()).lower() for p in self._cfg.get("exclude_dirs", [])]
        max_files = int(self._cfg.get("max_files_per_scan", 10000))

        files = []
        for root in roots:
            root_path = pathlib.Path(root)
            if not root_path.exists():
                continue

            for dirpath, dirnames, filenames in os.walk(root):
                dlow = dirpath.lower()
                if any(ex in dlow for ex in excluded):
                    continue
                for filename in filenames:
                    full = pathlib.Path(dirpath) / filename
                    try:
                        stat = full.stat()
                    except Exception:
                        continue
                    files.append(
                        {
                            "name": filename,
                            "path": str(full),
                            "ext": full.suffix.lower(),
                            "size": stat.st_size,
                            "mtime": int(stat.st_mtime),
                        }
                    )
                    if len(files) >= max_files:
                        break
                if len(files) >= max_files:
                    break
            if len(files) >= max_files:
                break

        return {
            "generated_at": int(time.time()),
            "count": len(files),
            "files": files,
            "roots": roots,
        }

    @staticmethod
    def _resolve_roots(raw_roots: list[str]) -> list[str]:
        roots = []
        for r in raw_roots:
            p = os.path.expandvars(r)
            p = os.path.expanduser(p)
            roots.append(str(pathlib.Path(p)))
        return roots

    def _save_index_to_disk(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False)

    def _load_index_from_disk(self):
        if not INDEX_FILE.exists():
            return
        try:
            with open(INDEX_FILE, encoding="utf-8") as f:
                self._index = json.load(f)
        except Exception:
            pass


_indexer: FileIndexer | None = None


def get_file_indexer() -> FileIndexer:
    global _indexer
    if _indexer is None:
        _indexer = FileIndexer()
    return _indexer
