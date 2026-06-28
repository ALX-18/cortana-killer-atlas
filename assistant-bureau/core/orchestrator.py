"""
Orchestrator — Multi-app orchestration (F3 v6.0).

DAG léger à exécution séquentielle. Le Planner (Qwen 7B) décompose une requête en
steps ; l'orchestrateur les exécute via l'ExecutionEngine en respectant les
dépendances (depends_on) et une politique d'échec par step (on_failure).

Politiques on_failure :
  - abort    : stoppe toute la chaîne
  - skip     : ignore le step échoué, continue
  - ask_user : met la chaîne en pause, demande confirmation
  - rollback : tente une action inverse (best-effort) puis stoppe

L'exécuteur de step est injectable (executor callable) → testable sans LLM réel.
Chaque step est logué en JSONL dédié (orchestration_id, step_id, status, latency).
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger("atlas.orchestrator")


class OnFailure(str, Enum):
    ABORT = "abort"
    SKIP = "skip"
    ASK_USER = "ask_user"
    ROLLBACK = "rollback"


@dataclass
class OrchestrationStep:
    id: str
    action: str                              # nom d'outil / intent verb
    params: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    on_failure: OnFailure = OnFailure.ABORT
    verify: Optional[Callable[[dict], bool]] = None
    rollback_action: Optional[dict] = None   # {action, params} pour ROLLBACK


@dataclass
class StepResult:
    step_id: str
    status: str                # success | failure | skipped | aborted | paused
    latency_ms: int
    result: dict = field(default_factory=dict)
    error: Optional[str] = None


def _topo_order(steps: list[OrchestrationStep]) -> list[OrchestrationStep]:
    """Tri topologique stable (respecte depends_on). Cycles → ordre d'origine."""
    by_id = {s.id: s for s in steps}
    visited: set[str] = set()
    order: list[OrchestrationStep] = []

    def visit(s: OrchestrationStep, stack: set[str]):
        if s.id in visited:
            return
        if s.id in stack:
            logger.warning("[ORCH] Cycle détecté sur '%s' — ignoré", s.id)
            return
        stack.add(s.id)
        for dep in s.depends_on:
            if dep in by_id:
                visit(by_id[dep], stack)
        stack.discard(s.id)
        visited.add(s.id)
        order.append(s)

    for s in steps:
        visit(s, set())
    return order


class Orchestrator:
    """Exécute un DAG de steps multi-app séquentiellement."""

    def __init__(self, executor: Optional[Callable[[str, dict], Awaitable[dict]]] = None):
        # executor(action, params) -> {"status": "success"|"error", ...}
        self._executor = executor

    async def _exec_step(self, step: OrchestrationStep) -> dict:
        if self._executor is not None:
            return await self._executor(step.action, step.params)
        # Exécuteur réel par défaut : passe par execute_tool
        from core.intent_engine import execute_tool
        from core.context_monitor import collect_context
        return await execute_tool(step.action, step.params, collect_context())

    async def run(
        self,
        steps: list[OrchestrationStep],
        orchestration_id: Optional[str] = None,
        step_callback: Optional[Callable] = None,
    ) -> dict:
        """
        Exécute la chaîne. Retourne {orchestration_id, status, steps:[StepResult...]}.
        status global : success | aborted | paused | partial.
        """
        orch_id = orchestration_id or f"orch_{uuid.uuid4().hex[:10]}"
        ordered = _topo_order(steps)
        results: list[StepResult] = []
        completed: dict[str, StepResult] = {}
        global_status = "success"

        for step in ordered:
            # Une dépendance qui n'a pas réussi (échec/abort/skip) → on saute le step
            dep_not_ok = any(
                d in completed and completed[d].status != "success"
                for d in step.depends_on
            )
            if dep_not_ok:
                sr = StepResult(step.id, "skipped", 0, error="dépendance non réussie")
                results.append(sr); completed[step.id] = sr
                await self._emit(step_callback, orch_id, sr)
                continue

            start = time.monotonic()
            try:
                res = await self._exec_step(step)
                latency = int((time.monotonic() - start) * 1000)
                ok = res.get("status") == "success" or res.get("success") is True
                if ok and step.verify is not None:
                    try:
                        ok = bool(step.verify(res))
                    except Exception:
                        ok = False
                if ok:
                    sr = StepResult(step.id, "success", latency, result=res)
                else:
                    sr = StepResult(step.id, "failure", latency, result=res,
                                    error=res.get("message") or "échec step")
            except Exception as e:
                latency = int((time.monotonic() - start) * 1000)
                sr = StepResult(step.id, "failure", latency, error=str(e)[:200])

            # Politique d'échec
            if sr.status == "failure":
                policy = step.on_failure
                if policy == OnFailure.SKIP:
                    sr.status = "skipped"
                    logger.info("[ORCH] Step '%s' échoué → skip", step.id)
                elif policy == OnFailure.ASK_USER:
                    sr.status = "paused"
                    results.append(sr); completed[step.id] = sr
                    await self._emit(step_callback, orch_id, sr)
                    global_status = "paused"
                    logger.info("[ORCH] Step '%s' échoué → pause (ask_user)", step.id)
                    break
                elif policy == OnFailure.ROLLBACK:
                    await self._rollback(step)
                    sr.status = "aborted"
                    results.append(sr); completed[step.id] = sr
                    await self._emit(step_callback, orch_id, sr)
                    global_status = "aborted"
                    logger.info("[ORCH] Step '%s' échoué → rollback + abort", step.id)
                    break
                else:  # ABORT
                    sr.status = "aborted"
                    results.append(sr); completed[step.id] = sr
                    await self._emit(step_callback, orch_id, sr)
                    global_status = "aborted"
                    logger.info("[ORCH] Step '%s' échoué → abort chaîne", step.id)
                    break

            results.append(sr); completed[step.id] = sr
            await self._emit(step_callback, orch_id, sr)

        if global_status == "success" and any(r.status == "skipped" for r in results):
            global_status = "partial"

        return {
            "orchestration_id": orch_id,
            "status": global_status,
            "steps": [self._sr_dict(r) for r in results],
        }

    async def _rollback(self, step: OrchestrationStep):
        if not step.rollback_action:
            return
        try:
            await self._exec_step(OrchestrationStep(
                id=f"{step.id}_rollback",
                action=step.rollback_action.get("action", ""),
                params=step.rollback_action.get("params", {}),
            ))
        except Exception as e:
            logger.debug("[ORCH] Rollback '%s' échoué : %s", step.id, e)

    async def _emit(self, callback, orch_id: str, sr: StepResult):
        # Log JSONL dédié orchestration
        try:
            from core.atlas_logger import log_orchestration_step
            await log_orchestration_step(orch_id, sr.step_id, sr.status, sr.latency_ms, sr.error)
        except Exception as e:
            logger.debug("[ORCH] Log step échoué : %s", e)
        if callback is not None:
            try:
                await callback(orch_id, self._sr_dict(sr))
            except Exception:
                pass

    @staticmethod
    def _sr_dict(sr: StepResult) -> dict:
        return {
            "step_id": sr.step_id, "status": sr.status,
            "latency_ms": sr.latency_ms, "error": sr.error,
        }


# --------------------------------------------------------------------------- #
#  Chaînes démo (C1/C2/C3)
# --------------------------------------------------------------------------- #

def build_demo_chain(name: str) -> list[OrchestrationStep]:
    """Construit une chaîne démo prédéfinie (C1/C2/C3)."""
    n = name.lower()
    if n in ("c1", "mode_travail", "travail"):
        return [
            OrchestrationStep("close_discord", "window_close",
                              {"title": "Discord"}, on_failure=OnFailure.ABORT),
            OrchestrationStep("open_vscode", "launch_app",
                              {"name": "code"}, depends_on=["close_discord"],
                              on_failure=OnFailure.ABORT),
            OrchestrationStep("open_spotify", "launch_app",
                              {"name": "spotify"}, depends_on=["open_vscode"],
                              on_failure=OnFailure.SKIP),
        ]
    if n in ("c2", "briefing", "briefing_matin"):
        return [
            OrchestrationStep("read_mails", "notify",
                              {"message": "[MOCK] Lecture des derniers mails (F6 à venir)"},
                              on_failure=OnFailure.SKIP),
            OrchestrationStep("weather", "web_search",
                              {"query": "météo aujourd'hui"}, on_failure=OnFailure.SKIP),
            OrchestrationStep("calendar", "notify",
                              {"message": "[MOCK] Agenda du jour"}, on_failure=OnFailure.SKIP),
        ]
    if n in ("c3", "mode_gaming", "gaming"):
        return [
            OrchestrationStep("close_prod", "notify",
                              {"message": "Fermeture des apps de productivité"},
                              on_failure=OnFailure.SKIP),
            OrchestrationStep("launch_steam", "launch_app",
                              {"name": "steam"}, depends_on=["close_prod"],
                              on_failure=OnFailure.ABORT),
            OrchestrationStep("launch_game", "ui_click_element",
                              {"element_name": "jouer", "app_title": "steam"},
                              depends_on=["launch_steam"], on_failure=OnFailure.ASK_USER),
        ]
    raise ValueError(f"Chaîne démo inconnue : {name}")


_instance: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    global _instance
    if _instance is None:
        _instance = Orchestrator()
    return _instance
