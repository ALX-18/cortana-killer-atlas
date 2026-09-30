"""
Validator — Résolution déterministe d'une intention vers un outil exact.

Zéro appel LLM. Mappe IntentResult → ResolvedAction en tenant compte du contexte.
"""

import logging
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from core.intent_classifier import IntentResult, INTENT_CATEGORIES
from tools.app_launcher import check_app_name
from tools.browser_bridge import check_url, get_bridge
from tools.window_controller import (
    VALID_SNAP_POSITIONS,
    check_click_params,
    check_type_text,
    check_window_title,
)

logger = logging.getLogger("atlas.validator")

_IMPLICIT_APP_TTL_S = 120.0  # 2 minutes

# B1-bis : actions qui désignent la fenêtre de travail, et le paramètre qui la nomme.
_WORKING_WINDOW_PARAM = {
    "ui_click_element": "app_title",
    "launch_app": "name",
    "window_focus": "title",
    "window_maximize": "title",
    "window_type": "target",
    "window_hotkey": "target",
}


def _is_atlas_desktop(title: str) -> bool:
    """True if the title is Atlas's own desktop window (never click ourselves)."""
    t = (title or "").lower()
    return "atlas" in t and "desktop" in t


def _resolve_implicit_app(world_state, context: dict) -> str:
    """Return app_title from last ui_click_element if it occurred < 2 min ago.

    Filters out Atlas Desktop to avoid routing clicks to the assistant UI itself.
    """
    if world_state is None:
        return ""
    la = world_state.last_action
    if not la or la.get("tool") != "ui_click_element":
        return ""
    if time.time() - getattr(world_state, "last_action_ts", 0.0) > _IMPLICIT_APP_TTL_S:
        return ""
    app_title = la.get("params", {}).get("app_title", "")
    if not app_title:
        return ""
    if _is_atlas_desktop(app_title):
        return ""
    return app_title


def _resolve_working_window(world_state) -> str:
    """Fenêtre de travail récente pour une frappe sans cible (B1-bis).

    La dernière action RÉUSSIE de moins de 2 minutes qui nommait une fenêtre : clic,
    lancement, focus, frappe. Jamais la fenêtre au premier plan, ni Atlas Desktop.
    """
    if world_state is None:
        return ""
    la = world_state.last_action
    if not isinstance(la, dict):
        return ""
    param = _WORKING_WINDOW_PARAM.get(la.get("tool"))
    if not param:
        return ""
    if (la.get("result") or {}).get("status") != "success":
        return ""
    if time.time() - getattr(world_state, "last_action_ts", 0.0) > _IMPLICIT_APP_TTL_S:
        return ""
    title, error = check_window_title((la.get("params") or {}).get(param))
    if error or _is_atlas_desktop(title):
        return ""
    return title


# --------------------------------------------------------------------------- #
#  Data structures
# --------------------------------------------------------------------------- #

@dataclass
class VerificationRule:
    type: str = "none"       # process_running | window_visible | url_loaded | text_in_window | none
    target: str = ""         # process name, window title, URL, expected text
    timeout_seconds: int = 5
    retry_count: int = 2


@dataclass
class ResolvedAction:
    tool: str
    params: dict = field(default_factory=dict)
    confirmation_required: bool = False
    verification: VerificationRule = field(default_factory=VerificationRule)
    fallback: Optional[str] = None
    intent: Optional[IntentResult] = None
    # B1 : action refusée par le validateur (paramètre invalide, cible indéterminée).
    # Rien n'est exécuté ; `tool` porte alors une réponse conversationnelle explicative.
    rejected: bool = False
    rejection_reason: str = ""


# --------------------------------------------------------------------------- #
#  Browser detection
# --------------------------------------------------------------------------- #

_BROWSER_NAMES = {
    "opera", "opera gx", "chrome", "google chrome", "firefox",
    "edge", "brave", "vivaldi", "chromium", "navigateur", "browser",
}

_BROWSER_PROCESSES = {
    "chrome.exe", "firefox.exe", "opera.exe", "msedge.exe",
    "brave.exe", "vivaldi.exe", "chromium.exe",
}

# --------------------------------------------------------------------------- #
#  F2 — LA source de vérité de la confirmation
#
#  Avant le sprint F, deux endroits en décidaient : le drapeau posé ici, et une liste
#  codée en dur dans `execute_tool` (kill_process, run_powershell, system_config). Le
#  moteur ne lisait que la sienne : fermer une fenêtre ou créer une tâche planifiée,
#  marqués « à confirmer » ici, s'exécutaient sans rien demander (sprint E, R04).
#
#  Désormais cette table est la seule. Le validateur en dérive son drapeau ; le moteur
#  l'applique. Deux portées :
#    - « toujours »   : quel que soit l'appelant (demande, plan, automatisation, rejeu) ;
#    - « interactif » : quand l'utilisateur le demande. Une tâche planifiée qui lance un
#      workflow a été confirmée à sa création ; personne ne peut confirmer à 3 h du matin.
#  Les actions « toujours » restent exclues des automatisations (B1-ter).
# --------------------------------------------------------------------------- #

CONFIRMATION_POLICY: dict[str, tuple[str, str]] = {
    "kill_process":    ("toujours", "arrêter un processus peut faire perdre le travail en cours"),
    "run_powershell":  ("toujours", "une commande système arbitraire"),
    "system_config":   ("toujours", "une modification de la configuration du système"),
    "window_close":    ("toujours", "fermer une fenêtre peut faire perdre le travail non enregistré"),
    "browser_open":    ("toujours", "ouvrir une adresse externe"),
    "schedule_add":    ("interactif", "créer une tâche qui se rejouera seule"),
    "trigger_add":     ("interactif", "créer un déclencheur automatique"),
    "workflow_create": ("interactif", "créer un workflow"),
    "workflow_run":    ("interactif", "lancer un workflow, soit plusieurs actions d'un coup"),
}


def confirmation_reason(tool_name: str, *, interactive: bool) -> Optional[str]:
    """Motif de confirmation de l'outil, ou None s'il n'en exige pas dans ce contexte."""
    rule = CONFIRMATION_POLICY.get(tool_name)
    if rule is None:
        return None
    scope, reason = rule
    if scope == "interactif" and not interactive:
        return None
    return reason

# --------------------------------------------------------------------------- #
#  B1 / L5 — touches autorisées pour window_hotkey
#
#  Liste blanche, comme le garde-fou docker du sprint B-minimal : on autorise
#  explicitement, on refuse le reste. Sans elle, le planificateur pouvait produire
#  window_hotkey {"keys": "Fichier"}, que l'exécuteur décomposait en sept frappes
#  (F, i, c, h, i, e, r) envoyées à la fenêtre active (rapport A, L5 / C02).
# --------------------------------------------------------------------------- #

_MODIFIER_KEYS = {"ctrl", "ctrlleft", "ctrlright", "alt", "altleft", "altright",
                  "shift", "shiftleft", "shiftright", "win", "winleft", "winright", "command", "option"}

_NAMED_KEYS = {
    "enter", "return", "tab", "esc", "escape", "space", "backspace", "delete", "del", "insert",
    "home", "end", "pageup", "pagedown", "up", "down", "left", "right",
    "capslock", "numlock", "scrolllock", "printscreen", "pause", "apps", "menu",
    "volumeup", "volumedown", "volumemute", "playpause", "nexttrack", "prevtrack",
}
_FUNCTION_KEYS = {f"f{i}" for i in range(1, 25)}
_CHARACTER_KEYS = set("abcdefghijklmnopqrstuvwxyz0123456789") | {
    "-", "=", "[", "]", "\\", ";", "'", ",", ".", "/", "`", "+", "*",
}
VALID_HOTKEY_KEYS = _MODIFIER_KEYS | _NAMED_KEYS | _FUNCTION_KEYS | _CHARACTER_KEYS

_MAX_HOTKEY_KEYS = 5


def normalize_hotkey_keys(raw) -> tuple[list[str], str]:
    """Normalise des touches en liste minuscule. Retourne (touches, erreur).

    Accepte une liste (["ctrl", "s"]) ou une chaîne de combinaison ("ctrl+s", "ctrl s").
    Toute touche hors liste blanche invalide l'ensemble : une chaîne comme « Fichier »
    est du texte, pas un raccourci.
    """
    if isinstance(raw, str):
        parts = [p for p in raw.replace("+", " ").split() if p]
    elif isinstance(raw, (list, tuple)):
        parts = list(raw)
    else:
        return [], f"paramètre 'keys' de type {type(raw).__name__}, attendu une liste ou une chaîne"

    if not parts:
        return [], "aucune touche fournie"
    if len(parts) > _MAX_HOTKEY_KEYS:
        return [], f"{len(parts)} touches, maximum {_MAX_HOTKEY_KEYS}"

    keys = []
    for part in parts:
        if not isinstance(part, str):
            return [], f"touche {part!r} : type {type(part).__name__} au lieu d'une chaîne"
        key = part.strip().lower()
        if key not in VALID_HOTKEY_KEYS:
            return [], f"touche inconnue : {part!r}"
        keys.append(key)
    return keys, ""


# --------------------------------------------------------------------------- #
#  B1-ter — automatisations : la validation comme invariant du stockage
#
#  Le planificateur horaire, les déclencheurs et les workflows exécutent des actions
#  ENREGISTRÉES, sans passer par resolve(). Ces règles s'appliquent à la création, au
#  chargement et à l'exécution (core/scheduler.py, core/trigger_engine.py,
#  core/workflow_engine.py, main.execute_automation_action). Une seule définition par
#  règle : la table ci-dessous réutilise les contrôles purs des outils.
# --------------------------------------------------------------------------- #

# Profondeur de workflow_run imbriqués : une tâche → workflow → sous-workflow →
# sous-sous-workflow. Aucun workflow existant n'en imbrique ; au-delà de trois niveaux, une
# chaîne n'est plus lisible par l'utilisateur qui l'a acceptée, et une erreur s'amplifie.
MAX_WORKFLOW_DEPTH = 3
MAX_NOTIFY_CHARS = 500
MAX_CLEANUP_AGE_DAYS = 365


def _unexpected(params: dict, allowed: set) -> str:
    extra = sorted(set(params) - allowed)
    return f"paramètre(s) inattendu(s) : {extra}" if extra else ""


def _check_no_params(params: dict) -> str:
    return _unexpected(params, set())


def _check_launch_app_call(params: dict) -> str:
    if "path" in params:
        return "paramètre 'path' interdit : seul un nom d'application est accepté"
    error = _unexpected(params, {"name", "wait"})
    if error:
        return error
    _, error = check_app_name(params.get("name"))
    if error:
        return error
    if "wait" in params and not isinstance(params["wait"], bool):
        return "'wait' doit être un booléen"
    return ""


def _check_notify_call(params: dict) -> str:
    error = _unexpected(params, {"message", "title", "duration_seconds"})
    if error:
        return error
    message = params.get("message")
    if not isinstance(message, str) or not message.strip():
        return "message de notification vide ou absent"
    if len(message) > MAX_NOTIFY_CHARS:
        return f"message de {len(message)} caractères, maximum {MAX_NOTIFY_CHARS}"
    title = params.get("title", "Atlas")
    if not isinstance(title, str) or len(title) > 100:
        return "titre de notification invalide"
    duration = params.get("duration_seconds", 5)
    if not isinstance(duration, int) or isinstance(duration, bool) or not 1 <= duration <= 60:
        return "durée de notification invalide (1 à 60 s)"
    return ""


def _check_cleanup_temp_call(params: dict) -> str:
    error = _unexpected(params, {"max_age_days"})
    if error:
        return error
    age = params.get("max_age_days", 7)
    if not isinstance(age, int) or isinstance(age, bool) or not 1 <= age <= MAX_CLEANUP_AGE_DAYS:
        return f"'max_age_days' invalide : {age!r} (entier de 1 à {MAX_CLEANUP_AGE_DAYS})"
    return ""


def _check_workflow_run_call(params: dict) -> str:
    error = _unexpected(params, {"workflow_id"})
    if error:
        return error
    wf_id = params.get("workflow_id")
    if not isinstance(wf_id, str) or not wf_id.strip() or len(wf_id) > 100:
        return "identifiant de workflow vide ou invalide"
    return ""


# Table outil → contrôle. Un outil absent de cette table n'a pas sa place dans une
# automatisation (BT2) ; sa présence ici vaut autorisation.
AUTOMATION_ACTION_CHECKS = {
    "launch_app": _check_launch_app_call,
    "notify": _check_notify_call,
    "get_diagnostics": _check_no_params,
    "maintenance_cleanup_temp": _check_cleanup_temp_call,
    "maintenance_gc": _check_no_params,
    "workflow_run": _check_workflow_run_call,
}

# Motif de refus, par famille, pour que le message dise POURQUOI.
_AUTOMATION_EXCLUSIONS = {
    "action interactive : la fenêtre au premier plan au moment du déclenchement est inconnue": {
        "window_type", "window_hotkey", "window_click", "window_close", "window_focus",
        "window_minimize", "window_maximize", "window_snap", "ui_click_element",
        "web_search_to_notepad", "browser_click", "browser_type", "browser_scroll", "browser_close",
        "browser_navigate", "browser_new_tab", "browser_ext_click", "browser_ext_type",
        "browser_ext_scroll",
    },
    "confirmation obligatoire, impossible sans utilisateur présent": {
        "kill_process", "run_powershell", "system_config", "browser_open",
    },
    "une automatisation ne crée, ne modifie ni ne relance d'autre automatisation": {
        "schedule_add", "schedule_remove", "schedule_run_now", "trigger_add", "trigger_toggle",
        "workflow_create",
    },
    "suppression définitive, rejouée à chaque exécution": {"maintenance_empty_bin"},
    "rejoue une action qui dépend du moment où elle a eu lieu": {"redo_last_action"},
    "paramètres non contrôlés (priorité de processus)": {"set_priority"},
    "sans effet utile : le résultat n'est remis à personne": {
        "list_processes", "window_list", "window_find", "window_get_active", "window_screenshot",
        "schedule_list", "trigger_list", "workflow_list", "browser_current_url",
        "browser_ext_get_content", "browser_ext_get_url", "browser_bridge_status",
        "web_search", "read_url", "screen_read",
    },
}


def _exclusion_reason(tool: str) -> str:
    for reason, tools in _AUTOMATION_EXCLUSIONS.items():
        if tool in tools:
            return reason
    return "outil inconnu"


def check_automation_action(action) -> str:
    """Contrôle UNE action enregistrée ({"action": outil, "params": {...}}). Erreur ou ""."""
    if not isinstance(action, dict):
        return f"action malformée ({type(action).__name__} au lieu d'un objet)"
    tool = action.get("action")
    if not isinstance(tool, str) or not tool:
        return "action sans nom d'outil"
    params = action.get("params") or {}
    if not isinstance(params, dict):
        return f"'{tool}' : paramètres malformés"
    check = AUTOMATION_ACTION_CHECKS.get(tool)
    if check is None:
        return f"action '{tool}' non autorisée dans une automatisation ({_exclusion_reason(tool)})"
    error = check(params)
    return f"'{tool}' : {error}" if error else ""


def check_automation_actions(actions, resolve_workflow=None, stack: tuple = ()) -> str:
    """Contrôle une liste d'actions, en descendant dans les workflow_run (cycles, profondeur).

    resolve_workflow(id) -> liste d'actions du workflow, ou None s'il est introuvable ou
    désactivé. `stack` : workflows déjà traversés, le plus externe en premier.
    """
    if not isinstance(actions, list):
        return "liste d'actions malformée"
    for index, action in enumerate(actions, 1):
        error = check_automation_action(action)
        if not error and action.get("action") == "workflow_run":
            wf_id = (action.get("params") or {})["workflow_id"].strip()
            error = _check_workflow_chain(wf_id, resolve_workflow, stack)
        if error:
            return f"action {index} — {error}"
    return ""


def _check_workflow_chain(wf_id: str, resolve_workflow, stack: tuple) -> str:
    chain = " → ".join(stack + (wf_id,))
    if wf_id in stack:
        return f"cycle de workflows : {chain}"
    if len(stack) >= MAX_WORKFLOW_DEPTH:
        return f"profondeur de workflows supérieure à {MAX_WORKFLOW_DEPTH} : {chain}"
    if resolve_workflow is None:
        return ""
    steps = resolve_workflow(wf_id)
    if steps is None:
        return f"workflow '{wf_id}' introuvable ou désactivé"
    error = check_automation_actions(steps, resolve_workflow, stack + (wf_id,))
    return f"workflow '{wf_id}' : {error}" if error else ""


# --- Signalement (BT1) : une automatisation bloquée ne doit jamais se taire --- #

AUTOMATION_TOAST_INTERVAL_S = 1800.0
_automation_notifier = None           # callable(titre, message), installé par main.py
_automation_last_toast: dict = {}     # (source, élément) → horodatage de la dernière notification


def set_automation_notifier(notifier) -> None:
    global _automation_notifier
    _automation_notifier = notifier


def report_automation_block(source: str, item: str, reason: str) -> None:
    """Journalise ET signale une automatisation bloquée.

    Trois canaux : le log applicatif ; une ligne ERR_AUTOMATION_BLOCKED dans le journal
    d'actions, celui que sert /api/logs/recent ; une notification Windows, au plus une par
    élément toutes les 30 minutes pour qu'un déclencheur réévalué toutes les 10 s ne noie
    pas l'utilisateur.
    """
    import json
    from datetime import datetime

    import core.atlas_logger as atlas_logger

    logger.warning("[AUTOMATION] %s « %s » bloqué : %s", source, item, reason)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user_input": f"automation:{source}",
        "intent": "automation/blocked",
        "tool": None,
        "target": item,
        "result": "blocked",
        "error": reason,
        "error_code": "ERR_AUTOMATION_BLOCKED",
        "latency_ms": 0,
        "retry_count": 0,
        "grounding_layer": None,
        "pipeline_stage": f"automation:{source}",
    }
    try:
        atlas_logger.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(atlas_logger.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("[AUTOMATION] journal d'actions inaccessible : %s", e)

    key = (source, item)
    now = time.time()
    if _automation_notifier is None or now - _automation_last_toast.get(key, float("-inf")) < AUTOMATION_TOAST_INTERVAL_S:
        return
    _automation_last_toast[key] = now
    try:
        _automation_notifier("Atlas — automatisation bloquée", f"{source} « {item} » : {reason}")
    except Exception as e:
        logger.error("[AUTOMATION] notification impossible : %s", e)


class Validator:
    """Mappe une intention vers un outil exact de façon déterministe."""

    def _reject(self, intent: IntentResult, reason: str, advice: str = "") -> ResolvedAction:
        """Refuse une action sans rien exécuter, avec un message destiné à l'utilisateur."""
        logger.warning("[VALIDATOR] Action refusée (%s/%s) : %s", intent.category, intent.verb, reason)
        message = f"Action refusée : {reason}."
        if advice:
            message += f" {advice}"
        return ResolvedAction(
            tool="__conversation__",
            params={"message": message},
            intent=intent,
            rejected=True,
            rejection_reason=reason,
        )

    def resolve(self, intent: IntentResult, context: dict) -> ResolvedAction:
        """
        Résolution déterministe :
        1. category + verb → outil via INTENT_CATEGORIES
        2. Contexte-aware : app running? browser bridge? destructive?
        """
        category = intent.category
        verb = intent.verb
        target = intent.target

        # --- Conversation → pas d'outil ---
        if category == "conversation":
            return ResolvedAction(
                tool="__conversation__",
                params={"message": intent.raw_input},
                intent=intent,
            )

        # --- Memory : redo → tool spécial ---
        if category == "memory" and verb == "redo":
            return ResolvedAction(
                tool="redo_last_action",
                params={},
                intent=intent,
            )

        # --- F2 v6.0 : Vision / lecture d'écran ---
        if category == "vision" and verb == "read_screen":
            return ResolvedAction(
                tool="screen_read",
                params={
                    "mode": intent.params.get("mode", "read"),
                    "summarize": intent.params.get("summarize", True),
                },
                intent=intent,
            )

        # --- Lookup outil dans INTENT_CATEGORIES ---
        cat_data = INTENT_CATEGORIES.get(category, {})
        tools_map = cat_data.get("tools", {})
        tool_name = tools_map.get(verb)

        if not tool_name:
            # Fallback : si le verb n'est pas dans la map, essayer le plus proche
            logger.warning("Verb '%s' non trouvé dans category '%s'", verb, category)
            return ResolvedAction(
                tool="__conversation__",
                params={"message": intent.raw_input},
                intent=intent,
            )

        # --- Contexte-aware resolution ---
        params = dict(intent.params)
        verification = VerificationRule()
        fallback = None

        # --- window_mgmt specializations ---
        if category == "window_mgmt":
            if verb == "open":
                # Check if app already running → window_focus instead
                if target and self._is_app_running(target, context):
                    logger.info("[VALIDATOR] '%s' déjà en cours → window_focus", target)
                    tool_name = "window_focus"
                    params = {"title": target}
                    verification = VerificationRule(
                        type="window_visible", target=target or "",
                    )
                else:
                    # B1-ter / BT6 : lancement par nom seulement. `path` exécutait n'importe
                    # quel fichier, et n'est utilisé par aucun appel légitime.
                    if params.get("path"):
                        return self._reject(intent, "lancement par chemin interdit",
                                            "Donne le nom de l'application, par exemple « ouvre Steam ».")
                    name, error = check_app_name(target or params.get("name"))
                    if error:
                        return self._reject(intent, f"application à lancer invalide ({error})")
                    tool_name = "launch_app"
                    params = {"name": name}
                    verification = VerificationRule(
                        type="process_running", target=target or "",
                    )

            elif verb == "close":
                # B1-bis : titre vide → getWindowsWithTitle("") renvoie toutes les fenêtres et
                # la première est fermée. La confirmation ne protège pas : elle porterait sur
                # « fermer une fenêtre » sans dire laquelle.
                title, error = check_window_title(target or params.get("title"))
                if error:
                    return self._reject(intent, "fenêtre à fermer non précisée",
                                        "Précise la fenêtre, par exemple « ferme le bloc-notes ».")
                tool_name = "window_close"
                params = {"title": title}

            elif verb in ("minimize", "maximize", "focus"):
                if target:
                    params = {"title": target}
                elif params.get("title") == "__last_window__" or verb == "focus":
                    # Recover last explicit window target for anaphora like "remets-la en premier plan"
                    try:
                        from core.world_state import get_world_state

                        ws = get_world_state()
                        la = ws.last_action or {}
                        la_params = la.get("params", {}) if isinstance(la, dict) else {}
                        last_title = la_params.get("title") or la_params.get("name")
                        if last_title:
                            params = {"title": last_title}
                    except Exception:
                        pass

                # B1-bis : plus de repli sur la fenêtre au premier plan (même règle que L24).
                # Quand l'utilisateur écrit à Atlas, le premier plan est souvent Atlas lui-même.
                title = params.get("title")
                if title == "__last_window__":
                    title = ""
                title, error = check_window_title(title)
                if error:
                    fg_title = (context.get("foreground_window", {}) or {}).get("title", "")
                    logger.info("[Validator] %s sans fenêtre nommée ; premier plan '%s' NON utilisé",
                                verb, fg_title or "?")
                    return self._reject(intent, "fenêtre cible non précisée",
                                        "Précise la fenêtre, par exemple « réduis le bloc-notes ».")
                params = {"title": title}
                verification = VerificationRule(
                    type="window_visible", target=target or "",
                )

            elif verb == "snap":
                title, error = check_window_title(target or params.get("title"))
                if error:
                    return self._reject(intent, "fenêtre à ancrer non précisée")
                position = params.get("position", "left")
                if position not in VALID_SNAP_POSITIONS:
                    return self._reject(
                        intent, f"position d'ancrage inconnue : {position!r}",
                        f"Positions possibles : {', '.join(VALID_SNAP_POSITIONS)}.",
                    )
                params = {"title": title, "position": position}

        # --- Web specializations ---
        elif category == "web":
            if verb == "navigate" or verb == "open_tab":
                # B1-bis : schéma d'URL en liste blanche (http, https). Une URL issue d'un
                # contenu externe ne doit ni ouvrir un fichier local ni exécuter de script.
                url, error = check_url(params.get("url"), allow_empty=(verb == "open_tab"))
                if error:
                    return self._reject(intent, f"adresse web refusée ({error})")
                params = {**params, "url": url}
                # If browser bridge connected → use bridge
                bridge = get_bridge()
                if bridge.is_connected():
                    tool_name = "browser_navigate" if verb == "navigate" else "browser_new_tab"
                else:
                    # Fallback to launch_app for browser
                    if verb == "navigate" and "url" in params:
                        tool_name = "browser_open"
                    else:
                        tool_name = "launch_app"
                        params = {"name": "opera gx", "args": [params.get("url", "")]}

            elif verb == "read":
                tool_name = "read_url"
                verification = VerificationRule(type="none")

            elif verb == "search":
                raw_lower = intent.raw_input.lower()
                raw_norm = unicodedata.normalize("NFKD", raw_lower).encode("ascii", "ignore").decode("ascii")
                wants_notepad = any(k in raw_lower for k in ["bloc notes", "bloc-notes", "blocnotes", "notepad"])
                wants_paste = any(k in raw_lower for k in ["colle", "coller", "copie", "copier", "copie-colle", "écris", "ecris", "mets", "met"])
                wants_wikipedia = ("wikipedia" in raw_norm) or ("wiki" in raw_norm)

                if wants_notepad and wants_paste and wants_wikipedia:
                    tool_name = "web_search_to_notepad"
                    params = {
                        "query": self._extract_wikipedia_query(intent.raw_input),
                        "target": "bloc notes",
                        "max_results": 5,
                    }
                    verification = VerificationRule(type="none")
                else:
                    tool_name = "web_search"
                    verification = VerificationRule(type="none")

        # --- Interaction specializations ---
        elif category == "interaction":
            if verb == "click":
                # Semantic click → route to grounding stack
                tool_name = "ui_click_element"
                # v5.3 AXE 3 — resolution priority:
                #   1. explicit app_title from the user ("dans Steam")
                #   2. last ui_click_element app (< 2min) — the user's working context
                #   3. foreground window, UNLESS it's Atlas Desktop itself
                # Rationale: when typing in the desktop UI, Atlas Desktop is the
                # foreground window. Using it as the click target made Atlas click
                # inside its own chat (v5.2 bug). last_action must win over foreground.
                app_title = params.get("app_title", "")
                if not app_title:
                    from core.world_state import get_world_state
                    app_title = _resolve_implicit_app(get_world_state(), context)
                    if app_title:
                        logger.info("[Validator] app_title résolu via last_action: '%s'", app_title)
                # B1 / L24 : plus de repli sur la fenêtre au premier plan. Elle n'a aucun
                # rapport avec la demande : au sprint A, « clique sur Fichier » a été cherché
                # dans une conversation Discord active (C05). Sans cible nommée ni contexte
                # de travail récent, on échoue explicitement.
                if not app_title:
                    fg_title = (context.get("foreground_window", {}) or {}).get("title", "")
                    logger.info(
                        "[Validator] aucune application nommée ; premier plan '%s' NON utilisé (L24)",
                        fg_title or "?",
                    )
                    return self._reject(
                        intent,
                        "application cible indéterminée pour le clic",
                        "Précise l'application, par exemple « clique sur Fichier dans le bloc-notes ».",
                    )
                params = {
                    "element_name": params.get("element_name", target or ""),
                    "app_title": app_title,
                }

            elif verb in ("type", "hotkey"):
                if verb == "type":
                    # B1-bis : texte contraint (chaîne, pas de caractère de contrôle, longueur bornée).
                    text, error = check_type_text(params.get("text"))
                    if error:
                        return self._reject(intent, f"texte à saisir invalide ({error})")
                    tool_name = "window_type"
                    params = {**params, "text": text}
                else:
                    # B1 / L5 : les touches viennent du LLM, elles ne sont pas fiables.
                    keys, error = normalize_hotkey_keys(params.get("keys"))
                    if error:
                        return self._reject(
                            intent,
                            f"raccourci clavier invalide ({error})",
                            "Pour saisir du texte, utilise une demande de frappe explicite.",
                        )
                    tool_name = "window_hotkey"
                    params = {**params, "keys": keys}

                # B1-bis : la moitié manquante de L5 — valider OÙ l'on frappe, pas seulement
                # quoi. Cible nommée, sinon fenêtre de travail récente, sinon refus. Jamais le
                # premier plan. `intent.target` n'est pas utilisé : pour une frappe issue du
                # classifieur, c'est le texte lui-même.
                window, error = check_window_title(params.get("target"))
                if error:
                    from core.world_state import get_world_state
                    window = _resolve_working_window(get_world_state())
                    if window:
                        logger.info("[Validator] frappe rattachée à la fenêtre de travail '%s'", window)
                if not window:
                    fg_title = (context.get("foreground_window", {}) or {}).get("title", "")
                    logger.info("[Validator] frappe sans fenêtre nommée ; premier plan '%s' NON utilisé",
                                fg_title or "?")
                    return self._reject(
                        intent,
                        "fenêtre cible indéterminée pour la saisie",
                        "Précise l'application, par exemple « écris bonjour dans le bloc-notes ».",
                    )
                params["target"] = window

            elif verb == "select":
                # B1-bis : clic par coordonnées — point sur un écran existant, bouton et nombre
                # de clics bornés. La fenêtre cible, si nommée, est vérifiée à l'exécution.
                x, y = params.get("x"), params.get("y")
                button, clicks = params.get("button", "left"), params.get("clicks", 1)
                error = check_click_params(x, y, button, clicks)
                if error:
                    return self._reject(intent, f"clic refusé ({error})")
                click_params = {"x": x, "y": y, "button": button, "clicks": clicks}
                window, error = check_window_title(params.get("target"))
                if not error:
                    click_params["target"] = window
                params = click_params

        # --- Process specializations ---
        # (la confirmation de kill_process est décidée par CONFIRMATION_POLICY)

        # --- Automation specializations ---
        elif category == "automation":
            # B1-ter : le contenu d'une automatisation est contrôlé dès la demande, avant la
            # confirmation. Le moteur le recontrôle à l'enregistrement, au chargement, à
            # l'exécution.
            stored = params.get("steps") if verb == "workflow_create" else params.get("actions")
            if verb in ("schedule", "trigger", "workflow_create") and stored:
                from core.workflow_engine import get_workflow_engine
                error = check_automation_actions(stored, get_workflow_engine().steps_for_validation)
                if error:
                    return self._reject(intent, f"automatisation refusée ({error})")
            if verb == "schedule":
                tool_name = "schedule_add"
                verification = VerificationRule(type="none")
                params.setdefault("trigger_type", "interval")
                params.setdefault("trigger_config", {"hours": 24})
                params.setdefault("actions", [])
            elif verb == "trigger":
                tool_name = "trigger_add"
                verification = VerificationRule(type="none")
            elif verb == "workflow":
                tool_name = "workflow_run"
                verification = VerificationRule(type="none")
            elif verb == "workflow_create":
                tool_name = "workflow_create"
                verification = VerificationRule(type="none")
            elif verb == "workflow_list":
                tool_name = "workflow_list"
                verification = VerificationRule(type="none")
            elif verb == "schedule_list":
                tool_name = "schedule_list"
                verification = VerificationRule(type="none")
            elif verb == "schedule_run_now":
                tool_name = "schedule_run_now"
                verification = VerificationRule(type="none")

        return ResolvedAction(
            tool=tool_name,
            params=params,
            # F2 : dérivée de CONFIRMATION_POLICY, la seule source de vérité. Le moteur
            # applique la même table ; aucune autre liste ne décide.
            confirmation_required=confirmation_reason(tool_name, interactive=True) is not None,
            verification=verification,
            fallback=fallback,
            intent=intent,
        )

    def _extract_wikipedia_query(self, raw_input: str) -> str:
        """Extrait une requete concise orientee Wikipedia depuis une instruction longue."""
        text = (raw_input or "").strip()

        # Priorite au texte entre guillemets : Cherche sur Wikipedia "Intelligence artificielle"
        import re
        quoted = re.findall(r"['\"]([^'\"]{2,120})['\"]", text)
        if quoted:
            return f"wikipedia {quoted[0]}"

        low = text.lower()
        idx = -1
        marker_len = len("wikipedia")
        if "wikipedia" in low:
            idx = low.find("wikipedia")
        elif "wikipédia" in low:
            idx = low.find("wikipédia")
            marker_len = len("wikipédia")

        if idx != -1:
            tail = text[idx + marker_len:]
            for stop in [" puis", " ensuite", " reviens", " colle", " copie", " dans", " sur un bloc", " sur bloc", " notepad"]:
                i = tail.lower().find(stop)
                if i != -1:
                    tail = tail[:i]
                    break
            tail = " ".join(tail.replace(":", " ").split())
            if tail:
                return f"wikipedia {tail}"

        return text

    def _is_app_running(self, app_name: str, context: dict) -> bool:
        """Vérifie si une app tourne dans le contexte actuel."""
        if not app_name:
            return False
        name_lower = app_name.lower()
        # Check top processes
        for proc in context.get("top_processes", []):
            proc_name = (proc.get("name") or "").lower()
            if name_lower in proc_name or proc_name.startswith(name_lower):
                return True
        # Check foreground window
        fg = context.get("foreground_window", {})
        fg_title = (fg.get("title") or "").lower()
        fg_process = (fg.get("process") or "").lower()
        if name_lower in fg_title or name_lower in fg_process:
            return True
        return False

    def _is_browser(self, target: str) -> bool:
        """Détecte si le target est un navigateur."""
        if not target:
            return False
        return target.lower().strip() in _BROWSER_NAMES


# --------------------------------------------------------------------------- #
#  Singleton
# --------------------------------------------------------------------------- #

_validator: Validator | None = None


def get_validator() -> Validator:
    global _validator
    if _validator is None:
        _validator = Validator()
    return _validator
