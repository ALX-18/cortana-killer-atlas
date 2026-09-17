"""
Planner — Génère des plans multi-étapes via Qwen2.5 14B.

Utilisé uniquement quand l'IntentClassifier détecte is_complex=True.
Le LLM planifie, le Validator valide chaque étape.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from core.validator import ResolvedAction, VerificationRule, get_validator

logger = logging.getLogger("atlas.planner")

# Étapes qui déterminent l'application de travail pour les étapes suivantes (B1 / L24).
_APP_TARGET_ACTIONS = {"open", "launch", "focus", "maximize", "minimize"}


@dataclass
class PlanStep:
    action: str        # verb
    target: str        # app, URL, etc.
    params: dict = field(default_factory=dict)
    verify: str = ""   # what to verify after
    wait_for_completion: bool = True
    resolved: Optional[ResolvedAction] = None


@dataclass
class ExecutionPlan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    fallback: str = "ask_user"


_PLANNER_SYSTEM_PROMPT = """\
Tu es un planificateur d'actions pour Atlas, un assistant bureau Windows.
Génère un plan JSON structuré, UNIQUEMENT du JSON, pas de texte.

Format :
{"goal": "description courte", "steps": [{"action": "verbe", "target": "cible", "params": {}, "verify": "condition", "wait_for_completion": true}], "fallback": "ask_user"}

Verbes disponibles : open, close, type, click, search, read, navigate, hotkey, minimize, maximize, focus

Exemples :
- "Ouvre le bloc-notes et écris hello" →
{"goal": "Ouvrir bloc-notes et écrire hello", "steps": [{"action": "open", "target": "bloc-notes", "params": {}, "verify": "window_visible", "wait_for_completion": true}, {"action": "type", "target": "bloc-notes", "params": {"text": "hello"}, "verify": "none", "wait_for_completion": false}], "fallback": "ask_user"}

- "Cherche la météo et ouvre le premier résultat" →
{"goal": "Rechercher météo puis ouvrir résultat", "steps": [{"action": "search", "target": "météo", "params": {"query": "météo"}, "verify": "none", "wait_for_completion": true}, {"action": "navigate", "target": "", "params": {"url": "first_result"}, "verify": "url_loaded", "wait_for_completion": false}], "fallback": "ask_user"}

RÈGLES :
- Chaque étape doit avoir un verbe clair de la liste ci-dessus
- verify peut être : window_visible, process_running, url_loaded, none
- wait_for_completion = true si l'étape suivante dépend du résultat
- Ne pas inventer d'outils ou de verbes
"""


class Planner:
    """Génère des plans multi-étapes via LLM."""

    async def plan(self, intent, context: dict) -> ExecutionPlan:
        """
        Génère un plan à partir d'une intention complexe.
        Utilise Qwen2.5 14B pour décomposer en étapes.
        Chaque étape est validée par le Validator.
        """
        from core.ollama_client import chat_full

        from core.world_state import get_world_state
        ws = get_world_state()

        prompt = f"Planifie cette demande : \"{intent.raw_input}\"\nContexte : {ws.get_context_summary()}"

        try:
            response = await chat_full(
                user_message=prompt,
                context=context,
                system_prompt=_PLANNER_SYSTEM_PROMPT,
            )
            plan = self._parse_plan(response)
            plan = self._validate_plan(plan, context)
            return plan
        except Exception as e:
            logger.error("Planner failed: %s", e, exc_info=True)
            # Fallback : simple plan from intent
            return self._fallback_plan(intent)

    async def replan(self, original_plan: ExecutionPlan,
                     failed_step: int, error: str,
                     context: dict) -> ExecutionPlan:
        """Replanning après échec d'une étape."""
        from core.ollama_client import chat_full
        from core.world_state import get_world_state
        ws = get_world_state()

        prompt = (
            f"Le plan a échoué à l'étape {failed_step + 1}.\n"
            f"Plan original : {original_plan.goal}\n"
            f"Erreur : {error}\n"
            f"Contexte actuel : {ws.get_context_summary()}\n"
            f"Propose un plan alternatif."
        )

        try:
            response = await chat_full(
                user_message=prompt,
                context=context,
                system_prompt=_PLANNER_SYSTEM_PROMPT,
            )
            return self._parse_plan(response)
        except Exception as e:
            logger.error("Replan failed: %s", e)
            return ExecutionPlan(goal="replan_failed", steps=[], fallback="ask_user")

    def _parse_plan(self, response: str) -> ExecutionPlan:
        """Parse la réponse LLM en ExecutionPlan."""
        # Find JSON in response
        stripped = response.strip()
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            # Try to extract JSON
            start = stripped.find("{")
            end = stripped.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    data = json.loads(stripped[start:end])
                except json.JSONDecodeError:
                    return ExecutionPlan(goal="parse_failed", steps=[], fallback="ask_user")
            else:
                return ExecutionPlan(goal="parse_failed", steps=[], fallback="ask_user")

        steps = []
        for s in data.get("steps", []):
            steps.append(PlanStep(
                action=s.get("action", ""),
                target=s.get("target", ""),
                params=s.get("params", {}),
                verify=s.get("verify", "none"),
                wait_for_completion=s.get("wait_for_completion", True),
            ))

        return ExecutionPlan(
            goal=data.get("goal", ""),
            steps=steps,
            fallback=data.get("fallback", "ask_user"),
        )

    def _validate_plan(self, plan: ExecutionPlan, context: dict) -> ExecutionPlan:
        """Valide chaque étape du plan via le Validator.

        B1 / L24 : les étapes sont toutes résolues AVANT la première exécution. Une étape
        « clique sur X » ne voit donc pas l'application ouverte par l'étape précédente, et
        se rabattait sur la fenêtre au premier plan — au sprint A, une conversation Discord
        (C05). L'application des étapes précédentes est désormais transmise explicitement.

        B1 / L5 : si le validateur refuse une étape, tout le plan est abandonné. Un plan qui
        contient un paramètre absurde n'est pas un plan de confiance ; exécuter ses autres
        étapes reviendrait à agir à moitié sur la foi d'une sortie LLM déjà démentie.
        """
        from core.intent_classifier import IntentResult

        validator = get_validator()
        current_app = ""

        for step in plan.steps:
            params = dict(step.params or {})
            if step.action == "click" and not params.get("app_title") and current_app:
                params["app_title"] = current_app
                logger.info("[PLANNER] Étape 'click' rattachée à l'application '%s'", current_app)

            intent = IntentResult(
                category=self._verb_to_category(step.action),
                verb=step.action,
                target=step.target,
                params=params,
                confidence=0.9,
                raw_input="",
            )
            resolved = validator.resolve(intent, context)
            step.resolved = resolved

            if resolved.rejected:
                logger.warning(
                    "[PLANNER] Plan abandonné : étape '%s' refusée (%s)",
                    step.action, resolved.rejection_reason,
                )
                step.params = params
                return ExecutionPlan(goal=plan.goal, steps=[step], fallback=plan.fallback)

            if step.action in _APP_TARGET_ACTIONS and step.target:
                current_app = step.target
            elif params.get("app_title"):
                current_app = params["app_title"]

        return plan

    def _fallback_plan(self, intent) -> ExecutionPlan:
        """Plan de fallback simple basé sur l'intention."""
        return ExecutionPlan(
            goal=intent.raw_input,
            steps=[PlanStep(
                action=intent.verb,
                target=intent.target or "",
                params=intent.params,
            )],
            fallback="ask_user",
        )

    def _verb_to_category(self, verb: str) -> str:
        """Mappe un verbe vers sa catégorie."""
        verb_category_map = {
            "open": "window_mgmt", "close": "window_mgmt",
            "minimize": "window_mgmt", "maximize": "window_mgmt",
            "focus": "window_mgmt",
            "search": "web", "read": "web", "navigate": "web",
            "type": "interaction", "click": "interaction",
            "hotkey": "interaction", "scroll": "interaction",
            "kill": "process", "launch": "window_mgmt",
            "schedule": "automation", "trigger": "automation",
            "workflow": "automation",
        }
        return verb_category_map.get(verb, "window_mgmt")


# --------------------------------------------------------------------------- #
#  Singleton
# --------------------------------------------------------------------------- #

_planner: Planner | None = None


def get_planner() -> Planner:
    global _planner
    if _planner is None:
        _planner = Planner()
    return _planner
