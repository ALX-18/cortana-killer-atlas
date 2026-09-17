"""Stabilisation v3.1 tests: observability and logging pipeline."""

import json
import pathlib

import pytest
from fastapi.testclient import TestClient


from core.atlas_logger import LOG_FILE  # redirigé vers un dossier temporaire par tests/conftest.py

assert "atlas_tests_root_" in str(LOG_FILE), "isolation des données inactive (tests/conftest.py)"


@pytest.fixture(autouse=True)
def clean_log_file():
    backup = LOG_FILE.read_text(encoding="utf-8") if LOG_FILE.exists() else None
    if LOG_FILE.exists():
        LOG_FILE.unlink()
    yield
    if backup is None:
        if LOG_FILE.exists():
            LOG_FILE.unlink()
    else:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOG_FILE.write_text(backup, encoding="utf-8")


@pytest.mark.asyncio
async def test_01_log_action_creates_file():
    from core.atlas_logger import log_action

    await log_action(
        user_input="test",
        intent_category="system",
        intent_verb="diagnose",
        tool="get_diagnostics",
        target=None,
        result="success",
        error=None,
        latency_ms=12,
    )
    assert LOG_FILE.exists()


@pytest.mark.asyncio
async def test_02_log_action_appends_lines():
    from core.atlas_logger import log_action

    await log_action("a", "web", "search", "web_search", "python", "success", None, 10)
    await log_action("b", "web", "search", "web_search", "fastapi", "success", None, 11)

    lines = LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


@pytest.mark.asyncio
async def test_03_log_json_format_valid():
    from core.atlas_logger import log_action

    await log_action("c", "window_mgmt", "open", "launch_app", "notepad", "success", None, 34)
    line = LOG_FILE.read_text(encoding="utf-8").strip()
    entry = json.loads(line)

    assert "timestamp" in entry
    assert entry["intent"] == "window_mgmt/open"
    assert entry["tool"] == "launch_app"
    assert entry["result"] == "success"
    assert isinstance(entry["latency_ms"], int)


def test_04_recent_logs_endpoint_returns_last_n():
    import main

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {"timestamp": "t1", "intent": "a/a", "tool": "x", "result": "success", "latency_ms": 1},
        {"timestamp": "t2", "intent": "b/b", "tool": "y", "result": "success", "latency_ms": 2},
        {"timestamp": "t3", "intent": "c/c", "tool": "z", "result": "failure", "latency_ms": 3},
    ]
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        for d in data:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    client = TestClient(main.app)
    resp = client.get("/api/logs/recent", params={"limit": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["logs"][0]["timestamp"] == "t2"
    assert body["logs"][1]["timestamp"] == "t3"


@pytest.mark.asyncio
async def test_05_engine_execute_generates_log():
    from core.intent_engine import get_execution_engine
    from core.validator import ResolvedAction, VerificationRule
    from core.intent_classifier import IntentResult

    engine = get_execution_engine()
    resolved = ResolvedAction(
        tool="get_diagnostics",
        params={},
        confirmation_required=False,
        verification=VerificationRule(type="none"),
        intent=IntentResult(
            category="system",
            verb="diagnose",
            target=None,
            params={},
            confidence=0.95,
            is_complex=False,
            raw_input="Fais un diagnostic",
        ),
    )

    context = {"user_input": "Fais un diagnostic"}
    result = await engine.execute(resolved, context)
    assert result.get("status") == "success"

    lines = LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    entry = json.loads(lines[-1])
    assert entry["tool"] == "get_diagnostics"
    assert entry["intent"] == "system/diagnose"
    assert entry["result"] in {"success", "retry_success"}
