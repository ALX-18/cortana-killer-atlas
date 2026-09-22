"""
Sprint B1-ter — la validation comme invariant du stockage.

BT1 : une automatisation bloquée est journalisée ET signalée (jamais de silence).
BT2 : liste blanche des actions planifiables.
BT3 : paramètres contrôlés par une table outil → contrôle.
BT4 : cycles et profondeur maximale de workflow_run.
BT5 : validation à la création, au chargement et à l'exécution ; élément invalide au
      chargement désactivé et signalé, jamais supprimé, fichier jamais réécrit.
BT6 : launch_app — plus de chemin arbitraire, ni par `path`, ni par la résolution du nom.

Aucun effet réel : chaque test travaille dans un répertoire de données temporaire, les
rappels d'exécution sont des enregistreurs, aucune notification Windows n'est affichée.
"""

import asyncio
import json
import os
from types import SimpleNamespace

import pytest
import yaml

import core.scheduler as scheduler_mod
import core.trigger_engine as trigger_mod
import core.workflow_engine as workflow_mod
from core.intent_classifier import IntentResult
from core.scheduler import AtlasScheduler, ScheduledJob
from core.trigger_engine import ContextTrigger, TriggerCondition, TriggerEngine
from core.workflow_engine import WorkflowEngine

# Actions qu'une automatisation peut contenir (BT2). Tout le reste est refusé.
EXPECTED_ALLOWED = {
    "launch_app", "notify", "get_diagnostics",
    "maintenance_cleanup_temp", "maintenance_gc", "workflow_run",
}

FORBIDDEN = [
    ("window_type", {"text": "bonjour", "target": "bloc-notes"}),        # interactive
    ("window_hotkey", {"keys": ["ctrl", "s"], "target": "bloc-notes"}),  # interactive
    ("ui_click_element", {"element_name": "Fichier", "app_title": "bloc-notes"}),
    ("window_close", {"title": "bloc-notes"}),
    ("kill_process", {"name": "teams.exe"}),                              # confirmation forcée
    ("system_config", {"action": "set_power_plan", "plan": "high_performance"}),
    ("run_powershell", {"command": "Get-Date"}),
    ("browser_open", {"url": "https://example.com"}),
    ("schedule_add", {"name": "x", "actions": []}),                       # automatisation
    ("trigger_add", {"name": "x", "actions": []}),
    ("workflow_create", {"name": "x", "steps": []}),
    ("maintenance_empty_bin", {}),                                        # suppression définitive
    ("redo_last_action", {}),
    ("set_priority", {"pid": 4, "priority": "high"}),
    ("browser_ext_type", {"selector": "input", "text": "x"}),
    ("outil_inexistant", {}),
]

INVALID_PARAMS = [
    ("launch_app", {"path": r"C:\Users\alexis\Downloads\setup.bat"}),
    ("launch_app", {"name": "steam", "path": r"C:\x.exe"}),
    ("launch_app", {"name": r"C:\Users\alexis\Downloads\setup.bat"}),
    ("launch_app", {"name": r"..\..\evil"}),
    ("launch_app", {"name": ""}),
    ("launch_app", {}),
    ("notify", {"message": 42}),
    ("notify", {"message": ""}),
    ("maintenance_cleanup_temp", {"max_age_days": -1}),
    ("maintenance_cleanup_temp", {"max_age_days": "7"}),
    ("get_diagnostics", {"inattendu": 1}),
    ("workflow_run", {"workflow_id": ""}),
]

MALFORMED_ACTIONS = ["launch_app", {"params": {"name": "steam"}}, {"action": "launch_app", "params": "steam"}, None]


# --------------------------------------------------------------------------- #
#  Fixtures : données isolées, signalement observable
# --------------------------------------------------------------------------- #

@pytest.fixture
def data(tmp_path, monkeypatch):
    d = tmp_path / "data"
    (d / "workflows").mkdir(parents=True)
    monkeypatch.setattr(scheduler_mod, "DATA_DIR", d)
    monkeypatch.setattr(scheduler_mod, "SCHEDULES_FILE", d / "schedules.json")
    monkeypatch.setattr(trigger_mod, "DATA_DIR", d)
    monkeypatch.setattr(trigger_mod, "TRIGGERS_FILE", d / "triggers.json")
    monkeypatch.setattr(workflow_mod, "DATA_DIR", d)
    monkeypatch.setattr(workflow_mod, "WORKFLOWS_DIR", d / "workflows")
    return d


@pytest.fixture
def reports(tmp_path, monkeypatch):
    """Ce que l'utilisateur voit : lignes du journal d'actions (/logs/recent) et notifications."""
    import core.atlas_logger as atlas_logger
    import core.validator as validator_mod

    log = tmp_path / "atlas_actions.jsonl"
    monkeypatch.setattr(atlas_logger, "LOG_FILE", log)
    toasts = []
    monkeypatch.setattr(validator_mod, "_automation_notifier",
                        lambda title, message: toasts.append((title, message)), raising=False)
    monkeypatch.setattr(validator_mod, "_automation_last_toast", {}, raising=False)

    def entries():
        if not log.exists():
            return []
        rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [r for r in rows if r.get("error_code") == "ERR_AUTOMATION_BLOCKED"]

    return SimpleNamespace(entries=entries, toasts=toasts)


def _job(actions, name="Tâche de test", job_id=""):
    return ScheduledJob(id=job_id, name=name, description="", trigger_type="interval",
                        trigger_config={"hours": 24}, actions=actions)


def _trigger(actions, name="Déclencheur de test", trig_id=""):
    return ContextTrigger(id=trig_id, name=name,
                          condition=TriggerCondition(metric="cpu_usage", operator=">", value=80),
                          actions=actions, cooldown_seconds=60)


def _write_workflow(data_dir, wf_id, steps, name=None):
    path = data_dir / "workflows" / f"{wf_id}.yaml"
    path.write_text(yaml.dump({"id": wf_id, "name": name or wf_id, "steps": steps}, allow_unicode=True),
                    encoding="utf-8")
    return path


def _recorder():
    calls = []

    async def execute(action):
        calls.append(action)
        return {"status": "success", "message": "simulé"}

    return calls, execute


# --------------------------------------------------------------------------- #
#  BT2 / BT3 / BT5 — à la création
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
@pytest.mark.parametrize("tool,params", FORBIDDEN + INVALID_PARAMS, ids=lambda v: str(v)[:40])
async def test_bt2_tache_planifiee_interdite_refusee_a_la_creation(data, tool, params):
    scheduler = AtlasScheduler()
    await scheduler.start()
    try:
        with pytest.raises(ValueError) as refused:
            await scheduler.add_job(_job([{"action": tool, "params": params}]))
        assert tool in str(refused.value) or "action" in str(refused.value)
    finally:
        await scheduler.stop()
    saved = json.loads(scheduler_mod.SCHEDULES_FILE.read_text(encoding="utf-8")) if scheduler_mod.SCHEDULES_FILE.exists() else []
    assert saved == [], f"{tool} {params} enregistré : {saved}"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,params", FORBIDDEN[:8], ids=lambda v: str(v)[:40])
async def test_bt2_declencheur_interdit_refuse_a_la_creation(data, tool, params):
    engine = TriggerEngine()
    engine._load_triggers()
    with pytest.raises(ValueError):
        await engine.add_trigger(_trigger([{"action": tool, "params": params}]))
    assert not trigger_mod.TRIGGERS_FILE.exists() or json.loads(trigger_mod.TRIGGERS_FILE.read_text(encoding="utf-8")) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,params", FORBIDDEN[:8] + [FORBIDDEN[11]], ids=lambda v: str(v)[:40])
async def test_bt2_workflow_interdit_refuse_a_la_creation(data, tool, params):
    engine = WorkflowEngine()
    engine.load_workflows()
    result = await engine.create_workflow("Essai", "", [{"name": "étape", "action": tool, "params": params}])
    assert result["success"] is False, f"workflow avec {tool} créé : {result}"
    assert list((data / "workflows").glob("*.yaml")) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("action", MALFORMED_ACTIONS, ids=lambda v: repr(v)[:30])
async def test_bt3_action_malformee_refusee(data, action):
    scheduler = AtlasScheduler()
    await scheduler.start()
    try:
        with pytest.raises(ValueError):
            await scheduler.add_job(_job([action]))
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_bt2_liste_blanche_exacte_sur_tous_les_outils(data):
    """Chaque outil enregistré est soit autorisé (liste attendue), soit refusé."""
    from core.intent_engine import TOOL_HANDLERS

    scheduler = AtlasScheduler()
    await scheduler.start()
    accepted = set()
    try:
        for tool in sorted(TOOL_HANDLERS):
            params = {"name": "steam"} if tool == "launch_app" else (
                {"message": "ok"} if tool == "notify" else (
                    {"workflow_id": "wf_ok"} if tool == "workflow_run" else {}))
            try:
                await scheduler.add_job(_job([{"action": tool, "params": params}], name=tool))
                accepted.add(tool)
            except ValueError:
                pass
    finally:
        await scheduler.stop()
    # workflow_run est jugé à part (il exige un workflow existant) : voir test_bt4_workflow_run_*
    assert accepted - {"workflow_run"} == EXPECTED_ALLOWED - {"workflow_run"}, (
        f"acceptés en trop : {sorted(accepted - EXPECTED_ALLOWED)} ; "
        f"refusés à tort : {sorted(EXPECTED_ALLOWED - accepted - {'workflow_run'})}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", [
    {"action": "launch_app", "params": {"name": "steam"}},
    {"action": "launch_app", "params": {"name": "opera gx", "wait": True}},
    {"action": "notify", "params": {"message": "Bon matin ! ☀️"}},
    {"action": "get_diagnostics", "params": {}},
    {"action": "get_diagnostics"},
    {"action": "maintenance_cleanup_temp", "params": {"max_age_days": 7}},
    {"action": "maintenance_gc", "params": {}},
])
async def test_bt2_actions_autorisees_acceptees(data, action):
    scheduler = AtlasScheduler()
    await scheduler.start()
    try:
        job_id = await scheduler.add_job(_job([action]))
    finally:
        await scheduler.stop()
    saved = json.loads(scheduler_mod.SCHEDULES_FILE.read_text(encoding="utf-8"))
    assert [j["id"] for j in saved] == [job_id]


def test_bt2_demande_utilisateur_de_planifier_une_action_interdite_refusee():
    """Chemin intention (plan LLM) : refus par le validateur, avant tout enregistrement."""
    from core.validator import get_validator

    intent = IntentResult(category="automation", verb="schedule", target="",
                          params={"name": "fermer teams", "actions": [{"action": "kill_process",
                                                                       "params": {"name": "teams.exe"}}]},
                          confidence=0.9, raw_input="")
    resolved = get_validator().resolve(intent, {})
    assert resolved.tool != "schedule_add", f"schedule_add avec kill_process accepté : {resolved.params}"
    assert resolved.rejected is True


# --------------------------------------------------------------------------- #
#  BT4 — récursion et cycles
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_bt4_workflow_run_vers_un_workflow_existant_accepte_inconnu_refuse(data):
    from core.workflow_engine import get_workflow_engine

    _write_workflow(data, "wf_ok", [{"name": "n", "action": "notify", "params": {"message": "ok"}}])
    get_workflow_engine().load_workflows()
    scheduler = AtlasScheduler()
    await scheduler.start()
    try:
        await scheduler.add_job(_job([{"action": "workflow_run", "params": {"workflow_id": "wf_ok"}}], "ok"))
        with pytest.raises(ValueError):
            await scheduler.add_job(_job([{"action": "workflow_run", "params": {"workflow_id": "wf_absent"}}], "ko"))
    finally:
        await scheduler.stop()

@pytest.mark.asyncio
async def test_bt4_workflow_qui_sappelle_lui_meme_refuse_a_la_creation(data):
    engine = WorkflowEngine()
    engine.load_workflows()
    result = await engine.create_workflow(
        "boucle", "", [{"name": "moi", "action": "workflow_run", "params": {"workflow_id": "boucle"}}])
    assert result["success"] is False, f"workflow auto-récursif créé : {result}"


@pytest.mark.asyncio
async def test_bt4_cycle_entre_fichiers_detecte_au_chargement_et_jamais_execute(data, reports):
    _write_workflow(data, "wf_a", [{"name": "vers b", "action": "workflow_run", "params": {"workflow_id": "wf_b"}}])
    _write_workflow(data, "wf_b", [{"name": "vers a", "action": "workflow_run", "params": {"workflow_id": "wf_a"}}])
    engine = WorkflowEngine()
    depth = {"n": 0}

    async def execute(action):
        # Comme en production : workflow_run relance le moteur.
        depth["n"] += 1
        assert depth["n"] < 30, "récursion infinie : le cycle wf_a → wf_b → wf_a s'exécute"
        if action["action"] == "workflow_run":
            return await engine.run_workflow(action["params"]["workflow_id"])
        return {"status": "success"}

    engine.set_execution_callback(execute)
    engine.load_workflows()
    result = await engine.run_workflow("wf_a")
    assert depth["n"] == 0, f"{depth['n']} étape(s) exécutée(s) malgré le cycle"
    assert result["success"] is False
    assert any("wf_a" in e["target"] for e in reports.entries())


@pytest.mark.asyncio
async def test_bt4_profondeur_maximale(data):
    """w1 → w2 → w3 → w4 : 4 niveaux, au-delà de la limite de 3. w2 (3 niveaux) reste valide."""
    import core.validator as validator_mod

    _write_workflow(data, "w4", [{"name": "fin", "action": "notify", "params": {"message": "fin"}}])
    for i in (3, 2, 1):
        _write_workflow(data, f"w{i}", [{"name": "suite", "action": "workflow_run", "params": {"workflow_id": f"w{i + 1}"}}])
    engine = WorkflowEngine()
    engine.load_workflows()
    listed = {w["id"]: w for w in await engine.list_workflows()}
    assert listed["w1"].get("disabled_reason"), "w1 (4 niveaux) accepté"
    assert "profondeur" in listed["w1"]["disabled_reason"]
    assert not listed["w2"].get("disabled_reason"), listed["w2"].get("disabled_reason")
    assert getattr(validator_mod, "MAX_WORKFLOW_DEPTH", None) == 3


@pytest.mark.asyncio
async def test_bt4_garde_a_lexecution_meme_si_le_cycle_apparait_apres_le_chargement(data):
    """Défense en profondeur : cycle introduit en mémoire après le chargement."""
    _write_workflow(data, "wf_x", [{"name": "n", "action": "notify", "params": {"message": "x"}}])
    engine = WorkflowEngine()
    engine.load_workflows()
    engine._workflows["wf_x"].steps.append(
        workflow_mod.WorkflowStep(name="retour", action="workflow_run", params={"workflow_id": "wf_x"}))
    depth = {"n": 0}

    async def execute(action):
        depth["n"] += 1
        assert depth["n"] < 30, "récursion infinie à l'exécution"
        return await engine.run_workflow(action["params"]["workflow_id"])

    engine.set_execution_callback(execute)
    engine.set_notification_callback(lambda msg: asyncio.sleep(0))
    result = await engine.run_workflow("wf_x")
    assert depth["n"] == 0, f"{depth['n']} relance(s) exécutée(s)"
    assert result["success"] is False


# --------------------------------------------------------------------------- #
#  BT5 — au chargement : désactivé, signalé, jamais supprimé ni réécrit
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_bt5_tache_editee_a_la_main_detectee_au_chargement(data, reports):
    raw = json.dumps([
        _job([{"action": "kill_process", "params": {"name": "teams.exe"}}], "Édition manuelle", "bad1").to_dict(),
        _job([{"action": "launch_app", "params": {"name": "steam"}}], "Steam", "good1").to_dict(),
    ], indent=2, ensure_ascii=False)
    scheduler_mod.SCHEDULES_FILE.write_text(raw, encoding="utf-8")

    calls, execute = _recorder()
    scheduler = AtlasScheduler()
    scheduler.set_execution_callback(execute)
    await scheduler.start()
    try:
        assert scheduler._scheduler.get_job("bad1") is None, "tâche invalide enregistrée dans APScheduler"
        assert scheduler._scheduler.get_job("good1") is not None
        result = await scheduler.run_job_now("bad1")
        assert calls == [], f"action exécutée : {calls}"
        assert result["success"] is False
        listed = {j.id: j for j in await scheduler.list_jobs()}
        assert "bad1" in listed, "tâche invalide supprimée de la liste"
        assert "kill_process" in (listed["bad1"].to_dict().get("invalid_reason") or "")
    finally:
        await scheduler.stop()
    assert any(e["target"] == "Édition manuelle" for e in reports.entries()), "aucun signalement journalisé"
    assert reports.toasts, "aucune notification à l'utilisateur"
    assert scheduler_mod.SCHEDULES_FILE.read_text(encoding="utf-8") == raw, "fichier réécrit"


@pytest.mark.asyncio
async def test_bt5_tache_invalide_conservee_telle_quelle_apres_un_ajout(data):
    """L'ajout d'une autre tâche réécrit le fichier : l'entrée invalide doit y rester intacte."""
    bad = _job([{"action": "kill_process", "params": {"name": "teams.exe"}}], "Édition manuelle", "bad1").to_dict()
    scheduler_mod.SCHEDULES_FILE.write_text(json.dumps([bad]), encoding="utf-8")
    scheduler = AtlasScheduler()
    await scheduler.start()
    try:
        await scheduler.add_job(_job([{"action": "notify", "params": {"message": "ok"}}], "Nouvelle"))
    finally:
        await scheduler.stop()
    saved = {j["id"]: j for j in json.loads(scheduler_mod.SCHEDULES_FILE.read_text(encoding="utf-8"))}
    assert saved.get("bad1") == bad, f"entrée invalide modifiée ou supprimée : {saved.get('bad1')}"


@pytest.mark.asyncio
async def test_bt5_entree_malformee_ne_fait_pas_perdre_les_autres(data, reports):
    """Aujourd'hui, une seule entrée illisible vide TOUTE la liste, puis le prochain ajout écrase le fichier."""
    good = _job([{"action": "launch_app", "params": {"name": "steam"}}], "Steam", "good1").to_dict()
    malformed = {"name": "sans identifiant", "actions": "pas une liste"}
    scheduler_mod.SCHEDULES_FILE.write_text(json.dumps([good, malformed]), encoding="utf-8")
    scheduler = AtlasScheduler()
    await scheduler.start()
    try:
        assert "good1" in {j.id for j in await scheduler.list_jobs()}, "tâche valide perdue au chargement"
        await scheduler.add_job(_job([{"action": "notify", "params": {"message": "ok"}}], "Nouvelle"))
    finally:
        await scheduler.stop()
    saved = json.loads(scheduler_mod.SCHEDULES_FILE.read_text(encoding="utf-8"))
    # Une tâche valide voit son champ next_run mis à jour par le planificateur (comportement
    # antérieur) : on compare ce que l'utilisateur a défini, pas la tenue de compte.
    user_fields = ("id", "name", "trigger_type", "trigger_config", "actions", "enabled")
    kept = [{k: j.get(k) for k in user_fields} for j in saved if isinstance(j, dict) and j.get("id") == "good1"]
    assert kept == [{k: good[k] for k in user_fields}], "tâche valide supprimée ou modifiée"
    assert malformed in saved, "entrée malformée supprimée du fichier"
    assert reports.entries(), "entrée malformée non signalée"


@pytest.mark.asyncio
async def test_bt5_fichier_illisible_jamais_ecrase(data, reports):
    raw = '[{"id": "a", "name": "virgule en trop",}]'
    scheduler_mod.SCHEDULES_FILE.write_text(raw, encoding="utf-8")
    scheduler = AtlasScheduler()
    await scheduler.start()
    try:
        with pytest.raises(ValueError):
            await scheduler.add_job(_job([{"action": "notify", "params": {"message": "ok"}}], "Nouvelle"))
    finally:
        await scheduler.stop()
    assert scheduler_mod.SCHEDULES_FILE.read_text(encoding="utf-8") == raw, "fichier illisible écrasé : données perdues"
    assert reports.entries(), "fichier illisible non signalé"


@pytest.mark.asyncio
async def test_bt5_declencheur_edite_a_la_main_jamais_declenche(data, reports):
    raw = json.dumps([_trigger([{"action": "window_type", "params": {"text": "x", "target": "bloc-notes"}}],
                               "Frappe auto", "t_bad").to_dict()], ensure_ascii=False)
    trigger_mod.TRIGGERS_FILE.write_text(raw, encoding="utf-8")
    calls, execute = _recorder()
    engine = TriggerEngine()
    engine.set_execution_callback(execute)
    engine.set_context_callback(lambda: {"cpu_usage": 99, "gpu_usage": 5, "ram_usage": 30, "running_processes": []})
    engine._load_triggers()
    await engine._check_triggers()
    assert calls == [], f"déclencheur invalide exécuté : {calls}"
    assert any(e["target"] == "Frappe auto" for e in reports.entries()), "aucun signalement"
    assert trigger_mod.TRIGGERS_FILE.read_text(encoding="utf-8") == raw, "fichier réécrit"


@pytest.mark.asyncio
async def test_bt5_workflow_edite_a_la_main_desactive_et_signale(data, reports):
    path = _write_workflow(data, "wf_manuel", [
        {"name": "Fermer Teams", "action": "kill_process", "params": {"name": "teams.exe"}},
        {"name": "Steam", "action": "launch_app", "params": {"name": "steam"}},
    ], name="Workflow manuel")
    raw = path.read_text(encoding="utf-8")
    calls, execute = _recorder()
    engine = WorkflowEngine()
    engine.set_execution_callback(execute)
    engine.load_workflows()
    result = await engine.run_workflow("wf_manuel")
    assert calls == [], f"étapes exécutées : {calls}"
    assert result["success"] is False
    assert "kill_process" in result["message"]
    listed = {w["id"]: w for w in await engine.list_workflows()}
    assert "wf_manuel" in listed and listed["wf_manuel"].get("disabled_reason")
    assert any(e["target"] == "Workflow manuel" for e in reports.entries())
    assert path.read_text(encoding="utf-8") == raw


@pytest.mark.asyncio
async def test_bt5_creation_necrase_pas_un_fichier_existant_non_charge(data):
    """Un fichier illisible n'est pas chargé : créer un workflow du même nom ne doit pas l'écraser."""
    path = data / "workflows" / "routine.yaml"
    path.write_text("id: routine\nsteps: [ : illisible", encoding="utf-8")
    raw = path.read_text(encoding="utf-8")
    engine = WorkflowEngine()
    engine.load_workflows()
    result = await engine.create_workflow("routine", "", [{"name": "n", "action": "notify", "params": {"message": "x"}}])
    assert path.read_text(encoding="utf-8") == raw, "fichier existant écrasé"
    assert result.get("success") is True and result["workflow_id"] != "routine"


# --------------------------------------------------------------------------- #
#  BT5 / BT1 — à l'exécution
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_bt5_tache_modifiee_en_memoire_refusee_a_lexecution(data, reports):
    calls, execute = _recorder()
    scheduler = AtlasScheduler()
    scheduler.set_execution_callback(execute)
    await scheduler.start()
    try:
        job_id = await scheduler.add_job(_job([{"action": "notify", "params": {"message": "ok"}}], "Mutée"))
        scheduler._jobs[job_id].actions.append({"action": "kill_process", "params": {"name": "teams.exe"}})
        await scheduler._on_job_trigger(job_id)
    finally:
        await scheduler.stop()
    assert calls == [], f"actions exécutées : {calls}"
    assert any(e["target"] == "Mutée" for e in reports.entries())


def test_bt1_point_dexecution_commun_bloque_et_signale(monkeypatch, reports):
    """main._execute_action : dernière barrière pour tout appelant (planificateur, déclencheurs, workflows)."""
    import main

    execute = getattr(main, "execute_automation_action", None)
    assert execute is not None, (
        "main n'expose aucun contrôle à l'exécution : _execute_action appelle execute_tool directement"
    )
    called = []

    async def fake_execute_tool(tool, params, context):
        called.append(tool)
        return {"status": "success"}

    monkeypatch.setattr("core.intent_engine.execute_tool", fake_execute_tool)
    monkeypatch.setattr("core.context_monitor.collect_context", lambda: {})
    result = asyncio.run(execute({"action": "kill_process", "params": {"name": "teams.exe"}}))
    assert called == []
    assert result["status"] == "blocked"
    assert reports.entries() and reports.toasts


def test_bt1_confirmation_impossible_devient_un_blocage_signale(monkeypatch, reports):
    """Anomalie A : une confirmation demandée en contexte automatique n'est plus un silence."""
    import main
    from core import confirmation

    execute = getattr(main, "execute_automation_action", None)
    assert execute is not None, "main._execute_action ne détecte pas les confirmations impossibles"

    async def fake_execute_tool(tool, params, context):
        confirmation.store_pending("cid-b1ter", tool, params, {"reason": "simulée"})
        return {"status": "confirmation_required", "confirmation_id": "cid-b1ter", "reason": "simulée"}

    monkeypatch.setattr("core.intent_engine.execute_tool", fake_execute_tool)
    monkeypatch.setattr("core.context_monitor.collect_context", lambda: {})
    result = asyncio.run(execute({"action": "launch_app", "params": {"name": "steam"}}))
    assert result["status"] == "blocked"
    assert confirmation.get_pending("cid-b1ter") is None, "confirmation orpheline laissée en attente"
    assert reports.entries() and reports.toasts


@pytest.mark.asyncio
async def test_bt1_notifications_limitees_pour_un_meme_element(data, reports):
    """Un déclencheur réévalué toutes les 10 s ne doit pas produire une notification toutes les 10 s."""
    scheduler_mod.SCHEDULES_FILE.write_text(json.dumps([
        _job([{"action": "kill_process", "params": {"name": "x"}}], "Répétée", "rep").to_dict()]), encoding="utf-8")
    scheduler = AtlasScheduler()
    scheduler.set_execution_callback(_recorder()[1])
    await scheduler.start()
    try:
        for _ in range(5):
            await scheduler._on_job_trigger("rep")
    finally:
        await scheduler.stop()
    assert len(reports.entries()) >= 5, "chaque blocage doit être journalisé"
    assert len(reports.toasts) == 1, f"{len(reports.toasts)} notifications pour le même élément"


# --------------------------------------------------------------------------- #
#  BT6 — launch_app : plus de chemin arbitraire
# --------------------------------------------------------------------------- #

@pytest.fixture
def no_launch(monkeypatch):
    from tools import app_launcher

    launched = []
    monkeypatch.setattr(app_launcher.os, "startfile", lambda p, *a: launched.append(p), raising=False)
    monkeypatch.setattr(app_launcher.subprocess, "Popen", lambda cmd, **k: launched.append(cmd))
    return launched


@pytest.mark.parametrize("kwargs", [
    {"path": r"C:\Users\alexis\Downloads\setup.bat"},
    {"name": "steam", "path": r"C:\Windows\System32\cmd.exe"},
    {"name": r"C:\Users\alexis\Downloads\setup.bat"},
    {"name": r"\\serveur\partage\outil.exe"},
])
def test_bt6_outil_launch_app_refuse_un_chemin(no_launch, kwargs):
    from tools.app_launcher import launch_app

    result = launch_app(**kwargs)
    assert no_launch == [], f"lancé : {no_launch}"
    assert result["success"] is False


def test_bt6_nom_ne_resout_pas_vers_un_script_telecharge(no_launch, monkeypatch, tmp_path):
    """Repli sur l'index de fichiers (Bureau, Documents, Téléchargements) : un .bat téléchargé
    répondant approximativement au nom demandé ne doit pas être exécuté."""
    from tools import app_launcher

    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    index = tmp_path / "file_index.json"
    index.write_text(json.dumps({"files": [
        {"name": "setup_tool.bat", "path": str(downloads / "setup_tool.bat"), "ext": ".bat"},
        {"name": "outil.exe", "path": str(downloads / "outil.exe"), "ext": ".exe"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(app_launcher, "FILE_INDEX_PATH", index)
    monkeypatch.setattr(app_launcher, "_RUNTIME_APP_INDEX", {})
    monkeypatch.setattr(app_launcher, "KNOWN_APPS", {})
    monkeypatch.setattr(app_launcher.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout=""))

    for name in ("setup tool", "outil"):
        app_launcher.launch_app(name=name)
    assert no_launch == [], f"fichier de l'index exécuté : {no_launch}"


def test_bt6_raccourci_du_bureau_reste_lancable(no_launch, monkeypatch, tmp_path):
    """Contrepartie : un raccourci .lnk du Bureau (jeu, application portable) reste lançable par son nom."""
    from tools import app_launcher

    lnk = tmp_path / "Desktop" / "Mon Jeu.lnk"
    index = tmp_path / "file_index.json"
    index.write_text(json.dumps({"files": [{"name": "Mon Jeu.lnk", "path": str(lnk), "ext": ".lnk"}]}),
                     encoding="utf-8")
    monkeypatch.setattr(app_launcher, "FILE_INDEX_PATH", index)
    monkeypatch.setattr(app_launcher, "_RUNTIME_APP_INDEX", {})
    monkeypatch.setattr(app_launcher, "KNOWN_APPS", {})
    result = app_launcher.launch_app(name="mon jeu")
    assert no_launch == [str(lnk)], result


def test_bt6_validateur_refuse_path_dans_une_demande():
    from core.validator import get_validator

    intent = IntentResult(category="window_mgmt", verb="open", target="",
                          params={"path": r"C:\Users\alexis\Downloads\setup.bat"}, confidence=0.9, raw_input="")
    resolved = get_validator().resolve(intent, {"top_processes": []})
    assert not (resolved.tool == "launch_app" and resolved.params.get("path")), f"path transmis : {resolved.params}"
    assert resolved.rejected is True


def test_bt6_actions_non_protegees_injoignables_par_une_intention():
    """set_priority, browser_ext_click et browser_ext_type ne sont produits par aucune intention :
    seules les automatisations pouvaient les atteindre, et la liste blanche les exclut."""
    from core.intent_classifier import INTENT_CATEGORIES

    produced = {tool for cat in INTENT_CATEGORIES.values() for tool in cat.get("tools", {}).values()}
    assert not produced & {"set_priority", "browser_ext_click", "browser_ext_type"}


# --------------------------------------------------------------------------- #
#  BT7 — classement des workflows modèles (copies de test, jamais les fichiers réels)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_bt7_classement_des_workflows_modeles():
    """Constat, pas action : les copies de test des workflows versionnés, classées par les règles."""
    engine = WorkflowEngine()
    engine.load_workflows()
    listed = {w["id"]: w.get("disabled_reason") for w in await engine.list_workflows()}
    assert listed["demarrage_matin"] is None and listed["mode_travail"] is None
    assert "kill_process" in (listed["mode_gaming"] or "")
    assert "maintenance_empty_bin" in (listed["nettoyage_systeme"] or "")
