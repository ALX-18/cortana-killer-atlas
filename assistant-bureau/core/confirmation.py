"""
Confirmation Manager — Intercepte les actions risquées et demande confirmation.
"""

import json
import logging
import pathlib
from typing import Any

logger = logging.getLogger("atlas.confirmation")

# --------------------------------------------------------------------------- #
#  Chargement config protection
# --------------------------------------------------------------------------- #

def _load_protection_rules() -> dict:
    cfg_path = pathlib.Path(__file__).resolve().parent.parent / "config" / "settings.json"
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f)["protection_rules"]

_rules = _load_protection_rules()

# Actions toujours destructives
DESTRUCTIVE_TOOLS = {"kill_process", "run_powershell", "system_config"}

# Processus système intouchables
ALWAYS_PROTECTED = set(p.lower() for p in _rules["always_protected"])

# Mots-clés jeux
GAME_KEYWORDS = [kw.lower() for kw in _rules["game_executables_keywords"]]

GPU_THRESHOLD = _rules["intouchable_gpu_threshold"]
CPU_THRESHOLD = _rules["intouchable_cpu_threshold"]


# --------------------------------------------------------------------------- #
#  Classification d'un processus
# --------------------------------------------------------------------------- #

def classify_process(
    proc_name: str,
    context: dict,
) -> str:
    """
    Retourne le niveau de protection d'un processus :
      '🔴 INTOUCHABLE', '🟡 DEMANDE', '🟢 LIBRE'
    """
    name_lower = proc_name.lower()

    # Processus système critique
    if name_lower in ALWAYS_PROTECTED:
        return "🔴 INTOUCHABLE"

    fg = context.get("foreground_window", {})
    gpu = context.get("gpu_usage", 0)
    cpu = context.get("cpu_usage", 0)
    audio_procs = [p.lower() for p in context.get("audio_active_processes", [])]
    net_procs = [p.lower() for p in context.get("network_active_processes", [])]

    # Foreground + forte charge → INTOUCHABLE
    if fg.get("process", "").lower() == name_lower:
        if gpu > GPU_THRESHOLD or cpu > CPU_THRESHOLD:
            return "🔴 INTOUCHABLE"
        # Foreground mais charge faible → quand même prudent
        return "🟡 DEMANDE"

    # Jeu détecté
    if any(kw in name_lower for kw in GAME_KEYWORDS):
        return "🔴 INTOUCHABLE"

    # Audio actif
    if name_lower in audio_procs:
        return "🟡 DEMANDE"

    # Réseau actif
    if name_lower in net_procs:
        return "🟡 DEMANDE"

    return "🟢 LIBRE"


# --------------------------------------------------------------------------- #
#  Decide si confirmation nécessaire
# --------------------------------------------------------------------------- #

def needs_confirmation(
    tool_name: str,
    args: dict[str, Any],
    context: dict,
) -> dict | None:
    """
    Retourne None si l'action peut être exécutée directement.
    Sinon retourne un dict décrivant pourquoi une confirmation est nécessaire :
      {"reason": str, "level": str, "target": str, "suggestion": str | None}
    """
    # Toute action destructive nécessite au moins une vérification
    if tool_name not in DESTRUCTIVE_TOOLS:
        return None

    # kill_process — vérifier la cible
    if tool_name == "kill_process":
        target = args.get("name", "")
        if not target and args.get("pid"):
            try:
                import psutil
                target = psutil.Process(args["pid"]).name()
            except Exception:
                target = f"PID {args['pid']}"

        level = classify_process(target, context)

        if level == "🔴 INTOUCHABLE":
            return {
                "reason": f"Le processus '{target}' est critique/actif au premier plan avec forte charge.",
                "level": level,
                "target": target,
                "suggestion": "Je recommande de ne pas y toucher. Voulez-vous vraiment continuer ?",
            }
        elif level == "🟡 DEMANDE":
            reasons = []
            if target.lower() in [p.lower() for p in context.get("audio_active_processes", [])]:
                reasons.append("il diffuse de l'audio")
            if target.lower() in [p.lower() for p in context.get("network_active_processes", [])]:
                reasons.append("il a des connexions réseau actives")
            fg = context.get("foreground_window", {})
            if fg.get("process", "").lower() == target.lower():
                reasons.append("il est au premier plan")
            reason_str = ", ".join(reasons) if reasons else "il semble actif en arrière-plan"
            return {
                "reason": f"Le processus '{target}' nécessite confirmation car {reason_str}.",
                "level": level,
                "target": target,
                "suggestion": None,
            }
        # 🟢 LIBRE — mais kill est destructif → confirmation quand même
        return {
            "reason": f"Fermer '{target}' est une action irréversible.",
            "level": level,
            "target": target,
            "suggestion": None,
        }

    # run_powershell — toujours confirmer
    if tool_name == "run_powershell":
        cmd = args.get("command", "")
        return {
            "reason": f"Exécution PowerShell : `{cmd}`",
            "level": "🟡 DEMANDE",
            "target": "powershell",
            "suggestion": "Voulez-vous exécuter cette commande ?",
        }

    # system_config — toujours confirmer
    if tool_name == "system_config":
        action = args.get("action", "inconnu")
        return {
            "reason": f"Modification système : {action}",
            "level": "🟡 DEMANDE",
            "target": "system",
            "suggestion": "Cette modification affecte la configuration du système.",
        }

    return None


# --------------------------------------------------------------------------- #
#  Pending confirmations store (in-memory)
# --------------------------------------------------------------------------- #

_pending: dict[str, dict] = {}   # confirmation_id → {tool, args, reason, ...}


def store_pending(confirmation_id: str, tool_name: str, args: dict, info: dict):
    _pending[confirmation_id] = {
        "tool": tool_name,
        "args": args,
        **info,
    }


def get_pending(confirmation_id: str) -> dict | None:
    return _pending.get(confirmation_id)


def resolve_pending(confirmation_id: str) -> dict | None:
    return _pending.pop(confirmation_id, None)
