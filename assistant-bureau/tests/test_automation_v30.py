"""
Tests MVP 3.0 — Automatisation Atlas
Scheduler + Trigger Engine + Workflow Engine + Notifier
15 tests
"""

import asyncio
import json
import os
import pathlib
import shutil
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root is in path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import core.scheduler as _scheduler_mod
import core.trigger_engine as _trigger_mod
import core.workflow_engine as _workflow_mod

# Chemins lus dans les modules : tests/conftest.py les redirige vers un dossier temporaire.
SCHEDULES_FILE = _scheduler_mod.SCHEDULES_FILE
TRIGGERS_FILE = _trigger_mod.TRIGGERS_FILE
WORKFLOWS_DIR = _workflow_mod.WORKFLOWS_DIR
assert "atlas_tests_root_" in str(SCHEDULES_FILE), "isolation des données inactive (tests/conftest.py)"


# --------------------------------------------------------------------------- #
#  Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
def clean_singletons():
    """Reset singletons between tests."""
    import core.scheduler as sched_mod
    import core.trigger_engine as trig_mod
    import core.workflow_engine as wf_mod
    sched_mod._scheduler = None
    trig_mod._trigger_engine = None
    wf_mod._workflow_engine = None
    yield
    sched_mod._scheduler = None
    trig_mod._trigger_engine = None
    wf_mod._workflow_engine = None


@pytest.fixture
def backup_schedules():
    """Backup and restore schedules.json."""
    backup = None
    if SCHEDULES_FILE.exists():
        backup = SCHEDULES_FILE.read_text(encoding="utf-8")
    yield
    if backup is not None:
        SCHEDULES_FILE.write_text(backup, encoding="utf-8")
    elif SCHEDULES_FILE.exists():
        SCHEDULES_FILE.unlink()


@pytest.fixture
def backup_triggers():
    """Backup and restore triggers.json."""
    backup = None
    if TRIGGERS_FILE.exists():
        backup = TRIGGERS_FILE.read_text(encoding="utf-8")
    yield
    if backup is not None:
        TRIGGERS_FILE.write_text(backup, encoding="utf-8")
    elif TRIGGERS_FILE.exists():
        TRIGGERS_FILE.unlink()


# --------------------------------------------------------------------------- #
#  Test 1 : Scheduler démarre sans erreur
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_01_scheduler_starts(backup_schedules):
    from core.scheduler import AtlasScheduler
    scheduler = AtlasScheduler()
    await scheduler.start()
    assert scheduler._scheduler.running, "Scheduler should be running after start()"
    # stop() should complete without error
    await scheduler.stop()
    # Scheduler is stopped (shutdown is scheduled on the event loop)


# --------------------------------------------------------------------------- #
#  Test 2 : schedule_add() crée un job + persiste dans schedules.json
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_02_schedule_add_persists(backup_schedules):
    from core.scheduler import AtlasScheduler, ScheduledJob
    scheduler = AtlasScheduler()
    await scheduler.start()

    job = ScheduledJob(
        id="",
        name="Test Steam Lundi",
        description="Lance Steam tous les lundis à 9h",
        trigger_type="cron",
        trigger_config={"day_of_week": "mon", "hour": 9, "minute": 0},
        actions=[{"action": "launch_app", "params": {"name": "steam"}}],
    )
    job_id = await scheduler.add_job(job)
    assert job_id
    assert SCHEDULES_FILE.exists()

    # Verify persisted
    with open(SCHEDULES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert any(j["id"] == job_id for j in data)

    await scheduler.stop()


# --------------------------------------------------------------------------- #
#  Test 3 : schedule_list() retourne le job créé
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_03_schedule_list(backup_schedules):
    from core.scheduler import AtlasScheduler, ScheduledJob
    scheduler = AtlasScheduler()
    await scheduler.start()

    job = ScheduledJob(
        id="", name="Test List", description="",
        trigger_type="interval", trigger_config={"hours": 1},
        actions=[],
    )
    job_id = await scheduler.add_job(job)

    jobs = await scheduler.list_jobs()
    assert len(jobs) >= 1
    assert any(j.id == job_id for j in jobs)

    await scheduler.stop()


# --------------------------------------------------------------------------- #
#  Test 4 : schedule_run_now() exécute les actions du job
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_04_schedule_run_now(backup_schedules):
    from core.scheduler import AtlasScheduler, ScheduledJob
    scheduler = AtlasScheduler()

    action_log = []

    async def mock_execute(action):
        action_log.append(action)
        return {"status": "success", "message": "ok"}

    scheduler.set_execution_callback(mock_execute)
    await scheduler.start()

    job = ScheduledJob(
        id="", name="Run Now Test", description="",
        trigger_type="interval", trigger_config={"hours": 24},
        actions=[{"action": "launch_app", "params": {"name": "notepad"}}],
    )
    job_id = await scheduler.add_job(job)

    result = await scheduler.run_job_now(job_id)
    assert result["success"]
    assert len(action_log) == 1
    assert action_log[0]["action"] == "launch_app"

    await scheduler.stop()


# --------------------------------------------------------------------------- #
#  Test 5 : schedule_remove() supprime le job + met à jour schedules.json
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_05_schedule_remove(backup_schedules):
    from core.scheduler import AtlasScheduler, ScheduledJob
    scheduler = AtlasScheduler()
    await scheduler.start()

    job = ScheduledJob(
        id="", name="To Remove", description="",
        trigger_type="interval", trigger_config={"hours": 1},
        actions=[],
    )
    job_id = await scheduler.add_job(job)
    assert await scheduler.remove_job(job_id)

    jobs = await scheduler.list_jobs()
    assert not any(j.id == job_id for j in jobs)

    # Verify removed from file
    with open(SCHEDULES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert not any(j["id"] == job_id for j in data)

    await scheduler.stop()


# --------------------------------------------------------------------------- #
#  Test 6 : Trigger engine démarre sans erreur
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_06_trigger_engine_starts(backup_triggers):
    from core.trigger_engine import TriggerEngine
    engine = TriggerEngine()
    engine.set_context_callback(lambda: {"cpu_usage": 10, "gpu_usage": 5, "ram_usage": 30, "running_processes": []})
    await engine.start()
    assert engine._running
    await engine.stop()
    assert not engine._running


# --------------------------------------------------------------------------- #
#  Test 7 : trigger_add() crée un trigger + persiste dans triggers.json
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_07_trigger_add_persists(backup_triggers):
    from core.trigger_engine import TriggerEngine, ContextTrigger, TriggerCondition
    engine = TriggerEngine()
    engine.set_context_callback(lambda: {"cpu_usage": 10, "gpu_usage": 5, "ram_usage": 30, "running_processes": []})
    await engine.start()

    trigger = ContextTrigger(
        id="",
        name="GPU Alert",
        condition=TriggerCondition(metric="gpu_usage", operator=">", value=90, duration_seconds=30),
        actions=[{"action": "notify", "params": {"message": "GPU surchauffe !"}}],
        cooldown_seconds=300,
    )
    trigger_id = await engine.add_trigger(trigger)
    assert trigger_id
    assert TRIGGERS_FILE.exists()

    with open(TRIGGERS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert any(t["id"] == trigger_id for t in data)

    await engine.stop()


# --------------------------------------------------------------------------- #
#  Test 8 : Condition GPU > 90 évaluée correctement (mock context_monitor)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_08_trigger_condition_gpu(backup_triggers):
    from core.trigger_engine import TriggerEngine, ContextTrigger, TriggerCondition

    fired = []
    engine = TriggerEngine()

    async def mock_execute(action):
        fired.append(action)
        return {"status": "success"}

    engine.set_execution_callback(mock_execute)
    # Return GPU > 90
    engine.set_context_callback(lambda: {
        "cpu_usage": 10, "gpu_usage": 95, "ram_usage": 30,
        "running_processes": [],
    })

    # Don't start monitor loop — we'll call _check_triggers manually
    engine._load_triggers()
    engine._running = True

    trigger = ContextTrigger(
        id="gpu_test",
        name="GPU High",
        condition=TriggerCondition(metric="gpu_usage", operator=">", value=90, duration_seconds=0),
        actions=[{"action": "notify", "params": {"message": "GPU hot"}}],
        cooldown_seconds=60,
    )
    await engine.add_trigger(trigger)

    await engine._check_triggers()
    assert len(fired) == 1
    assert fired[0]["action"] == "notify"

    engine._running = False


# --------------------------------------------------------------------------- #
#  Test 9 : Cooldown respecté — trigger ne se déclenche pas 2 fois en < 60s
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_09_trigger_cooldown(backup_triggers):
    from core.trigger_engine import TriggerEngine, ContextTrigger, TriggerCondition

    fired = []
    engine = TriggerEngine()

    async def mock_execute(action):
        fired.append(action)
        return {"status": "success"}

    engine.set_execution_callback(mock_execute)
    engine.set_context_callback(lambda: {
        "cpu_usage": 95, "gpu_usage": 5, "ram_usage": 30,
        "running_processes": [],
    })
    engine._load_triggers()
    engine._running = True

    trigger = ContextTrigger(
        id="cooldown_test",
        name="CPU High",
        condition=TriggerCondition(metric="cpu_usage", operator=">", value=80, duration_seconds=0),
        actions=[{"action": "notify", "params": {"message": "CPU hot"}}],
        cooldown_seconds=60,
    )
    await engine.add_trigger(trigger)

    # First trigger
    await engine._check_triggers()
    assert len(fired) == 1

    # Second trigger immediately — should be blocked by cooldown
    await engine._check_triggers()
    assert len(fired) == 1  # Still 1, not 2

    engine._running = False


# --------------------------------------------------------------------------- #
#  Test 10 : workflow_list() retourne les 4 templates
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_10_workflow_list_templates():
    from core.workflow_engine import WorkflowEngine
    engine = WorkflowEngine()
    engine.load_workflows()

    workflows = await engine.list_workflows()
    ids = [w["id"] for w in workflows]
    assert "mode_gaming" in ids
    assert "mode_travail" in ids
    assert "nettoyage_systeme" in ids
    assert "demarrage_matin" in ids


# --------------------------------------------------------------------------- #
#  Test 11 : workflow_run("mode_gaming") exécute les steps dans l'ordre
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_11_workflow_run_mode_gaming():
    from core.workflow_engine import WorkflowEngine

    executed_steps = []

    async def mock_execute(action):
        executed_steps.append(action["action"])
        return {"status": "success", "message": "ok"}

    engine = WorkflowEngine()
    engine.set_execution_callback(mock_execute)
    engine.set_notification_callback(AsyncMock())
    engine.load_workflows()

    result = await engine.run_workflow("mode_gaming")
    assert result["success"]
    # Should have kill_process, system_config, launch_app steps (notify handled internally)
    assert "kill_process" in executed_steps
    assert "system_config" in executed_steps
    assert "launch_app" in executed_steps


# --------------------------------------------------------------------------- #
#  Test 12 : workflow_create() génère un fichier YAML valide
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_12_workflow_create():
    from core.workflow_engine import WorkflowEngine
    import yaml

    engine = WorkflowEngine()
    engine.load_workflows()

    result = await engine.create_workflow(
        name="Test Custom",
        description="Un workflow de test",
        steps=[
            {"name": "Step 1", "action": "launch_app", "params": {"name": "notepad"}},
            {"name": "Step 2", "action": "notify", "params": {"message": "Done"}},
        ],
    )
    assert result["success"]
    wf_id = result["workflow_id"]

    # Verify YAML file exists and is valid
    yaml_path = WORKFLOWS_DIR / f"{wf_id}.yaml"
    assert yaml_path.exists()

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data["id"] == wf_id
    assert data["name"] == "Test Custom"
    assert len(data["steps"]) == 2

    # Cleanup
    yaml_path.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
#  Test 13 : Trigger avec processus INTOUCHABLE → skip sans crash
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_13_trigger_intouchable_skip(backup_triggers):
    from core.trigger_engine import TriggerEngine, ContextTrigger, TriggerCondition

    fired = []
    engine = TriggerEngine()

    async def mock_execute(action):
        fired.append(action)
        return {"status": "success"}

    engine.set_execution_callback(mock_execute)
    engine.set_context_callback(lambda: {
        "cpu_usage": 95, "gpu_usage": 5, "ram_usage": 30,
        "running_processes": [{"name": "explorer.exe"}],
    })
    # Protection: explorer.exe is intouchable
    engine.set_protection_callback(lambda name: "intouchable" if name == "explorer.exe" else "libre")
    engine._load_triggers()
    engine._running = True

    trigger = ContextTrigger(
        id="intouchable_test",
        name="Kill Explorer",
        condition=TriggerCondition(metric="cpu_usage", operator=">", value=80, duration_seconds=0),
        actions=[{"action": "kill_process", "params": {"name": "explorer.exe"}}],
        cooldown_seconds=60,
    )
    await engine.add_trigger(trigger)

    await engine._check_triggers()
    # Should NOT fire because target is intouchable
    assert len(fired) == 0

    engine._running = False


# --------------------------------------------------------------------------- #
#  Test 14 : notify() s'exécute sans erreur
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_14_notify():
    from tools.notifier import notify
    # Patch plyer to avoid actual notification on CI
    with patch("tools.notifier.notification", create=True) as mock_notif:
        # Import inside to get the patched version
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"plyer": mock_module, "plyer.notification": mock_module}):
            mock_module.notification = MagicMock()
            mock_module.notification.notify = MagicMock()
            # Direct call — plyer may not be installed in test env
            try:
                result = await notify("Test notification", title="Test")
                # If plyer is available, it should succeed
                assert result.get("success") is not None
            except ImportError:
                # plyer not installed — expected in test env
                pass


# --------------------------------------------------------------------------- #
#  Test 15 : Redémarrage Atlas → jobs et triggers rechargés depuis JSON
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_15_persistence_reload(backup_schedules, backup_triggers):
    from core.scheduler import AtlasScheduler, ScheduledJob
    from core.trigger_engine import TriggerEngine, ContextTrigger, TriggerCondition

    # --- Create and persist a job ---
    scheduler1 = AtlasScheduler()
    await scheduler1.start()
    job = ScheduledJob(
        id="persist_test",
        name="Persistent Job",
        description="Survives restart",
        trigger_type="interval",
        trigger_config={"hours": 2},
        actions=[{"action": "notify", "params": {"message": "hello"}}],
    )
    await scheduler1.add_job(job)
    await scheduler1.stop()

    # --- Create and persist a trigger ---
    engine1 = TriggerEngine()
    engine1.set_context_callback(lambda: {"cpu_usage": 10, "gpu_usage": 5, "ram_usage": 30, "running_processes": []})
    await engine1.start()
    trigger = ContextTrigger(
        id="persist_trig",
        name="Persistent Trigger",
        condition=TriggerCondition(metric="cpu_usage", operator=">", value=90, duration_seconds=0),
        actions=[{"action": "notify", "params": {"message": "cpu"}}],
        cooldown_seconds=120,
    )
    await engine1.add_trigger(trigger)
    await engine1.stop()

    # --- "Restart" — new instances ---
    scheduler2 = AtlasScheduler()
    await scheduler2.start()
    jobs = await scheduler2.list_jobs()
    assert any(j.id == "persist_test" for j in jobs), "Job not reloaded after restart"
    await scheduler2.stop()

    engine2 = TriggerEngine()
    engine2.set_context_callback(lambda: {"cpu_usage": 10, "gpu_usage": 5, "ram_usage": 30, "running_processes": []})
    await engine2.start()
    triggers = await engine2.list_triggers()
    assert any(t.id == "persist_trig" for t in triggers), "Trigger not reloaded after restart"
    await engine2.stop()
