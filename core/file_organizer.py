"""
File Organizer — safe file reorganization planner.

Default flow is plan/simulate first.
Apply is explicit and bounded.
"""

from __future__ import annotations

import json
import time
import uuid
import pathlib
import shutil
from typing import Any

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
HISTORY_FILE = DATA_DIR / "file_reorg_history.jsonl"

CATEGORY_DIRS = {
    "images": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"},
    "documents": {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt"},
    "spreadsheets": {".xls", ".xlsx", ".csv"},
    "archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "code": {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cpp", ".c", ".cs", ".go", ".rs"},
    "media": {".mp3", ".wav", ".flac", ".mp4", ".mkv", ".mov", ".avi"},
}


def _category_for(ext: str) -> str:
    low = ext.lower()
    for name, exts in CATEGORY_DIRS.items():
        if low in exts:
            return name
    return "other"


def build_reorg_plan(root_dir: str, max_ops: int = 300) -> dict[str, Any]:
    root = pathlib.Path(root_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        return {"success": False, "message": f"Root invalide: {root}", "operations": []}

    operations = []
    for p in root.iterdir():
        if not p.is_file():
            continue
        category = _category_for(p.suffix)
        target_dir = root / category
        target_path = target_dir / p.name
        if p.parent == target_dir:
            continue
        operations.append(
            {
                "src": str(p),
                "dst": str(target_path),
                "category": category,
            }
        )
        if len(operations) >= max_ops:
            break

    return {
        "success": True,
        "message": f"Plan genere: {len(operations)} operation(s)",
        "root": str(root),
        "operations": operations,
    }


def apply_reorg_plan(plan: dict[str, Any], max_apply: int = 300) -> dict[str, Any]:
    ops = plan.get("operations", [])
    if not isinstance(ops, list):
        return {"success": False, "message": "Plan invalide", "moved": 0}

    moved = 0
    errors: list[str] = []
    moved_entries: list[dict[str, str]] = []

    for op in ops[:max_apply]:
        src = pathlib.Path(op["src"])
        dst = pathlib.Path(op["dst"])
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists() and src.is_file():
                shutil.move(str(src), str(dst))
                moved += 1
                moved_entries.append({"src": str(src), "dst": str(dst)})
        except Exception as e:
            errors.append(f"{src} -> {dst}: {e}")

    operation_id = _save_history(plan=plan, moved_entries=moved_entries, errors=errors)

    return {
        "success": len(errors) == 0,
        "message": f"Reorganisation appliquee: {moved} deplace(s), {len(errors)} erreur(s)",
        "moved": moved,
        "errors": errors,
        "operation_id": operation_id,
    }


def rollback_reorg(operation_id: str, max_restore: int = 300) -> dict[str, Any]:
    entry = _find_history_entry(operation_id)
    if not entry:
        return {"success": False, "message": f"Operation introuvable: {operation_id}", "restored": 0, "errors": []}

    moved_entries = entry.get("moved_entries", [])
    restored = 0
    errors: list[str] = []

    # Reverse order to restore safely.
    for item in list(reversed(moved_entries))[:max_restore]:
        src = pathlib.Path(item.get("src", ""))
        dst = pathlib.Path(item.get("dst", ""))
        try:
            if dst.exists() and dst.is_file():
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
                restored += 1
        except Exception as e:
            errors.append(f"{dst} -> {src}: {e}")

    return {
        "success": len(errors) == 0,
        "message": f"Rollback termine: {restored} restaure(s), {len(errors)} erreur(s)",
        "restored": restored,
        "errors": errors,
        "operation_id": operation_id,
    }


def _save_history(plan: dict[str, Any], moved_entries: list[dict[str, str]], errors: list[str]) -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    op_id = str(uuid.uuid4())[:8]
    row = {
        "operation_id": op_id,
        "timestamp": int(time.time()),
        "plan_root": plan.get("root"),
        "moved_entries": moved_entries,
        "errors": errors,
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return op_id


def _find_history_entry(operation_id: str) -> dict | None:
    if not HISTORY_FILE.exists():
        return None
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("operation_id") == operation_id:
                return row
    return None
