"""
Diagnostics — CPU / RAM / GPU / Disque / Température.
"""

import logging
import platform
from typing import Any

import psutil

logger = logging.getLogger("atlas.diagnostics")


def get_cpu_info() -> dict[str, Any]:
    freq = psutil.cpu_freq()
    return {
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "current_freq_mhz": round(freq.current, 0) if freq else None,
        "max_freq_mhz": round(freq.max, 0) if freq else None,
        "usage_percent": psutil.cpu_percent(interval=0.5),
        "per_core_percent": psutil.cpu_percent(interval=0.3, percpu=True),
    }


def get_ram_info() -> dict[str, Any]:
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "total_gb": round(mem.total / (1024**3), 2),
        "available_gb": round(mem.available / (1024**3), 2),
        "used_gb": round(mem.used / (1024**3), 2),
        "percent": mem.percent,
        "swap_total_gb": round(swap.total / (1024**3), 2),
        "swap_used_gb": round(swap.used / (1024**3), 2),
        "swap_percent": swap.percent,
    }


def get_disk_info() -> list[dict[str, Any]]:
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total_gb": round(usage.total / (1024**3), 1),
                "used_gb": round(usage.used / (1024**3), 1),
                "free_gb": round(usage.free / (1024**3), 1),
                "percent": usage.percent,
            })
        except PermissionError:
            continue
    return disks


def get_gpu_info() -> dict[str, Any]:
    """Récupère les infos GPU via nvidia-smi (NVIDIA uniquement)."""
    try:
        import subprocess
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            return {
                "available": True,
                "name": parts[0],
                "temperature_c": int(parts[1]),
                "usage_percent": float(parts[2]),
                "memory_used_mb": int(parts[3]),
                "memory_total_mb": int(parts[4]),
            }
    except Exception:
        pass
    return {"available": False}


def get_network_info() -> dict[str, Any]:
    counters = psutil.net_io_counters()
    return {
        "bytes_sent": counters.bytes_sent,
        "bytes_recv": counters.bytes_recv,
        "packets_sent": counters.packets_sent,
        "packets_recv": counters.packets_recv,
    }


def get_temperatures() -> dict[str, Any]:
    """Retourne les températures si disponibles."""
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            result = {}
            for name, entries in temps.items():
                result[name] = [
                    {"label": e.label or "N/A", "current": e.current, "high": e.high, "critical": e.critical}
                    for e in entries
                ]
            return result
    except AttributeError:
        pass  # Windows ne supporte pas sensors_temperatures nativement
    return {}


def get_boot_time() -> str:
    import datetime
    bt = psutil.boot_time()
    return datetime.datetime.fromtimestamp(bt).isoformat()


def get_system_info() -> dict[str, Any]:
    uname = platform.uname()
    return {
        "system": uname.system,
        "node_name": uname.node,
        "release": uname.release,
        "version": uname.version,
        "machine": uname.machine,
        "processor": uname.processor,
    }


# --------------------------------------------------------------------------- #
#  Public — rapport complet
# --------------------------------------------------------------------------- #

def full_diagnostics() -> dict[str, Any]:
    """Retourne un rapport complet de diagnostics système."""
    return {
        "system": get_system_info(),
        "boot_time": get_boot_time(),
        "cpu": get_cpu_info(),
        "ram": get_ram_info(),
        "gpu": get_gpu_info(),
        "disks": get_disk_info(),
        "network": get_network_info(),
        "temperatures": get_temperatures(),
    }
