"""
World State — Maintient l'état du monde entre les actions.

Snapshot léger mis à jour après chaque action pour fournir du contexte
au Planner et au Classifier.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Any

logger = logging.getLogger("atlas.world_state")


@dataclass
class WorldState:
    running_processes: list[dict] = field(default_factory=list)
    foreground_window: dict = field(default_factory=dict)
    last_action: Optional[dict] = None       # {tool, params, result}
    last_action_ts: float = 0.0              # time.time() when last_action was recorded
    last_action_raw: Optional[str] = None     # raw user input of last action
    conversation_history: list[dict] = field(default_factory=list)  # last N
    pending_plan: Optional[Any] = None        # ExecutionPlan in progress

    _MAX_HISTORY = 10

    def update_from_context(self, context: dict):
        """Met à jour le state depuis le contexte système."""
        self.running_processes = context.get("top_processes", [])
        self.foreground_window = context.get("foreground_window", {})

    def update_after_action(self, tool: str, params: dict, result: dict,
                            raw_input: str = ""):
        """Met à jour le state après chaque action exécutée."""
        self.last_action = {
            "tool": tool,
            "params": params,
            "result": result,
        }
        self.last_action_ts = time.time()
        if raw_input:
            self.last_action_raw = raw_input

    def add_to_history(self, role: str, content: str):
        """Ajoute un échange à l'historique de conversation."""
        self.conversation_history.append({"role": role, "content": content})
        # Garder seulement les N derniers
        if len(self.conversation_history) > self._MAX_HISTORY:
            self.conversation_history = self.conversation_history[-self._MAX_HISTORY:]

    def get_context_summary(self) -> str:
        """Résumé compact pour injection dans les prompts LLM."""
        parts = []

        # Foreground
        fg = self.foreground_window
        if fg:
            parts.append(f"Fenêtre active: {fg.get('title', '?')} ({fg.get('process', '?')})")

        # Last action
        if self.last_action:
            la = self.last_action
            parts.append(f"Dernière action: {la.get('tool', '?')}({la.get('params', {})})")

        # Top 5 processes
        if self.running_processes:
            top5 = [p.get("name", "?") for p in self.running_processes[:5]]
            parts.append(f"Processus actifs: {', '.join(top5)}")

        return " | ".join(parts) if parts else "Aucun contexte disponible."


# --------------------------------------------------------------------------- #
#  Singleton
# --------------------------------------------------------------------------- #

_world_state: WorldState | None = None


def get_world_state() -> WorldState:
    global _world_state
    if _world_state is None:
        _world_state = WorldState()
    return _world_state
