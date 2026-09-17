"""
Sprint B1 — sécurité des actions : L5 (paramètres de touches) et L24 (cible de clic).

Tests de DÉCISION : ils exercent le vrai validateur, le vrai planificateur et la vraie
fonction de grounding, mais n'exécutent aucune action réelle — ni frappe clavier, ni clic,
ni lancement d'application. Les couches de grounding sont remplacées quand il le faut, et
un garde-fou vérifie que pyautogui n'est jamais sollicité.

Référence : rapport Sprint A — L5 (C02 : « F-i-c-h-i-e-r » tapé dans le Bloc-notes),
L24 (C05 : clic cherché dans la fenêtre Discord au premier plan).
"""

import asyncio

import pytest

from core.intent_classifier import IntentResult
from core.planner import ExecutionPlan, PlanStep, get_planner
from core.validator import get_validator

DISCORD_FOREGROUND = {
    "foreground_window": {"title": "★ conversation privée - Discord", "process": "Discord.exe"},
    "top_processes": [{"name": "Discord.exe"}],
}


@pytest.fixture(autouse=True)
def no_real_input(monkeypatch):
    """Aucune frappe ni clic réels : pyautogui échoue bruyamment s'il est appelé."""
    import pyautogui

    def boom(*args, **kwargs):
        raise AssertionError("effet réel interdit dans ces tests (pyautogui appelé)")

    for name in ("click", "hotkey", "press", "typewrite", "write", "moveTo"):
        monkeypatch.setattr(pyautogui, name, boom, raising=False)


def _intent(category, verb, target="", params=None, raw=""):
    return IntentResult(
        category=category, verb=verb, target=target,
        params=params or {}, confidence=0.99, raw_input=raw,
    )


# --------------------------------------------------------------------------- #
#  L5 — paramètres de touches
# --------------------------------------------------------------------------- #

def test_l5_hotkey_avec_chaine_arbitraire_est_rejete():
    """« Fichier » n'est pas une combinaison de touches : l'action doit être refusée.

    Avant correction : le validateur renvoyait window_hotkey avec keys='Fichier', que
    l'exécuteur décomposait en F, i, c, h, i, e, r — texte tapé dans la fenêtre active.
    """
    resolved = get_validator().resolve(
        _intent("interaction", "hotkey", params={"keys": "Fichier"}), {},
    )
    assert not (resolved.tool == "window_hotkey" and resolved.params.get("keys") == "Fichier"), (
        "le validateur laisse passer une frappe de texte arbitraire : "
        f"{resolved.tool} params={resolved.params}"
    )
    assert resolved.rejected is True, f"action non rejetée : {resolved.tool} {resolved.params}"
    assert "Fichier" in resolved.rejection_reason


@pytest.mark.parametrize("keys", ["ctrl+s", ["ctrl", "s"], "CTRL+SHIFT+n", ["alt", "f4"], "win", ["f5"]])
def test_l5_hotkeys_valides_acceptees(keys):
    """Les vraies combinaisons restent acceptées, et les touches sont normalisées en liste."""
    resolved = get_validator().resolve(_intent("interaction", "hotkey", params={"keys": keys}), {})
    assert resolved.rejected is False
    assert resolved.tool == "window_hotkey"
    assert isinstance(resolved.params["keys"], list)
    assert all(isinstance(k, str) and k == k.lower() for k in resolved.params["keys"])


@pytest.mark.parametrize("keys", ["Fichier", "", None, "ctrl+inexistante", ["ctrl", "Fichier"], 42, ["ctrl", 5]])
def test_l5_parametres_de_touches_invalides_rejetes(keys):
    resolved = get_validator().resolve(_intent("interaction", "hotkey", params={"keys": keys}), {})
    assert resolved.tool != "window_hotkey", f"{keys!r} exécutable tel quel : params={resolved.params}"
    assert resolved.rejected is True, f"{keys!r} accepté à tort"


def test_l5_plan_contenant_un_hotkey_invalide_est_rejete_en_entier():
    """Un plan dont une étape est refusée ne doit exécuter aucune de ses étapes."""
    plan = ExecutionPlan(goal="ouvrir le bloc-notes puis cliquer sur Fichier", steps=[
        PlanStep(action="open", target="bloc-notes", params={}),
        PlanStep(action="hotkey", target="bloc-notes", params={"keys": "Fichier"}),
    ])
    validated = get_planner()._validate_plan(plan, DISCORD_FOREGROUND)
    tools = [s.resolved.tool for s in validated.steps if s.resolved]
    assert "window_hotkey" not in tools, "une frappe clavier invalide reste exécutable"
    assert "launch_app" not in tools, "le reste de la chaîne doit être abandonné"
    assert any(s.resolved is not None and s.resolved.rejected for s in validated.steps)


# --------------------------------------------------------------------------- #
#  L24 — cible de clic
# --------------------------------------------------------------------------- #

def test_l24_clic_sans_application_nommee_ne_vise_pas_le_premier_plan():
    """Sans application nommée, le clic ne doit pas partir sur la fenêtre au premier plan.

    Avant correction : app_title devenait le titre de la fenêtre Discord active.
    """
    from core.world_state import get_world_state

    ws = get_world_state()
    ws.last_action = None  # pas de contexte de travail récent
    resolved = get_validator().resolve(
        _intent("interaction", "click", target="Fichier", params={"element_name": "Fichier"}),
        DISCORD_FOREGROUND,
    )
    assert "Discord" not in resolved.params.get("app_title", ""), "clic dirigé vers le premier plan"
    assert resolved.rejected is True, "l'absence de cible doit être un échec explicite"


def test_l24_clic_avec_application_nommee_garde_cette_application():
    resolved = get_validator().resolve(
        _intent("interaction", "click", target="Fichier",
                params={"element_name": "Fichier", "app_title": "bloc-notes"}),
        DISCORD_FOREGROUND,
    )
    assert resolved.rejected is False
    assert resolved.params["app_title"] == "bloc-notes"


def test_l24_plan_le_clic_herite_de_lapplication_de_letape_precedente():
    """C05 : « ouvre le bloc-notes puis clique sur Fichier », Discord au premier plan."""
    plan = ExecutionPlan(goal="ouvrir le bloc-notes puis cliquer sur Fichier", steps=[
        PlanStep(action="open", target="bloc-notes", params={}),
        PlanStep(action="click", target="Fichier", params={"element_name": "Fichier"}),
    ])
    validated = get_planner()._validate_plan(plan, DISCORD_FOREGROUND)
    click = validated.steps[1].resolved
    assert click is not None and click.tool == "ui_click_element"
    assert "Discord" not in click.params.get("app_title", "")
    assert "bloc-notes" in click.params.get("app_title", "").lower(), \
        f"app_title attendu = bloc-notes, obtenu {click.params.get('app_title')!r}"


# --------------------------------------------------------------------------- #
#  L24 — grounding : pas de repli sur une fenêtre quelconque
# --------------------------------------------------------------------------- #

def test_l24_grounding_refuse_une_cible_vide():
    from tools import grounding

    result = asyncio.run(grounding.find_and_click("", "Fichier"))
    assert result["success"] is False
    assert result["method"] == "no_target"


def test_l24_grounding_echoue_explicitement_si_application_absente(monkeypatch):
    """Application nommée introuvable : échec clair, sans essayer les couches sur une autre fenêtre."""
    from tools import grounding

    monkeypatch.setattr(grounding, "_find_candidate_windows", lambda title: [])
    attempted = []
    for layer in ("_try_uia", "_try_cache", "_try_ocr", "_try_easyocr"):
        async def never(app, elem, _n=layer):
            attempted.append(_n)
            return None
        never.__name__ = layer
        monkeypatch.setattr(grounding, layer, never)

    result = asyncio.run(grounding.find_and_click("bloc-notes", "Fichier"))
    assert result["success"] is False
    assert result["method"] == "app_not_found", result
    assert attempted == [], f"couches tentées malgré l'absence de la fenêtre : {attempted}"
