import asyncio
import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest


class _DummyVerification:
    def __init__(self, vtype="none", retry_count=0, target=""):
        self.type = vtype
        self.retry_count = retry_count
        self.target = target


class _DummyResolved:
    def __init__(self, tool, params=None, verification=None, intent=None):
        self.tool = tool
        self.params = params or {}
        self.verification = verification or _DummyVerification()
        self.intent = intent


class _DummyResp:
    def __init__(self, status_code=200):
        self.status_code = status_code


class _DummyAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        return _DummyResp(200)


def test_01_mono_instance_second_launch_exits_cleanly(monkeypatch, tmp_path):
    import main
    from main import acquire_instance_lock, release_instance_lock

    # Verrou dans un dossier temporaire : ne jamais toucher data/atlas.lock d'une instance réelle.
    monkeypatch.setattr(main, "LOCK_FILE", tmp_path / "atlas.lock")

    ok1, _ = acquire_instance_lock()
    if not ok1:
        pytest.skip("Atlas already running in this environment; mono-instance lock is expected to be held")
    ok2, msg2 = acquire_instance_lock()
    release_instance_lock()

    assert ok1 is True
    assert ok2 is False
    assert "déjà active" in msg2


def test_02_wait_port_released_after_shutdown(monkeypatch):
    from main import _wait_port_released

    states = iter([False, False, True])

    def _fake_is_port_free(_host, _port):
        try:
            return next(states)
        except StopIteration:
            return True

    monkeypatch.setattr("main._is_port_free", _fake_is_port_free)

    async def _check():
        return await _wait_port_released("127.0.0.1", 8550, timeout_seconds=0.5)

    released = asyncio.run(_check())
    assert released is True


def test_03_window_focus_retry_x3_without_crash(monkeypatch):
    import tools.window_controller as wc

    calls = {"n": 0}

    def _always_fail(_):
        calls["n"] += 1
        raise RuntimeError("focus fail")

    monkeypatch.setattr(wc, "HAS_WIN32", False)
    monkeypatch.setattr(wc, "HAS_PYWINAUTO", False)
    monkeypatch.setattr(wc.gw, "getWindowsWithTitle", _always_fail)

    res = wc.window_focus("Notepad")
    assert res["success"] is False
    assert calls["n"] >= 3


def test_04_idempotent_launch_skip(monkeypatch):
    import core.intent_engine as ie

    engine = ie.ExecutionEngine()
    resolved = _DummyResolved("launch_app", {"name": "notepad"})

    monkeypatch.setattr("tools.app_launcher._is_process_running", lambda _: True)

    async def _execute_tool(*args, **kwargs):
        raise AssertionError("execute_tool should not run for idempotent action")

    monkeypatch.setattr(ie, "execute_tool", _execute_tool)

    result = asyncio.run(engine.execute(resolved, {"user_input": "ouvre notepad"}))
    assert result["status"] == "success"
    assert result.get("idempotent_skip") is True


def test_05_execution_engine_breaks_recursive_replan(monkeypatch):
    import core.intent_engine as ie
    import core.planner as planner_mod

    engine = ie.ExecutionEngine()

    step = SimpleNamespace(
        action="launch_app",
        target="notepad",
        params={"name": "notepad"},
        wait_for_completion=False,
        resolved=_DummyResolved("launch_app", {"name": "notepad"}),
    )
    plan = SimpleNamespace(steps=[step])

    async def _always_error(*args, **kwargs):
        return {"status": "error", "message": "forced failure", "error_code": "ERR_TOOL_EXECUTION_FAILED"}

    class _DummyPlanner:
        async def replan(self, *args, **kwargs):
            return plan

    monkeypatch.setattr(ie, "execute_tool", _always_error)
    monkeypatch.setattr(planner_mod, "get_planner", lambda: _DummyPlanner())

    results = asyncio.run(engine.execute_plan(plan, {"user_input": "test recursion"}))
    assert any(r.get("error_code") in {"ERR_RECURSION_DETECTED", "ERR_REPLAN_LIMIT"} for r in results)


def test_06_api_health_returns_all_services(monkeypatch):
    import api.routes as routes

    monkeypatch.setattr(routes.httpx, "AsyncClient", _DummyAsyncClient)
    monkeypatch.setattr(routes, "get_memory_manager", lambda: SimpleNamespace(is_connected=lambda: True))

    class _Voice:
        _running = False

    monkeypatch.setattr("core.voice_engine.get_voice_engine", lambda: _Voice())

    payload = asyncio.run(routes.api_health())
    assert "services" in payload
    assert set(payload["services"].keys()) == {"ollama", "chromadb", "searxng", "voice"}


def test_07_api_errors_recent_returns_last_n_actionable(monkeypatch):
    import api.routes as routes

    from core.atlas_logger import LOG_FILE as log_path  # redirigé par tests/conftest.py

    assert "atlas_tests_root_" in str(log_path)
    previous = log_path.read_text(encoding="utf-8") if log_path.exists() else ""

    try:
        entries = [
            {"timestamp": "2026-04-09T10:00:00", "tool": "launch_app", "result": "success", "error": None},
            {
                "timestamp": "2026-04-09T10:01:00",
                "tool": "web_search",
                "result": "failure",
                "error": "timeout",
                "error_code": "ERR_MODEL_TIMEOUT",
            },
            {
                "timestamp": "2026-04-09T10:02:00",
                "tool": "workflow_run",
                "result": "failure",
                "error": "loop",
                "error_code": "ERR_RECURSION_DETECTED",
            },
        ]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

        payload = asyncio.run(routes.recent_actionable_errors(limit=2))
        assert payload["count"] == 2
        assert all("actionable_fix" in e for e in payload["errors"])
    finally:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(previous)


def test_08_web_search_fallback_to_ddgs(monkeypatch):
    import tools.web_search as ws

    async def _searx_fail(*args, **kwargs):
        raise RuntimeError("searx down")

    async def _ddgs_ok(*args, **kwargs):
        return [{"title": "ok", "url": "https://example.com", "snippet": "x", "source": "duckduckgo"}]

    logs = []

    async def _log(*args, **kwargs):
        logs.append((args, kwargs))

    monkeypatch.setattr(ws, "_search_searxng", _searx_fail)
    monkeypatch.setattr(ws, "_search_duckduckgo", _ddgs_ok)
    monkeypatch.setattr(ws, "_log_search_fallback", _log)
    monkeypatch.setattr("core.memory_manager.get_memory_manager", lambda: SimpleNamespace(save=lambda **_: None))

    results = asyncio.run(ws.search("meteo paris", 3))
    assert len(results) == 1
    assert results[0]["source"] == "duckduckgo"
    assert len(logs) >= 1


def test_09_web_search_total_degraded_message(monkeypatch):
    import tools.web_search as ws

    async def _searx_fail(*args, **kwargs):
        raise RuntimeError("searx down")

    async def _ddgs_fail(*args, **kwargs):
        raise RuntimeError("ddgs down")

    monkeypatch.setattr(ws, "_search_searxng", _searx_fail)
    monkeypatch.setattr(ws, "_search_duckduckgo", _ddgs_fail)
    monkeypatch.setattr("core.memory_manager.get_memory_manager", lambda: SimpleNamespace(save=lambda **_: None))

    results = asyncio.run(ws.search("python", 2))
    assert len(results) == 1
    assert "La recherche est indisponible" in results[0]["snippet"]


def test_10_workflow_mode_gaming_criteria_success(monkeypatch):
    from core.workflow_engine import get_workflow_engine

    engine = get_workflow_engine()
    engine.load_workflows()

    async def _exec(action):
        return {"status": "success", "result": {"success": True}, "message": f"ok:{action['action']}"}

    async def _notify(_):
        return {"success": True}

    engine.set_execution_callback(_exec)
    engine.set_notification_callback(_notify)
    engine.set_protection_callback(lambda *_: "libre")

    result = asyncio.run(engine.run_workflow("mode_gaming"))
    assert result["success"] is True
    assert result["criteria"]["success"] is True
    assert result["criteria"]["checks"]["steam_lance"] is True
