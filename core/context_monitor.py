"""
Context Monitor — Collecte du contexte système en temps réel.
Processus, fenêtre active, audio, CPU/RAM/GPU, réseau.
Détection passive des habitudes avec persistance SQLite.
"""

import asyncio
import json
import logging
import pathlib
import sqlite3
import time
from datetime import datetime
from typing import Any

import psutil

logger = logging.getLogger("atlas.context")

# --------------------------------------------------------------------------- #
#  Windows-specific imports (graceful fallback)
# --------------------------------------------------------------------------- #
try:
    import win32gui
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    logger.warning("pywin32 non disponible — détection de fenêtre active désactivée")

try:
    from pycaw.pycaw import AudioUtilities
    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False
    logger.warning("pycaw non disponible — détection audio désactivée")


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

def _get_foreground_window() -> dict[str, Any]:
    """Retourne le titre et le processus de la fenêtre au premier plan."""
    if not HAS_WIN32:
        return {"title": "unknown", "process": "unknown", "pid": -1}
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            proc = psutil.Process(pid)
            name = proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            name = "unknown"
        return {"title": title, "process": name, "pid": pid}
    except Exception as exc:
        logger.debug("foreground detection failed: %s", exc)
        return {"title": "unknown", "process": "unknown", "pid": -1}


def _get_audio_active_processes() -> list[str]:
    """Liste les processus émettant de l'audio actuellement."""
    if not HAS_PYCAW:
        return []
    try:
        sessions = AudioUtilities.GetAllSessions()
        active = []
        for s in sessions:
            if s.Process and s.Process.name():
                active.append(s.Process.name())
        return active
    except Exception as exc:
        logger.debug("audio detection failed: %s", exc)
        return []


def _get_gpu_usage() -> float:
    """Tente de récupérer l'usage GPU via nvidia-smi."""
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return float(result.stdout.strip().split("\n")[0])
    except Exception:
        pass
    # Fallback WMI — souvent moins fiable
    try:
        import wmi
        w = wmi.WMI(namespace="root\\cimv2")
        # Tenter via Win32_VideoController (pas toujours dispo)
        for gpu in w.Win32_VideoController():
            pass  # WMI ne donne pas le % d'usage facilement
    except Exception:
        pass
    return -1.0  # -1 = indisponible


def _get_top_processes(n: int = 20) -> list[dict]:
    """Retourne les N processus les plus gourmands."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            procs.append({
                "pid": info["pid"],
                "name": info["name"],
                "cpu_percent": info["cpu_percent"] or 0.0,
                "memory_percent": round(info["memory_percent"] or 0.0, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: x["cpu_percent"] + x["memory_percent"], reverse=True)
    return procs[:n]


def _get_network_active_processes() -> list[str]:
    """Liste les processus avec des connexions réseau actives."""
    active = set()
    for conn in psutil.net_connections(kind="inet"):
        if conn.status == "ESTABLISHED" and conn.pid:
            try:
                proc = psutil.Process(conn.pid)
                active.add(proc.name())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    return list(active)


# --------------------------------------------------------------------------- #
#  Public API
# --------------------------------------------------------------------------- #

def collect_context() -> dict[str, Any]:
    """
    Collecte un snapshot complet du contexte système.
    Appelé avant chaque interaction avec l'IA.
    """
    mem = psutil.virtual_memory()
    disk = {}
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disk[part.mountpoint] = {
                "total_gb": round(usage.total / (1024**3), 1),
                "used_gb": round(usage.used / (1024**3), 1),
                "percent": usage.percent,
            }
        except PermissionError:
            continue

    ctx = {
        "timestamp": time.time(),
        "foreground_window": _get_foreground_window(),
        "running_processes": _get_top_processes(20),
        "audio_active_processes": _get_audio_active_processes(),
        "cpu_usage": psutil.cpu_percent(interval=0.3),
        "ram_usage": mem.percent,
        "ram_available_gb": round(mem.available / (1024**3), 1),
        "gpu_usage": _get_gpu_usage(),
        "disk_usage": disk,
        "network_active_processes": _get_network_active_processes(),
    }

    # Détection passive des habitudes
    _track_process_habits(ctx)

    return ctx


# --------------------------------------------------------------------------- #
#  Habit detection — détection passive avec persistance SQLite
# --------------------------------------------------------------------------- #

# Config
def _load_habit_config() -> dict:
    cfg_path = pathlib.Path(__file__).resolve().parent.parent / "config" / "settings.json"
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f).get("memory", {})

_habit_cfg = _load_habit_config()
HABIT_THRESHOLD: int = _habit_cfg.get("habit_detection_threshold", 3)

# SQLite DB path
_DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "habits.db"

# RAM cache : {process_name: detection_count}
_process_session_counts: dict[str, int] = {}
_current_session_processes: set[str] = set()
_session_id: int = 0
_db_initialized: bool = False

# Ignore list (system processes)
_SYSTEM_PROCS = frozenset({
    "svchost.exe", "explorer.exe", "csrss.exe", "lsass.exe",
    "system", "winlogon.exe", "dwm.exe", "conhost.exe",
    "taskhostw.exe", "runtimebroker.exe", "searchhost.exe",
    "idle", "registry", "smss.exe", "services.exe",
    "wininit.exe", "fontdrvhost.exe", "sihost.exe",
})


def _init_db():
    """Crée la table SQLite si nécessaire et charge les compteurs en RAM."""
    global _process_session_counts, _db_initialized
    if _db_initialized:
        return

    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS process_habits (
                process_name TEXT PRIMARY KEY,
                detection_count INTEGER DEFAULT 0,
                last_seen TEXT,
                marked_as_habit BOOLEAN DEFAULT FALSE
            )
        """)
        conn.commit()

        # Charger les compteurs existants en RAM
        rows = conn.execute("SELECT process_name, detection_count FROM process_habits").fetchall()
        for name, count in rows:
            _process_session_counts[name] = count
        conn.close()

        _db_initialized = True
        logger.info("SQLite habits: %d processus chargés depuis %s", len(rows), _DB_PATH.name)
    except Exception as e:
        logger.warning("Erreur initialisation SQLite habits: %s", e)


def _persist_habit(process_name: str, count: int):
    """Persiste un compteur d'habitude dans SQLite (synchrone, rapide)."""
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.execute(
            """INSERT INTO process_habits (process_name, detection_count, last_seen, marked_as_habit)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(process_name) DO UPDATE SET
                   detection_count = ?,
                   last_seen = ?,
                   marked_as_habit = CASE WHEN ? >= ? THEN TRUE ELSE marked_as_habit END
            """,
            (
                process_name, count, datetime.now().isoformat(), count >= HABIT_THRESHOLD,
                count, datetime.now().isoformat(),
                count, HABIT_THRESHOLD,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug("Erreur persistence habitude SQLite: %s", e)


def _persist_habit_async(process_name: str, count: int):
    """Lance la persistence en background sans bloquer la boucle asyncio."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.run_in_executor(None, _persist_habit, process_name, count)
        else:
            _persist_habit(process_name, count)
    except RuntimeError:
        # Pas de boucle asyncio active — écriture synchrone
        _persist_habit(process_name, count)


def start_new_session():
    """Appelé au démarrage de l'app — incrémente le compteur de session et charge SQLite."""
    global _session_id, _current_session_processes
    _init_db()
    _session_id += 1
    _current_session_processes = set()
    logger.info("Nouvelle session de détection d'habitudes (#%d) — seuil=%d", _session_id, HABIT_THRESHOLD)


def _track_process_habits(context: dict):
    """
    Détecte les processus récurrents entre sessions.
    Si un processus est vu dans >= HABIT_THRESHOLD sessions → sauvegarde comme habitude.
    Persistence SQLite asynchrone.
    """
    global _current_session_processes

    if not _db_initialized:
        _init_db()

    procs = context.get("running_processes", [])
    for p in procs:
        name = p.get("name", "").lower()
        if not name or name in _current_session_processes:
            continue

        # Ignorer les processus système
        if name in _SYSTEM_PROCS:
            continue

        _current_session_processes.add(name)

        # Incrémenter le compteur de sessions
        prev = _process_session_counts.get(name, 0)
        _process_session_counts[name] = prev + 1
        count = _process_session_counts[name]

        # Persister dans SQLite (async, non bloquant)
        _persist_habit_async(name, count)

        # Si seuil atteint → sauvegarder comme habitude dans ChromaDB
        if count == HABIT_THRESHOLD:
            try:
                from core.memory_manager import get_memory_manager
                mem = get_memory_manager()
                if mem.is_connected():
                    mem.save(
                        category="habit",
                        content=f"Le processus '{name}' est détecté actif de manière récurrente ({HABIT_THRESHOLD}+ sessions). C'est probablement une application régulièrement utilisée.",
                        metadata={"process": name, "sessions_seen": HABIT_THRESHOLD},
                    )
                    logger.info("Habitude détectée et sauvegardée : %s", name)
            except Exception as e:
                logger.debug("Erreur sauvegarde habitude ChromaDB : %s", e)
