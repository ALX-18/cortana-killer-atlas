"""
App Launcher — Lancer des applications avec logique de dépendance.
"""

import logging
import os
import subprocess
import time
import pathlib
import json
import unicodedata
from difflib import get_close_matches
from typing import Any

import psutil

logger = logging.getLogger("atlas.app_launcher")

_RUNTIME_APP_INDEX: dict[str, str] | None = None
FILE_INDEX_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "file_index.json"

APP_TYPES: dict[str, str] = {
    "steam": "electron",
    "discord": "electron",
    "spotify": "electron",
    "vscode": "electron",
    "opera gx": "electron",
    "opera": "electron",
    "chrome": "electron",
    "firefox": "electron",
    "notepad": "win32",
    "bloc-notes": "win32",
    "bloc notes": "win32",
    "explorer": "win32",
    "task manager": "win32",
    "calculator": "win32",
}

# --------------------------------------------------------------------------- #
#  Catalogue d'apps connues (chemins courants Windows)
# --------------------------------------------------------------------------- #

KNOWN_APPS: dict[str, list[str]] = {
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    ],
    "opera gx": [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera GX\opera.exe"),
    ],
    "opera": [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
    ],
    "notepad": [r"C:\Windows\notepad.exe"],
    "bloc-notes": [r"C:\Windows\notepad.exe"],
    "bloc notes": [r"C:\Windows\notepad.exe"],
    "blocnotes": [r"C:\Windows\notepad.exe"],
    "notepad++": [
        r"C:\Program Files\Notepad++\notepad++.exe",
        r"C:\Program Files (x86)\Notepad++\notepad++.exe",
    ],
    "vscode": [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
    ],
    "discord": [
        os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe"),
    ],
    "spotify": [
        os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
    ],
    "steam": [
        r"C:\Program Files (x86)\Steam\steam.exe",
        r"C:\Program Files\Steam\steam.exe",
    ],
    "epic games": [
        r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
        r"C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
    ],
    "task manager": [r"C:\Windows\System32\Taskmgr.exe"],
    "explorer": [r"C:\Windows\explorer.exe"],
    "cmd": [r"C:\Windows\System32\cmd.exe"],
    "powershell": [r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"],
    "calculator": ["calc.exe"],
    "calculatrice": ["calc.exe"],
    "paint": [r"C:\Windows\System32\mspaint.exe"],
    "terminal": [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"),
        r"C:\Windows\System32\cmd.exe",
    ],
    "snipping tool": [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\SnippingTool.exe"),
    ],
    "outil capture": [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\SnippingTool.exe"),
    ],
    "photos": [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Microsoft.Photos.exe"),
    ],
    "vlc": [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ],
    "winrar": [
        r"C:\Program Files\WinRAR\WinRAR.exe",
        r"C:\Program Files (x86)\WinRAR\WinRAR.exe",
    ],
    "7zip": [
        r"C:\Program Files\7-Zip\7zFM.exe",
        r"C:\Program Files (x86)\7-Zip\7zFM.exe",
    ],
    "word": [
        r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE",
    ],
    "excel": [
        r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\EXCEL.EXE",
    ],
}


def _normalize_app_name(name: str) -> str:
    """Normalize app names to improve tolerant matching (accents, dashes, spacing)."""
    clean = (name or "").strip().lower()
    clean = unicodedata.normalize("NFKD", clean)
    clean = "".join(ch for ch in clean if not unicodedata.combining(ch))
    clean = clean.replace("-", " ").replace("_", " ").replace(".", " ")
    while "  " in clean:
        clean = clean.replace("  ", " ")
    return clean.strip()


def _build_runtime_app_index() -> dict[str, str]:
    """
    Build a lightweight local index from Start Menu entries to tolerate fuzzy names.
    Key: normalized display name, Value: shortcut/executable path.
    """
    global _RUNTIME_APP_INDEX
    if _RUNTIME_APP_INDEX is not None:
        return _RUNTIME_APP_INDEX

    index: dict[str, str] = {}
    candidates = [
        pathlib.Path(os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs")),
        pathlib.Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")),
    ]

    for root in candidates:
        if not root.exists():
            continue
        for ext in ("*.lnk", "*.exe"):
            for p in root.rglob(ext):
                stem = p.stem.strip()
                if not stem:
                    continue
                key = _normalize_app_name(stem)
                if key and key not in index:
                    index[key] = str(p)

    # Seed index with known apps names for stronger fuzzy candidate pool.
    for name, paths in KNOWN_APPS.items():
        key = _normalize_app_name(name)
        if key and key not in index and paths:
            index[key] = paths[0]

    _RUNTIME_APP_INDEX = index
    return _RUNTIME_APP_INDEX


def _resolve_app_candidate(name: str) -> tuple[str | None, str | None, str]:
    """
    Resolve app by exact alias, loose contains, then fuzzy match.
    Returns (resolved_name, resolved_path, strategy).
    """
    if not name:
        return None, None, "empty"

    raw = name.strip()
    normalized = _normalize_app_name(raw)
    normalized_no_exe = normalized[:-4].strip() if normalized.endswith(" exe") else normalized

    # 1) exact match in KNOWN_APPS
    for key in (normalized, normalized_no_exe):
        if key in KNOWN_APPS:
            for p in KNOWN_APPS[key]:
                if os.path.isfile(p) or p.endswith(".exe"):
                    return key, p, "known_exact"

    # 2) exact match in runtime index
    runtime = _build_runtime_app_index()
    for key in (normalized, normalized_no_exe):
        if key in runtime:
            return key, runtime[key], "runtime_exact"

    # 3) contains match in known apps (e.g., 'bloc note' -> 'bloc-notes')
    for key in KNOWN_APPS.keys():
        nk = _normalize_app_name(key)
        if normalized in nk or nk in normalized:
            for p in KNOWN_APPS[key]:
                if os.path.isfile(p) or p.endswith(".exe"):
                    return key, p, "known_contains"

    # 4) fuzzy matching on combined candidate pool
    candidate_keys = sorted(set([_normalize_app_name(k) for k in KNOWN_APPS.keys()] + list(runtime.keys())))
    best = get_close_matches(normalized_no_exe, candidate_keys, n=1, cutoff=0.72)
    if best:
        bk = best[0]
        if bk in runtime:
            return bk, runtime[bk], "runtime_fuzzy"
        if bk in KNOWN_APPS:
            for p in KNOWN_APPS[bk]:
                if os.path.isfile(p) or p.endswith(".exe"):
                    return bk, p, "known_fuzzy"

    # 5) fallback with passive file index (desktop/docs/downloads)
    indexed_name, indexed_path = _resolve_from_file_index(normalized_no_exe)
    if indexed_path:
        return indexed_name, indexed_path, "file_index"

    return None, None, "unresolved"


def get_app_type(name: str | None) -> str:
    """Best-effort app type detection used by grounding stack."""
    if not name:
        return "win32"
    normalized = _normalize_app_name(name)
    if normalized in APP_TYPES:
        return APP_TYPES[normalized]

    resolved_name, _, _ = _resolve_app_candidate(name)
    if resolved_name and _normalize_app_name(resolved_name) in APP_TYPES:
        return APP_TYPES[_normalize_app_name(resolved_name)]

    if any(k in normalized for k in ("steam", "epic", "valorant", "game")):
        return "game"
    return "win32"


def _resolve_from_file_index(query_normalized: str) -> tuple[str | None, str | None]:
    """Use passive file index to find launchable shortcuts/executables by fuzzy name."""
    if not FILE_INDEX_PATH.exists() or not query_normalized:
        return None, None
    try:
        with open(FILE_INDEX_PATH, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None, None

    files = payload.get("files", []) if isinstance(payload, dict) else []
    candidates: dict[str, str] = {}
    for item in files:
        path = str(item.get("path", ""))
        name = str(item.get("name", ""))
        ext = str(item.get("ext", "")).lower()
        if ext not in {".lnk", ".exe", ".bat", ".cmd", ".url"}:
            continue
        nk = _normalize_app_name(pathlib.Path(name).stem)
        if nk and nk not in candidates:
            candidates[nk] = path

    if not candidates:
        return None, None

    exact = candidates.get(query_normalized)
    if exact:
        return query_normalized, exact

    partial = [k for k in candidates.keys() if query_normalized in k or k in query_normalized]
    if partial:
        k = partial[0]
        return k, candidates[k]

    best = get_close_matches(query_normalized, sorted(candidates.keys()), n=1, cutoff=0.74)
    if best:
        k = best[0]
        return k, candidates[k]
    return None, None


def _find_app_path(name: str) -> str | None:
    """Résout le chemin d'une application connue."""
    resolved_name, resolved_path, _ = _resolve_app_candidate(name)
    if resolved_path:
        return resolved_path

    # Tenter avec `where` (cherche dans le PATH)
    try:
        result = subprocess.run(
            ["where", name],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0]
    except Exception:
        pass
    return None


def _is_process_running(name: str) -> bool:
    """Vérifie si un processus est en cours d'exécution."""
    name_lower = name.lower()
    for p in psutil.process_iter(["name"]):
        try:
            if name_lower in (p.info["name"] or "").lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def _wait_for_process(name: str, timeout: int = 30, interval: float = 1.0) -> bool:
    """Attend qu'un processus apparaisse, avec timeout."""
    start = time.time()
    while time.time() - start < timeout:
        if _is_process_running(name):
            return True
        time.sleep(interval)
    return False


# UWP / protocol-based apps (launched via os.startfile or shell:AppsFolder)
_UWP_APPS: dict[str, str] = {
    "calculator": "calculator:",
    "calculatrice": "calculator:",
    "settings": "ms-settings:",
    "paramètres": "ms-settings:",
    "store": "ms-windows-store:",
    "maps": "bingmaps:",
    "clock": "ms-clock:",
    "horloge": "ms-clock:",
    "alarm": "ms-clock:alarm",
    "alarme": "ms-clock:alarm",
    "weather": "bingweather:",
    "météo": "bingweather:",
}


# --------------------------------------------------------------------------- #
#  Public API
# --------------------------------------------------------------------------- #

def launch_app(
    name: str | None = None,
    path: str | None = None,
    args: list[str] | None = None,
    wait_ready: bool = False,
) -> dict[str, Any]:
    """
    Lance une application par nom ou par chemin.
    """
    # Check UWP protocol first
    if name and not path:
        protocol = _UWP_APPS.get(_normalize_app_name(name))
        if protocol:
            try:
                os.startfile(protocol)
                return {
                    "success": True,
                    "message": f"'{name}' lancé via protocole UWP.",
                }
            except Exception as e:
                logger.debug("UWP launch failed for '%s': %s", name, e)

    exe_path = path
    resolve_strategy = "direct_path"
    resolved_display_name = name
    if not exe_path and name:
        resolved_name, resolved_path, strategy = _resolve_app_candidate(name)
        resolve_strategy = strategy
        if resolved_name:
            resolved_display_name = resolved_name
        if resolved_path:
            exe_path = resolved_path

    if not exe_path and name:
        exe_path = _find_app_path(name)
        if exe_path:
            resolve_strategy = "where"

    if not exe_path:
        runtime = _build_runtime_app_index()
        suggestions = get_close_matches(
            _normalize_app_name(name or ""),
            sorted(runtime.keys()),
            n=3,
            cutoff=0.62,
        )
        if not suggestions:
            suggestions = sorted(runtime.keys())[:3]
        suggestion_text = f" Suggestions: {', '.join(suggestions)}" if suggestions else ""
        return {
            "success": False,
            "message": (
                f"Application '{name or path}' introuvable. Vérifiez le nom ou fournissez le chemin complet."
                f"{suggestion_text}"
            ),
        }

    # Shortcut / document / script path: open via shell directly.
    path_lower = exe_path.lower()
    if path_lower.endswith((".lnk", ".url", ".bat", ".cmd")) or not path_lower.endswith(".exe"):
        try:
            os.startfile(exe_path)
            return {
                "success": True,
                "message": f"'{resolved_display_name or name or exe_path}' ouvert via shell.",
                "path": exe_path,
                "resolved_by": resolve_strategy,
            }
        except Exception as e:
            return {"success": False, "message": f"Erreur ouverture shell: {e}"}

    # Discord special case (Update.exe --processStart Discord.exe)
    display_name = resolved_display_name or name or os.path.basename(exe_path)
    cmd = [exe_path]
    if "discord" in display_name.lower() and "Update.exe" in exe_path:
        cmd.extend(["--processStart", "Discord.exe"])

    if args:
        cmd.extend(args)

    try:
        logger.info("Launching: %s", " ".join(cmd))
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        result = {
            "success": True,
            "message": f"'{display_name}' lancé avec succès.",
            "path": exe_path,
            "resolved_by": resolve_strategy,
        }

        if wait_ready:
            proc_name = os.path.basename(exe_path)
            if _wait_for_process(proc_name, timeout=30):
                result["ready"] = True
                result["message"] += " (processus détecté)"
            else:
                result["ready"] = False
                result["message"] += " (timeout — le processus n'a pas été détecté dans les 30s)"

        return result

    except FileNotFoundError:
        return {"success": False, "message": f"Fichier introuvable : {exe_path}"}
    except PermissionError:
        return {"success": False, "message": f"Permission refusée pour lancer '{display_name}'."}
    except Exception as e:
        return {"success": False, "message": f"Erreur lors du lancement : {e}"}


def launch_steam_game(game_id: str) -> dict[str, Any]:
    """Lance un jeu Steam via son App ID."""
    steam_url = f"steam://rungameid/{game_id}"
    try:
        os.startfile(steam_url)
        return {"success": True, "message": f"Lancement du jeu Steam (ID: {game_id}) via protocole steam://."}
    except Exception as e:
        return {"success": False, "message": f"Erreur : {e}"}


def launch_chained(steps: list[dict]) -> list[dict[str, Any]]:
    """
    Exécute une chaîne de lancements ordonnés.

    Chaque step:
      {"name": str, "path": str | None, "wait": bool, "delay": float}
    """
    results = []
    for step in steps:
        name = step.get("name", "")
        path = step.get("path")
        delay = step.get("delay", 2.0)
        wait = step.get("wait", True)

        result = launch_app(name=name, path=path, wait_ready=wait)
        results.append(result)

        if not result["success"]:
            results.append({"success": False, "message": f"Chaîne interrompue après échec de '{name}'."})
            break

        if delay > 0:
            time.sleep(delay)

    return results
