"""
Sprint F / F2 — le moteur honore la confirmation, de bout en bout.

Cause racine (sprint E, R04 / D-E1) : deux endroits décidaient si une action exige une
confirmation — le drapeau du validateur, et une liste codée en dur dans `execute_tool`.
Le moteur ne lisait que la sienne : `window_close`, `schedule_add`, `trigger_add`,
`workflow_run` et `workflow_create`, marqués « à confirmer » par le validateur,
s'exécutaient sans rien demander. Et même les confirmations qui fonctionnaient étaient
invisibles : `/api/chat` renvoyait `message=None`, la fenêtre affichait « Action executee. ».

Ces tests partent d'une DEMANDE et vérifient l'EFFET. Aucun ne s'arrête au drapeau.
Aucune action réelle : les outils sont remplacés par des enregistreurs.
"""

import asyncio
import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import core.intent_engine as ie
from core import confirmation
from core.intent_classifier import INTENT_CATEGORIES, IntentResult
from core.validator import get_validator

CONTEXT = {"foreground_window": {"title": "Sans titre - Bloc-notes", "process": "notepad.exe"},
           "top_processes": [], "gpu_usage": 5, "cpu_usage": 5}


@pytest.fixture
def executed(monkeypatch):
    """Remplace chaque outil par un enregistreur : on voit ce qui AURAIT été exécuté."""
    calls = []
    for name in list(ie.TOOL_HANDLERS):
        monkeypatch.setitem(ie.TOOL_HANDLERS, name,
                            (lambda n: lambda args: calls.append((n, args))
                             or {"success": True, "message": f"[simulé] {n}"})(name))
    monkeypatch.setattr(ie, "_save_action_to_memory", lambda *a, **k: None)
    confirmation._pending.clear()
    yield calls
    confirmation._pending.clear()


def _intent(category, verb, target="", params=None, raw=""):
    return IntentResult(category=category, verb=verb, target=target, params=params or {},
                        confidence=0.95, raw_input=raw)


def _run(category, verb, target="", params=None):
    resolved = get_validator().resolve(_intent(category, verb, target, params), CONTEXT)
    return resolved, asyncio.run(ie.get_execution_engine().execute(resolved, CONTEXT))


# --------------------------------------------------------------------------- #
#  Le moteur respecte la décision du validateur
# --------------------------------------------------------------------------- #

def test_f2_fermer_une_fenetre_attend_la_confirmation(executed):
    """R04 : « ferme la fenêtre Steam » fermait Steam sans rien demander."""
    resolved, result = _run("window_mgmt", "close", target="bloc-notes")
    assert resolved.confirmation_required is True
    assert executed == [], f"fenêtre fermée sans confirmation : {executed}"
    assert result["status"] == "confirmation_required"
    assert result.get("confirmation_id") in confirmation._pending


@pytest.mark.parametrize("category,verb,params", [
    ("automation", "schedule", {"name": "t", "actions": [{"action": "notify", "params": {"message": "x"}}]}),
    ("automation", "trigger", {"name": "t", "actions": [{"action": "notify", "params": {"message": "x"}}]}),
    ("automation", "workflow", {"workflow_id": "demarrage_matin"}),
])
def test_f2_actions_marquees_par_le_validateur_attendent_la_confirmation(executed, category, verb, params):
    resolved, result = _run(category, verb, params=params)
    assert resolved.confirmation_required is True
    assert executed == [], f"{resolved.tool} exécuté sans confirmation : {executed}"
    assert result["status"] == "confirmation_required"


def test_f2_une_seule_source_de_verite(executed):
    """Toute intention que le validateur marque « à confirmer » est bloquée par le moteur."""
    trous = []
    for category, data in INTENT_CATEGORIES.items():
        for verb in sorted(set(data.get("tools", {}))):
            params = {"url": "https://example.com"} if category == "web" else {}
            target = "bloc-notes" if category in ("window_mgmt", "process") else ""
            resolved = get_validator().resolve(_intent(category, verb, target, params), CONTEXT)
            if not resolved.confirmation_required or resolved.rejected:
                continue
            executed.clear()
            asyncio.run(ie.get_execution_engine().execute(resolved, CONTEXT))
            if executed:
                trous.append(f"{category}/{verb} → {resolved.tool}")
    assert trous == [], f"marqués « à confirmer » mais exécutés directement : {trous}"


def test_f2_confirmer_execute_l_action_une_seule_fois(executed):
    _, result = _run("window_mgmt", "close", target="bloc-notes")
    assert result["status"] == "confirmation_required", "aucune confirmation demandée"
    sortie = asyncio.run(ie.execute_confirmed(result["confirmation_id"], CONTEXT))
    assert [n for n, _ in executed] == ["window_close"]
    assert sortie.get("status") == "success"
    # Une deuxième validation du même identifiant ne rejoue rien.
    asyncio.run(ie.execute_confirmed(result["confirmation_id"], CONTEXT))
    assert [n for n, _ in executed] == ["window_close"]


def test_f2_refuser_n_execute_rien_et_efface_l_attente(executed):
    from api.models import ConfirmationResponse
    from api.routes import confirm_endpoint

    _, result = _run("window_mgmt", "close", target="bloc-notes")
    cid = result.get("confirmation_id")
    assert cid, "aucune confirmation demandée"
    reponse = asyncio.run(confirm_endpoint(ConfirmationResponse(confirmation_id=cid, accepted=False)))
    assert executed == []
    assert reponse["status"] == "cancelled"
    assert cid not in confirmation._pending, "confirmation refusée laissée en attente"


def test_f2_expiration_refus_par_defaut(executed, monkeypatch):
    """Une confirmation sans réponse ne reste pas pendante, et ne s'exécute jamais."""
    _, result = _run("window_mgmt", "close", target="bloc-notes")
    cid = result.get("confirmation_id")
    assert cid, "aucune confirmation demandée"
    reel = time.time
    monkeypatch.setattr(ie.time, "time", lambda: reel() + 3600)
    sortie = asyncio.run(ie.execute_confirmed(cid, CONTEXT))
    assert executed == [], "action exécutée après expiration"
    assert sortie.get("status") == "expired", f"statut inattendu : {sortie}"
    assert cid not in confirmation._pending


# --------------------------------------------------------------------------- #
#  La confirmation se voit
# --------------------------------------------------------------------------- #

def test_f2_la_fenetre_recoit_la_confirmation(executed):
    """Avant : type='tool_execution', message=None → « Action executee. » affiché, rien d'autre."""
    from api.models import ChatRequest
    from api.routes import chat_endpoint

    reponse = asyncio.run(chat_endpoint(ChatRequest(message="ferme la fenêtre bloc-notes", history=[])))
    assert executed == [], f"exécuté sans confirmation : {executed}"
    assert reponse.get("type") == "confirmation_required", (
        f"la fenêtre reçoit type={reponse.get('type')!r} message={reponse.get('message')!r}"
    )
    for cle in ("confirmation_id", "action", "target", "message", "expires_in"):
        assert reponse.get(cle), f"champ '{cle}' absent : la fenêtre ne peut pas l'afficher"


def test_f2_les_confirmations_en_attente_sont_exposees(executed):
    """Une confirmation demandée à la voix doit apparaître dans la fenêtre : il faut une route."""
    import api.routes as routes

    chemins = {getattr(r, "path", "") for r in routes.router.routes}
    assert "/confirmations" in chemins, (
        "aucune route n'expose les confirmations en attente : une demande vocale resterait invisible"
    )
    _run("window_mgmt", "close", target="bloc-notes")
    liste = asyncio.run(routes.list_confirmations())
    assert len(liste["pending"]) == 1
    item = liste["pending"][0]
    assert item["action"] == "window_close" and item["target"] == "bloc-notes"
    assert 0 < item["expires_in"] <= 120


# --------------------------------------------------------------------------- #
#  Protection des processus : « intouchable » veut dire refusé (décision d'Alexis)
# --------------------------------------------------------------------------- #

def test_f2_processus_systeme_refuse_sans_confirmation_possible(executed):
    systeme = sorted(confirmation.ALWAYS_PROTECTED)[0]
    resolved, result = _run("process", "kill", target=systeme, params={"name": systeme})
    assert executed == []
    assert result["status"] != "confirmation_required", (
        f"« {systeme} » est un processus système : une confirmation est proposée, un clic suffirait à le tuer"
    )
    assert not confirmation._pending


def test_f2_processus_ordinaire_reste_confirmable(executed):
    resolved, result = _run("process", "kill", target="notepad.exe", params={"name": "notepad.exe"})
    assert executed == []
    assert result["status"] == "confirmation_required"


# --------------------------------------------------------------------------- #
#  Aucune réouverture des automatisations (B1-ter)
# --------------------------------------------------------------------------- #

def test_f2_un_workflow_planifie_n_est_pas_bloque(executed, monkeypatch):
    """Un workflow lancé par une tâche planifiée a été confirmé à sa création : il ne
    doit pas attendre une confirmation que personne ne peut donner."""
    import main

    monkeypatch.setattr("core.context_monitor.collect_context", lambda: CONTEXT)
    sortie = asyncio.run(main.execute_automation_action(
        {"action": "workflow_run", "params": {"workflow_id": "demarrage_matin"}}))
    assert sortie.get("status") != "blocked", f"workflow planifié bloqué : {sortie}"
    assert ("workflow_run", {"workflow_id": "demarrage_matin"}) in executed


def test_f2_une_automatisation_ne_peut_toujours_pas_fermer_de_fenetre(executed, monkeypatch):
    import main

    monkeypatch.setattr("core.context_monitor.collect_context", lambda: CONTEXT)
    sortie = asyncio.run(main.execute_automation_action(
        {"action": "window_close", "params": {"title": "bloc-notes"}}))
    assert sortie["status"] == "blocked"
    assert executed == []


# --------------------------------------------------------------------------- #
#  Le chemin vocal du sprint E se déclenche enfin en réel
# --------------------------------------------------------------------------- #

def test_f2_voix_fermer_une_fenetre_annonce_la_confirmation(executed, monkeypatch):
    """Au sprint E, ce chemin n'était prouvé qu'avec un moteur simulé : en réel, la
    fenêtre était fermée. Ici, seul l'outil est simulé ; validateur et moteur sont réels."""
    from core.voice_engine import VoiceEngine

    affiche = []
    monkeypatch.setattr(VoiceEngine, "_announce_on_screen",
                        lambda self, titre, message: affiche.append((titre, message)))
    reponse = asyncio.run(VoiceEngine()._run_text_pipeline("ferme la fenêtre bloc-notes"))
    assert executed == [], f"fenêtre fermée à la voix sans confirmation : {executed}"
    assert "confirmation" in reponse.lower() and "écran" in reponse.lower(), reponse
    assert affiche, "rien n'est affiché à l'écran"
    assert len(confirmation._pending) == 1, "la confirmation doit rester en attente pour la fenêtre"
