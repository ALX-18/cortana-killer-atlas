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
from tools.browser_bridge import get_bridge

logger = logging.getLogger("atlas.validator")

_IMPLICIT_APP_TTL_S = 120.0  # 2 minutes


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

# Destructive actions
_DESTRUCTIVE_VERBS = {"close", "kill", "shutdown", "restart"}

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
        confirmation = verb in _DESTRUCTIVE_VERBS
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
                    tool_name = "launch_app"
                    params = {"name": target} if target else params
                    verification = VerificationRule(
                        type="process_running", target=target or "",
                    )

            elif verb == "close":
                tool_name = "window_close"
                params = {"title": target} if target else params
                confirmation = True

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

                # Final fallback: current foreground window title
                if not params.get("title"):
                    fg_title = (context.get("foreground_window", {}) or {}).get("title")
                    if fg_title:
                        params["title"] = fg_title
                verification = VerificationRule(
                    type="window_visible", target=target or "",
                )

        # --- Web specializations ---
        elif category == "web":
            if verb == "navigate" or verb == "open_tab":
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

            elif verb == "type":
                tool_name = "window_type"

            elif verb == "hotkey":
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

        # --- Process specializations ---
        elif category == "process":
            if verb == "kill":
                confirmation = True

        # --- Automation specializations ---
        elif category == "automation":
            if verb == "schedule":
                tool_name = "schedule_add"
                confirmation = True
                verification = VerificationRule(type="none")
                params.setdefault("trigger_type", "interval")
                params.setdefault("trigger_config", {"hours": 24})
                params.setdefault("actions", [])
            elif verb == "trigger":
                tool_name = "trigger_add"
                confirmation = True
                verification = VerificationRule(type="none")
            elif verb == "workflow":
                tool_name = "workflow_run"
                confirmation = True
                verification = VerificationRule(type="none")
            elif verb == "workflow_create":
                tool_name = "workflow_create"
                confirmation = True
                verification = VerificationRule(type="none")
            elif verb == "workflow_list":
                tool_name = "workflow_list"
                confirmation = False
                verification = VerificationRule(type="none")
            elif verb == "schedule_list":
                tool_name = "schedule_list"
                confirmation = False
                verification = VerificationRule(type="none")
            elif verb == "schedule_run_now":
                tool_name = "schedule_run_now"
                confirmation = False
                verification = VerificationRule(type="none")

        return ResolvedAction(
            tool=tool_name,
            params=params,
            confirmation_required=confirmation,
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
