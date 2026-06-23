"""
Atlas structured action logger.

Append-only JSONL logs for pipeline observability.
"""

import json
from datetime import datetime
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent.parent / "data" / "atlas_actions.jsonl"


async def log_action(
    user_input: str,
    intent_category: str,
    intent_verb: str,
    tool: str,
    target: str | None,
    result: str,
    error: str | None,
    latency_ms: int,
    error_code: str | None = None,
    retry_count: int = 0,
    grounding_layer: str | None = None,
    pipeline_stage: str | None = None,
    click_verified: bool | None = None,
    disambiguation_triggered: bool = False,
    grounding_attempts: list[dict] | None = None,
):
    """Append one structured Atlas action entry as JSONL."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user_input": user_input,
        "intent": f"{intent_category}/{intent_verb}",
        "tool": tool,
        "target": target,
        "result": result,
        "error": error,
        "error_code": error_code,
        "latency_ms": latency_ms,
        "retry_count": retry_count,
        "grounding_layer": grounding_layer,
        "pipeline_stage": pipeline_stage,
    }
    if click_verified is not None:
        entry["click_verified"] = click_verified
    if disambiguation_triggered:
        entry["disambiguation_triggered"] = True
    if grounding_attempts:
        entry["grounding_attempts"] = grounding_attempts

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
