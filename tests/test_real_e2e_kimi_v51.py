"""
Quick real-world E2E checks for Kimi sprint (manual/interactive environment).
Runs a compact 5-command validation target.
"""

import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.intent_classifier import get_classifier
from core.validator import get_validator
from core.intent_engine import execute_tool


def _run_pipeline(user_input: str, context: dict | None = None):
    context = context or {}
    classifier = get_classifier()
    validator = get_validator()
    intent = classifier.classify(user_input, context)
    resolved = validator.resolve(intent, context)
    return intent, resolved


def test_cmd_reduce_opera_target_only():
    intent, resolved = _run_pipeline("réduis la fenêtre opera gx svp")
    assert intent.target == "opera gx"
    assert resolved.tool == "window_minimize"


def test_cmd_refais_detected():
    intent, resolved = _run_pipeline("refais")
    assert intent.verb == "redo"
    assert resolved.tool == "redo_last_action"
