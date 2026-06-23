from pathlib import Path


def test_build_reorg_plan_groups_files(tmp_path):
    from core.file_organizer import build_reorg_plan

    root = tmp_path / "workspace"
    root.mkdir(parents=True)
    (root / "a.txt").write_text("x", encoding="utf-8")
    (root / "b.png").write_text("x", encoding="utf-8")
    (root / "c.py").write_text("x", encoding="utf-8")

    plan = build_reorg_plan(str(root), max_ops=20)
    assert plan["success"] is True
    assert len(plan["operations"]) == 3
    cats = {op["category"] for op in plan["operations"]}
    assert {"documents", "images", "code"}.issubset(cats)


def test_apply_reorg_plan_moves_files(tmp_path):
    from core.file_organizer import build_reorg_plan, apply_reorg_plan

    root = tmp_path / "workspace"
    root.mkdir(parents=True)
    src = root / "notes.txt"
    src.write_text("x", encoding="utf-8")

    plan = build_reorg_plan(str(root), max_ops=10)
    result = apply_reorg_plan(plan, max_apply=10)

    assert result["moved"] == 1
    assert result.get("operation_id")
    assert (root / "documents" / "notes.txt").exists()
    assert not src.exists()


def test_rollback_reorg_restores_files(tmp_path, monkeypatch):
    import core.file_organizer as org

    history = tmp_path / "history.jsonl"
    monkeypatch.setattr(org, "HISTORY_FILE", history)
    monkeypatch.setattr(org, "DATA_DIR", tmp_path)

    root = tmp_path / "workspace"
    root.mkdir(parents=True)
    src = root / "notes.txt"
    src.write_text("x", encoding="utf-8")

    plan = org.build_reorg_plan(str(root), max_ops=10)
    applied = org.apply_reorg_plan(plan, max_apply=10)
    op_id = applied["operation_id"]

    rolled = org.rollback_reorg(op_id, max_restore=10)
    assert rolled["success"] is True
    assert rolled["restored"] == 1
    assert src.exists()
