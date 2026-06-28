"""
Intent Engine — Décompose les requêtes en étapes ordonnées,
vérifie les conflits contextuels, et orchestre l'exécution des outils.
"""

import asyncio
import json
import inspect
import logging
import re
import uuid
import time
import tempfile
import os
import shutil
from datetime import datetime
from typing import Any

from core.confirmation import needs_confirmation, store_pending, classify_process
from core.memory_manager import get_memory_manager
from tools import (
    process_manager,
    app_launcher,
    diagnostics,
    system_config,
    web_search,
    web_reader,
    browser_controller,
    window_controller,
    browser_bridge,
)

logger = logging.getLogger("atlas.intent_engine")

# --------------------------------------------------------------------------- #
#  Browser process detection — pour le routage interaction
# --------------------------------------------------------------------------- #

BROWSER_PROCESSES = [
    "chrome.exe", "firefox.exe", "opera.exe", "msedge.exe",
    "brave.exe", "vivaldi.exe", "chromium.exe",
]


# --------------------------------------------------------------------------- #
#  Tool registry
# --------------------------------------------------------------------------- #

TOOL_HANDLERS = {
    "list_processes": lambda args: process_manager.list_processes(
        sort_by=args.get("sort_by", "memory"),
        limit=args.get("limit", 30),
    ),
    "kill_process": lambda args: process_manager.kill_process(
        pid=args.get("pid"),
        name=args.get("name"),
    ),
    "set_priority": lambda args: process_manager.set_priority(
        pid=args["pid"],
        priority=args["priority"],
    ),
    "launch_app": lambda args: app_launcher.launch_app(
        name=args.get("name"),
        path=args.get("path"),
        wait_ready=args.get("wait", False),
    ),
    "get_diagnostics": lambda args: diagnostics.full_diagnostics(),
    "run_powershell": lambda args: system_config.run_powershell(args["command"]),
    "system_config": lambda args: system_config.dispatch_system_config(
        action=args["action"],
        **{k: v for k, v in args.items() if k != "action"},
    ),
    "web_search": lambda args: web_search.search(
        query=args.get("query", ""),
        max_results=args.get("max_results", 5),
    ),
    "web_search_to_notepad": lambda args: _run_web_search_to_notepad(args),
    "read_url": lambda args: web_reader.summarize_url(
        url=args.get("url", ""),
    ),
    "browser_open": lambda args: browser_controller.browser_open(
        url=args.get("url", ""),
    ),
    "browser_click": lambda args: browser_controller.browser_click(
        selector=args.get("selector", ""),
    ),
    "browser_type": lambda args: browser_controller.browser_type(
        selector=args.get("selector", ""),
        text=args.get("text", ""),
    ),
    "browser_scroll": lambda args: browser_controller.browser_scroll(
        direction=args.get("direction", "down"),
        amount=args.get("amount", 600),
    ),
    "browser_current_url": lambda args: browser_controller.browser_current_url(),
    "browser_close": lambda args: browser_controller.browser_close(),

    # --- MVP 2.2 : Interaction Apps (window_controller) --- #
    "window_find": lambda args: window_controller.window_find(
        title=args.get("title", ""),
    ),
    "window_focus": lambda args: window_controller.window_focus(
        title=args.get("title", ""),
    ),
    "window_type": lambda args: window_controller.window_type(
        text=args.get("text", ""),
        target=args.get("target"),
        use_clipboard=args.get("use_clipboard", False),
    ),
    "window_hotkey": lambda args: window_controller.window_hotkey(
        *args.get("keys", []),
        target=args.get("target"),
    ),
    "window_click": lambda args: window_controller.window_click(
        x=args.get("x"),
        y=args.get("y"),
        button=args.get("button", "left"),
        clicks=args.get("clicks", 1),
        target=args.get("target"),
    ),
    "window_screenshot": lambda args: window_controller.window_screenshot(
        title=args.get("title"),
    ),
    "window_get_active": lambda args: window_controller.window_get_active(),

    # --- MVP 2.3 : Window management étendu --- #
    "window_close": lambda args: window_controller.window_close(
        title=args.get("title", ""),
    ),
    "window_minimize": lambda args: window_controller.window_minimize(
        title=args.get("title", ""),
    ),
    "window_maximize": lambda args: window_controller.window_maximize(
        title=args.get("title", ""),
    ),
    "window_list": lambda args: window_controller.window_list(),
    "window_snap": lambda args: window_controller.window_snap(
        title=args.get("title", ""),
        position=args.get("position", "left"),
    ),

    # --- MVP 2.2 : Interaction Apps (browser_bridge) --- #
    "browser_navigate": lambda args: browser_bridge.browser_navigate(
        url=args.get("url", ""),
    ),
    "browser_new_tab": lambda args: browser_bridge.browser_new_tab(
        url=args.get("url", ""),
    ),
    "browser_ext_click": lambda args: browser_bridge.browser_ext_click(
        selector=args.get("selector", ""),
    ),
    "browser_ext_type": lambda args: browser_bridge.browser_ext_type(
        selector=args.get("selector", ""),
        text=args.get("text", ""),
    ),
    "browser_ext_scroll": lambda args: browser_bridge.browser_ext_scroll(
        direction=args.get("direction", "down"),
        amount=args.get("amount", 500),
    ),
    "browser_ext_get_content": lambda args: browser_bridge.browser_ext_get_content(
        selector=args.get("selector", "body"),
    ),
    "browser_ext_get_url": lambda args: browser_bridge.browser_ext_get_url(),
    "browser_bridge_status": lambda args: browser_bridge.browser_bridge_status(),

    # --- MVP 2.3 : Grounding + Redo --- #
    "ui_click_element": lambda args: _run_grounding(args),
    "redo_last_action": lambda args: _run_redo(args),

    # --- F2 v6.0 : Lecture d'écran (CU-1/3/4/5) --- #
    "screen_read": lambda args: _run_screen_read(args),

    # --- MVP 3.0 : Automation --- #
    "schedule_add": lambda args: _run_schedule_add(args),
    "schedule_list": lambda args: _run_schedule_list(args),
    "schedule_remove": lambda args: _run_schedule_remove(args),
    "schedule_run_now": lambda args: _run_schedule_run_now(args),
    "trigger_add": lambda args: _run_trigger_add(args),
    "trigger_list": lambda args: _run_trigger_list(args),
    "trigger_toggle": lambda args: _run_trigger_toggle(args),
    "workflow_run": lambda args: _run_workflow_run(args),
    "workflow_create": lambda args: _run_workflow_create(args),
    "workflow_list": lambda args: _run_workflow_list(args),
    "notify": lambda args: _run_notify(args),

    # --- v3.1 stabilization: maintenance actions (non-interactive) --- #
    "maintenance_empty_bin": lambda args: _run_maintenance_empty_bin(args),
    "maintenance_cleanup_temp": lambda args: _run_maintenance_cleanup_temp(args),
    "maintenance_gc": lambda args: _run_maintenance_gc(args),
}


# --------------------------------------------------------------------------- #
#  Tool call parser — strict JSON parsing with regex fallback
# --------------------------------------------------------------------------- #

# Valid actions (must match TOOL_HANDLERS keys + legacy "tool" field)
VALID_ACTIONS = set(TOOL_HANDLERS.keys())


# --------------------------------------------------------------------------- #
#  Async tool wrappers for grounding and redo
# --------------------------------------------------------------------------- #

def _run_grounding(args: dict):
    """Wrapper synchrone → retourne un awaitable pour le grounding stack."""
    from tools.grounding import find_and_click
    exclude = args.get("_exclude_methods")
    return find_and_click(
        app_title=args.get("app_title", ""),
        element_name=args.get("element_name", ""),
        exclude_methods=set(exclude) if exclude else None,
    )


def _run_screen_read(args: dict):
    """Wrapper async → lecture d'écran (F2 v6.0)."""
    from tools.screen_reader import read_screen
    return read_screen(mode=args.get("mode", "read"), summarize=args.get("summarize", True))


def _run_redo(args: dict):
    """Refait la dernière action depuis le WorldState."""
    from core.world_state import get_world_state
    ws = get_world_state()
    if ws.last_action is None:
        return {"success": False, "message": "Aucune action précédente à refaire."}
    la = ws.last_action
    handler = TOOL_HANDLERS.get(la["tool"])
    if not handler:
        return {"success": False, "message": f"Outil '{la['tool']}' introuvable pour le redo."}
    return handler(la["params"])


async def _run_web_search_to_notepad(args: dict):
    """Recherche web puis colle la premiere phrase dans Bloc-notes."""
    query = (args.get("query") or "").strip()
    target = (args.get("target") or "bloc notes").strip() or "bloc notes"
    max_results = int(args.get("max_results", 5))

    if not query:
        return {"success": False, "message": "Requête vide pour la recherche web."}

    results = await web_search.search(query=query, max_results=max_results)
    if not results:
        return {"success": False, "message": "Aucun résultat de recherche."}

    def _pick_wikipedia_result(items: list[dict]) -> dict:
        for item in items:
            url = str(item.get("url", "")).lower()
            if "wikipedia.org/wiki/" in url and "wikipedia:" not in url and "wikip%C3%A9dia:" not in url:
                return item
        return items[0]

    def _first_sentence(text: str) -> str:
        clean = " ".join((text or "").split())
        if not clean:
            return ""
        parts = re.split(r"(?<=[.!?])\s+", clean)
        return (parts[0] if parts else clean).strip()

    chosen = _pick_wikipedia_result(results)
    sentence = _first_sentence(str(chosen.get("snippet", "")))
    if not sentence:
        return {
            "success": False,
            "message": "Résultat trouvé mais impossible d'extraire une phrase exploitable.",
            "url": chosen.get("url", ""),
        }

    # Focus (or launch) notepad target then paste sentence.
    aliases = [target, "bloc-notes", "bloc notes", "notepad"]
    focus_name = None

    def _try_focus() -> str | None:
        for name in aliases:
            res = window_controller.window_focus(name)
            if res.get("success"):
                return name
        return None

    focus_name = _try_focus()
    if focus_name is None:
        launch_res = app_launcher.launch_app(name=target)
        if not launch_res.get("success"):
            # Fallback launch with canonical executable alias.
            launch_res = app_launcher.launch_app(name="notepad")

        # Notepad may take a moment before being discoverable by title.
        for _ in range(20):  # up to ~10s
            await asyncio.sleep(0.5)
            focus_name = _try_focus()
            if focus_name is not None:
                break

    if focus_name is None:
        return {
            "success": False,
            "message": f"Recherche OK mais collage impossible dans '{target}'. Aucune fenêtre trouvée pour '{target}'.",
            "url": chosen.get("url", ""),
            "sentence": sentence,
            "search_top": results[:3],
        }

    type_res = window_controller.window_type(text=sentence, target=focus_name, use_clipboard=True)
    if not type_res.get("success"):
        return {
            "success": False,
            "message": f"Recherche OK mais collage impossible dans '{target}'. {type_res.get('message', '')}".strip(),
            "url": chosen.get("url", ""),
            "sentence": sentence,
            "search_top": results[:3],
        }

    return {
        "success": True,
        "message": "Terminé.",
        "url": chosen.get("url", ""),
        "sentence": sentence,
        "target": target,
    }


# --------------------------------------------------------------------------- #
#  MVP 3.0 : Automation wrappers
# --------------------------------------------------------------------------- #

async def _run_schedule_add(args: dict):
    from core.scheduler import get_scheduler, ScheduledJob
    job = ScheduledJob(
        id="",
        name=args.get("name", "Job sans nom"),
        description=args.get("description", ""),
        trigger_type=args.get("trigger_type", "cron"),
        trigger_config=args.get("trigger_config", {}),
        actions=args.get("actions", []),
    )
    job_id = await get_scheduler().add_job(job)
    return {"success": True, "message": f"Job '{job.name}' planifié (ID: {job_id})."}


async def _run_schedule_list(args: dict):
    from core.scheduler import get_scheduler
    jobs = await get_scheduler().list_jobs()
    return {
        "success": True,
        "message": f"{len(jobs)} job(s) planifié(s).",
        "jobs": [j.to_dict() for j in jobs],
    }


async def _run_schedule_remove(args: dict):
    from core.scheduler import get_scheduler
    removed = await get_scheduler().remove_job(args.get("job_id", ""))
    if removed:
        return {"success": True, "message": "Job supprimé."}
    return {"success": False, "message": "Job introuvable."}


async def _run_schedule_run_now(args: dict):
    from core.scheduler import get_scheduler
    scheduler = get_scheduler()
    job_id = args.get("job_id", "")
    if job_id == "latest":
        jobs = await scheduler.list_jobs()
        if not jobs:
            return {"success": False, "message": "Aucun job planifié."}
        jobs_sorted = sorted(jobs, key=lambda j: j.created_at or "")
        job_id = jobs_sorted[-1].id
    return await scheduler.run_job_now(job_id)


async def _run_trigger_add(args: dict):
    from core.trigger_engine import get_trigger_engine, ContextTrigger, TriggerCondition
    cond_data = args.get("condition", {})
    condition = TriggerCondition(
        metric=cond_data.get("metric", "cpu_usage"),
        operator=cond_data.get("operator", ">"),
        value=cond_data.get("value", 90),
        duration_seconds=cond_data.get("duration_seconds", 0),
    )
    trigger = ContextTrigger(
        id="",
        name=args.get("name", "Trigger sans nom"),
        condition=condition,
        actions=args.get("actions", []),
        cooldown_seconds=args.get("cooldown_seconds", 300),
    )
    trigger_id = await get_trigger_engine().add_trigger(trigger)
    return {"success": True, "message": f"Trigger '{trigger.name}' créé (ID: {trigger_id})."}


async def _run_trigger_list(args: dict):
    from core.trigger_engine import get_trigger_engine
    triggers = await get_trigger_engine().list_triggers()
    return {
        "success": True,
        "message": f"{len(triggers)} trigger(s) actif(s).",
        "triggers": [t.to_dict() for t in triggers],
    }


async def _run_trigger_toggle(args: dict):
    from core.trigger_engine import get_trigger_engine
    result = await get_trigger_engine().toggle_trigger(
        args.get("trigger_id", ""), args.get("enabled", True),
    )
    if result:
        return {"success": True, "message": "Trigger mis à jour."}
    return {"success": False, "message": "Trigger introuvable."}


async def _run_workflow_run(args: dict):
    from core.workflow_engine import get_workflow_engine
    return await get_workflow_engine().run_workflow(args.get("workflow_id", ""))


async def _run_workflow_create(args: dict):
    from core.workflow_engine import get_workflow_engine
    return await get_workflow_engine().create_workflow(
        name=args.get("name", ""),
        description=args.get("description", ""),
        steps=args.get("steps", []),
    )


async def _run_workflow_list(args: dict):
    from core.workflow_engine import get_workflow_engine
    workflows = await get_workflow_engine().list_workflows()
    return {
        "success": True,
        "message": f"{len(workflows)} workflow(s) disponible(s).",
        "workflows": workflows,
    }


async def _run_notify(args: dict):
    from tools.notifier import notify
    return await notify(
        message=args.get("message", ""),
        title=args.get("title", "Atlas"),
        duration_seconds=args.get("duration_seconds", 5),
    )


def _run_maintenance_empty_bin(args: dict):
    from tools.system_config import empty_recycle_bin
    result = empty_recycle_bin()
    if not result.get("success") and "Timeout" in (result.get("stderr") or ""):
        return {
            "success": True,
            "message": "Commande corbeille lancée (Windows n'a pas répondu avant timeout).",
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "soft_timeout": True,
        }
    return result


def _run_maintenance_cleanup_temp(args: dict):
    """Nettoie les fichiers temporaires anciens sans PowerShell arbitraire."""
    max_age_days = int(args.get("max_age_days", 7))
    cutoff = time.time() - (max_age_days * 24 * 3600)
    temp_dir = tempfile.gettempdir()

    removed_files = 0
    removed_dirs = 0
    errors = 0

    for root, dirs, files in os.walk(temp_dir, topdown=False):
        for name in files:
            path = os.path.join(root, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed_files += 1
            except Exception:
                errors += 1
        for name in dirs:
            path = os.path.join(root, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    shutil.rmtree(path, ignore_errors=False)
                    removed_dirs += 1
            except Exception:
                errors += 1

    return {
        "success": True,
        "message": f"Temp nettoyé: {removed_files} fichiers, {removed_dirs} dossiers.",
        "removed_files": removed_files,
        "removed_dirs": removed_dirs,
        "errors": errors,
    }


def _run_maintenance_gc(args: dict):
    import gc
    collected = gc.collect()
    return {
        "success": True,
        "message": f"GC exécuté, objets collectés: {collected}.",
        "collected": collected,
    }


# --------------------------------------------------------------------------- #
#  Execution Engine — v2.3 verify + retry pipeline
# --------------------------------------------------------------------------- #

class ExecutionEngine:
    """
    Exécute des ResolvedAction avec vérification + retry.
    Remplace le chemin process_ai_response pour le nouveau pipeline (classifier → validator → engine).
    """

    async def execute(self, resolved, context: dict) -> dict:
        """
        Exécute une seule ResolvedAction avec vérification et retry.
        resolved: ResolvedAction from validator.resolve()
        """
        start_time = time.monotonic()
        retry_count = 0
        tool_name = resolved.tool
        params = resolved.params

        # Special: conversation → no execution
        if tool_name == "__conversation__":
            return {"status": "conversation", "message": params.get("message", "")}

        # F4 v6.0 — apprentissage erreurs : mitigation pré-action (skip_layer appris)
        learned_mitigation = None
        if tool_name == "ui_click_element":
            try:
                from core.error_learning import get_error_learning
                el = get_error_learning()
                intent = getattr(resolved, "intent", None)
                learned_mitigation = el.lookup_mitigation(
                    intent_category=intent.category if intent else "interaction",
                    target=params.get("element_name", ""),
                    app_context=params.get("app_title", ""),
                )
                if learned_mitigation and learned_mitigation.get("strategy") == "skip_layer":
                    skip = learned_mitigation.get("skip_layer")
                    if skip:
                        params = {**params, "_exclude_methods": [skip]}
                        logger.info("[ENGINE] Mitigation apprise : skip couche '%s'", skip)
            except Exception as _e:
                logger.debug("Lookup mitigation échoué : %s", _e)

        idempotent_result = await self._check_idempotence(tool_name, params, context)
        if idempotent_result is not None:
            result = idempotent_result
            result["idempotent_skip"] = True
            logger.info("[ENGINE] Action idempotente skip: %s %s", tool_name, params)
        else:
            result = await execute_tool(tool_name, params, context)

        # P1: Post-click verification for ui_click_element
        click_verified: bool | None = None
        if (
            tool_name == "ui_click_element"
            and result.get("status") == "success"
            and not result.get("idempotent_skip")
        ):
            from tools.grounding import verify_post_click, find_and_click as grounding_click
            app_title = params.get("app_title", "")
            element_name = params.get("element_name", "")
            if app_title and element_name:
                verify = await verify_post_click(app_title, element_name)
                if not verify["verified"]:
                    method_used = (result.get("result") or {}).get("method") or ""
                    exclude = {method_used} if method_used and method_used not in {"all_failed", "none"} else None
                    retry = await grounding_click(app_title, element_name, exclude_methods=exclude)
                    if retry.get("success"):
                        verify2 = await verify_post_click(app_title, element_name)
                    else:
                        verify2 = {"verified": False}
                    if not verify2["verified"]:
                        result["status"] = "replan_required"
                        result["replan_reason"] = f"Clic '{element_name}' exécuté mais état UI inchangé"
                        logger.warning("[ENGINE] Post-click verification failed pour '%s'", element_name)
                        click_verified = False
                    else:
                        click_verified = True
                else:
                    click_verified = True

        # Verification if success
        if result.get("status") == "success" and resolved.verification.type != "none":
            verified = await self._verify(resolved.verification, context)
            if not verified:
                # Retry
                for attempt in range(resolved.verification.retry_count):
                    retry_count += 1
                    logger.info("[ENGINE] Retry %d/%d pour %s", attempt + 1,
                                resolved.verification.retry_count, tool_name)
                    await asyncio.sleep(1.0)
                    result = await execute_tool(tool_name, params, context)
                    if result.get("status") == "success":
                        verified = await self._verify(resolved.verification, context)
                        if verified:
                            break
                if not verified:
                    result["verification_failed"] = True
                    logger.warning("[ENGINE] Vérification échouée après retries pour %s", tool_name)

        # Update world state
        from core.world_state import get_world_state
        ws = get_world_state()
        ws.update_after_action(tool_name, params, result)

        # Structured observability log (v3.1)
        try:
            from core.atlas_logger import log_action

            latency_ms = int((time.monotonic() - start_time) * 1000)
            status = result.get("status", "error")
            if status == "success" and retry_count > 0:
                log_result = "retry_success"
            elif status == "success":
                log_result = "success"
            else:
                log_result = "failure"

            error_msg = None
            error_code = None
            if status != "success":
                error_msg = result.get("message") or result.get("reason") or "execution_error"
                error_code = result.get("error_code") or "ERR_TOOL_EXECUTION_FAILED"

            intent = getattr(resolved, "intent", None)
            target = params.get("target") or params.get("name") or params.get("title") or params.get("workflow_id")

            disambiguation_fired = bool(
                result.get("type") == "disambiguation"
                or result.get("error_code") == "ERR_DISAMBIGUATION_REQUIRED"
            )

            # v5.1 corrective — extract grounding instrumentation for ui_click_element
            grounding_layer_used: str | None = None
            grounding_attempts: list[dict] | None = None
            if tool_name == "ui_click_element":
                inner = result.get("result")
                if isinstance(inner, dict):
                    grounding_layer_used = inner.get("method")
                    grounding_attempts = inner.get("layer_attempts")

            await log_action(
                user_input=context.get("user_input", ""),
                intent_category=intent.category if intent else "unknown",
                intent_verb=intent.verb if intent else "unknown",
                tool=tool_name,
                target=str(target) if target is not None else None,
                result=log_result,
                error=error_msg,
                latency_ms=latency_ms,
                error_code=error_code,
                retry_count=retry_count,
                grounding_layer=grounding_layer_used,
                pipeline_stage="engine",
                click_verified=click_verified,
                disambiguation_triggered=disambiguation_fired,
                grounding_attempts=grounding_attempts,
            )
        except Exception as e:
            logger.debug("Structured log failed: %s", e)

        # F4 v6.0 — apprentissage erreurs : enregistrer l'échec pour mitigation future
        if result.get("status") in ("error", "replan_required") or result.get("verification_failed"):
            try:
                from core.error_learning import get_error_learning, classify_cause
                intent = getattr(resolved, "intent", None)
                cause = classify_cause(
                    result.get("message") or result.get("replan_reason"),
                    result.get("error_code"),
                )
                layer_failed = None
                if tool_name == "ui_click_element":
                    inner = result.get("result") or {}
                    layer_failed = inner.get("method")
                get_error_learning().record_failure(
                    intent_category=intent.category if intent else "unknown",
                    target=params.get("element_name") or params.get("name") or params.get("title") or "",
                    app_context=params.get("app_title") or context.get("foreground_window", {}).get("title", ""),
                    cause=cause,
                    grounding_layer_failed=layer_failed,
                )
            except Exception as _e:
                logger.debug("Record failure échoué : %s", _e)

        return result

    async def execute_plan(self, plan, context: dict, step_callback=None, _depth: int = 0, _seen_signatures: set | None = None) -> list[dict]:
        """
        Exécute un ExecutionPlan étape par étape.
        plan: ExecutionPlan from planner.plan()
        """
        from core.planner import get_planner
        results = []
        total = len(plan.steps)

        if _seen_signatures is None:
            _seen_signatures = set()

        signature = tuple(
            (s.action, s.target, json.dumps(s.params or {}, sort_keys=True, ensure_ascii=False))
            for s in plan.steps
        )
        if signature in _seen_signatures:
            logger.error("[ENGINE] Boucle de replan détectée — arrêt pour éviter récursion infinie")
            return [{
                "status": "error",
                "message": "Boucle de replan détectée. Exécution interrompue.",
                "error_code": "ERR_RECURSION_DETECTED",
            }]
        _seen_signatures.add(signature)

        if _depth >= 2:
            logger.error("[ENGINE] Profondeur de replan maximale atteinte (%d)", _depth)
            return [{
                "status": "error",
                "message": "Nombre maximal de replan atteint.",
                "error_code": "ERR_REPLAN_LIMIT",
            }]

        for idx, step in enumerate(plan.steps):
            step_num = idx + 1

            if step_callback:
                await step_callback(
                    step=step_num, total=total, status="running",
                    message=f"Étape {step_num}/{total}: {step.action} {step.target}",
                )

            if step.resolved:
                result = await self.execute(step.resolved, context)
            else:
                # Fallback: direct tool execution
                result = await execute_tool(
                    step.action,
                    step.params,
                    context,
                )

            results.append({
                "step": step_num,
                "total": total,
                "tool": step.resolved.tool if step.resolved else step.action,
                "params": step.resolved.params if step.resolved else step.params,
                **result,
            })

            if result.get("status") == "error":
                # Replan
                if step_callback:
                    await step_callback(
                        step=step_num, total=total, status="error",
                        message=f"Échec étape {step_num}, tentative de replan...",
                    )
                planner = get_planner()
                new_plan = await planner.replan(
                    plan, idx, result.get("message", "erreur"), context,
                )
                if new_plan.steps:
                    if step_callback:
                        await step_callback(
                            step=step_num, total=total, status="replanning",
                            message="Nouveau plan généré, exécution...",
                        )
                    sub_results = await self.execute_plan(
                        new_plan,
                        context,
                        step_callback,
                        _depth=_depth + 1,
                        _seen_signatures=_seen_signatures,
                    )
                    results.extend(sub_results)
                break

            if result.get("status") == "confirmation_required":
                if step_callback:
                    await step_callback(
                        step=step_num, total=total, status="confirmation",
                        message=result.get("reason", "Confirmation requise"),
                    )
                break

            if step_callback:
                res_msg = ""
                if isinstance(result.get("result"), dict):
                    res_msg = result["result"].get("message", "")
                await step_callback(
                    step=step_num, total=total, status="done",
                    message=res_msg or f"{step.action} terminé",
                )

            if step.wait_for_completion and step_num < total:
                await asyncio.sleep(1.5)

        return results

    async def _check_idempotence(self, tool_name: str, params: dict, context: dict) -> dict | None:
        """Return a synthetic success when action is already effectively done."""
        try:
            if tool_name == "launch_app":
                name = (params.get("name") or "").strip()
                if name:
                    from tools.app_launcher import _is_process_running

                    if _is_process_running(name):
                        return {
                            "status": "success",
                            "result": {"success": True, "message": f"Action déjà accomplie: '{name}' est déjà lancé."},
                        }

            if tool_name == "window_focus":
                target = (params.get("title") or "").strip().lower()
                if target:
                    active = window_controller.window_get_active()
                    if active.get("success"):
                        current = (active.get("title") or "").lower()
                        if target in current:
                            return {
                                "status": "success",
                                "result": {"success": True, "message": f"Action déjà accomplie: '{target}' est déjà active."},
                            }
        except Exception as e:
            logger.debug("Idempotence precheck failed (%s): %s", tool_name, e)

        return None

    async def _verify(self, rule, context: dict) -> bool:
        """Vérifie qu'une action a réussi selon la règle."""
        import asyncio
        await asyncio.sleep(0.5)  # short settle time

        if rule.type == "process_running":
            from tools.app_launcher import _is_process_running
            return _is_process_running(rule.target)

        elif rule.type == "window_visible":
            result = window_controller.window_find(rule.target)
            return result.get("success", False)

        elif rule.type == "url_loaded":
            bridge = browser_bridge.get_bridge()
            if bridge.is_connected():
                result = await bridge.get_url()
                return rule.target.lower() in (result or "").lower()
            return True  # can't verify without bridge

        elif rule.type == "text_in_window":
            # Would require OCR — skip for MVP
            return True

        return True  # "none" type


# Singleton
_engine: ExecutionEngine | None = None


def get_execution_engine() -> ExecutionEngine:
    global _engine
    if _engine is None:
        _engine = ExecutionEngine()
    return _engine


def route_interaction(context: dict) -> str:
    """
    Détermine le mode d'interaction en fonction du contexte système.
    
    Returns:
        "browser_bridge" — si la fenêtre active est un navigateur (utiliser l'extension)
        "window_controller" — sinon (utiliser PyAutoGUI + Win32)
    """
    fg = context.get("foreground_window", {})
    fg_process = (fg.get("process") or "").lower()

    for browser in BROWSER_PROCESSES:
        if browser.lower() in fg_process:
            # Vérifier si le bridge est connecté
            bridge = browser_bridge.get_bridge()
            if bridge.is_connected():
                return "browser_bridge"
            else:
                logger.debug(
                    "Navigateur '%s' détecté mais bridge non connecté — fallback window_controller",
                    fg_process,
                )
                return "window_controller"

    return "window_controller"


def parse_model_response(raw: str) -> dict | list | str:
    """
    Retourne un dict si l'IA veut exécuter UNE action (JSON valide détecté).
    Retourne une list si l'IA veut exécuter une SÉQUENCE d'actions.
    Retourne une str si c'est une réponse texte normale.
    En cas de JSON malformé → logger l'erreur + retourner le texte brut.
    """
    stripped = raw.strip()

    # Tenter le parsing JSON direct (nouveau format strict)
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
            # Séquence multi-actions
            if _is_valid_sequence(parsed):
                return _normalize_sequence(parsed)
            if _is_valid_tool_call(parsed):
                return _normalize_tool_call(parsed)
            # JSON valide mais pas un tool call → texte
            return stripped
        except json.JSONDecodeError as e:
            logger.debug("JSON direct échoué (%s), tentative extraction multi-objets", e)
            # Ne PAS retourner ici — laisser tomber dans les fallbacks ci-dessous

    # Chercher un JSON embarqué dans du texte (fallback pour ancien format)
    # Extraire les blocs ```json ... ``` — utilise extraction par accolades équilibrées
    code_block_starts = [m.end() for m in re.finditer(r'```(?:json)?\s*', stripped)]
    for start_pos in code_block_starts:
        json_obj = _extract_json_object(stripped[start_pos:])
        if json_obj is not None:
            if _is_valid_sequence(json_obj):
                return _normalize_sequence(json_obj)
            if _is_valid_tool_call(json_obj):
                return _normalize_tool_call(json_obj)

    # Extraire TOUS les objets JSON du texte (gère les réponses multi-JSON d'Ollama)
    all_objects = _extract_all_json_objects(stripped)
    # Priorité : préférer une séquence si trouvée, sinon le premier tool call valide
    first_tool_call = None
    for obj in all_objects:
        if _is_valid_sequence(obj):
            return _normalize_sequence(obj)
        if first_tool_call is None and _is_valid_tool_call(obj):
            first_tool_call = obj
    if first_tool_call is not None:
        return _normalize_tool_call(first_tool_call)

    return stripped


def _is_valid_tool_call(obj: dict) -> bool:
    """Vérifie si le dict est un appel d'outil valide (nouveau ou ancien format)."""
    # Nouveau format: {"action": "...", "params": {...}}
    if "action" in obj and obj["action"] in VALID_ACTIONS:
        return True
    # Ancien format: {"tool": "...", "args": {...}}
    if "tool" in obj and obj["tool"] in VALID_ACTIONS:
        return True
    # Format imbriqué Mistral: {"response": {"action": "...", ...}}
    if "response" in obj and isinstance(obj["response"], dict):
        inner = obj["response"]
        if ("action" in inner and inner["action"] in VALID_ACTIONS) or \
           ("tool" in inner and inner["tool"] in VALID_ACTIONS):
            return True
    return False


def _is_valid_sequence(obj: dict) -> bool:
    """Vérifie si le dict est une séquence multi-actions valide."""
    if "sequence" not in obj or not isinstance(obj["sequence"], list):
        return False
    if len(obj["sequence"]) == 0:
        return False
    # Chaque élément doit être un tool call valide
    return all(_is_valid_tool_call(step) for step in obj["sequence"])


def _normalize_tool_call(obj: dict) -> dict:
    """Normalise vers le format interne {"tool": ..., "args": ...}."""
    if "action" in obj:
        return {
            "tool": obj["action"],
            "args": obj.get("params", obj.get("args", {})),
            "confirmation_required": obj.get("confirmation_required", False),
            "reason": obj.get("reason", ""),
            "wait_for_completion": obj.get("wait_for_completion", True),
        }
    # Déjà en format legacy
    return obj


def _normalize_sequence(obj: dict) -> list[dict]:
    """Normalise une séquence en liste de tool calls internes."""
    steps = []
    for step in obj["sequence"]:
        normalized = _normalize_tool_call(step)
        steps.append(normalized)
    return steps


def _extract_json_object(text: str) -> dict | None:
    """Extrait le premier objet JSON valide du texte par accolades équilibrées."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None
    return None


def _extract_all_json_objects(text: str) -> list[dict]:
    """Extrait tous les objets JSON valides du texte (gère les multi-JSON concaténés)."""
    objects = []
    remaining = text
    while remaining:
        obj = _extract_json_object(remaining)
        if obj is None:
            break
        objects.append(obj)
        # Avancer après le premier objet trouvé pour chercher le suivant
        start = remaining.find("{")
        depth = 0
        in_string = False
        escape = False
        end_pos = None
        for i in range(start, len(remaining)):
            c = remaining[i]
            if escape:
                escape = False
                continue
            if c == '\\':
                escape = True
                continue
            if c == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end_pos = i + 1
                    break
        if end_pos is None:
            break
        remaining = remaining[end_pos:]
    return objects


def extract_tool_calls(text: str) -> list[dict[str, Any]]:
    """
    Parse le texte de l'IA pour trouver les appels d'outils.
    Utilise parse_model_response pour le parsing strict.
    Retourne une liste de dicts {"tool": ..., "args": ...}.
    Gère les séquences multi-actions (retourne la liste directement).
    """
    result = parse_model_response(text)
    if isinstance(result, list):
        # Séquence multi-actions
        return result
    if isinstance(result, dict):
        return [result]
    return []


# --------------------------------------------------------------------------- #
#  Execute a single tool call
# --------------------------------------------------------------------------- #

async def execute_tool(tool_name: str, args: dict, context: dict) -> dict[str, Any]:
    """
    Exécute un appel d'outil. Retourne le résultat ou une demande de confirmation.
    Intègre route_interaction() comme filet de sécurité pour corriger le routage.
    """
    # ------------------------------------------------------------------ #
    #  Routage automatique — filet de sécurité
    # ------------------------------------------------------------------ #
    INTERACTION_ACTIONS = {
        "window_type", "window_click", "window_hotkey",
        "window_focus", "window_screenshot",
        "browser_navigate", "browser_new_tab",
        "browser_ext_click", "browser_ext_type",
        "browser_ext_scroll", "browser_ext_get_content",
    }

    # Rediriger browser_open (Playwright legacy) → browser_navigate si bridge connecté
    if tool_name == "browser_open":
        bridge = browser_bridge.get_bridge()
        if bridge.is_connected():
            logger.warning(
                "[ROUTAGE] Redirection browser_open → browser_navigate (bridge connecté)"
            )
            tool_name = "browser_navigate"
            # browser_navigate attend "url", browser_open aussi — compatible
        # Si bridge pas connecté, laisser browser_open avec sa confirmation

    if tool_name in INTERACTION_ACTIONS:
        correct_route = route_interaction(context)

        # Ollama a choisi un outil browser sur une app native → corriger
        if correct_route == "window_controller" and tool_name.startswith("browser_"):
            app_name = args.get("target", args.get("app_name", ""))
            logger.warning(
                "[ROUTAGE] Correction : %s → window_focus(%s)", tool_name, app_name
            )
            tool_name = "window_focus"
            if app_name:
                args = {"title": app_name}

        # Ollama a choisi un outil window sur un navigateur → juste logger
        elif correct_route == "browser_bridge" and tool_name.startswith("window_"):
            logger.warning(
                "[ROUTAGE] Navigateur détecté au premier plan, bridge recommandé"
            )

    # ------------------------------------------------------------------ #
    #  Vérification handler
    # ------------------------------------------------------------------ #
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return {
            "status": "error",
            "message": f"Outil inconnu : '{tool_name}'",
            "error_code": "ERR_UNKNOWN_TOOL",
        }

    # Confirmation stricte pour actions sensibles (même en mode automatique)
    if tool_name == "kill_process" or (
        tool_name == "system_config" and str(args.get("action", "")).lower() in {"shutdown", "restart", "hibernate", "sleep"}
    ):
        conf = needs_confirmation(tool_name, args, context)
        confirmation_id = str(uuid.uuid4())[:8]
        conf = conf or {
            "reason": "Action sensible.",
            "level": "🟡 DEMANDE",
            "target": args.get("name") or args.get("action") or "system",
            "suggestion": "Confirmation obligatoire.",
        }
        store_pending(confirmation_id, tool_name, args, conf)
        return {
            "status": "confirmation_required",
            "confirmation_id": confirmation_id,
            "reason": conf["reason"],
            "level": conf["level"],
            "suggestion": conf.get("suggestion"),
            "target": conf.get("target"),
            "error_code": "ERR_CONFIRMATION_REQUIRED",
        }

    # Forcer la confirmation avant toute navigation externe (browser_open legacy)
    if tool_name == "browser_open":
        target_url = args.get("url", "")
        confirmation_id = str(uuid.uuid4())[:8]
        conf = {
            "reason": f"Ouverture du navigateur vers : {target_url}",
            "level": "🟡 DEMANDE",
            "target": target_url,
            "suggestion": "Confirmez-vous l'ouverture de cette URL externe ?",
        }
        store_pending(confirmation_id, tool_name, args, conf)
        return {
            "status": "confirmation_required",
            "confirmation_id": confirmation_id,
            "reason": conf["reason"],
            "level": conf["level"],
            "suggestion": conf.get("suggestion"),
            "target": conf.get("target"),
        }

    # Vérifier si confirmation nécessaire
    conf = needs_confirmation(tool_name, args, context)
    if conf:
        confirmation_id = str(uuid.uuid4())[:8]
        store_pending(confirmation_id, tool_name, args, conf)
        return {
            "status": "confirmation_required",
            "confirmation_id": confirmation_id,
            "reason": conf["reason"],
            "level": conf["level"],
            "suggestion": conf.get("suggestion"),
            "target": conf.get("target"),
            "error_code": "ERR_CONFIRMATION_REQUIRED",
        }

    # Exécuter directement
    try:
        result = handler(args)
        if inspect.isawaitable(result):
            result = await result

        # P2: Grounding disambiguation — surface as confirmation_required
        if isinstance(result, dict) and result.get("type") == "disambiguation_required":
            return {
                "status": "confirmation_required",
                "type": "disambiguation",
                "confirmation_id": result.get("confirmation_id"),
                "message": result.get("message", ""),
                "candidates": result.get("candidates", []),
                "error_code": "ERR_DISAMBIGUATION_REQUIRED",
            }

        # Normalize tool payload failures into pipeline error status.
        if isinstance(result, dict) and result.get("success") is False:
            message = result.get("message") or f"Echec outil: {tool_name}"
            logger.warning("Tool '%s' returned success=false: %s", tool_name, message)
            return {
                "status": "error",
                "message": message,
                "error_code": "ERR_TOOL_RESULT_FAILURE",
                "result": result,
            }

        logger.info("Tool '%s' executed: %s", tool_name, args)

        # Sauvegarder l'action en mémoire long terme
        _save_action_to_memory(tool_name, args, result, context)

        return {
            "status": "success",
            "result": result,
        }
    except Exception as e:
        logger.error("Tool '%s' failed: %s", tool_name, e, exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "error_code": "ERR_TOOL_EXECUTION_FAILED",
        }


# --------------------------------------------------------------------------- #
#  Process IA response — parse + execute
# --------------------------------------------------------------------------- #

async def execute_sequence(
    sequence: list[dict], context: dict, step_callback=None
) -> list[dict[str, Any]]:
    """
    Exécute une liste d'actions dans l'ordre.
    - Respecte wait_for_completion pour les actions dépendantes
    - Si une action échoue → stopper la séquence + notifier l'utilisateur
    - Si une action nécessite confirmation → mettre la séquence en pause,
      stocker les étapes restantes pour reprise après confirmation
    - Retourner le résultat de chaque étape : {tool, args, status, result, error}
    """
    results: list[dict[str, Any]] = []
    total = len(sequence)

    for idx, tc in enumerate(sequence):
        tool_name = tc["tool"]
        args = tc.get("args", {})
        step_num = idx + 1

        # Notify step start
        if step_callback:
            await step_callback(
                step=step_num, total=total, status="running",
                message=f"Exécution : {tool_name} {tc.get('reason', '')}".strip(),
            )

        result = await execute_tool(tool_name, args, context)

        step_result = {
            "tool": tool_name,
            "args": args,
            "step": step_num,
            "total": total,
            **result,
        }
        results.append(step_result)

        if result["status"] == "confirmation_required":
            # Store remaining steps for resumption after confirmation
            remaining = sequence[idx + 1:]
            if remaining:
                step_result["remaining_sequence"] = remaining
            if step_callback:
                await step_callback(
                    step=step_num, total=total, status="confirmation",
                    message=result.get("reason", "Confirmation requise"),
                )
            break

        if result["status"] == "error":
            # Stop sequence on error
            logger.warning(
                "Séquence arrêtée à l'étape %d/%d : %s a échoué — %s",
                step_num, total, tool_name, result.get("message", ""),
            )
            if step_callback:
                await step_callback(
                    step=step_num, total=total, status="error",
                    message=f"Échec de {tool_name} : {result.get('message', 'erreur inconnue')}",
                )
            break

        # Step done
        if step_callback:
            res_msg = ""
            if isinstance(result.get("result"), dict):
                res_msg = result["result"].get("message", "")
            await step_callback(
                step=step_num, total=total, status="done",
                message=res_msg or f"{tool_name} terminé",
            )

        # If wait_for_completion, add a short delay for dependent actions
        if tc.get("wait_for_completion", True) and step_num < total:
            import asyncio
            await asyncio.sleep(1.5)

    return results


async def process_ai_response(
    ai_text: str, context: dict, step_callback=None
) -> dict[str, Any]:
    """
    Analyse la réponse de l'IA, exécute les outils demandés,
    retourne la réponse enrichie.
    Gère les séquences multi-actions.
    """
    tool_calls = extract_tool_calls(ai_text)

    if not tool_calls:
        # Pas d'appel d'outil — réponse textuelle pure
        return {
            "type": "text",
            "message": ai_text,
            "tool_results": [],
        }

    is_sequence = len(tool_calls) > 1

    if is_sequence:
        # Multi-actions — exécuteur séquentiel
        results = await execute_sequence(tool_calls, context, step_callback)
    else:
        # Single action
        tc = tool_calls[0]
        tool_name = tc["tool"]
        args = tc.get("args", {})
        result = await execute_tool(tool_name, args, context)
        results = [{"tool": tool_name, "args": args, **result}]

    # Nettoyer le texte IA des blocs JSON pour l'affichage
    clean_text = ai_text
    # Supprimer les blocs ```json...```
    clean_text = re.sub(r'```(?:json)?\s*\{[\s\S]*?\}\s*```', '', clean_text)
    # Supprimer tous les objets JSON (accolades équilibrées)
    while True:
        start = clean_text.find('{')
        if start == -1:
            break
        obj = _extract_json_object(clean_text[start:])
        if obj is None:
            # Accolade orpheline — supprimer
            clean_text = clean_text[:start] + clean_text[start + 1:]
            continue
        # Trouver la fin de l'objet JSON dans le texte
        depth = 0
        in_string = False
        escape = False
        end_pos = None
        for i in range(start, len(clean_text)):
            c = clean_text[i]
            if escape:
                escape = False
                continue
            if c == '\\':
                escape = True
                continue
            if c == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end_pos = i + 1
                    break
        if end_pos is None:
            break
        clean_text = clean_text[:start] + clean_text[end_pos:]
    clean_text = clean_text.strip()

    # Si pas de texte explicatif, générer un résumé des actions
    if not clean_text and results:
        summaries = []
        for r in results:
            tool = r.get("tool", "")
            status = r.get("status", "")
            res = r.get("result", {})
            if isinstance(res, dict):
                msg = res.get("message", "")
            else:
                msg = str(res)[:100]
            if msg:
                summaries.append(msg)
        clean_text = " — ".join(summaries) if summaries else None

    return {
        "type": "sequence" if is_sequence else "tool_execution",
        "message": clean_text if clean_text else None,
        "tool_results": results,
    }


# --------------------------------------------------------------------------- #
#  Execute confirmed action
# --------------------------------------------------------------------------- #

async def execute_confirmed(confirmation_id: str, context: dict) -> dict[str, Any]:
    """Exécute une action précédemment mise en attente de confirmation."""
    from core.confirmation import resolve_pending

    pending = resolve_pending(confirmation_id)
    if not pending:
        return {"status": "error", "message": "Confirmation expirée ou invalide."}

    tool_name = pending["tool"]
    args = pending["args"]
    handler = TOOL_HANDLERS.get(tool_name)

    if not handler:
        return {"status": "error", "message": f"Outil inconnu: {tool_name}"}

    try:
        result = handler(args)
        if inspect.isawaitable(result):
            result = await result
        logger.info("Confirmed tool '%s' executed: %s", tool_name, args)

        # Sauvegarder l'action confirmée en mémoire
        _save_action_to_memory(tool_name, args, result, context)

        return {"status": "success", "result": result}
    except Exception as e:
        logger.error("Confirmed tool '%s' failed: %s", tool_name, e, exc_info=True)
        return {"status": "error", "message": str(e)}


def save_rejection(confirmation_id: str, tool_name: str, args: dict, context: dict):
    """Sauvegarde le refus d'une action comme correction en mémoire."""
    mem = get_memory_manager()
    fg = context.get("foreground_window", {})
    context_desc = f"foreground={fg.get('process', '?')}, cpu={context.get('cpu_usage', '?')}%, ram={context.get('ram_usage', '?')}%"
    mem.save(
        category="correction",
        content=f"L'utilisateur a refusé l'action '{tool_name}' avec args={json.dumps(args, ensure_ascii=False)} dans ce contexte : {context_desc}. Ne pas reproduire.",
        metadata={
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "target": args.get("name", args.get("pid", "")),
        },
    )


# --------------------------------------------------------------------------- #
#  Memory helpers
# --------------------------------------------------------------------------- #

def _save_action_to_memory(tool_name: str, args: dict, result: Any, context: dict):
    """Sauvegarde une action exécutée avec succès dans la mémoire long terme."""
    try:
        mem = get_memory_manager()
        result_msg = ""
        if isinstance(result, dict):
            result_msg = result.get("message", json.dumps(result, ensure_ascii=False, default=str)[:200])
        else:
            result_msg = str(result)[:200]

        content = f"Action '{tool_name}' exécutée. Args: {json.dumps(args, ensure_ascii=False)}. Résultat: {result_msg}"

        fg = context.get("foreground_window", {})
        mem.save(
            category="action_history",
            content=content,
            metadata={
                "timestamp": datetime.now().isoformat(),
                "tool": tool_name,
                "target": str(args.get("name", args.get("pid", args.get("command", "")))),
                "foreground": fg.get("process", ""),
            },
        )
    except Exception as e:
        logger.debug("Erreur sauvegarde action en mémoire : %s", e)
