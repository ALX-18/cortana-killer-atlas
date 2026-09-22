"""
Workflow Engine — Séquences réutilisables YAML.

MVP 3.0 : Charge des workflows depuis data/workflows/, permet
l'exécution séquentielle d'étapes, et la création par conversation.
"""

import contextvars
import json
import logging
import pathlib
import uuid
import time
from dataclasses import dataclass, field
from typing import Optional

import yaml

logger = logging.getLogger("atlas.workflow_engine")

# --------------------------------------------------------------------------- #
#  Paths
# --------------------------------------------------------------------------- #

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
WORKFLOWS_DIR = DATA_DIR / "workflows"

_SOURCE = "workflow"

# B1-ter / BT4 : workflows en cours d'exécution dans la tâche asyncio courante. Un
# workflow_run imbriqué passe par execute_tool puis revient ici, dans le même contexte.
_RUNNING: contextvars.ContextVar[tuple] = contextvars.ContextVar("atlas_running_workflows", default=())


# --------------------------------------------------------------------------- #
#  Data model
# --------------------------------------------------------------------------- #

@dataclass
class WorkflowStep:
    name: str
    action: str
    params: dict = field(default_factory=dict)
    skip_if_intouchable: bool = False
    wait_for_completion: bool = False

    def to_dict(self) -> dict:
        d = {"name": self.name, "action": self.action, "params": self.params}
        if self.skip_if_intouchable:
            d["skip_if_intouchable"] = True
        if self.wait_for_completion:
            d["wait_for_completion"] = True
        return d


@dataclass
class WorkflowCondition:
    type: str = ""           # "confirm_before_run"
    message: str = ""

    def to_dict(self) -> dict:
        return {"type": self.type, "message": self.message}


@dataclass
class Workflow:
    id: str
    name: str
    description: str = ""
    version: str = "1.0"
    created_by: str = "user_manual"
    steps: list[WorkflowStep] = field(default_factory=list)
    conditions: list[WorkflowCondition] = field(default_factory=list)
    # B1-ter : motif de désactivation, calculé au chargement ; jamais écrit dans le fichier.
    invalid_reason: Optional[str] = None

    def as_actions(self) -> list[dict]:
        return [{"action": s.action, "params": s.params} for s in self.steps]

    def to_yaml_dict(self) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "created_by": self.created_by,
            "steps": [s.to_dict() for s in self.steps],
        }
        if self.conditions:
            d["conditions"] = [c.to_dict() for c in self.conditions]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Workflow":
        steps = []
        for s in d.get("steps", []):
            steps.append(WorkflowStep(
                name=s.get("name", ""),
                action=s.get("action", ""),
                params=s.get("params", {}),
                skip_if_intouchable=s.get("skip_if_intouchable", False),
                wait_for_completion=s.get("wait_for_completion", False),
            ))
        conditions = []
        for c in d.get("conditions", []):
            conditions.append(WorkflowCondition(
                type=c.get("type", ""),
                message=c.get("message", ""),
            ))
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            version=d.get("version", "1.0"),
            created_by=d.get("created_by", "user_manual"),
            steps=steps,
            conditions=conditions,
        )


# --------------------------------------------------------------------------- #
#  Workflow Engine
# --------------------------------------------------------------------------- #

class WorkflowEngine:
    """Moteur d'exécution de workflows YAML."""

    def __init__(self):
        self._workflows: dict[str, Workflow] = {}
        self._execution_callback = None
        self._protection_callback = None
        self._notification_callback = None
        self._loaded = False

    def load_workflows(self):
        """Charge tous les fichiers .yaml du répertoire workflows.

        B1-ter : deux passes. On lit tout, puis on valide chaque workflow en descendant dans
        ses workflow_run (cycles, profondeur). Un workflow invalide reste listé, désactivé et
        signalé ; un fichier illisible est signalé. Aucun fichier n'est jamais réécrit.
        """
        from core.validator import report_automation_block

        WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
        self._workflows = {}
        for yaml_file in sorted(WORKFLOWS_DIR.glob("*.yaml")):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not (data and isinstance(data, dict) and data.get("id")):
                    raise ValueError("objet YAML avec un champ 'id' attendu")
                if not isinstance(data.get("steps", []), list):
                    raise ValueError("'steps' doit être une liste")
                wf = Workflow.from_dict(data)
            except Exception as e:
                report_automation_block(_SOURCE, yaml_file.name, f"fichier illisible ({e}), laissé intact")
                continue
            self._workflows[wf.id] = wf
            logger.debug("📋 Workflow chargé : %s (%s)", wf.name, wf.id)

        def resolve(wf_id):  # pendant le chargement : tous les workflows lus, valides ou non
            wf = self._workflows.get(wf_id)
            return wf.as_actions() if wf else None

        for wf in self._workflows.values():
            reason = self._validate(wf, resolve)
            if reason:
                wf.invalid_reason = reason
                report_automation_block(_SOURCE, wf.name or wf.id, reason)
        self._loaded = True
        logger.info("📋 Workflow Engine : %d workflow(s) chargé(s)", len(self._workflows))

    @staticmethod
    def _validate(wf: Workflow, resolve) -> str:
        from core.validator import check_automation_actions
        return check_automation_actions(wf.as_actions(), resolve, (wf.id,))

    def steps_for_validation(self, workflow_id: str) -> Optional[list[dict]]:
        """Actions d'un workflow valide, pour contrôler une tâche ou un déclencheur qui le lance.
        None s'il est introuvable ou désactivé."""
        if not self._loaded:
            self.load_workflows()
        wf = self._workflows.get(workflow_id)
        if wf is None or wf.invalid_reason:
            return None
        return wf.as_actions()

    def set_execution_callback(self, callback):
        """Callback async pour exécuter une action (async function(action_dict) -> dict)."""
        self._execution_callback = callback

    def set_protection_callback(self, callback):
        """Callback pour vérifier la protection d'un processus."""
        self._protection_callback = callback

    def set_notification_callback(self, callback):
        """Callback pour envoyer des notifications."""
        self._notification_callback = callback

    async def run_workflow(self, workflow_id: str) -> dict:
        """Exécute un workflow par son ID."""
        from core.validator import MAX_WORKFLOW_DEPTH, report_automation_block

        wf = self._workflows.get(workflow_id)
        if not wf:
            return {"success": False, "message": f"Workflow '{workflow_id}' introuvable."}

        # B1-ter : garde à l'exécution — cycle ou profondeur, même si le contenu a changé
        # depuis le chargement ; puis revalidation complète avant la première étape.
        running = _RUNNING.get()
        reason = ""
        if workflow_id in running:
            reason = f"cycle de workflows à l'exécution : {' → '.join(running + (workflow_id,))}"
        elif len(running) >= MAX_WORKFLOW_DEPTH:
            reason = f"profondeur de workflows supérieure à {MAX_WORKFLOW_DEPTH} à l'exécution"
        else:
            reason = wf.invalid_reason or self._validate(wf, self.steps_for_validation)
        if reason:
            wf.invalid_reason = wf.invalid_reason or reason
            report_automation_block(_SOURCE, wf.name or wf.id, reason)
            return {"success": False, "status": "blocked",
                    "message": f"Workflow '{wf.name}' désactivé : {reason}."}

        token = _RUNNING.set(running + (workflow_id,))
        try:
            return await self._run_steps(wf)
        finally:
            _RUNNING.reset(token)

    async def _run_steps(self, wf: Workflow) -> dict:
        logger.info("▶️ Exécution workflow : %s (%s)", wf.name, wf.id)
        results = []

        for idx, step in enumerate(wf.steps):
            step_num = idx + 1
            logger.info("  Étape %d/%d : %s", step_num, len(wf.steps), step.name)
            start = time.monotonic()

            # Check protection
            if step.skip_if_intouchable and self._protection_callback:
                targets = step.params.get("targets", [])
                if isinstance(targets, str):
                    targets = [targets]
                target_name = step.params.get("name", "")
                if target_name:
                    targets.append(target_name)

                skip = False
                for t in targets:
                    if t and self._protection_callback(t) == "intouchable":
                        logger.warning("🔴 Étape '%s' : processus '%s' INTOUCHABLE — skip", step.name, t)
                        results.append({
                            "step": step_num,
                            "name": step.name,
                            "status": "skipped",
                            "message": f"Processus '{t}' intouchable",
                        })
                        skip = True
                        break
                if skip:
                    continue

            # Handle notify action
            if step.action == "notify":
                msg = step.params.get("message", "")
                notify_error = None
                if self._notification_callback:
                    try:
                        await self._notification_callback(msg)
                    except Exception as e:
                        logger.error("Erreur notification : %s", e)
                        notify_error = str(e)
                results.append({
                    "step": step_num,
                    "name": step.name,
                    "status": "error" if notify_error else "success",
                    "message": msg,
                    "error": notify_error,
                })
                await self._log_workflow_step(wf, step, results[-1], int((time.monotonic() - start) * 1000))
                continue

            # Execute action
            if self._execution_callback:
                action = {"action": step.action, "params": step.params}
                try:
                    result = await self._execution_callback(action)
                    results.append({
                        "step": step_num,
                        "name": step.name,
                        **result,
                    })
                    await self._log_workflow_step(wf, step, results[-1], int((time.monotonic() - start) * 1000))
                except Exception as e:
                    logger.error("Erreur étape '%s' : %s", step.name, e)
                    results.append({
                        "step": step_num,
                        "name": step.name,
                        "status": "error",
                        "message": str(e),
                    })
                    await self._log_workflow_step(wf, step, results[-1], int((time.monotonic() - start) * 1000))
            else:
                results.append({
                    "step": step_num,
                    "name": step.name,
                    "status": "error",
                    "message": "Pas de callback d'exécution configuré",
                })
                await self._log_workflow_step(wf, step, results[-1], int((time.monotonic() - start) * 1000))

            if step.wait_for_completion:
                import asyncio
                await asyncio.sleep(1.5)

        summary = f"Workflow '{wf.name}' terminé — {sum(1 for r in results if r.get('status') == 'success')}/{len(wf.steps)} étapes réussies"
        logger.info("✅ %s", summary)
        criteria = self._evaluate_workflow_criteria(wf.id, results)
        return {"success": True, "message": summary, "results": results, "criteria": criteria}

    async def _log_workflow_step(self, workflow: Workflow, step: WorkflowStep, result: dict, latency_ms: int):
        """Write each workflow step as PASS/FAIL in atlas_actions.jsonl."""
        try:
            from core.atlas_logger import log_action

            status = result.get("status", "error")
            await log_action(
                user_input=f"workflow:{workflow.id}",
                intent_category="workflow",
                intent_verb="run",
                tool=step.action,
                target=step.name,
                result="success" if status == "success" else "failure",
                error=result.get("error") or (None if status == "success" else result.get("message", "workflow_step_error")),
                latency_ms=latency_ms,
                error_code=None if status == "success" else "ERR_WORKFLOW_STEP_FAILED",
                retry_count=0,
                grounding_layer=None,
                pipeline_stage=f"workflow:{workflow.id}",
            )
        except Exception as e:
            logger.debug("Workflow step structured log failed: %s", e)

    def _evaluate_workflow_criteria(self, workflow_id: str, results: list[dict]) -> dict:
        """Formal production criteria expected by sprint v5.0."""
        actions_success = {
            r.get("name", ""): r.get("status") == "success"
            for r in results
        }

        def _has_step(partial_name: str) -> bool:
            partial = partial_name.lower()
            return any(partial in (name or "").lower() and ok for name, ok in actions_success.items())

        checks: dict[str, bool] = {}
        if workflow_id == "mode_gaming":
            checks = {
                "steam_lance": _has_step("steam"),
                "notification_recue": _has_step("notification"),
                "power_plan_applique": _has_step("haute performance"),
            }
        elif workflow_id == "mode_travail":
            checks = {
                "navigateur_ouvert": _has_step("navigateur"),
                "apps_pro_ouvertes": _has_step("vs code") and _has_step("discord"),
                "notification_recue": _has_step("notification"),
            }
        elif workflow_id == "nettoyage_systeme":
            checks = {
                "corbeille_videe": _has_step("corbeille"),
                "temp_nettoye": _has_step("temporaires"),
                "ram_liberee": _has_step("ram"),
                "notification_recue": _has_step("notification"),
            }
        elif workflow_id == "demarrage_matin":
            checks = {
                "apps_favorites_lancees": _has_step("navigateur") and _has_step("discord") and _has_step("vs code"),
                "diagnostic_affiche": _has_step("diagnostic"),
            }

        if not checks:
            return {"workflow_id": workflow_id, "checks": {}, "success": True}
        return {
            "workflow_id": workflow_id,
            "checks": checks,
            "success": all(checks.values()),
        }

    async def create_workflow(self, name: str, description: str, steps: list[dict],
                              created_by: str = "atlas_conversation") -> dict:
        """Crée un nouveau workflow et le sauvegarde en YAML."""
        from core.validator import check_automation_actions

        wf_id = name.lower().replace(" ", "_").replace("'", "")
        # Deduplicate ID if needed — B1-ter : un fichier existant (même illisible, donc non
        # chargé) n'est jamais écrasé.
        while wf_id in self._workflows or (WORKFLOWS_DIR / f"{wf_id}.yaml").exists():
            wf_id = f"{name.lower().replace(' ', '_').replace(chr(39), '')}_{str(uuid.uuid4())[:4]}"

        # B1-ter : contrôle à la création, y compris un workflow qui se lancerait lui-même.
        new_actions = steps if isinstance(steps, list) else None
        reason = check_automation_actions(
            new_actions,
            lambda other: new_actions if other == wf_id else self.steps_for_validation(other),
            (wf_id,),
        )
        if reason:
            logger.warning("Workflow refusé à la création '%s' : %s", name, reason)
            return {"success": False, "message": f"Workflow '{name}' refusé : {reason}."}

        wf_steps = []
        for s in steps:
            wf_steps.append(WorkflowStep(
                name=s.get("name", ""),
                action=s.get("action", ""),
                params=s.get("params", {}),
                skip_if_intouchable=s.get("skip_if_intouchable", False),
                wait_for_completion=s.get("wait_for_completion", False),
            ))

        wf = Workflow(
            id=wf_id,
            name=name,
            description=description,
            created_by=created_by,
            steps=wf_steps,
            conditions=[WorkflowCondition(
                type="confirm_before_run",
                message=f"Exécuter le workflow '{name}' ?",
            )],
        )

        # Save to YAML
        WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
        yaml_path = WORKFLOWS_DIR / f"{wf_id}.yaml"
        try:
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(wf.to_yaml_dict(), f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        except Exception as e:
            return {"success": False, "message": f"Erreur sauvegarde YAML : {e}"}

        self._workflows[wf.id] = wf
        logger.info("📋 Workflow créé : %s (%s) → %s", wf.name, wf.id, yaml_path.name)
        return {"success": True, "message": f"Workflow '{name}' créé.", "workflow_id": wf.id, "file": yaml_path.name}

    async def list_workflows(self) -> list[dict]:
        """Liste tous les workflows disponibles."""
        return [
            {
                "id": wf.id,
                "name": wf.name,
                "description": wf.description,
                "steps_count": len(wf.steps),
                "created_by": wf.created_by,
                "disabled_reason": wf.invalid_reason,
            }
            for wf in self._workflows.values()
        ]

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """Retourne un workflow par son ID."""
        return self._workflows.get(workflow_id)


# --------------------------------------------------------------------------- #
#  Singleton
# --------------------------------------------------------------------------- #

_workflow_engine: WorkflowEngine | None = None


def get_workflow_engine() -> WorkflowEngine:
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowEngine()
    return _workflow_engine
