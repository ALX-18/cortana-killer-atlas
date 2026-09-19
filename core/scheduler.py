"""
Scheduler — Tâches planifiées via APScheduler.

MVP 3.0 : Permet de planifier des actions récurrentes (cron, interval, date).
Persiste dans data/schedules.json. Intégré dans le lifespan FastAPI.
"""

import asyncio
import json
import logging
import pathlib
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

logger = logging.getLogger("atlas.scheduler")

# --------------------------------------------------------------------------- #
#  Data model
# --------------------------------------------------------------------------- #

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
SCHEDULES_FILE = DATA_DIR / "schedules.json"


@dataclass
class ScheduledJob:
    id: str
    name: str
    description: str
    trigger_type: str               # "cron" | "interval" | "date"
    trigger_config: dict
    actions: list[dict]             # Tool-calls à exécuter
    enabled: bool = True
    created_at: str = ""
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    # B1-ter : motif de désactivation, calculé au chargement ; jamais écrit dans le fichier.
    invalid_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_storage_dict(self) -> dict:
        d = asdict(self)
        d.pop("invalid_reason", None)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ScheduledJob":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__ and k != "invalid_reason"})


_SOURCE = "tâche planifiée"


# --------------------------------------------------------------------------- #
#  Atlas Scheduler
# --------------------------------------------------------------------------- #

class AtlasScheduler:
    """Gestionnaire de tâches planifiées pour Atlas."""

    def __init__(self):
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[str, ScheduledJob] = {}
        self._execution_callback = None
        # B1-ter : ce qui a été lu mais ne peut pas être exécuté est CONSERVÉ tel quel.
        self._raw_entries: dict[str, dict] = {}    # id → entrée d'origine, telle que lue
        self._unparsed_entries: list = []          # entrées illisibles, réécrites à l'identique
        self._storage_error: Optional[str] = None  # fichier illisible : aucune écriture

    def _validate(self, job: ScheduledJob) -> str:
        from core.validator import check_automation_actions
        from core.workflow_engine import get_workflow_engine
        return check_automation_actions(job.actions, get_workflow_engine().steps_for_validation)

    def _block(self, job: ScheduledJob, reason: str) -> dict:
        from core.validator import report_automation_block
        job.invalid_reason = reason
        report_automation_block(_SOURCE, job.name, reason)
        return {"success": False, "status": "blocked",
                "message": f"Tâche '{job.name}' désactivée : {reason}."}

    async def start(self):
        """Démarre le scheduler et charge les jobs persistés."""
        self._load_jobs()
        for job in self._jobs.values():
            reason = self._validate(job)
            if reason:
                self._block(job, reason)
            elif job.enabled:
                self._register_apscheduler_job(job)
        self._scheduler.start()
        logger.info("⏰ Scheduler démarré — %d job(s) chargé(s)", len(self._jobs))

    async def stop(self):
        """Arrête proprement le scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            # Force state to stopped since AsyncIOScheduler.shutdown may not complete
            # synchronously in all contexts
            from apscheduler.schedulers.base import STATE_STOPPED
            self._scheduler._state = STATE_STOPPED
        logger.info("⏰ Scheduler arrêté")

    def set_execution_callback(self, callback):
        """Définit le callback pour exécuter les actions d'un job."""
        self._execution_callback = callback

    async def add_job(self, job: ScheduledJob) -> str:
        """Ajoute un job planifié. Retourne l'ID.

        B1-ter : ValueError si une action n'est pas autorisée, ou si le fichier existant est
        illisible (l'écraser ferait perdre les tâches de l'utilisateur).
        """
        if self._storage_error:
            raise ValueError(f"Tâche '{job.name}' non enregistrée : {self._storage_error}")
        reason = self._validate(job)
        if reason:
            logger.warning("Tâche planifiée refusée à la création '%s' : %s", job.name, reason)
            raise ValueError(f"Tâche '{job.name}' refusée : {reason}")
        if not job.id:
            job.id = str(uuid.uuid4())[:8]
        if not job.created_at:
            job.created_at = datetime.now().isoformat()

        self._jobs[job.id] = job
        if job.enabled:
            self._register_apscheduler_job(job)
        self._save_jobs()
        logger.info("➕ Job planifié ajouté : %s (%s)", job.name, job.id)
        return job.id

    async def remove_job(self, job_id: str) -> bool:
        """Supprime un job planifié."""
        if job_id not in self._jobs:
            return False
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass  # Job may not be registered in APScheduler
        del self._jobs[job_id]
        self._save_jobs()
        logger.info("➖ Job planifié supprimé : %s", job_id)
        return True

    async def list_jobs(self) -> list[ScheduledJob]:
        """Liste tous les jobs planifiés."""
        # Update next_run from APScheduler
        for job_id, job in self._jobs.items():
            try:
                ap_job = self._scheduler.get_job(job_id)
                if ap_job and ap_job.next_run_time:
                    job.next_run = ap_job.next_run_time.isoformat()
                else:
                    job.next_run = None
            except Exception:
                pass
        return list(self._jobs.values())

    async def run_job_now(self, job_id: str) -> dict:
        """Exécute immédiatement un job planifié."""
        job = self._jobs.get(job_id)
        if not job:
            return {"success": False, "message": f"Job '{job_id}' introuvable."}
        reason = job.invalid_reason or self._validate(job)
        if reason:
            return self._block(job, reason)

        results = await self._execute_job_actions(job)
        job.last_run = datetime.now().isoformat()
        self._save_jobs()
        return {"success": True, "message": f"Job '{job.name}' exécuté.", "results": results}

    # ----- Internal ----- #

    def _build_trigger(self, job: ScheduledJob):
        """Construit un trigger APScheduler depuis la config du job."""
        tc = job.trigger_config
        if job.trigger_type == "cron":
            if not tc:
                raise ValueError("trigger_config requis pour trigger_type='cron'")
            return CronTrigger(**tc)
        elif job.trigger_type == "interval":
            return IntervalTrigger(**tc)
        elif job.trigger_type == "date":
            return DateTrigger(**tc)
        else:
            raise ValueError(f"Type de trigger inconnu : {job.trigger_type}")

    def _register_apscheduler_job(self, job: ScheduledJob):
        """Enregistre un job dans APScheduler."""
        try:
            # Remove existing if any
            try:
                self._scheduler.remove_job(job.id)
            except Exception:
                pass
            trigger = self._build_trigger(job)
            self._scheduler.add_job(
                self._on_job_trigger,
                trigger=trigger,
                id=job.id,
                args=[job.id],
                name=job.name,
                replace_existing=True,
            )
            # Update next_run
            ap_job = self._scheduler.get_job(job.id)
            next_run = getattr(ap_job, "next_run_time", None) if ap_job else None
            if next_run:
                job.next_run = next_run.isoformat()
        except Exception as e:
            logger.error("Échec enregistrement job '%s' : %s", job.name, e)

    async def _on_job_trigger(self, job_id: str):
        """Callback quand un job se déclenche."""
        job = self._jobs.get(job_id)
        if not job:
            return
        logger.info("⏰ Job déclenché : %s (%s)", job.name, job.id)
        reason = job.invalid_reason or self._validate(job)
        if reason:
            self._block(job, reason)
            return
        await self._execute_job_actions(job)
        job.last_run = datetime.now().isoformat()
        self._save_jobs()

    async def _execute_job_actions(self, job: ScheduledJob) -> list[dict]:
        """Exécute les actions d'un job via le callback d'exécution."""
        results = []
        if self._execution_callback:
            for action in job.actions:
                try:
                    result = await self._execution_callback(action)
                    results.append(result)
                except Exception as e:
                    logger.error("Erreur exécution action job '%s': %s", job.name, e)
                    results.append({"status": "error", "message": str(e)})
        else:
            logger.warning("Pas de callback d'exécution configuré pour le scheduler")
        return results

    def _load_jobs(self):
        """Charge les jobs depuis le fichier JSON.

        B1-ter : entrée par entrée. Avant, une seule entrée illisible vidait toute la liste,
        et le prochain enregistrement écrasait le fichier : les tâches étaient perdues.
        """
        from core.validator import report_automation_block

        self._jobs, self._raw_entries, self._unparsed_entries = {}, {}, []
        self._storage_error = None
        if not SCHEDULES_FILE.exists():
            return
        try:
            with open(SCHEDULES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("une liste de tâches est attendue")
        except Exception as e:
            self._storage_error = f"schedules.json illisible ({e}), fichier laissé intact"
            report_automation_block(_SOURCE, "schedules.json", self._storage_error)
            return
        for entry in data:
            try:
                job = ScheduledJob.from_dict(entry)
                if not isinstance(job.id, str) or not job.id or job.id in self._jobs:
                    raise ValueError("identifiant absent ou en double")
            except Exception as e:
                self._unparsed_entries.append(entry)
                label = entry.get("name", "?") if isinstance(entry, dict) else "?"
                report_automation_block(_SOURCE, str(label), f"entrée illisible ({e}), conservée telle quelle")
                continue
            self._jobs[job.id] = job
            self._raw_entries[job.id] = entry
        logger.info("📂 %d job(s) chargé(s) depuis schedules.json", len(self._jobs))

    def _save_jobs(self):
        """Persiste les jobs dans le fichier JSON.

        B1-ter : une tâche désactivée est réécrite exactement comme elle a été lue, et les
        entrées illisibles sont conservées. Fichier illisible : aucune écriture.
        """
        if self._storage_error:
            logger.error("schedules.json non réécrit : %s", self._storage_error)
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            data = [
                self._raw_entries[j.id] if j.invalid_reason and j.id in self._raw_entries else j.to_storage_dict()
                for j in self._jobs.values()
            ] + self._unparsed_entries
            with open(SCHEDULES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Erreur sauvegarde schedules.json : %s", e)


# --------------------------------------------------------------------------- #
#  Singleton
# --------------------------------------------------------------------------- #

_scheduler: AtlasScheduler | None = None


def get_scheduler() -> AtlasScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AtlasScheduler()
    return _scheduler
