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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ScheduledJob":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# --------------------------------------------------------------------------- #
#  Atlas Scheduler
# --------------------------------------------------------------------------- #

class AtlasScheduler:
    """Gestionnaire de tâches planifiées pour Atlas."""

    def __init__(self):
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[str, ScheduledJob] = {}
        self._execution_callback = None

    async def start(self):
        """Démarre le scheduler et charge les jobs persistés."""
        self._load_jobs()
        for job in self._jobs.values():
            if job.enabled:
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
        """Ajoute un job planifié. Retourne l'ID."""
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
        """Charge les jobs depuis le fichier JSON."""
        if not SCHEDULES_FILE.exists():
            self._jobs = {}
            return
        try:
            with open(SCHEDULES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._jobs = {j["id"]: ScheduledJob.from_dict(j) for j in data}
            logger.info("📂 %d job(s) chargé(s) depuis schedules.json", len(self._jobs))
        except Exception as e:
            logger.error("Erreur chargement schedules.json : %s", e)
            self._jobs = {}

    def _save_jobs(self):
        """Persiste les jobs dans le fichier JSON."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            data = [j.to_dict() for j in self._jobs.values()]
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
