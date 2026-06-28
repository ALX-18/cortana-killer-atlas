"""
Intent Classifier — Classification déterministe des intentions utilisateur.

Architecture v2.3 : le LLM ne choisit plus l'outil.
Le Classifier détecte la catégorie + verbe + cible via des règles heuristiques (80%).
Fallback LLM uniquement si confidence < 0.85.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("atlas.intent_classifier")


# --------------------------------------------------------------------------- #
#  Intent result
# --------------------------------------------------------------------------- #

@dataclass
class IntentResult:
    category: str           # window_mgmt | web | system | process | interaction | memory | conversation
    verb: str               # open, close, search, type, click, ...
    target: Optional[str]   # app name, URL, process name, ...
    params: dict = field(default_factory=dict)
    confidence: float = 0.0
    is_complex: bool = False   # multi-step detected
    raw_input: str = ""


# --------------------------------------------------------------------------- #
#  Categories & verb mapping
# --------------------------------------------------------------------------- #

INTENT_CATEGORIES = {
    "window_mgmt": {
        "verbs_map": {
            # FR
            "ouvre": "open", "ouvrir": "open", "lance": "open", "lancer": "open",
            "démarre": "open", "démarrer": "open", "exécute": "open",
            "ferme": "close", "fermer": "close", "quitte": "close", "quitter": "close",
            "réduis": "minimize", "réduire": "minimize", "minimise": "minimize",
            "maximise": "maximize", "maximiser": "maximize", "agrandis": "maximize",
            "agrandir": "maximize", "plein écran": "maximize",
            "affiche": "focus", "montre": "focus", "mets au premier plan": "focus",
            "premier plan": "focus", "en premier plan": "focus",
            "focus": "focus",
            "liste les fenêtres": "list", "liste fenêtres": "list",
            # EN
            "open": "open", "launch": "open", "start": "open", "run": "open",
            "close": "close", "quit": "close", "exit": "close",
            "minimize": "minimize", "maximise": "maximize", "maximize": "maximize",
            "focus": "focus", "show": "focus", "bring": "focus",
            "list windows": "list", "snap": "snap", "restore": "restore",
        },
        "tools": {
            "open": "launch_app",
            "close": "window_close",
            "minimize": "window_minimize",
            "maximize": "window_maximize",
            "focus": "window_focus",
            "list": "window_list",
            "snap": "window_snap",
            "restore": "window_restore",
        },
    },
    "web": {
        "verbs_map": {
            # FR
            "cherche": "search", "recherche": "search", "trouve": "search",
            "google": "search", "chercher": "search",
            "lis": "read", "résume": "read", "résumer": "read", "lire": "read",
            "ouvre un onglet": "open_tab", "nouvel onglet": "open_tab",
            "navigue": "navigate", "va sur": "navigate", "va à": "navigate",
            "aller sur": "navigate", "aller à": "navigate",
            # EN
            "search": "search", "find": "search", "look up": "search",
            "read": "read", "summarize": "read", "summarise": "read",
            "open tab": "open_tab", "new tab": "open_tab",
            "navigate": "navigate", "go to": "navigate", "browse": "navigate",
        },
        "tools": {
            "search": "web_search",
            "read": "read_url",
            "navigate": "browser_navigate",
            "open_tab": "browser_new_tab",
        },
    },
    "system": {
        "verbs_map": {
            # FR
            "configure": "configure", "paramètre": "configure", "règle": "configure",
            "diagnostique": "diagnose", "diagnostic": "diagnose",
            "vérifie": "diagnose", "check": "diagnose",
            "redémarre": "restart", "redémarrer": "restart",
            "éteins": "shutdown", "éteindre": "shutdown", "arrête le pc": "shutdown",
            "veille": "sleep", "mettre en veille": "sleep",
            # EN
            "configure": "configure", "set": "configure", "settings": "configure",
            "diagnose": "diagnose", "check": "diagnose",
            "restart": "restart", "reboot": "restart",
            "shutdown": "shutdown", "power off": "shutdown",
            "sleep": "sleep",
        },
        "tools": {
            "configure": "system_config",
            "diagnose": "get_diagnostics",
            "run": "run_powershell",
            "restart": "system_config",
            "shutdown": "system_config",
            "sleep": "system_config",
        },
    },
    "process": {
        "verbs_map": {
            # FR
            "tue": "kill", "tuer": "kill", "arrête": "kill", "stop": "kill",
            "kill": "kill",
            "liste les processus": "list", "liste processus": "list",
            "processus": "list",
            # EN
            "kill": "kill", "stop": "kill", "terminate": "kill",
            "list processes": "list",
        },
        "tools": {
            "kill": "kill_process",
            "list": "list_processes",
        },
    },
    "interaction": {
        "verbs_map": {
            # FR
            "tape": "type", "taper": "type", "écris": "type", "écrire": "type",
            "saisis": "type", "saisir": "type",
            "clique": "click", "cliquer": "click", "appuie": "click",
            "appuie sur": "hotkey", "raccourci": "hotkey",
            "ctrl": "hotkey",
            "scroll": "scroll", "défile": "scroll", "défiler": "scroll",
            "sélectionne": "select", "sélectionner": "select",
            # EN
            "type": "type", "write": "type", "enter": "type",
            "click": "click", "press": "hotkey",
            "scroll": "scroll", "select": "select",
        },
        "tools": {
            "type": "window_type",
            "click": "ui_click_element",
            "hotkey": "window_hotkey",
            "scroll": "browser_ext_scroll",
            "select": "window_click",
        },
    },
    "memory": {
        "verbs_map": {
            # FR
            "souviens": "remember", "souvenir": "remember", "retiens": "remember",
            "oublie": "forget", "oublier": "forget",
            "rappelle": "recall", "rappeler": "recall",
            "refais": "redo", "refaire": "redo", "encore": "redo",
            # v5.2 clôture — variantes courantes + fautes de frappe
            "refait": "redo", "relance": "redo", "relancer": "redo",
            "répète": "redo", "repete": "redo", "répéter": "redo", "repeter": "redo",
            "rejoue": "redo", "rejouer": "redo", "réexécute": "redo", "reexecute": "redo",
            "encore une fois": "redo", "à nouveau": "redo", "a nouveau": "redo",
            "qu'est-ce que j'ai fait": "recall",
            # EN
            "remember": "remember", "memorize": "remember",
            "forget": "forget",
            "recall": "recall", "what did": "recall",
            "redo": "redo", "again": "redo", "repeat": "redo",
        },
        "tools": {
            "remember": "memory_save",
            "recall": "memory_recall",
            "redo": "redo_last_action",
            "forget": "memory_forget",
        },
    },
    "automation": {
        "verbs_map": {
            # FR
            "planifie": "schedule", "programme": "schedule", "tous les": "schedule",
            "planifier": "schedule", "programmer": "schedule",
            "déclenche": "trigger", "si ": "trigger",
            "active le mode": "workflow", "workflow": "workflow",
            "automatise": "schedule", "automatiser": "schedule",
            "mode gaming": "workflow", "mode travail": "workflow",
            "mode nettoyage": "workflow", "routine du matin": "workflow",
            "nettoyage système": "workflow", "démarrage matin": "workflow",
            # EN
            "schedule": "schedule", "every": "schedule",
            "trigger": "trigger", "if ": "trigger",
            "workflow": "workflow", "activate mode": "workflow",
            "create workflow": "workflow_create", "list workflows": "workflow_list",
            "run now": "schedule_run_now", "list schedules": "schedule_list",
        },
        "tools": {
            "schedule": "schedule_add",
            "trigger": "trigger_add",
            "workflow": "workflow_run",
            "workflow_create": "workflow_create",
            "workflow_list": "workflow_list",
            "schedule_list": "schedule_list",
            "schedule_run_now": "schedule_run_now",
        },
    },
}

# Sequence keywords
_SEQUENCE_KEYWORDS = [
    "puis", "ensuite", "et après", "après ça", "et aussi",
    " et ", "then", "and then", "after that", "also",
]

# URL pattern
_URL_PATTERN = re.compile(
    r'https?://[^\s<>"\']+|www\.[^\s<>"\']+\.[a-z]{2,}',
    re.IGNORECASE,
)

# Hotkey pattern (Ctrl+X, Alt+F4, etc.)
_HOTKEY_PATTERN = re.compile(
    r'\b(ctrl|alt|shift|win|super|windows)\s*[\+\-]\s*\w+',
    re.IGNORECASE,
)

# App name extraction — after verb, capture the target
_TARGET_STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "l'",
    "mon", "ma", "mes", "sur", "dans", "à", "au", "en",
    "the", "a", "an", "my", "on", "in", "at", "to",
    "s'il", "te", "plaît", "plait", "stp",
}

_ARTICLES_RE = re.compile(
    r"\b(le|la|les|de|des|du|un|une|mon|ma|mes|l[ea]?|fenetre|fenêtre|window|application|app)\b",
    re.IGNORECASE,
)

_POLITENESS_RE = re.compile(
    r"\b(stp|svp|s'il te plait|s'il te plaît|s'il vous plait|s'il vous plaît|please)\b",
    re.IGNORECASE,
)

# v5.3 extra — recognized app names for "clique sur <element> sur <app>" parsing.
# "sur" is ambiguous (it's also the click preposition in "clique sur X"), so a
# trailing "sur <app>" is only treated as the application when <app> is recognized.
_KNOWN_APP_NAMES = {
    "steam", "discord", "spotify", "chrome", "firefox", "edge", "opera",
    "notepad", "bloc-notes", "blocnotes", "vscode", "code", "slack", "teams",
    "explorer", "explorateur", "word", "excel", "outlook", "telegram",
    "whatsapp", "obs", "twitch", "epic", "battlenet", "origin", "steamwebhelper",
}


# v5.2 clôture — typo-tolerant matching for memory/redo
# Single-word verbs only (multi-word phrases handled by substring path above)
_REDO_FUZZY_VERBS = (
    "refais", "refaire", "refait",
    "relance", "relancer",
    "répète", "repete", "répéter", "repeter",
    "rejoue", "rejouer",
    "réexécute", "reexecute",
    "recommence", "recommencer",
    "redo", "repeat", "again",
)


def _levenshtein(a: str, b: str) -> int:
    """Iterative Levenshtein distance — O(len(a)*len(b)) time, O(min) space."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a  # ensure a is the longer string
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


class IntentClassifier:
    """Classifie les intentions utilisateur de manière déterministe."""

    def classify(self, user_input: str, context: dict) -> IntentResult:
        """
        Classifie l'intention de l'utilisateur.
        Étape 1 : règles heuristiques (verbes, patterns)
        Étape 2 : fallback LLM si confidence < 0.85
        """
        raw = user_input.strip()
        normalized = raw.lower()

        # --- F2 v6.0 — Lecture d'écran (CU-1/3/4/5) ---
        # CU-3 "que fais-je actuellement" → mode activity
        if any(p in normalized for p in [
            "que fais-je", "que fais je", "qu'est-ce que je fais", "quest-ce que je fais",
            "je fais quoi", "qu'est ce que je fais",
        ]):
            return IntentResult(
                category="vision", verb="read_screen", target=None,
                params={"mode": "activity", "summarize": True},
                confidence=0.95, is_complex=False, raw_input=raw,
            )
        # CU-1/4/5 "lis-moi l'écran", "résume cette page", "que vois-tu"
        screen_read_markers = [
            "lis-moi ce qui est à l", "lis moi ce qui est a l", "lis-moi l'écran", "lis moi l'ecran",
            "lis l'écran", "lis l'ecran", "résume cette page", "resume cette page",
            "résume la page", "resume la page", "résume l'écran", "resume l'ecran",
            "que vois-tu", "que vois tu", "qu'est-ce que tu vois", "quest-ce que tu vois",
            "qu'est-ce qu'il y a à l'écran", "ce qui est affiché", "ce qui est affiche",
        ]
        if any(p in normalized for p in screen_read_markers):
            return IntentResult(
                category="vision", verb="read_screen", target=None,
                params={"mode": "read", "summarize": True},
                confidence=0.95, is_complex=False, raw_input=raw,
            )

        # --- P3 v6.0.1 — anti-faux-positif : question d'opinion → conversation ---
        # "Tu penses que…?", "que penses-tu de…?" tombaient en action (web/read).
        _opinion_verbs = ("penses", "penser", "crois", "croire", "estimes", "estimer",
                          "imagines", "imaginer", "trouves", "trouver", "pense", "crois-tu",
                          "penses-tu", "trouves-tu", "qu'en penses")
        _is_question = raw.rstrip().endswith("?") or normalized.startswith(("que ", "qu'", "est-ce", "penses-tu", "crois-tu"))
        _has_2nd_person = any(w in f" {normalized} " for w in (" tu ", " te ", " toi ", "-tu", " ton ", " ta "))
        if _is_question and _has_2nd_person and any(v in normalized for v in _opinion_verbs):
            return IntentResult(
                category="conversation", verb="chat", target=None,
                confidence=0.9, is_complex=False, raw_input=raw,
            )

        # --- P1 v6.0.1 — paramètres/réglages d'une app → clic (heuristiques Electron) ---
        # "va dans les paramètres de Discord" tombait en system/configure.
        _settings_markers = ("parametre", "paramètre", "reglage", "réglage", "settings", "configuration")
        if any(m in normalized for m in _settings_markers):
            app_found = None
            for app in _KNOWN_APP_NAMES:
                if app in normalized:
                    app_found = app
                    break
            if app_found is None:
                fg = (context or {}).get("foreground_window", {}) or {}
                fg_title = (fg.get("title", "") or "").lower()
                for app in _KNOWN_APP_NAMES:
                    if app in fg_title:
                        app_found = app
                        break
            if app_found:
                return IntentResult(
                    category="interaction", verb="click", target="paramètres",
                    params={"element_name": "paramètres", "app_title": app_found},
                    confidence=0.93, is_complex=False, raw_input=raw,
                )

        # --- Natural one-shot fast-path: wikipedia -> bloc-notes ---
        wiki_markers = ["wikipedia", "wikipédia", "wiki"]
        note_markers = ["bloc notes", "bloc-notes", "blocnotes", "notepad"]
        write_markers = ["copie", "copier", "colle", "coller", "écris", "ecris", "mets", "met"]
        if any(k in normalized for k in wiki_markers) and any(k in normalized for k in note_markers) and any(k in normalized for k in write_markers):
            return IntentResult(
                category="web",
                verb="search",
                target=raw,
                params={"query": raw},
                confidence=0.97,
                is_complex=False,
                raw_input=raw,
            )

        # --- Automation fast-paths for stable workflow/schedule commands ---
        if any(k in normalized for k in ["mode gaming", "mode travail", "nettoie", "nettoyage", "demarrage du matin", "démarrage du matin"]):
            return IntentResult(
                category="automation",
                verb="workflow",
                target=raw,
                params=self._build_params("automation", "workflow", raw, raw),
                confidence=0.98,
                is_complex=False,
                raw_input=raw,
            )

        if "cree un workflow" in normalized or "crée un workflow" in normalized or "create workflow" in normalized:
            return IntentResult(
                category="automation",
                verb="workflow_create",
                target=raw,
                params=self._build_params("automation", "workflow_create", raw, raw),
                confidence=0.98,
                is_complex=False,
                raw_input=raw,
            )

        if "liste mes workflows" in normalized or "liste les workflows" in normalized or "list workflows" in normalized:
            return IntentResult(
                category="automation",
                verb="workflow_list",
                target=None,
                params={},
                confidence=0.98,
                is_complex=False,
                raw_input=raw,
            )

        if "schedule_run_now" in normalized or "run now" in normalized:
            return IntentResult(
                category="automation",
                verb="schedule_run_now",
                target=raw,
                params=self._build_params("automation", "schedule_run_now", raw, raw),
                confidence=0.95,
                is_complex=False,
                raw_input=raw,
            )

        if "liste mes taches" in normalized or "liste les taches" in normalized or "liste les tâches" in normalized or "list schedules" in normalized:
            return IntentResult(
                category="automation",
                verb="schedule_list",
                target=None,
                params={},
                confidence=0.95,
                is_complex=False,
                raw_input=raw,
            )

        # --- Détection spéciale : URL → web/read ---
        url = self._detect_url(raw)
        if url:
            return IntentResult(
                category="web",
                verb="read",
                target=url,
                params={"url": url},
                confidence=0.95,
                is_complex=False,
                raw_input=raw,
            )

        # --- Détection spéciale : hotkey ---
        hotkey_match = _HOTKEY_PATTERN.search(normalized)
        if hotkey_match and any(v in normalized for v in ["fais", "appuie", "press", "tape"]):
            keys = self._parse_hotkey(hotkey_match.group())
            target = self._extract_target_after_keyword(normalized, ["dans", "sur", "in"])
            return IntentResult(
                category="interaction",
                verb="hotkey",
                target=target,
                params={"keys": keys, "target": target},
                confidence=0.92,
                is_complex=False,
                raw_input=raw,
            )

        # --- Détection spéciale : "refais" / "encore" / variantes → memory/redo ---
        # v5.2 clôture — expanded list to cover common typos and synonyms
        redo_words = [
            # FR canon + variantes
            "refais", "refaire", "refait",
            "relance", "relancer",
            "répète", "repete", "répéter", "repeter",
            "rejoue", "rejouer",
            "réexécute", "reexecute",
            "encore", "encore une fois", "à nouveau", "a nouveau",
            "recommence", "recommencer", "une autre fois",
            # EN
            "redo", "repeat", "again",
        ]
        if any(w in normalized for w in redo_words):
            return IntentResult(
                category="memory",
                verb="redo",
                target=None,
                confidence=0.95,
                is_complex=False,
                raw_input=raw,
            )

        # --- Détection multi-step ---
        is_complex = self._detect_sequence_keywords(normalized)

        # --- Matching verbe par catégorie ---
        best_match = None
        best_confidence = 0.0

        for cat_name, cat_data in INTENT_CATEGORIES.items():
            verbs_map = cat_data["verbs_map"]
            for trigger, verb in verbs_map.items():
                if trigger in normalized:
                    # Calcul de confidence basé sur la position et la précision
                    pos = normalized.find(trigger)
                    # Verbe en début de phrase → plus confiant
                    confidence = 0.90 if pos < 5 else 0.85
                    # Bonus si le trigger est un mot complet
                    if self._is_word_boundary(normalized, trigger, pos):
                        confidence += 0.05
                    # Strong bonus for longer/more specific triggers
                    # "diagnostic" (10 chars) beats "fais" (4 chars)
                    confidence += min(len(trigger) * 0.008, 0.10)

                    if confidence > best_confidence:
                        best_confidence = confidence
                        target = self._extract_target(normalized, trigger, cat_name)
                        best_match = IntentResult(
                            category=cat_name,
                            verb=verb,
                            target=target,
                            params=self._build_params(cat_name, verb, target, raw),
                            confidence=confidence,
                            is_complex=is_complex,
                            raw_input=raw,
                        )

        if best_match and best_match.confidence >= 0.85:
            return best_match

        # v5.2 clôture — fuzzy fallback (Levenshtein ≤ 2) on memory/redo verbs only.
        # Placed AFTER the main verb_map loop so unambiguous matches (e.g. "remets ...
        # en premier plan" → window_mgmt/focus) win first. Only fires when nothing
        # stronger matched — catches typos like "refoit" (refais), "rrefait" (refait).
        if not (best_match and best_match.confidence >= 0.7):
            if self._fuzzy_redo_match(normalized):
                return IntentResult(
                    category="memory",
                    verb="redo",
                    target=None,
                    confidence=0.75,
                    is_complex=False,
                    raw_input=raw,
                )

        # --- Fallback : considérer comme conversation ---
        if best_match and best_match.confidence >= 0.5:
            # Match partiel — retourner quand même mais avec confidence basse
            return best_match

        return IntentResult(
            category="conversation",
            verb="chat",
            target=None,
            confidence=0.8,
            is_complex=False,
            raw_input=raw,
        )

    def _detect_url(self, text: str) -> Optional[str]:
        """Détecte une URL dans le texte."""
        match = _URL_PATTERN.search(text)
        return match.group() if match else None

    def _detect_sequence_keywords(self, text: str) -> bool:
        """Détecte si l'input nécessite plusieurs actions."""
        return any(kw in text for kw in _SEQUENCE_KEYWORDS)

    def _fuzzy_redo_match(self, normalized: str) -> bool:
        """
        v5.2 clôture — typo-tolerant memory/redo detection.
        Returns True if any word in `normalized` is within Levenshtein distance ≤ 2
        of a known redo verb. Skipped for short words (< 4 chars) to avoid false positives.
        Strict scope: redo only — does not match other categories.
        """
        # Strip punctuation lightly so "refoit." → "refoit"
        cleaned = re.sub(r"[^\w\s'éèêëàâäùûüôöîïçñ-]", " ", normalized, flags=re.UNICODE)
        for token in cleaned.split():
            token = token.strip("'-")
            if len(token) < 4:
                continue
            for verb in _REDO_FUZZY_VERBS:
                if abs(len(token) - len(verb)) > 2:
                    continue  # quick reject — distance can't be ≤ 2
                if _levenshtein(token, verb) <= 2:
                    return True
        return False

    def _is_word_boundary(self, text: str, word: str, pos: int) -> bool:
        """Vérifie que le match est un mot complet (pas un sous-mot)."""
        if pos > 0 and text[pos - 1].isalnum():
            return False
        end = pos + len(word)
        if end < len(text) and text[end].isalnum():
            return False
        return True

    def _extract_target(self, normalized: str, trigger: str, category: str) -> Optional[str]:
        """Extrait la cible (app name, URL, etc.) du texte."""
        # Remove everything before and including the matched verb.
        pattern = rf".*?\b{re.escape(trigger)}\b"
        target = re.sub(pattern, "", normalized, flags=re.IGNORECASE).strip()

        # Stop at sequence markers.
        target = re.split(r"\b(puis|ensuite|et apres|et après|après|after|then|and then)\b", target, maxsplit=1)[0]

        # Remove common articles/noise and politeness markers.
        target = _ARTICLES_RE.sub(" ", target)
        target = _POLITENESS_RE.sub(" ", target)

        # Final cleanup.
        target = " ".join(target.split()).strip().rstrip(".,!?;:")

        # Remove residual leading prepositions often seen in click/focus commands.
        target = re.sub(r"^(sur|dans|in|on|to)\s+", "", target, flags=re.IGNORECASE).strip()
        return target if target else None

    def _extract_target_after_keyword(self, text: str, keywords: list[str]) -> Optional[str]:
        """Extrait la cible après un mot-clé spécifique (dans, sur, in)."""
        for kw in keywords:
            idx = text.rfind(f" {kw} ")
            if idx != -1:
                after = text[idx + len(kw) + 2:].strip()
                words = [w for w in after.split() if w not in _TARGET_STOPWORDS]
                return " ".join(words).strip().rstrip(".,!?;:") or None
        return None

    def _parse_hotkey(self, hotkey_str: str) -> list[str]:
        """Parse 'Ctrl+S' ou 'ctrl-a' en liste ['ctrl', 's']."""
        parts = re.split(r'[\+\-\s]+', hotkey_str.strip().lower())
        return [p for p in parts if p]

    def _build_params(self, category: str, verb: str, target: Optional[str], raw: str) -> dict:
        """Construit les paramètres d'outil à partir de l'intention."""
        params = {}

        if category == "window_mgmt":
            if verb == "open" and target:
                params["name"] = target
            elif target:
                params["title"] = target

            if verb == "focus" and not params.get("title"):
                raw_low = raw.lower()
                # Ex: "mets la fenetre de discord en premier plan"
                m = re.search(r"\bde\s+(.+?)\s+\b(en|au)\s+premier\s+plan\b", raw_low)
                if m:
                    params["title"] = m.group(1).strip().rstrip(".,!?;:")
                else:
                    # Ex: "remets la en premier plan" -> pronoun target to be resolved by validator/world_state
                    if re.search(r"\b(la|le|celle|celui|it|that)\b", raw_low):
                        params["title"] = "__last_window__"

        elif category == "web":
            if verb == "search" and target:
                params["query"] = target
            elif verb == "read":
                url = self._detect_url(raw)
                params["url"] = url or target or ""
            elif verb in ("navigate", "open_tab"):
                url = self._detect_url(raw)
                if url:
                    params["url"] = url
                elif target:
                    # Assume it's a domain
                    t = target.strip()
                    if "." in t and not t.startswith("http"):
                        params["url"] = f"https://{t}"
                    else:
                        params["url"] = f"https://www.{t}.com" if t else ""

        elif category == "interaction":
            if verb == "type":
                # Extract quoted text
                quoted = re.findall(r"['\"](.+?)['\"]", raw)
                params["text"] = quoted[0] if quoted else target or ""
                # Find target app
                app_target = self._extract_target_after_keyword(raw.lower(), ["dans", "sur", "in"])
                if app_target:
                    params["target"] = app_target
            elif verb == "click":
                raw_low = raw.lower()
                # Pattern: "sur la fenetre <app> clique sur <element>"
                m2 = re.search(r"\bsur\s+la\s+fenetre\s+(.+?)\s+clique\s+sur\s+(.+)$", raw_low)
                if m2:
                    app_title = m2.group(1).strip().rstrip(".,!?;:")
                    element = m2.group(2).strip().rstrip(".,!?;:")
                    params["element_name"] = element
                    params["app_title"] = app_title
                    return params

                # Pattern: "clique sur <element> dans <app>"
                m = re.search(r"\bsur\s+(.+?)\s+\b(dans|in)\b\s+(.+)$", raw_low)
                # v5.3 extra — Pattern: "clique sur <element> sur <app>" (last sur = app)
                # Greedy element so the trailing "sur <app>" wins; gated on known apps.
                m_sur = re.search(r"\bsur\s+(.+)\s+\bsur\s+([\w-]+)$", raw_low)
                if m:
                    element = m.group(1).strip().rstrip(".,!?;:")
                    app_title = m.group(3).strip().rstrip(".,!?;:")
                    params["element_name"] = element
                    params["app_title"] = app_title
                elif m_sur and m_sur.group(2).strip().lower() in _KNOWN_APP_NAMES:
                    element = m_sur.group(1).strip().rstrip(".,!?;:")
                    app_title = m_sur.group(2).strip().rstrip(".,!?;:")
                    params["element_name"] = element
                    params["app_title"] = app_title
                else:
                    element = target or ""
                    element = re.sub(r"^(sur|dans|in|on)\s+", "", element, flags=re.IGNORECASE).strip()
                    params["element_name"] = element
                    app_target = self._extract_target_after_keyword(raw_low, ["dans", "in"])
                    if app_target:
                        params["app_title"] = app_target

        elif category == "process":
            if verb == "kill" and target:
                params["name"] = target

        elif category == "automation":
            if verb == "schedule" and target:
                target_lower = target.lower() if target else ""
                params["name"] = target_lower
                # Heuristic: "tous les lundis a 9h lance steam"
                if "lundi" in target_lower:
                    params["trigger_type"] = "cron"
                    params["trigger_config"] = {"day_of_week": "mon", "hour": 9, "minute": 0}
                elif "mardi" in target_lower:
                    params["trigger_type"] = "cron"
                    params["trigger_config"] = {"day_of_week": "tue", "hour": 9, "minute": 0}
                else:
                    params["trigger_type"] = "interval"
                    params["trigger_config"] = {"hours": 24}

                app_targets = ["steam", "discord", "vscode", "opera gx", "spotify"]
                app = "steam"
                for a in app_targets:
                    if a in target_lower:
                        app = a
                        break
                params["actions"] = [{"action": "launch_app", "params": {"name": app}}]
            elif verb == "trigger" and target:
                params["name"] = target
            elif verb == "workflow":
                # Extract workflow ID from known modes
                wf_map = {
                    "gaming": "mode_gaming", "jeu": "mode_gaming",
                    "travail": "mode_travail", "work": "mode_travail",
                    "nettoyage": "nettoyage_systeme", "nettoie": "nettoyage_systeme", "clean": "nettoyage_systeme", "systeme": "nettoyage_systeme",
                    "matin": "demarrage_matin", "morning": "demarrage_matin",
                }
                for key, wf_id in wf_map.items():
                    if key in (target or "").lower() or key in raw.lower():
                        params["workflow_id"] = wf_id
                        break
                if "workflow_id" not in params and target:
                    params["workflow_id"] = target.lower().replace(" ", "_")
            elif verb == "workflow_create":
                params["name"] = "workflow_discord_spotify"
                params["description"] = "Workflow créé par conversation"
                steps = []
                if "discord" in raw.lower():
                    steps.append({"name": "Lancer Discord", "action": "launch_app", "params": {"name": "discord"}})
                if "spotify" in raw.lower():
                    steps.append({"name": "Lancer Spotify", "action": "launch_app", "params": {"name": "spotify"}})
                if not steps:
                    steps.append({"name": "Notification", "action": "notify", "params": {"message": "Workflow exécuté"}})
                params["steps"] = steps
            elif verb == "schedule_run_now":
                # Select most recent job when no explicit ID is given
                params["job_id"] = "latest"

        return params


# --------------------------------------------------------------------------- #
#  Singleton
# --------------------------------------------------------------------------- #

_classifier: Optional[IntentClassifier] = None


def get_classifier() -> IntentClassifier:
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier
