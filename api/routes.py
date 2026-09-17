"""
Routes FastAPI — Endpoints de l'assistant.
Architecture v2.3 : Classifier → Validator/Planner → ExecutionEngine
"""

import asyncio
import json
import logging
import pathlib
import time
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi import Body
from fastapi.responses import StreamingResponse
import httpx

from api.models import ChatRequest, ConfirmationResponse, MemoryIngestRequest
from core.context_monitor import collect_context
from core.ollama_client import chat_stream, chat_full, OllamaStreamTimeout, STREAM_TIMEOUT
from core.intent_engine import process_ai_response, execute_confirmed, save_rejection, get_execution_engine
from core.intent_classifier import get_classifier
from core.validator import get_validator
from core.planner import get_planner
from core.world_state import get_world_state
from core.memory_manager import get_memory_manager
from core.file_indexer import get_file_indexer
from core.file_organizer import build_reorg_plan, apply_reorg_plan, rollback_reorg
from tools.diagnostics import full_diagnostics
from tools.process_manager import list_processes, find_process, get_process_details
from tools.app_launcher import KNOWN_APPS

logger = logging.getLogger("atlas.routes")

router = APIRouter()

# --------------------------------------------------------------------------- #
#  Adaptive timeout helper
# --------------------------------------------------------------------------- #

_WEB_TOOLS = {"web_search", "read_url", "browser_open"}


def _api_error(message: str, error_code: str, *, details: str | None = None, tool_results: list | None = None) -> dict:
    payload = {
        "type": "error",
        "message": message,
        "error_code": error_code,
        "tool_results": tool_results or [],
    }
    if details:
        payload["details"] = details
    return payload


def _compute_timeout(user_message: str, full_response: str = "") -> int:
    """
    Timeout adaptatif selon la complexité de la requête.
    - Simple (< 50 tokens) → STREAM_TIMEOUT
    - Outils web détectés   → x2
    - Séquence multi-actions → x3
    """
    base = STREAM_TIMEOUT
    token_estimate = len(user_message.split())

    # Check if web tools or sequence in response
    has_web = any(kw in full_response.lower() for kw in ("web_search", "read_url", "browser_open"))
    has_sequence = '"sequence"' in full_response

    if has_sequence:
        return base * 3
    if has_web or token_estimate > 80:
        return base * 2
    return base


# --------------------------------------------------------------------------- #
#  Chat — non-streaming
# --------------------------------------------------------------------------- #

@router.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """
    Endpoint principal v2.3 :
    1. Classifier détecte l'intention
    2. Si conversation → LLM text response
    3. Si action simple → Validator → ExecutionEngine
    4. Si complexe → Planner → ExecutionEngine
    """
    context = collect_context()
    context["user_input"] = req.message
    ws = get_world_state()
    ws.update_from_context(context)

    mem = get_memory_manager()
    memories = mem.recall_for_prompt(req.message)
    mem.add_to_session("user", req.message)
    ws.add_to_history("user", req.message)

    # --- Step 1: Classify intent ---
    classifier = get_classifier()
    intent = classifier.classify(req.message, context)
    logger.info("[V2.3] Intent: cat=%s verb=%s target=%s conf=%.2f complex=%s",
                intent.category, intent.verb, intent.target, intent.confidence, intent.is_complex)

    # --- Step 2: Route based on classification ---
    if intent.category == "conversation" or intent.confidence < 0.5:
        # Pure conversation → LLM streaming (non-streaming here)
        full_response = ""
        try:
            async for token in chat_stream(req.message, context, req.history, memories=memories):
                full_response += token
        except (httpx.ReadTimeout, asyncio.TimeoutError) as e:
            logger.warning("Ollama timeout on /chat : %s", e)
            return _api_error(
                f"Atlas met trop de temps à répondre (timeout {STREAM_TIMEOUT}s).",
                "ERR_MODEL_TIMEOUT",
                details=str(e),
            )
        except Exception as e:
            logger.warning("Ollama error on /chat : %s", e)
            return _api_error(
                "Le modèle local est indisponible pour le moment.",
                "ERR_MODEL_UNAVAILABLE",
                details=str(e),
            )
        # P2 v6.0.1 — garde linguistique : retry FR si dérive non-latine détectée
        from core.ollama_client import contains_non_latin_script, chat_full
        if contains_non_latin_script(full_response):
            logger.warning("[LANG] Dérive détectée sur /chat — retry FR strict.")
            try:
                full_response = await chat_full(req.message, context, req.history, memories=memories)
            except Exception:
                from core.ollama_client import LANG_FALLBACK_MESSAGE
                full_response = LANG_FALLBACK_MESSAGE
        mem.add_to_session("assistant", full_response)
        ws.add_to_history("assistant", full_response)
        # F4 — ingestion conversation (long terme, non bloquant si échec)
        try:
            mem.ingest_conversation(req.message, full_response,
                                    intent_category=intent.category, success=True)
        except Exception as _e:
            logger.debug("Ingestion conversation échouée : %s", _e)
        return {"type": "text", "message": full_response, "tool_results": []}

    # --- Step 3: Action execution ---
    validator = get_validator()
    engine = get_execution_engine()

    if intent.is_complex:
        # Complex → Planner → ExecutionEngine
        planner = get_planner()
        plan = await planner.plan(intent, context)
        results = await engine.execute_plan(plan, context)
    else:
        # Simple → Validator → ExecutionEngine
        resolved = validator.resolve(intent, context)
        if resolved.tool == "__conversation__":
            # Validator decided it's conversation after all
            full_response = ""
            try:
                async for token in chat_stream(req.message, context, req.history, memories=memories):
                    full_response += token
            except (httpx.ReadTimeout, asyncio.TimeoutError):
                return _api_error("Timeout Atlas.", "ERR_MODEL_TIMEOUT")
            except Exception:
                return _api_error("Le modèle local est indisponible.", "ERR_MODEL_UNAVAILABLE")
            mem.add_to_session("assistant", full_response)
            ws.add_to_history("assistant", full_response)
            try:
                mem.ingest_conversation(req.message, full_response,
                                        intent_category=intent.category, success=True)
            except Exception as _e:
                logger.debug("Ingestion conversation échouée : %s", _e)
            return {"type": "text", "message": full_response, "tool_results": []}

        result = await engine.execute(resolved, context)
        results = [{"tool": resolved.tool, "params": resolved.params, **result}]

    # P2: Propagate grounding disambiguation to client before building response
    for r in results:
        if r.get("type") == "disambiguation":
            return {
                "type": "disambiguation_required",
                "confirmation_id": r.get("confirmation_id"),
                "message": r.get("message", "Confirmation requise"),
                "candidates": r.get("candidates", []),
            }

    # Build response message
    summaries = []
    for r in results:
        res = r.get("result", {})
        if isinstance(res, dict):
            msg = res.get("message", "")
        else:
            msg = str(res)[:200]
        if msg:
            summaries.append(msg)

    clean_text = " — ".join(summaries) if summaries else None
    ws.last_action_raw = req.message

    return {
        "type": "tool_execution",
        "message": clean_text,
        "tool_results": results,
    }


# --------------------------------------------------------------------------- #
#  Chat — streaming with keepalive + step feedback
# --------------------------------------------------------------------------- #

@router.post("/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    """
    Endpoint streaming v2.3 :
    - Classifier détecte l'intention
    - Conversation → stream LLM tokens via SSE
    - Action → thinking event + execute + result event
    """
    context = collect_context()
    context["user_input"] = req.message
    ws = get_world_state()
    ws.update_from_context(context)

    mem = get_memory_manager()
    memories = mem.recall_for_prompt(req.message)
    mem.add_to_session("user", req.message)
    ws.add_to_history("user", req.message)

    # Classify upfront
    classifier = get_classifier()
    intent = classifier.classify(req.message, context)
    logger.info("[V2.3-STREAM] Intent: cat=%s verb=%s target=%s conf=%.2f complex=%s",
                intent.category, intent.verb, intent.target, intent.confidence, intent.is_complex)

    async def generate() -> AsyncGenerator[str, None]:
        # --- Conversation route → stream LLM ---
        if intent.category == "conversation" or intent.confidence < 0.5:
            full_response = ""
            last_activity = time.monotonic()
            try:
                token_iter = chat_stream(req.message, context, req.history, memories=memories).__aiter__()
                while True:
                    try:
                        token = await asyncio.wait_for(token_iter.__anext__(), timeout=5.0)
                        last_activity = time.monotonic()
                        full_response += token
                        yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        elapsed = time.monotonic() - last_activity
                        adaptive_timeout = _compute_timeout(req.message, full_response)
                        if elapsed > adaptive_timeout:
                            yield f"data: {json.dumps({'type': 'error', 'message': f'Timeout ({int(elapsed)}s)'}, ensure_ascii=False)}\n\n"
                            yield "data: [DONE]\n\n"
                            return
                        yield f"data: {json.dumps({'type': 'keepalive'}, ensure_ascii=False)}\n\n"
                        continue
            except httpx.ConnectError:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Ollama injoignable.'}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Erreur: {e}'}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            mem.add_to_session("assistant", full_response)
            ws.add_to_history("assistant", full_response)
            yield f"data: {json.dumps({'type': 'result', 'content': {'type': 'text', 'message': full_response, 'tool_results': []}}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

        # --- Action route → execute tools ---
        yield f"data: {json.dumps({'type': 'thinking', 'content': '⏳ Exécution en cours...'}, ensure_ascii=False)}\n\n"

        step_events = []

        async def step_callback(step, total, status, message):
            step_events.append(
                f"data: {json.dumps({'type': 'step', 'step': step, 'total': total, 'status': status, 'message': message}, ensure_ascii=False)}\n\n"
            )

        validator = get_validator()
        engine = get_execution_engine()

        if intent.is_complex:
            planner = get_planner()
            plan = await planner.plan(intent, context)
            results = await engine.execute_plan(plan, context, step_callback)
        else:
            resolved = validator.resolve(intent, context)
            if resolved.tool == "__conversation__":
                # Fallback to LLM
                full_response = ""
                try:
                    async for token in chat_stream(req.message, context, req.history, memories=memories):
                        full_response += token
                        yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
                except Exception:
                    pass
                mem.add_to_session("assistant", full_response)
                ws.add_to_history("assistant", full_response)
                yield f"data: {json.dumps({'type': 'result', 'content': {'type': 'text', 'message': full_response, 'tool_results': []}}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            result = await engine.execute(resolved, context)
            results = [{"tool": resolved.tool, "params": resolved.params, **result}]

        # Yield step events
        for evt in step_events:
            yield evt

        # Build summary
        summaries = []
        for r in results:
            res = r.get("result", {})
            if isinstance(res, dict):
                msg = res.get("message", "")
            else:
                msg = str(res)[:200]
            if msg:
                summaries.append(msg)

        clean_text = " — ".join(summaries) if summaries else None
        ws.last_action_raw = req.message

        final_result = {
            "type": "tool_execution",
            "message": clean_text,
            "tool_results": results,
        }

        yield f"data: {json.dumps({'type': 'result', 'content': final_result}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --------------------------------------------------------------------------- #
#  Confirmation
# --------------------------------------------------------------------------- #

@router.post("/confirm")
async def confirm_endpoint(req: ConfirmationResponse):
    """Confirme ou rejette une action en attente."""
    context = collect_context()

    if not req.accepted:
        # Sauvegarder le refus comme correction en mémoire
        from core.confirmation import get_pending
        pending = get_pending(req.confirmation_id)
        if pending:
            save_rejection(
                req.confirmation_id,
                pending.get("tool", ""),
                pending.get("args", {}),
                context,
            )
        return {"status": "cancelled", "message": "Action annulée — je m'en souviendrai."}

    result = await execute_confirmed(req.confirmation_id, context)
    return result


@router.get("/logs/recent")
async def get_recent_logs(limit: int = 50):
    """Retourne les N dernières actions loguées."""
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    if limit > 500:
        limit = 500

    log_file = pathlib.Path(__file__).resolve().parent.parent / "data" / "atlas_actions.jsonl"
    if not log_file.exists():
        return {"count": 0, "logs": []}

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        recent_lines = lines[-limit:]

        logs = []
        for line in recent_lines:
            line = line.strip()
            if not line:
                continue
            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        return {"count": len(logs), "logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read logs: {e}")


@router.get("/health")
async def api_health():
    """Global health for core dependencies and voice runtime."""
    from core.voice_engine import get_voice_engine

    settings_path = pathlib.Path(__file__).resolve().parent.parent / "config" / "settings.json"
    with open(settings_path, encoding="utf-8") as f:
        cfg = json.load(f)

    web_cfg = cfg.get("web", {})
    mem = get_memory_manager()

    ollama_ok = False
    searxng_ok = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            ollama_resp = await client.get("http://127.0.0.1:11434/api/tags")
            ollama_ok = ollama_resp.status_code == 200
    except Exception:
        ollama_ok = False

    try:
        searx_url = web_cfg.get("searxng_url", "http://localhost:8888")
        async with httpx.AsyncClient(timeout=2.0) as client:
            sx_resp = await client.get(f"{searx_url}/search", params={"q": "atlas health", "format": "json"})
            searxng_ok = sx_resp.status_code == 200
    except Exception:
        searxng_ok = False

    voice_status = {"enabled": bool(cfg.get("voice", {}).get("enabled", False)), "running": False}
    try:
        voice = get_voice_engine()
        voice_status["running"] = bool(getattr(voice, "_running", False))
    except Exception:
        pass

    # Tesseract OCR probe
    import subprocess as _sp
    tesseract_ok = False
    tesseract_version: str | None = None
    try:
        _tr = _sp.run(["tesseract", "--version"], capture_output=True, text=True, timeout=3.0)
        tesseract_ok = _tr.returncode == 0
        if tesseract_ok:
            tesseract_version = (_tr.stdout or "").strip().split("\n")[0] or None
    except Exception:
        pass

    grounding_cfg = cfg.get("grounding", {})
    vision_enabled = bool(grounding_cfg.get("vision_enabled", True))

    services = {
        "ollama": {"ok": ollama_ok},
        "chromadb": {"ok": mem.is_connected()},
        "searxng": {"ok": searxng_ok},
        "voice": voice_status,
    }
    global_ok = all([services["ollama"]["ok"], services["chromadb"]["ok"], services["searxng"]["ok"]])

    return {
        "status": "ok" if global_ok else "degraded",
        "services": services,
        "tesseract_status": {"ok": tesseract_ok, "version": tesseract_version},
        "vision_enabled": vision_enabled,
    }


@router.get("/errors/recent")
async def recent_actionable_errors(limit: int = 20):
    """Return recent actionable pipeline errors from structured atlas actions."""
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    if limit > 200:
        limit = 200

    log_file = pathlib.Path(__file__).resolve().parent.parent / "data" / "atlas_actions.jsonl"
    if not log_file.exists():
        return {"count": 0, "errors": []}

    fixes = {
        "ERR_MODEL_TIMEOUT": "Vérifier charge CPU/GPU et augmenter stream_timeout_seconds.",
        "ERR_MODEL_UNAVAILABLE": "Vérifier qu'Ollama tourne sur le port 11434.",
        "ERR_UNKNOWN_TOOL": "Vérifier la table TOOL_HANDLERS et le validator.",
        "ERR_TOOL_EXECUTION_FAILED": "Consulter message d'erreur et logs système pour l'outil concerné.",
        "ERR_RECURSION_DETECTED": "Analyser la logique de plan/replan pour éviter la boucle.",
        "ERR_REPLAN_LIMIT": "Réduire la complexité du plan ou renforcer les règles validator.",
    }

    errors = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            if item.get("result") not in {"failure"} and not item.get("error"):
                continue

            error_code = item.get("error_code") or "ERR_TOOL_EXECUTION_FAILED"
            errors.append(
                {
                    "timestamp": item.get("timestamp"),
                    "tool": item.get("tool"),
                    "error": item.get("error") or "unknown_error",
                    "error_code": error_code,
                    "actionable_fix": fixes.get(error_code, "Consulter les logs détaillés et reproduire localement."),
                }
            )

    recent = errors[-limit:]
    return {"count": len(recent), "errors": recent}


# --------------------------------------------------------------------------- #
#  Context
# --------------------------------------------------------------------------- #

@router.get("/context")
async def get_context():
    """Retourne le contexte système actuel."""
    return collect_context()


# --------------------------------------------------------------------------- #
#  Diagnostics
# --------------------------------------------------------------------------- #

@router.get("/diagnostics")
async def get_diagnostics():
    """Retourne un rapport complet de diagnostics."""
    return full_diagnostics()


# --------------------------------------------------------------------------- #
#  Processes
# --------------------------------------------------------------------------- #

@router.get("/processes")
async def get_processes(sort_by: str = "memory", limit: int = 30):
    return list_processes(sort_by=sort_by, limit=limit)


@router.get("/processes/search/{name}")
async def search_processes(name: str):
    return find_process(name)


@router.get("/processes/{pid}")
async def get_process(pid: int):
    return get_process_details(pid)


# --------------------------------------------------------------------------- #
#  Apps connues
# --------------------------------------------------------------------------- #

@router.get("/apps")
async def get_known_apps():
    """Liste les applications connues par l'assistant."""
    return {name: paths for name, paths in KNOWN_APPS.items()}


@router.get("/files/index/status")
async def files_index_status():
    """Filesystem assistant index status."""
    return get_file_indexer().status()


@router.post("/files/index/rebuild")
async def files_index_rebuild():
    """Run one immediate indexing pass (manual trigger)."""
    status = await get_file_indexer().run_once()
    return {"status": "ok", "index": status}


@router.get("/files/search")
async def files_search(query: str, limit: int = 20):
    """Search indexed local files by name/path."""
    matches = await get_file_indexer().search(query, limit)
    return {"count": len(matches), "results": matches}


@router.post("/files/organize/plan")
async def files_organize_plan(payload: dict = Body(...)):
    """Build a safe file organization plan (no file move)."""
    root_dir = payload.get("root_dir", "")
    max_ops = int(payload.get("max_ops", 300))
    return build_reorg_plan(root_dir=root_dir, max_ops=max_ops)


@router.post("/files/organize/apply")
async def files_organize_apply(payload: dict = Body(...)):
    """
    Apply a previously generated plan.
    Requires explicit allow_apply=true to prevent accidental execution.
    """
    allow_apply = bool(payload.get("allow_apply", False))
    if not allow_apply:
        return {
            "success": False,
            "message": "Apply bloque: envoyez allow_apply=true pour executer le plan.",
            "moved": 0,
            "errors": [],
        }

    plan = payload.get("plan", {})
    max_apply = int(payload.get("max_apply", 300))
    return apply_reorg_plan(plan=plan, max_apply=max_apply)


@router.post("/files/organize/rollback")
async def files_organize_rollback(payload: dict = Body(...)):
    """Rollback a previous apply operation using operation_id."""
    operation_id = str(payload.get("operation_id", "")).strip()
    if not operation_id:
        return {
            "success": False,
            "message": "operation_id requis",
            "restored": 0,
            "errors": [],
        }

    max_restore = int(payload.get("max_restore", 300))
    return rollback_reorg(operation_id=operation_id, max_restore=max_restore)


# --------------------------------------------------------------------------- #
#  Memory
# --------------------------------------------------------------------------- #

@router.get("/memory/stats")
async def memory_stats():
    """Statistiques de la mémoire."""
    mem = get_memory_manager()
    return mem.stats()


@router.get("/memory/recall")
async def memory_recall(query: str, top_k: int = 5, category: str | None = None):
    """Recherche des souvenirs par requête."""
    mem = get_memory_manager()
    return mem.recall(query, top_k=top_k, category=category)


@router.delete("/memory/{memory_id}")
async def memory_forget(memory_id: str):
    """Supprime un souvenir spécifique."""
    mem = get_memory_manager()
    success = mem.forget(memory_id)
    if success:
        return {"status": "ok", "message": f"Souvenir '{memory_id}' supprimé."}
    return {"status": "error", "message": "Souvenir introuvable ou ChromaDB indisponible."}


@router.delete("/memory/category/{category}")
async def memory_forget_category(category: str):
    """Supprime tous les souvenirs d'une catégorie."""
    mem = get_memory_manager()
    count = mem.forget_category(category)
    return {"status": "ok", "message": f"{count} souvenir(s) supprimé(s) de '{category}'."}


@router.post("/memory/reconnect")
async def memory_reconnect():
    """Retente la connexion à ChromaDB."""
    mem = get_memory_manager()
    mem.reconnect()
    return {"connected": mem.is_connected()}


@router.post("/memory/ingest")
async def memory_ingest(req: MemoryIngestRequest):
    """
    Ingère un document (.txt/.md/.pdf) dans la mémoire long terme (F4 v6.0).
    Extraction → chunking (512/64) → embeddings e5 → partition documents.
    """
    from tools.memory_ingest import ingest_file
    mem = get_memory_manager()
    if not mem.is_connected():
        raise HTTPException(status_code=503, detail="ChromaDB indisponible — ingestion impossible.")
    result = ingest_file(req.path, memory_manager=mem)
    if not result["success"]:
        # 422 pour erreurs utilisateur (format/fichier), 200 sinon
        raise HTTPException(status_code=422, detail=result["message"])
    return result


# --------------------------------------------------------------------------- #
#  Bridge status
# --------------------------------------------------------------------------- #

@router.get("/metrics/grounding")
async def metrics_grounding(limit: int = 500):
    """
    Métriques qualité du grounding stack (P5 v5.1).
    Lit atlas_actions.jsonl et calcule :
    - taux de clic vérifié, répartition couches, latence médiane, taux succès par app.
    """
    import statistics

    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    if limit > 5000:
        limit = 5000

    log_file = pathlib.Path(__file__).resolve().parent.parent / "data" / "atlas_actions.jsonl"
    if not log_file.exists():
        return {"total_actions": 0, "click_verified_rate": None, "disambiguation_count": 0,
                "layer_distribution": {}, "median_latency_ms_by_layer": {}, "success_rate_by_app": {}}

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cannot read log: {e}")

    recent = lines[-limit:]
    entries: list[dict] = []
    for line in recent:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    grounding_entries = [e for e in entries if e.get("tool") == "ui_click_element"]

    # --- Click verified rate ---
    verified_entries = [e for e in grounding_entries if e.get("click_verified") is not None]
    if verified_entries:
        click_verified_rate = round(sum(1 for e in verified_entries if e["click_verified"]) / len(verified_entries), 3)
    else:
        click_verified_rate = None

    # --- Disambiguation count ---
    disambiguation_count = sum(1 for e in grounding_entries if e.get("disambiguation_triggered"))

    # --- Layer distribution (grounding_layer field) ---
    layer_distribution: dict[str, int] = {}
    for e in entries:
        layer = e.get("grounding_layer")
        if layer:
            layer_distribution[layer] = layer_distribution.get(layer, 0) + 1

    # --- Median latency by layer ---
    latency_by_layer: dict[str, list[int]] = {}
    for e in grounding_entries:
        layer = e.get("grounding_layer")
        lat = e.get("latency_ms")
        if layer and isinstance(lat, int):
            latency_by_layer.setdefault(layer, []).append(lat)
    median_latency_ms_by_layer = {
        layer: round(statistics.median(vals))
        for layer, vals in latency_by_layer.items()
        if vals
    }

    # --- Success rate + count by app (target field) ---
    success_by_app: dict[str, list[bool]] = {}
    for e in grounding_entries:
        target = e.get("target")
        if not target:
            continue
        ok = e.get("result") in ("success", "retry_success")
        success_by_app.setdefault(target, []).append(ok)
    success_rate_by_app = {
        app: round(sum(vals) / len(vals), 3)
        for app, vals in success_by_app.items()
        if vals
    }
    usage_count_by_app = {app: len(vals) for app, vals in success_by_app.items()}

    # --- Per-layer success rate + median latency from grounding_attempts ---
    # v5.2 clôture — exploits the detailed instrumentation (v5.1 corrective)
    layer_attempt_stats: dict[str, dict] = {}
    layer_attempt_latencies: dict[str, list[int]] = {}
    for e in grounding_entries:
        attempts = e.get("grounding_attempts") or []
        for a in attempts:
            layer = a.get("layer")
            result = a.get("result")
            lat = a.get("latency_ms")
            if not layer:
                continue
            stats = layer_attempt_stats.setdefault(
                layer, {"total": 0, "success": 0, "timeout": 0, "failure": 0, "skipped": 0}
            )
            stats["total"] += 1
            if result in stats:
                stats[result] += 1
            if isinstance(lat, int) and lat >= 0:
                layer_attempt_latencies.setdefault(layer, []).append(lat)

    layer_success_rate: dict[str, float] = {}
    for layer, stats in layer_attempt_stats.items():
        total = stats["total"]
        if total > 0:
            layer_success_rate[layer] = round(stats["success"] / total, 3)

    median_attempt_latency_ms_by_layer = {
        layer: round(statistics.median(vals))
        for layer, vals in layer_attempt_latencies.items()
        if vals
    }

    return {
        "total_actions": len(grounding_entries),
        "click_verified_rate": click_verified_rate,
        "disambiguation_count": disambiguation_count,
        "layer_distribution": layer_distribution,
        "median_latency_ms_by_layer": median_latency_ms_by_layer,
        "success_rate_by_app": success_rate_by_app,
        "usage_count_by_app": usage_count_by_app,
        "layer_attempt_stats": layer_attempt_stats,
        "layer_success_rate": layer_success_rate,
        "median_attempt_latency_ms_by_layer": median_attempt_latency_ms_by_layer,
    }


@router.get("/bridge/status")
async def bridge_status():
    """Retourne l'état de la connexion bridge navigateur."""
    from tools.browser_bridge import get_bridge
    bridge = get_bridge()
    return {
        "connected": bridge.is_connected(),
        "clients": bridge.connected_clients,
        "port": bridge.port,
    }
