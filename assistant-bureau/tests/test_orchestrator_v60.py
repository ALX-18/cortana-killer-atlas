"""
Sprint v6.0 — F3 Multi-app Orchestration.

Tests de l'orchestrateur DAG avec exécuteur mocké (pas de LLM/app réelle).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.orchestrator import (
    Orchestrator, OrchestrationStep, OnFailure, build_demo_chain, _topo_order,
)


def _executor_factory(fail_steps=None):
    """Crée un exécuteur mock qui échoue sur les step.action listés."""
    fail_steps = fail_steps or set()
    calls = []

    async def executor(action, params):
        calls.append(action)
        if action in fail_steps:
            return {"status": "error", "message": f"forced fail {action}"}
        return {"status": "success", "result": {"action": action}}

    executor.calls = calls
    return executor


# --------------------------------------------------------------------------- #
#  Exécution de base
# --------------------------------------------------------------------------- #

class TestOrchestratorBasic:
    @pytest.mark.asyncio
    async def test_three_steps_all_success(self):
        ex = _executor_factory()
        orch = Orchestrator(executor=ex)
        steps = [
            OrchestrationStep("a", "step_a"),
            OrchestrationStep("b", "step_b", depends_on=["a"]),
            OrchestrationStep("c", "step_c", depends_on=["b"]),
        ]
        res = await orch.run(steps, orchestration_id="t1")
        assert res["status"] == "success"
        assert len(res["steps"]) == 3
        assert all(s["status"] == "success" for s in res["steps"])
        assert ex.calls == ["step_a", "step_b", "step_c"]

    @pytest.mark.asyncio
    async def test_orchestration_id_returned(self):
        orch = Orchestrator(executor=_executor_factory())
        res = await orch.run([OrchestrationStep("a", "x")], orchestration_id="myid")
        assert res["orchestration_id"] == "myid"

    @pytest.mark.asyncio
    async def test_latency_recorded(self):
        orch = Orchestrator(executor=_executor_factory())
        res = await orch.run([OrchestrationStep("a", "x")])
        assert isinstance(res["steps"][0]["latency_ms"], int)


# --------------------------------------------------------------------------- #
#  Politiques on_failure
# --------------------------------------------------------------------------- #

class TestFailurePolicies:
    @pytest.mark.asyncio
    async def test_abort_stops_chain(self):
        ex = _executor_factory(fail_steps={"step_b"})
        orch = Orchestrator(executor=ex)
        steps = [
            OrchestrationStep("a", "step_a"),
            OrchestrationStep("b", "step_b", on_failure=OnFailure.ABORT),
            OrchestrationStep("c", "step_c", depends_on=["b"]),
        ]
        res = await orch.run(steps)
        assert res["status"] == "aborted"
        # step_c jamais exécuté
        assert "step_c" not in ex.calls
        statuses = {s["step_id"]: s["status"] for s in res["steps"]}
        assert statuses["a"] == "success"
        assert statuses["b"] == "aborted"

    @pytest.mark.asyncio
    async def test_skip_continues_chain(self):
        ex = _executor_factory(fail_steps={"step_b"})
        orch = Orchestrator(executor=ex)
        steps = [
            OrchestrationStep("a", "step_a"),
            OrchestrationStep("b", "step_b", on_failure=OnFailure.SKIP),
            OrchestrationStep("c", "step_c"),  # pas de dépendance sur b
        ]
        res = await orch.run(steps)
        assert res["status"] == "partial"
        assert "step_c" in ex.calls
        statuses = {s["step_id"]: s["status"] for s in res["steps"]}
        assert statuses["b"] == "skipped"
        assert statuses["c"] == "success"

    @pytest.mark.asyncio
    async def test_ask_user_pauses(self):
        ex = _executor_factory(fail_steps={"step_b"})
        orch = Orchestrator(executor=ex)
        steps = [
            OrchestrationStep("a", "step_a"),
            OrchestrationStep("b", "step_b", on_failure=OnFailure.ASK_USER),
            OrchestrationStep("c", "step_c"),
        ]
        res = await orch.run(steps)
        assert res["status"] == "paused"
        assert "step_c" not in ex.calls
        assert res["steps"][-1]["status"] == "paused"

    @pytest.mark.asyncio
    async def test_rollback_invokes_inverse(self):
        ex = _executor_factory(fail_steps={"open_app"})
        orch = Orchestrator(executor=ex)
        steps = [
            OrchestrationStep(
                "open_app", "open_app", on_failure=OnFailure.ROLLBACK,
                rollback_action={"action": "close_app", "params": {}},
            ),
        ]
        res = await orch.run(steps)
        assert res["status"] == "aborted"
        # l'action de rollback a été appelée
        assert "close_app" in ex.calls

    @pytest.mark.asyncio
    async def test_dependency_failure_skips_dependent(self):
        ex = _executor_factory(fail_steps={"step_a"})
        orch = Orchestrator(executor=ex)
        steps = [
            OrchestrationStep("a", "step_a", on_failure=OnFailure.SKIP),
            OrchestrationStep("b", "step_b", depends_on=["a"]),
        ]
        res = await orch.run(steps)
        statuses = {s["step_id"]: s["status"] for s in res["steps"]}
        # a skippé (échec) ; b dépend de a → b skippé aussi
        assert statuses["a"] == "skipped"
        assert statuses["b"] == "skipped"


# --------------------------------------------------------------------------- #
#  Tri topologique
# --------------------------------------------------------------------------- #

class TestTopoOrder:
    def test_respects_dependencies(self):
        steps = [
            OrchestrationStep("c", "c", depends_on=["b"]),
            OrchestrationStep("a", "a"),
            OrchestrationStep("b", "b", depends_on=["a"]),
        ]
        order = [s.id for s in _topo_order(steps)]
        assert order.index("a") < order.index("b") < order.index("c")

    def test_cycle_does_not_crash(self):
        steps = [
            OrchestrationStep("a", "a", depends_on=["b"]),
            OrchestrationStep("b", "b", depends_on=["a"]),
        ]
        order = _topo_order(steps)
        assert len(order) == 2


# --------------------------------------------------------------------------- #
#  Chaînes démo
# --------------------------------------------------------------------------- #

class TestDemoChains:
    def test_c1_structure(self):
        chain = build_demo_chain("c1")
        ids = [s.id for s in chain]
        assert ids == ["close_discord", "open_vscode", "open_spotify"]
        assert chain[2].on_failure == OnFailure.SKIP

    def test_c3_structure(self):
        chain = build_demo_chain("mode_gaming")
        assert chain[-1].on_failure == OnFailure.ASK_USER
        assert chain[1].action == "launch_app"

    def test_unknown_chain_raises(self):
        with pytest.raises(ValueError):
            build_demo_chain("c99")

    @pytest.mark.asyncio
    async def test_c1_runs_with_mock(self):
        ex = _executor_factory()
        orch = Orchestrator(executor=ex)
        res = await orch.run(build_demo_chain("c1"))
        assert res["status"] == "success"
        assert len(res["steps"]) == 3
