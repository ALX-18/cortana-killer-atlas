"""
Sprint v5.2 clôture — AXE 3
Tests endpoint /api/metrics/grounding sur des entrées JSONL réalistes.

Vérifie que les nouveaux champs (click_verified, disambiguation_triggered,
grounding_layer, grounding_attempts) sont correctement agrégés.
"""

import json
import pathlib

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG_FILE = PROJECT_ROOT / "data" / "atlas_actions.jsonl"


@pytest.fixture(autouse=True)
def isolate_log_file():
    """Backup the JSONL log around each test, restore after."""
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


def _write_entries(entries: list[dict]) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _click_entry(
    target: str,
    layer: str,
    result: str = "success",
    latency_ms: int = 4500,
    click_verified: bool = True,
    disambiguation_triggered: bool = False,
    grounding_attempts: list[dict] | None = None,
) -> dict:
    return {
        "timestamp": "2026-04-28T18:00:00",
        "user_input": f"clique sur {target}",
        "intent": "interaction/click",
        "tool": "ui_click_element",
        "target": target,
        "result": result,
        "error": None if result in ("success", "retry_success") else "no_match",
        "error_code": None,
        "latency_ms": latency_ms,
        "retry_count": 0,
        "grounding_layer": layer,
        "pipeline_stage": "engine",
        "click_verified": click_verified,
        "disambiguation_triggered": disambiguation_triggered,
        "grounding_attempts": grounding_attempts or [],
    }


# --------------------------------------------------------------------------- #
#  Endpoint smoke tests
# --------------------------------------------------------------------------- #

class TestMetricsGroundingEmpty:
    def test_no_log_returns_zero_counts(self):
        import main
        client = TestClient(main.app)
        resp = client.get("/api/metrics/grounding")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_actions"] == 0
        assert body["disambiguation_count"] == 0
        assert body["layer_distribution"] == {}


class TestMetricsGroundingRealData:
    def test_returns_data_after_clicks(self):
        """After 3 ui_click_element entries, /metrics/grounding must report count > 0."""
        import main
        attempts_ocr_success = [
            {"layer": "cache", "result": "failure", "latency_ms": 0, "error": "no_match"},
            {"layer": "ocr", "result": "success", "latency_ms": 4400, "error": None},
        ]
        attempts_ocr_fail_then_vision = [
            {"layer": "cache", "result": "failure", "latency_ms": 0, "error": "no_match"},
            {"layer": "ocr", "result": "failure", "latency_ms": 139, "error": "no_match"},
            {"layer": "vision", "result": "success", "latency_ms": 7800, "error": None},
        ]
        _write_entries([
            _click_entry("Steam", "ocr", latency_ms=4500, grounding_attempts=attempts_ocr_success),
            _click_entry("Steam", "ocr", latency_ms=5100, grounding_attempts=attempts_ocr_success),
            _click_entry("Discord", "vision", latency_ms=8200, grounding_attempts=attempts_ocr_fail_then_vision),
        ])

        client = TestClient(main.app)
        resp = client.get("/api/metrics/grounding")
        assert resp.status_code == 200
        body = resp.json()

        assert body["total_actions"] == 3
        # Layer distribution from grounding_layer field
        assert body["layer_distribution"].get("ocr") == 2
        assert body["layer_distribution"].get("vision") == 1
        # Click verified rate (3/3 verified)
        assert body["click_verified_rate"] == 1.0
        # Median latency by layer
        assert body["median_latency_ms_by_layer"].get("ocr") in (4500, 5100, 4800)  # median of [4500, 5100]
        # Usage count by app
        assert body["usage_count_by_app"].get("Steam") == 2
        assert body["usage_count_by_app"].get("Discord") == 1
        # Success rate by app — all entries are "success" → 1.0
        assert body["success_rate_by_app"].get("Steam") == 1.0

    def test_disambiguation_count(self):
        import main
        _write_entries([
            _click_entry("Steam", "ocr", disambiguation_triggered=True),
            _click_entry("Steam", "ocr", disambiguation_triggered=False),
            _click_entry("Discord", "vision", disambiguation_triggered=True),
        ])
        client = TestClient(main.app)
        resp = client.get("/api/metrics/grounding")
        body = resp.json()
        assert body["disambiguation_count"] == 2

    def test_grounding_attempts_aggregated(self):
        """layer_attempt_stats must aggregate across grounding_attempts arrays."""
        import main
        attempts1 = [
            {"layer": "cache", "result": "failure", "latency_ms": 0, "error": "no_match"},
            {"layer": "ocr", "result": "success", "latency_ms": 4400, "error": None},
        ]
        attempts2 = [
            {"layer": "cache", "result": "failure", "latency_ms": 0, "error": "no_match"},
            {"layer": "ocr", "result": "failure", "latency_ms": 139, "error": "no_match"},
            {"layer": "vision", "result": "success", "latency_ms": 7800, "error": None},
        ]
        _write_entries([
            _click_entry("Steam", "ocr", grounding_attempts=attempts1),
            _click_entry("Discord", "vision", grounding_attempts=attempts2),
        ])
        client = TestClient(main.app)
        resp = client.get("/api/metrics/grounding")
        body = resp.json()

        stats = body["layer_attempt_stats"]
        # cache: 2 attempts, both failure
        assert stats["cache"]["total"] == 2
        assert stats["cache"]["failure"] == 2
        assert stats["cache"]["success"] == 0
        # ocr: 2 attempts (1 success, 1 failure)
        assert stats["ocr"]["total"] == 2
        assert stats["ocr"]["success"] == 1
        assert stats["ocr"]["failure"] == 1
        # vision: 1 attempt success
        assert stats["vision"]["total"] == 1
        assert stats["vision"]["success"] == 1

        # Layer success rates
        assert body["layer_success_rate"]["cache"] == 0.0
        assert body["layer_success_rate"]["ocr"] == 0.5
        assert body["layer_success_rate"]["vision"] == 1.0

        # Median attempt latency per layer
        assert body["median_attempt_latency_ms_by_layer"]["vision"] == 7800

    def test_global_timeout_layer_recorded(self):
        """Pre-Tesseract entries with grounding_layer=global_timeout must be visible."""
        import main
        _write_entries([
            _click_entry("Steam", "global_timeout", result="failure", latency_ms=90359,
                         click_verified=False),
        ])
        client = TestClient(main.app)
        resp = client.get("/api/metrics/grounding")
        body = resp.json()
        assert body["layer_distribution"].get("global_timeout") == 1
        assert body["click_verified_rate"] == 0.0

    def test_limit_parameter_clamps(self):
        import main
        _write_entries([_click_entry("App", "ocr") for _ in range(20)])
        client = TestClient(main.app)
        resp = client.get("/api/metrics/grounding", params={"limit": 5})
        assert resp.status_code == 200
        assert resp.json()["total_actions"] == 5

    def test_limit_invalid_returns_400(self):
        import main
        client = TestClient(main.app)
        resp = client.get("/api/metrics/grounding", params={"limit": 0})
        assert resp.status_code == 400
