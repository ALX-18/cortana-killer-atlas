"""
Process Manager — Lister / tuer / prioriser des processus.
"""

import logging
from typing import Any

import psutil

logger = logging.getLogger("atlas.process_manager")

# Mapping texte → constante psutil
PRIORITY_MAP = {
    "idle": psutil.IDLE_PRIORITY_CLASS,
    "below_normal": psutil.BELOW_NORMAL_PRIORITY_CLASS,
    "normal": psutil.NORMAL_PRIORITY_CLASS,
    "above_normal": psutil.ABOVE_NORMAL_PRIORITY_CLASS,
    "high": psutil.HIGH_PRIORITY_CLASS,
    "realtime": psutil.REALTIME_PRIORITY_CLASS,
}

PRIORITY_REVERSE = {v: k for k, v in PRIORITY_MAP.items()}


def list_processes(sort_by: str = "memory", limit: int = 30) -> list[dict[str, Any]]:
    """
    Liste les processus triés par CPU ou mémoire.
    """
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            info = p.info
            procs.append({
                "pid": info["pid"],
                "name": info["name"],
                "cpu_percent": round(info["cpu_percent"] or 0.0, 1),
                "memory_percent": round(info["memory_percent"] or 0.0, 1),
                "status": info["status"],
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    key = "memory_percent" if sort_by == "memory" else "cpu_percent"
    procs.sort(key=lambda x: x[key], reverse=True)
    return procs[:limit]


def find_process(name: str) -> list[dict[str, Any]]:
    """Cherche un processus par nom (partiel, insensible à la casse)."""
    results = []
    name_lower = name.lower()
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            if name_lower in (p.info["name"] or "").lower():
                results.append({
                    "pid": p.info["pid"],
                    "name": p.info["name"],
                    "cpu_percent": round(p.info["cpu_percent"] or 0.0, 1),
                    "memory_percent": round(p.info["memory_percent"] or 0.0, 1),
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return results


def kill_process(pid: int | None = None, name: str | None = None) -> dict[str, Any]:
    """
    Termine un processus par PID ou par nom.
    Retourne le résultat de l'opération.
    """
    if pid:
        try:
            proc = psutil.Process(pid)
            proc_name = proc.name()
            proc.terminate()
            proc.wait(timeout=5)
            logger.info("Terminated process: %s (PID %d)", proc_name, pid)
            return {"success": True, "message": f"Processus '{proc_name}' (PID {pid}) terminé."}
        except psutil.NoSuchProcess:
            return {"success": False, "message": f"Aucun processus avec le PID {pid}."}
        except psutil.AccessDenied:
            return {"success": False, "message": f"Accès refusé pour terminer le PID {pid}. Essayez en administrateur."}
        except psutil.TimeoutExpired:
            # Force kill
            try:
                psutil.Process(pid).kill()
                return {"success": True, "message": f"Processus PID {pid} tué de force (ne répondait pas)."}
            except Exception as e:
                return {"success": False, "message": f"Impossible de tuer le PID {pid}: {e}"}

    elif name:
        killed = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if name.lower() in (p.info["name"] or "").lower():
                    p.terminate()
                    killed.append({"pid": p.info["pid"], "name": p.info["name"]})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if killed:
            logger.info("Killed %d processes matching '%s'", len(killed), name)
            return {"success": True, "message": f"{len(killed)} processus '{name}' terminé(s).", "killed": killed}
        return {"success": False, "message": f"Aucun processus correspondant à '{name}'."}

    return {"success": False, "message": "Il faut spécifier un PID ou un nom."}


def set_priority(pid: int, priority: str) -> dict[str, Any]:
    """Change la priorité d'un processus."""
    priority_lower = priority.lower()
    if priority_lower not in PRIORITY_MAP:
        return {
            "success": False,
            "message": f"Priorité inconnue '{priority}'. Valides : {list(PRIORITY_MAP.keys())}",
        }
    try:
        proc = psutil.Process(pid)
        proc.nice(PRIORITY_MAP[priority_lower])
        logger.info("Set priority of PID %d to %s", pid, priority_lower)
        return {"success": True, "message": f"Priorité de '{proc.name()}' (PID {pid}) → {priority_lower}."}
    except psutil.NoSuchProcess:
        return {"success": False, "message": f"Aucun processus avec le PID {pid}."}
    except psutil.AccessDenied:
        return {"success": False, "message": f"Accès refusé. Essayez en administrateur."}


def get_process_details(pid: int) -> dict[str, Any]:
    """Retourne les détails d'un processus."""
    try:
        p = psutil.Process(pid)
        with p.oneshot():
            return {
                "pid": p.pid,
                "name": p.name(),
                "exe": p.exe(),
                "status": p.status(),
                "cpu_percent": p.cpu_percent(interval=0.3),
                "memory_mb": round(p.memory_info().rss / (1024**2), 1),
                "create_time": p.create_time(),
                "num_threads": p.num_threads(),
                "priority": PRIORITY_REVERSE.get(p.nice(), str(p.nice())),
            }
    except psutil.NoSuchProcess:
        return {"error": f"Aucun processus avec le PID {pid}."}
    except psutil.AccessDenied:
        return {"error": f"Accès refusé pour le PID {pid}."}
