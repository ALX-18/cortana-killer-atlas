"""
Trigger Engine — Déclencheurs contextuels automatiques.

MVP 3.0 : Surveille les métriques système (GPU, CPU, RAM, processus)
et déclenche des actions quand les conditions sont remplies.
"""

import asyncio
import json
import logging
import pathlib
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger("atlas.trigger_engine")

# --------------------------------------------------------------------------- #
#  Data model
# --------------------------------------------------------------------------- #

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
TRIGGERS_FILE = DATA_DIR / "triggers.json"

MAX_ACTIVE_TRIGGERS = 20
MIN_COOLDOWN_SECONDS = 60


@dataclass
class TriggerCondition:
    metric: str         # "gpu_usage"|"cpu_usage"|"ram_usage"|"process_started"|"process_stopped"
    operator: str       # ">"|"<"|">="|"<="|"=="|"!="
    value: float | str
    duration_seconds: int = 0   # Condition vraie pendant N secondes avant déclenchement

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TriggerCondition":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ContextTrigger:
    id: str
    name: str
    condition: TriggerCondition
    actions: list[dict]
    cooldown_seconds: int = 300
    enabled: bool = True
    trigger_count: int = 0
    last_triggered: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ContextTrigger":
        cond = d.pop("condition", {})
        if isinstance(cond, dict):
            cond = TriggerCondition.from_dict(cond)
        return cls(condition=cond, **{k: v for k, v in d.items() if k in cls.__dataclass_fields__ and k != "condition"})


# --------------------------------------------------------------------------- #
#  Operator evaluation
# --------------------------------------------------------------------------- #

_OPERATORS = {
    ">":  lambda a, b: a > b,
    "<":  lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


# --------------------------------------------------------------------------- #
#  Trigger Engine
# --------------------------------------------------------------------------- #

class TriggerEngine:
    """Moteur de déclencheurs contextuels."""

    def __init__(self):
        self._triggers: dict[str, ContextTrigger] = {}
        self._condition_true_since: dict[str, float] = {}   # trigger_id → timestamp when condition first became true
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._check_interval = 10  # seconds
        self._execution_callback = None
        self._context_callback = None
        self._protection_callback = None

    async def start(self):
        """Démarre la boucle de surveillance."""
        self._load_triggers()
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("🔔 Trigger Engine démarré — %d trigger(s) chargé(s)", len(self._triggers))

    async def stop(self):
        """Arrête la boucle de surveillance."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🔔 Trigger Engine arrêté")

    def set_execution_callback(self, callback):
        """Callback pour exécuter les actions (async function(action_dict) -> dict)."""
        self._execution_callback = callback

    def set_context_callback(self, callback):
        """Callback pour obtenir le contexte système (function() -> dict)."""
        self._context_callback = callback

    def set_protection_callback(self, callback):
        """Callback pour vérifier la protection d'un processus (function(process_name) -> str)."""
        self._protection_callback = callback

    def set_check_interval(self, seconds: int):
        """Configure l'intervalle de surveillance."""
        self._check_interval = max(5, seconds)

    async def add_trigger(self, trigger: ContextTrigger) -> str:
        """Ajoute un trigger. Retourne l'ID."""
        # Enforce limits
        active_count = sum(1 for t in self._triggers.values() if t.enabled)
        if active_count >= MAX_ACTIVE_TRIGGERS:
            raise ValueError(f"Maximum de {MAX_ACTIVE_TRIGGERS} triggers actifs atteint.")

        if not trigger.id:
            trigger.id = str(uuid.uuid4())[:8]

        # Enforce minimum cooldown
        trigger.cooldown_seconds = max(MIN_COOLDOWN_SECONDS, trigger.cooldown_seconds)

        self._triggers[trigger.id] = trigger
        self._save_triggers()
        logger.info("➕ Trigger ajouté : %s (%s)", trigger.name, trigger.id)
        return trigger.id

    async def remove_trigger(self, trigger_id: str) -> bool:
        """Supprime un trigger."""
        if trigger_id not in self._triggers:
            return False
        del self._triggers[trigger_id]
        self._condition_true_since.pop(trigger_id, None)
        self._save_triggers()
        logger.info("➖ Trigger supprimé : %s", trigger_id)
        return True

    async def toggle_trigger(self, trigger_id: str, enabled: bool) -> bool:
        """Active/désactive un trigger."""
        trigger = self._triggers.get(trigger_id)
        if not trigger:
            return False
        trigger.enabled = enabled
        if not enabled:
            self._condition_true_since.pop(trigger_id, None)
        self._save_triggers()
        return True

    async def list_triggers(self) -> list[ContextTrigger]:
        """Liste tous les triggers."""
        return list(self._triggers.values())

    # ----- Monitor loop ----- #

    async def _monitor_loop(self):
        """Boucle principale de surveillance."""
        while self._running:
            try:
                await self._check_triggers()
            except Exception as e:
                logger.error("Erreur dans la boucle trigger : %s", e, exc_info=True)
            await asyncio.sleep(self._check_interval)

    async def _check_triggers(self):
        """Évalue tous les triggers actifs."""
        if not self._context_callback:
            return

        context = self._context_callback()
        now = time.monotonic()

        for trigger_id, trigger in list(self._triggers.items()):
            if not trigger.enabled:
                continue

            # Check cooldown
            if trigger.last_triggered:
                try:
                    last = datetime.fromisoformat(trigger.last_triggered)
                    elapsed = (datetime.now() - last).total_seconds()
                    if elapsed < trigger.cooldown_seconds:
                        continue
                except (ValueError, TypeError):
                    pass

            # Evaluate condition
            condition_met = self._evaluate_condition(trigger.condition, context)

            if condition_met:
                if trigger_id not in self._condition_true_since:
                    self._condition_true_since[trigger_id] = now

                # Check duration requirement
                duration_met = (now - self._condition_true_since[trigger_id]) >= trigger.condition.duration_seconds

                if duration_met:
                    # Fire trigger
                    await self._fire_trigger(trigger, context)
                    self._condition_true_since.pop(trigger_id, None)
            else:
                # Condition no longer true → reset timer
                self._condition_true_since.pop(trigger_id, None)

    def _evaluate_condition(self, condition: TriggerCondition, context: dict) -> bool:
        """Évalue une condition de trigger."""
        metric = condition.metric
        op_func = _OPERATORS.get(condition.operator)
        if not op_func:
            logger.warning("Opérateur inconnu : %s", condition.operator)
            return False

        if metric == "gpu_usage":
            current_value = context.get("gpu_usage", -1)
            if current_value < 0:
                return False
            return op_func(current_value, float(condition.value))

        elif metric == "cpu_usage":
            current_value = context.get("cpu_usage", 0)
            return op_func(current_value, float(condition.value))

        elif metric == "ram_usage":
            current_value = context.get("ram_usage", 0)
            return op_func(current_value, float(condition.value))

        elif metric == "process_started":
            proc_name = str(condition.value).lower()
            running = [p.get("name", "").lower() for p in context.get("running_processes", [])]
            is_running = any(proc_name in name for name in running)
            return op_func(is_running, True) if condition.operator == "==" else is_running

        elif metric == "process_stopped":
            proc_name = str(condition.value).lower()
            running = [p.get("name", "").lower() for p in context.get("running_processes", [])]
            is_stopped = not any(proc_name in name for name in running)
            return is_stopped

        return False

    async def _fire_trigger(self, trigger: ContextTrigger, context: dict):
        """Déclenche un trigger — exécute ses actions."""
        logger.info("🔔 Trigger déclenché : %s (%s)", trigger.name, trigger.id)

        # Check protection on target processes
        for action in trigger.actions:
            target = action.get("params", {}).get("name", "") or action.get("params", {}).get("targets", [])
            if isinstance(target, str):
                target = [target]
            for t in target:
                if t and self._protection_callback:
                    protection_level = self._protection_callback(t)
                    if protection_level == "intouchable":
                        logger.warning("🔴 Trigger '%s' : processus '%s' INTOUCHABLE — action ignorée",
                                       trigger.name, t)
                        return

        # Execute actions
        if self._execution_callback:
            for action in trigger.actions:
                try:
                    await self._execution_callback(action)
                except Exception as e:
                    logger.error("Erreur exécution trigger '%s' action : %s", trigger.name, e)

        trigger.trigger_count += 1
        trigger.last_triggered = datetime.now().isoformat()
        self._save_triggers()

    # ----- Persistence ----- #

    def _load_triggers(self):
        """Charge les triggers depuis le fichier JSON."""
        if not TRIGGERS_FILE.exists():
            self._triggers = {}
            return
        try:
            with open(TRIGGERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._triggers = {t["id"]: ContextTrigger.from_dict(t) for t in data}
            logger.info("📂 %d trigger(s) chargé(s) depuis triggers.json", len(self._triggers))
        except Exception as e:
            logger.error("Erreur chargement triggers.json : %s", e)
            self._triggers = {}

    def _save_triggers(self):
        """Persiste les triggers dans le fichier JSON."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            data = [t.to_dict() for t in self._triggers.values()]
            with open(TRIGGERS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Erreur sauvegarde triggers.json : %s", e)


# --------------------------------------------------------------------------- #
#  Singleton
# --------------------------------------------------------------------------- #

_trigger_engine: TriggerEngine | None = None


def get_trigger_engine() -> TriggerEngine:
    global _trigger_engine
    if _trigger_engine is None:
        _trigger_engine = TriggerEngine()
    return _trigger_engine
