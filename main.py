"""
Atlas — Assistant Bureau Windows
Point d'entrée principal FastAPI.
"""

import json
import logging
import os
import pathlib
import socket
import sys
import asyncio
import webbrowser
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# --------------------------------------------------------------------------- #
#  Logging
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            pathlib.Path(__file__).parent / "logs" / "atlas.log",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("atlas")

# --------------------------------------------------------------------------- #
#  Config
# --------------------------------------------------------------------------- #

CONFIG_PATH = pathlib.Path(__file__).parent / "config" / "settings.json"
with open(CONFIG_PATH, encoding="utf-8") as f:
    CONFIG = json.load(f)

HOST = CONFIG["server"]["host"]
PORT = CONFIG["server"]["port"]
LOCK_FILE = pathlib.Path(__file__).parent / "data" / "atlas.lock"
_INSTANCE_LOCK_FH = None


def _check_tesseract() -> dict:
    """
    Probe Tesseract OCR availability at startup (v5.3 AXE 4).
    Returns {ok, version?, langs?, warning?, error?}.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["tesseract", "--version"],
            capture_output=True, text=True, timeout=3.0,
        )
        if result.returncode != 0:
            return {"ok": False, "error": f"exit_code={result.returncode}"}
        version_line = (result.stdout or "").strip().split("\n")[0]

        # Probe installed languages — 'fra' is required for French UI labels.
        langs: list[str] = []
        try:
            langs_result = subprocess.run(
                ["tesseract", "--list-langs"],
                capture_output=True, text=True, timeout=3.0,
            )
            if langs_result.returncode == 0:
                lines = (langs_result.stdout or "").strip().split("\n")
                langs = [l.strip() for l in lines[1:] if l.strip()]  # skip header line
        except Exception:
            pass

        if langs and "fra" not in langs:
            return {"ok": True, "version": version_line, "langs": langs,
                    "warning": "Langue 'fra' absente — matching FR dégradé"}
        return {"ok": True, "version": version_line, "langs": langs}
    except FileNotFoundError:
        return {"ok": False, "error": "not_found"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _warn_if_voice_gpu_missing(voice_enabled: bool):
    """Warn when voice is enabled but CUDA is unavailable."""
    if not voice_enabled:
        return
    try:
        import torch

        if not torch.cuda.is_available():
            logger.warning(
                "⚠️ Atlas Voice : aucun GPU CUDA detecte. La transcription STT sera lente (~3-5s). "
                "Performance optimale sur GPU NVIDIA. Pour desactiver: voice.enabled=false"
            )
    except Exception:
        logger.warning("⚠️ Atlas Voice : torch indisponible, impossible de verifier CUDA.")


def _is_port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) != 0


def _find_available_port(host: str, preferred_port: int, max_tries: int = 20) -> int:
    if _is_port_free(host, preferred_port):
        return preferred_port
    for offset in range(1, max_tries + 1):
        candidate = preferred_port + offset
        if _is_port_free(host, candidate):
            return candidate
    return preferred_port


def acquire_instance_lock() -> tuple[bool, str]:
    """
    Acquire a process-level lock to guarantee a single Atlas instance.
    Returns (ok, message).
    """
    global _INSTANCE_LOCK_FH

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _INSTANCE_LOCK_FH is None:
        _INSTANCE_LOCK_FH = open(LOCK_FILE, "a+", encoding="utf-8")

    try:
        if os.name == "nt":
            import msvcrt

            # Lock first byte in non-blocking mode.
            _INSTANCE_LOCK_FH.seek(0)
            msvcrt.locking(_INSTANCE_LOCK_FH.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(_INSTANCE_LOCK_FH.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        _INSTANCE_LOCK_FH.seek(0)
        _INSTANCE_LOCK_FH.truncate(0)
        _INSTANCE_LOCK_FH.write(f"pid={os.getpid()}\n")
        _INSTANCE_LOCK_FH.flush()
        return True, "instance lock acquired"
    except OSError:
        return False, "Une autre instance Atlas est déjà active. Arrêt propre du second lancement."


def release_instance_lock() -> None:
    """Release instance lock if held."""
    global _INSTANCE_LOCK_FH
    if _INSTANCE_LOCK_FH is None:
        return

    try:
        if os.name == "nt":
            import msvcrt

            _INSTANCE_LOCK_FH.seek(0)
            msvcrt.locking(_INSTANCE_LOCK_FH.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(_INSTANCE_LOCK_FH.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        logger.debug("Release lock warning: %s", e)
    finally:
        try:
            _INSTANCE_LOCK_FH.close()
        except Exception:
            pass
        _INSTANCE_LOCK_FH = None


async def _wait_port_released(host: str, port: int, timeout_seconds: float = 3.0):
    """Wait briefly for a port to be released after shutdown."""
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        if _is_port_free(host, port):
            return True
        await asyncio.sleep(0.1)
    return _is_port_free(host, port)

# Ensure data directory exists
DATA_DIR = pathlib.Path(__file__).parent / "data" / "chromadb"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- #
#  Lifespan — startup / shutdown
# --------------------------------------------------------------------------- #

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise la détection des habitudes et la mémoire au démarrage."""
    from core.context_monitor import start_new_session, collect_context
    from core.memory_manager import get_memory_manager
    from tools.browser_bridge import get_bridge
    from core.world_state import get_world_state
    from core.intent_classifier import get_classifier
    from core.validator import get_validator
    from core.intent_engine import get_execution_engine, execute_tool
    from core.scheduler import get_scheduler
    from core.trigger_engine import get_trigger_engine
    from core.workflow_engine import get_workflow_engine
    from core.confirmation import classify_process
    from tools.notifier import notify
    from tools.systray import AtlasSystray
    from core.voice_engine import get_voice_engine
    from core.file_indexer import get_file_indexer

    lock_ok, lock_msg = acquire_instance_lock()
    if not lock_ok:
        logger.error("⛔ %s", lock_msg)
        raise RuntimeError(lock_msg)
    logger.info("🔒 Mono-instance lock acquis")

    # v5.1 corrective — mitigate Python 3.12 + Proactor + Windows socket cleanup bug
    # AssertionError raised in asyncio.proactor_events._attach when a deferred IOCP
    # completion fires after self._sockets is cleaned. Not actionable; log and swallow.
    try:
        loop = asyncio.get_running_loop()

        def _proactor_exception_handler(loop_, context):
            exc = context.get("exception")
            if isinstance(exc, AssertionError):
                src = (context.get("message") or "")
                # Only swallow proactor _attach assertion — surface anything else.
                if "_attach" in src or "_sockets" in src or "proactor" in src.lower():
                    logger.warning(
                        "[asyncio] Proactor socket cleanup AssertionError silencée (bug connu Python 3.12 Windows): %s",
                        src,
                    )
                    return
            loop_.default_exception_handler(context)

        loop.set_exception_handler(_proactor_exception_handler)
    except Exception as e:
        logger.debug("Proactor handler install warning: %s", e)

    tess = _check_tesseract()
    app.state.tesseract_status = tess  # v5.3 AXE 4 — exposed via /api/health
    if tess["ok"] and tess.get("warning"):
        logger.warning("⚠️ Tesseract : %s", tess["warning"])
    elif tess["ok"]:
        logger.info("🔍 Tesseract OCR : %s", tess.get("version", "ok"))
    else:
        logger.warning("=" * 60)
        logger.warning("⚠️  TESSERACT OCR NON DISPONIBLE")
        logger.warning("   Erreur : %s", tess.get("error", "?"))
        logger.warning("   Conséquence : commandes 'clique sur X' lentes/échouées")
        logger.warning("   Voir docs/runbook.md section 6 pour l'installation")
        logger.warning("=" * 60)

    start_new_session()
    mem = get_memory_manager()
    logger.info("🧠 Mémoire : %s", "connectée" if mem.is_connected() else "ChromaDB indisponible — mode dégradé")

    # Instantiate v2.3 components
    ws = get_world_state()
    classifier = get_classifier()
    validator = get_validator()
    engine = get_execution_engine()
    logger.info("🏗️ Architecture v2.3 : WorldState + Classifier + Validator + Engine initialisés")

    # --- MVP 3.0 : Automation components ---

    # Shared execution callback for scheduler/trigger/workflow
    async def _execute_action(action: dict) -> dict:
        tool_name = action.get("action", "")
        params = action.get("params", {})
        context = collect_context()
        return await execute_tool(tool_name, params, context)

    # Protection callback
    def _check_protection(process_name: str) -> str:
        level = classify_process(process_name, collect_context())
        if "INTOUCHABLE" in level:
            return "intouchable"
        elif "DEMANDE" in level:
            return "demande"
        return "libre"

    # Scheduler
    scheduler = get_scheduler()
    scheduler.set_execution_callback(_execute_action)
    await scheduler.start()

    # Trigger Engine
    trigger_engine = get_trigger_engine()
    trigger_engine.set_execution_callback(_execute_action)
    trigger_engine.set_context_callback(collect_context)
    trigger_engine.set_protection_callback(_check_protection)
    # Load check interval from settings
    trigger_check_interval = CONFIG.get("automation", {}).get("trigger_check_interval_seconds", 10)
    trigger_engine.set_check_interval(trigger_check_interval)
    await trigger_engine.start()

    # Workflow Engine
    workflow_engine = get_workflow_engine()
    workflow_engine.set_execution_callback(_execute_action)
    workflow_engine.set_protection_callback(_check_protection)
    workflow_engine.set_notification_callback(lambda msg: notify(msg))
    workflow_engine.load_workflows()

    logger.info("🤖 Architecture v3.0 : Scheduler + TriggerEngine + WorkflowEngine initialisés")

    # --- v4.0: Voice & Presence (optional) ---
    voice_cfg = CONFIG.get("voice", {})
    voice_enabled = bool(voice_cfg.get("enabled", False))

    systray = None
    voice_engine = None
    if voice_enabled:
        _warn_if_voice_gpu_missing(voice_enabled=True)

        loop = asyncio.get_running_loop()

        def _on_open_ui():
            try:
                webbrowser.open(f"http://{HOST}:{PORT}")
            except Exception as e:
                logger.debug("Open UI from systray failed: %s", e)

        def _on_toggle_voice(new_enabled: bool):
            if voice_engine is None:
                return

            async def _apply():
                try:
                    if new_enabled:
                        await voice_engine.start()
                    else:
                        await voice_engine.stop()
                except Exception as e:
                    logger.warning("Voice toggle failed: %s", e)

            loop.call_soon_threadsafe(lambda: asyncio.create_task(_apply()))

        def _on_quit_app():
            # pystray callback runs in dedicated thread; hard-exit is the most reliable here.
            os._exit(0)

        systray = AtlasSystray(
            on_open=_on_open_ui,
            on_toggle_voice=_on_toggle_voice,
            on_quit=_on_quit_app,
        )
        systray.set_voice_enabled(True)
        systray.start()

        voice_engine = get_voice_engine(systray=systray)
        try:
            await voice_engine.start()
            logger.info("🎙️ VoiceEngine demarre")
        except Exception as e:
            logger.warning("⚠️ VoiceEngine demarrage echoue: %s", e)

    # Démarrer le Browser Bridge WebSocket (MVP 2.2)
    bridge = get_bridge()
    try:
        await bridge.start()
        logger.info("🔌 Browser Bridge : WebSocket prêt sur le port %d", bridge.port)
    except Exception as e:
        logger.warning("⚠️ Browser Bridge : démarrage échoué — %s (fonctionnalité désactivée)", e)

    file_indexer = get_file_indexer()
    if file_indexer.enabled():
        try:
            await file_indexer.start()
            logger.info("📂 FileIndexer actif (mode passif)")
        except Exception as e:
            logger.warning("⚠️ FileIndexer démarrage échoué — %s", e)

    yield

    # Shutdown
    try:
        if voice_engine is not None:
            await voice_engine.stop()
    except Exception:
        pass
    try:
        if systray is not None:
            systray.stop()
    except Exception:
        pass
    try:
        await scheduler.stop()
    except Exception:
        pass
    try:
        await trigger_engine.stop()
    except Exception:
        pass
    try:
        await bridge.stop()
    except Exception:
        pass
    try:
        await file_indexer.stop()
    except Exception:
        pass

    try:
        bridge_released = await _wait_port_released(HOST, int(CONFIG.get("browser_bridge", {}).get("port", 9999)))
        api_released = await _wait_port_released(HOST, PORT)
        logger.info(
            "🧹 Ports shutdown — api:%s bridge:%s",
            "libéré" if api_released else "occupé",
            "libéré" if bridge_released else "occupé",
        )
    except Exception as e:
        logger.debug("Port release check warning: %s", e)

    release_instance_lock()
    logger.info("🔓 Mono-instance lock libéré")
    logger.info("Atlas arrêt propre.")


# --------------------------------------------------------------------------- #
#  App
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="Atlas — Assistant Bureau Windows",
    version="4.0.0",
    description="Assistant local intelligent pour le contrôle de PC Windows — Architecture Controlled Loop + Automatisation + Voix & Presence",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
from api.routes import router as api_router
app.include_router(api_router, prefix="/api")

# Serve static UI files
UI_DIR = pathlib.Path(__file__).parent / "ui"
app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")


@app.get("/")
async def serve_index():
    return FileResponse(str(UI_DIR / "index.html"))


@app.get("/health")
async def health():
    from core.memory_manager import get_memory_manager
    mem = get_memory_manager()
    return {
        "status": "ok",
        "model": CONFIG["ollama"]["model"],
        "memory_connected": mem.is_connected(),
    }

# --------------------------------------------------------------------------- #
#  Launch
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    lock_ok, lock_msg = acquire_instance_lock()
    if not lock_ok:
        logger.error("⛔ %s", lock_msg)
        raise SystemExit(1)

    # Release here because the authoritative lock is held in lifespan.
    release_instance_lock()

    if not _is_port_free(HOST, PORT):
        logger.error("⛔ Port %d déjà occupé. Vérifiez qu'Atlas n'est pas déjà démarré.", PORT)
        raise SystemExit(1)

    actual_port = PORT

    logger.info("🚀 Atlas démarrage — %s:%d", HOST, actual_port)
    logger.info("📡 Modèle Ollama : %s", CONFIG["ollama"]["model"])
    logger.info("🌐 Interface : http://%s:%d", HOST, actual_port)

    # Important: éviter les boucles de reload causées par les écritures de logs/data.
    # Active le reload uniquement si demandé explicitement via ATLAS_RELOAD=1.
    reload_enabled = os.getenv("ATLAS_RELOAD", "0") == "1"

    uvicorn.run(
        "main:app",
        host=HOST,
        port=actual_port,
        reload=reload_enabled,
        reload_excludes=["logs/*", "data/*"],
        log_level="info",
    )
