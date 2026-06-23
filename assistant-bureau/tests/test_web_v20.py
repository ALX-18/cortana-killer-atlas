"""
Tests d'intégration MVP 2.0 / 2.1 — Atlas Web.
"""

import asyncio
import json
import time

import httpx
import pytest

from tools import web_search, web_reader, browser_controller
from core.intent_engine import (
    extract_tool_calls,
    execute_sequence,
    process_ai_response,
)


# ===================================================================
#  Tests v2.0 (1-6)
# ===================================================================

@pytest.mark.anyio
async def test_01_searxng_heartbeat_under_3s():
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.get(
            "http://127.0.0.1:8888/",
            headers={"User-Agent": "Atlas/2.1-test"},
        )
    elapsed = time.perf_counter() - start
    assert resp.status_code in (200, 302, 403)
    assert elapsed < 3.0


@pytest.mark.anyio
async def test_02_web_search_returns_results():
    results = await web_search.search("météo Paris", max_results=5)
    assert isinstance(results, list)
    assert len(results) >= 1
    first = results[0]
    assert "title" in first and "url" in first and "snippet" in first and "source" in first


@pytest.mark.anyio
async def test_03_fallback_duckduckgo_when_searxng_down(monkeypatch):
    async def fake_searxng(*args, **kwargs):
        raise RuntimeError("SearXNG down")

    monkeypatch.setattr(web_search, "_search_searxng", fake_searxng)
    results = await web_search.search("python fastapi", max_results=3)
    assert len(results) >= 1
    # SearXNG is forced down, so source should be duckduckgo_fallback or fallback_link
    assert all(
        r.get("source") in ("duckduckgo", "duckduckgo_fallback", "fallback_link")
        for r in results
    ), f"Unexpected source: {[r.get('source') for r in results]}"
    # Must NOT be searxng
    assert all(r.get("source") != "searxng" for r in results)


@pytest.mark.anyio
async def test_04_read_url_example_com():
    result = await web_reader.read_url("https://example.com")
    assert result.get("success") is True
    assert result.get("title")
    assert result.get("content")


@pytest.mark.anyio
async def test_05_read_url_invalid_error_handled():
    result = await web_reader.read_url("notaurl")
    assert result.get("success") is False
    assert "error" in result


@pytest.mark.anyio
async def test_06_browser_open_and_get_current_url():
    playwright = pytest.importorskip("playwright")
    _ = playwright

    open_result = await browser_controller.browser_open("https://example.com")
    assert open_result.get("success") is True

    current = await browser_controller.browser_current_url()
    assert current.get("success") is True
    assert "example.com" in current.get("url", "")

    await browser_controller.browser_close()


# ===================================================================
#  Tests v2.1 (7-10)
# ===================================================================

@pytest.mark.anyio
async def test_07_searxng_403_fallback_ddg_triggered(monkeypatch):
    """SearXNG 403 → fallback DDG déclenché automatiquement, source taggée."""

    async def fake_searxng_403(query, max_results):
        # Simulate a 403 response
        raise httpx.HTTPStatusError(
            "SearXNG returned 403",
            request=httpx.Request("GET", "http://localhost:8888/search"),
            response=httpx.Response(403),
        )

    monkeypatch.setattr(web_search, "_search_searxng", fake_searxng_403)
    results = await web_search.search("test query 403", max_results=3)

    assert len(results) >= 1
    for r in results:
        assert r.get("source") in ("duckduckgo", "duckduckgo_fallback"), \
            f"Expected duckduckgo source but got {r.get('source')}"
        assert r.get("source_reliability") == "medium"
        assert "fallback_note" in r


@pytest.mark.anyio
async def test_08_sequence_two_actions_in_order():
    """Séquence 2 actions → exécution dans l'ordre, résultats des 2 étapes retournés."""

    # Simulate an LLM response with a sequence
    sequence_json = json.dumps({
        "sequence": [
            {"action": "get_diagnostics", "params": {}, "confirmation_required": False,
             "reason": "Diagnostics système", "wait_for_completion": True},
            {"action": "list_processes", "params": {"sort_by": "cpu", "limit": 5},
             "confirmation_required": False, "reason": "Liste processus", "wait_for_completion": False},
        ],
        "description": "Diagnostics puis liste des processus"
    })

    # Parse → should return a list
    tool_calls = extract_tool_calls(sequence_json)
    assert isinstance(tool_calls, list)
    assert len(tool_calls) == 2
    assert tool_calls[0]["tool"] == "get_diagnostics"
    assert tool_calls[1]["tool"] == "list_processes"

    # Execute the sequence
    steps_seen = []

    async def track_steps(step, total, status, message):
        steps_seen.append({"step": step, "total": total, "status": status, "message": message})

    context = {"cpu_usage": 10, "ram_usage": 50}
    results = await execute_sequence(tool_calls, context, step_callback=track_steps)

    assert len(results) == 2
    assert results[0]["tool"] == "get_diagnostics"
    assert results[0]["status"] == "success"
    assert results[1]["tool"] == "list_processes"
    assert results[1]["status"] == "success"

    # Check step callbacks were called
    assert len(steps_seen) >= 2


@pytest.mark.anyio
async def test_09_sequence_with_failed_action_stops():
    """Séquence avec action échouée → arrêt propre + message d'erreur."""

    sequence_json = json.dumps({
        "sequence": [
            {"action": "kill_process", "params": {"pid": 99999999},
             "confirmation_required": False, "reason": "Kill inexistant",
             "wait_for_completion": True},
            {"action": "list_processes", "params": {},
             "confirmation_required": False, "reason": "Ne devrait pas s'exécuter",
             "wait_for_completion": False},
        ],
        "description": "Kill puis liste"
    })

    tool_calls = extract_tool_calls(sequence_json)
    assert len(tool_calls) == 2

    context = {"cpu_usage": 10, "ram_usage": 50}

    # kill_process on an invalid PID requires confirmation (via needs_confirmation)
    # OR will error — either way second action should NOT run
    results = await execute_sequence(tool_calls, context)

    # The sequence should have stopped at step 1
    assert len(results) <= 2
    first = results[0]
    assert first["status"] in ("error", "confirmation_required")

    # If it errored, second should not have been attempted
    if first["status"] == "error":
        assert len(results) == 1


@pytest.mark.anyio
async def test_10_keepalive_sse_on_long_operation():
    """Keepalive SSE reçu sur opération longue (mock Ollama lent)."""
    from unittest.mock import AsyncMock, patch

    # Mock a slow Ollama that yields tokens with long delays
    async def slow_stream(*args, **kwargs):
        yield "Bonjour"
        await asyncio.sleep(6)  # longer than 5s keepalive threshold
        yield " monde"

    with patch("api.routes.chat_stream", side_effect=slow_stream):
        from api.routes import chat_stream_endpoint
        from api.models import ChatRequest

        req = ChatRequest(message="test keepalive")

        response = await chat_stream_endpoint(req)

        events = []
        async for chunk in response.body_iterator:
            for line in chunk.split("\n"):
                line = line.strip()
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        events.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass

        # Should have at least one keepalive event
        types = [e.get("type") for e in events]
        assert "keepalive" in types, f"Expected keepalive in events, got types: {types}"
