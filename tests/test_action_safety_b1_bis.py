"""
Sprint B1-bis — généraliser le patron de sécurité aux actions restantes.

BS1 : cible obligatoire pour la frappe (window_type, window_hotkey) et contrainte sur `text`.
BS2 : titre non vide pour les actions de fenêtre, `position` de window_snap en liste blanche.
BS3 : bornes des coordonnées de window_click, multi-écrans compris.
BS4 : schémas d'URL en liste blanche pour la navigation.

Tests de DÉCISION : vrai validateur, vrai planificateur, vraies fonctions d'outil, mais aucune
action réelle. pyautogui échoue s'il est appelé ; le focus, la fenêtre active, la liste des
fenêtres et la géométrie des écrans sont simulés. Référence : rapport B1, annexe A.
"""

import asyncio
from types import SimpleNamespace

import pytest

from core.intent_classifier import IntentResult
from core.planner import ExecutionPlan, PlanStep, get_planner
from core.validator import get_validator

DISCORD_FOREGROUND = {
    "foreground_window": {"title": "★ conversation privée - Discord", "process": "Discord.exe"},
    "top_processes": [{"name": "Discord.exe"}],
}

# Deux écrans : principal 1920x1080 en (0, 0), secondaire 1920x1080 placé À GAUCHE.
TWO_MONITORS = [(-1920, 0, 0, 1080), (0, 0, 1920, 1080)]


@pytest.fixture(autouse=True)
def no_real_input(monkeypatch):
    """Aucune frappe ni clic réels : pyautogui échoue bruyamment s'il est appelé."""
    import pyautogui

    def boom(*args, **kwargs):
        raise AssertionError("effet réel interdit dans ces tests (pyautogui appelé)")

    for name in ("click", "hotkey", "press", "typewrite", "write", "moveTo", "keyDown", "keyUp"):
        monkeypatch.setattr(pyautogui, name, boom, raising=False)


@pytest.fixture(autouse=True)
def no_recent_context():
    """Pas de contexte de travail récent, sauf si un test le pose explicitement."""
    from core.world_state import get_world_state

    ws = get_world_state()
    saved = (ws.last_action, ws.last_action_ts)
    ws.last_action, ws.last_action_ts = None, 0.0
    yield ws
    ws.last_action, ws.last_action_ts = saved


@pytest.fixture
def screens(monkeypatch):
    from tools import window_controller

    monkeypatch.setattr(window_controller, "_monitor_rects", lambda: list(TWO_MONITORS), raising=False)


def _intent(category, verb, target="", params=None, raw=""):
    return IntentResult(
        category=category, verb=verb, target=target,
        params=params or {}, confidence=0.99, raw_input=raw,
    )


def _resolve(category, verb, target="", params=None, context=None):
    return get_validator().resolve(_intent(category, verb, target, params), context or DISCORD_FOREGROUND)


# --------------------------------------------------------------------------- #
#  Couche outil simulée : on enregistre au lieu d'agir
# --------------------------------------------------------------------------- #

class FakeDesktop:
    """Remplace focus, fenêtre active et actions clavier/souris du window_controller."""

    def __init__(self, monkeypatch, foreground="★ conversation privée - Discord",
                 focus_moves_foreground=True, window_rect=(100, 100, 800, 600)):
        from tools import window_controller as wc

        self.foreground = foreground
        self.focused = []
        self.typed = []
        self.hotkeys = []
        self.clicks = []
        self.window_rect = window_rect  # left, top, width, height de la fenêtre active

        def focus_window(title):
            self.focused.append(title)
            if focus_moves_foreground:
                self.foreground = f"Sans titre - {title}"
            return {"success": True, "message": f"focus {title} (simulé)"}

        def active():
            left, top, width, height = self.window_rect
            return SimpleNamespace(title=self.foreground, left=left, top=top, width=width, height=height)

        monkeypatch.setattr(wc._controller, "focus_window", focus_window)
        monkeypatch.setattr(wc._controller, "type_text",
                            lambda text, interval=0.02, use_clipboard=False:
                            self.typed.append((self.foreground, text)) or {"success": True, "message": "tapé"})
        monkeypatch.setattr(wc._controller, "send_hotkey",
                            lambda *keys: self.hotkeys.append((self.foreground, keys)) or {"success": True, "message": "ok"})
        monkeypatch.setattr(wc._controller, "click",
                            lambda x=None, y=None, button="left", clicks=1:
                            self.clicks.append((self.foreground, x, y)) or {"success": True, "message": "clic"})
        monkeypatch.setattr(wc.gw, "getActiveWindow", active)
        monkeypatch.setattr(wc, "time", SimpleNamespace(sleep=lambda s: None))


# --------------------------------------------------------------------------- #
#  BS1 — cible obligatoire pour la frappe
# --------------------------------------------------------------------------- #

def test_bs1_frappe_sans_cible_est_refusee():
    """« écris bonjour », sans application nommée ni contexte récent, Discord au premier plan."""
    resolved = _resolve("interaction", "type", target="bonjour", params={"text": "bonjour"})
    assert not (resolved.tool == "window_type" and not resolved.params.get("target")), (
        f"frappe sans cible, partirait dans la fenêtre au premier plan : {resolved.tool} {resolved.params}"
    )
    assert resolved.rejected is True


def test_bs1_hotkey_sans_cible_est_refuse():
    resolved = _resolve("interaction", "hotkey", params={"keys": "ctrl+s"})
    assert not (resolved.tool == "window_hotkey" and not resolved.params.get("target")), (
        f"raccourci sans cible, partirait dans la fenêtre au premier plan : {resolved.tool} {resolved.params}"
    )
    assert resolved.rejected is True


@pytest.mark.parametrize("verb,params", [
    ("type", {"text": "bonjour", "target": "bloc-notes"}),
    ("hotkey", {"keys": "ctrl+s", "target": "bloc-notes"}),
])
def test_bs1_frappe_avec_cible_explicite_acceptee(verb, params):
    resolved = _resolve("interaction", verb, params=params)
    assert resolved.rejected is False
    assert resolved.params["target"] == "bloc-notes"


@pytest.mark.parametrize("last_action", [
    {"tool": "ui_click_element", "params": {"app_title": "bloc-notes", "element_name": "Fichier"},
     "result": {"status": "success"}},
    {"tool": "launch_app", "params": {"name": "bloc-notes"}, "result": {"status": "success"}},
])
def test_bs1_frappe_herite_du_contexte_de_travail_recent(no_recent_context, last_action):
    import time

    no_recent_context.last_action = last_action
    no_recent_context.last_action_ts = time.time()
    resolved = _resolve("interaction", "type", params={"text": "bonjour"})
    assert resolved.rejected is False, resolved.rejection_reason
    assert resolved.params.get("target") == "bloc-notes"


def test_bs1_contexte_perime_ou_en_echec_nest_pas_herite(no_recent_context):
    import time

    no_recent_context.last_action = {"tool": "launch_app", "params": {"name": "bloc-notes"},
                                     "result": {"status": "success"}}
    no_recent_context.last_action_ts = time.time() - 600
    assert _resolve("interaction", "type", params={"text": "bonjour"}).rejected is True

    no_recent_context.last_action = {"tool": "launch_app", "params": {"name": "bloc-notes"},
                                     "result": {"status": "error"}}
    no_recent_context.last_action_ts = time.time()
    assert _resolve("interaction", "type", params={"text": "bonjour"}).rejected is True


@pytest.mark.parametrize("step", [
    PlanStep(action="type", target="", params={"text": "bonjour"}),
    # l'exemple même du prompt du planificateur : la cible est dans step.target
    PlanStep(action="type", target="bloc-notes", params={"text": "hello"}),
    PlanStep(action="hotkey", target="", params={"keys": "ctrl+s"}),
])
def test_bs1_plan_la_frappe_vise_lapplication_ouverte(step):
    plan = ExecutionPlan(goal="ouvrir le bloc-notes puis écrire", steps=[
        PlanStep(action="open", target="bloc-notes", params={}), step,
    ])
    validated = get_planner()._validate_plan(plan, DISCORD_FOREGROUND)
    assert len(validated.steps) == 2, f"plan abandonné : {validated.steps[0].resolved.rejection_reason}"
    resolved = validated.steps[1].resolved
    assert resolved.tool in ("window_type", "window_hotkey")
    assert resolved.params.get("target") == "bloc-notes", (
        f"cible attendue bloc-notes, obtenue {resolved.params.get('target')!r} : la frappe irait au premier plan"
    )


@pytest.mark.parametrize("text", [
    "\x1b[2J", "bonjour\x00", "abc\x08\x08\x08", "a\x7fb",
    ["win", "r"], None, "", 42, "x" * 2001,
])
def test_bs1_texte_invalide_refuse(text):
    resolved = _resolve("interaction", "type", params={"text": text, "target": "bloc-notes"})
    assert resolved.tool != "window_type", f"texte {text!r:.40} accepté : {resolved.params!r:.120}"
    assert resolved.rejected is True


@pytest.mark.parametrize("text", ["bonjour", "ligne 1\nligne 2", "col1\tcol2", "Été à Paris !", "x" * 2000])
def test_bs1_texte_valide_accepte(text):
    resolved = _resolve("interaction", "type", params={"text": text, "target": "bloc-notes"})
    assert resolved.rejected is False
    assert resolved.params["text"] == text


# --- Couche outil : les chemins sans validateur (planificateur horaire, déclencheurs, workflows)

def test_bs1_outil_window_type_sans_cible_ne_tape_rien(monkeypatch):
    from tools import window_controller as wc

    desk = FakeDesktop(monkeypatch)
    result = wc.window_type("bonjour")
    assert desk.typed == [], f"texte tapé dans {desk.typed[0][0]!r}"
    assert result["success"] is False


def test_bs1_outil_window_hotkey_sans_cible_nenvoie_rien(monkeypatch):
    from tools import window_controller as wc

    desk = FakeDesktop(monkeypatch)
    result = wc.window_hotkey("ctrl", "s")
    assert desk.hotkeys == [], f"raccourci envoyé à {desk.hotkeys[0][0]!r}"
    assert result["success"] is False


def test_bs1_outil_focus_rate_ne_tape_pas_au_premier_plan(monkeypatch):
    """Le focus « réussit » mais Windows laisse Discord au premier plan (anti-vol de focus)."""
    from tools import window_controller as wc

    desk = FakeDesktop(monkeypatch, focus_moves_foreground=False)
    result = wc.window_type("bonjour", target="bloc-notes")
    assert desk.typed == [], f"texte tapé dans {desk.typed[0][0]!r} au lieu du bloc-notes"
    assert result["success"] is False


def test_bs1_outil_focus_reussi_tape_dans_la_cible(monkeypatch):
    from tools import window_controller as wc

    desk = FakeDesktop(monkeypatch)
    result = wc.window_type("bonjour", target="bloc-notes")
    assert result["success"] is True
    assert desk.typed == [("Sans titre - bloc-notes", "bonjour")]


def test_bs1_outil_texte_de_controle_refuse(monkeypatch):
    from tools import window_controller as wc

    desk = FakeDesktop(monkeypatch)
    result = wc.window_type("\x1b[2Jbonjour", target="bloc-notes")
    assert desk.typed == [], "séquence de contrôle tapée"
    assert result["success"] is False


# --------------------------------------------------------------------------- #
#  BS2 — titre non vide pour les actions de fenêtre
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("verb", ["close", "minimize", "maximize", "focus"])
def test_bs2_action_de_fenetre_sans_titre_refusee(verb):
    resolved = _resolve("window_mgmt", verb)
    assert "Discord" not in str(resolved.params.get("title", "")), f"{verb} dirigé vers le premier plan"
    assert resolved.rejected is True, f"{verb} sans titre accepté : {resolved.tool} {resolved.params}"


def test_bs2_anaphore_sans_fenetre_precedente_refusee():
    """« remets-la au premier plan » sans fenêtre précédente : pas de titre fictif."""
    resolved = _resolve("window_mgmt", "focus", params={"title": "__last_window__"})
    assert resolved.params.get("title") != "__last_window__"
    assert resolved.rejected is True


def test_bs2_anaphore_avec_fenetre_precedente_resolue(no_recent_context):
    import time

    no_recent_context.last_action = {"tool": "window_minimize", "params": {"title": "bloc-notes"},
                                     "result": {"status": "success"}}
    no_recent_context.last_action_ts = time.time()
    resolved = _resolve("window_mgmt", "focus", params={"title": "__last_window__"})
    assert resolved.rejected is False
    assert resolved.params["title"] == "bloc-notes"


@pytest.mark.parametrize("verb", ["close", "minimize", "maximize", "focus"])
def test_bs2_action_de_fenetre_avec_titre_acceptee(verb):
    resolved = _resolve("window_mgmt", verb, target="bloc-notes")
    assert resolved.rejected is False
    assert resolved.params["title"] == "bloc-notes"


@pytest.mark.parametrize("params", [
    {"title": "bloc-notes", "position": "center"},
    {"title": "bloc-notes", "position": "; rm -rf"},
    {"title": "bloc-notes", "position": None},
    {"title": "", "position": "left"},
])
def test_bs2_snap_parametres_invalides_refuses(params):
    resolved = _resolve("window_mgmt", "snap", params=params)
    assert resolved.rejected is True, f"window_snap accepté : {resolved.params}"


def test_bs2_snap_valide_accepte():
    resolved = _resolve("window_mgmt", "snap", target="bloc-notes", params={"position": "top-left"})
    assert resolved.rejected is False
    assert resolved.tool == "window_snap"
    assert resolved.params == {"title": "bloc-notes", "position": "top-left"}


@pytest.mark.parametrize("func", ["window_close", "window_minimize", "window_maximize", "window_focus", "window_snap"])
@pytest.mark.parametrize("title", ["", "   "])
def test_bs2_outil_titre_vide_ne_touche_aucune_fenetre(monkeypatch, func, title):
    """getWindowsWithTitle("") renvoie TOUTES les fenêtres : la première serait fermée."""
    from tools import window_controller as wc

    touched = []
    victim = SimpleNamespace(
        title="★ conversation privée - Discord", isMinimized=False,
        close=lambda: touched.append("close"), minimize=lambda: touched.append("minimize"),
        maximize=lambda: touched.append("maximize"), restore=lambda: touched.append("restore"),
        activate=lambda: touched.append("activate"), moveTo=lambda x, y: touched.append("moveTo"),
        resizeTo=lambda w, h: touched.append("resizeTo"),
    )
    monkeypatch.setattr(wc.gw, "getWindowsWithTitle", lambda t: [victim])
    monkeypatch.setattr(wc, "HAS_WIN32", False)
    monkeypatch.setattr(wc, "HAS_PYWINAUTO", False)
    monkeypatch.setattr(wc, "time", SimpleNamespace(sleep=lambda s: None))
    monkeypatch.setattr(wc.pyautogui, "size", lambda: (1920, 1080))

    result = getattr(wc, func)(title)
    assert touched == [], f"{func}({title!r}) a agi sur {victim.title!r} : {touched}"
    assert result["success"] is False


# --------------------------------------------------------------------------- #
#  BS3 — bornes des coordonnées de clic
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("params", [
    {"x": 5000, "y": 500},          # au-delà de l'écran principal
    {"x": -2500, "y": 500},         # au-delà de l'écran secondaire gauche
    {"x": 500, "y": -10},           # au-dessus des écrans
    {"x": 500, "y": 1080},          # bord exclu
    {"x": 500},                     # y absent : clic à la position courante de la souris
    {},                             # aucune coordonnée
    {"x": "500", "y": 500},         # type chaîne
    {"x": True, "y": 500},          # booléen
    {"x": 500, "y": 500, "button": "double"},
    {"x": 500, "y": 500, "clicks": 50},
])
def test_bs3_clic_coordonnees_invalides_refuse(screens, params):
    resolved = _resolve("interaction", "select", params=params)
    assert resolved.tool != "window_click", f"window_click accepté : {resolved.params}"
    assert resolved.rejected is True


@pytest.mark.parametrize("x,y", [(500, 500), (-500, 500), (-1920, 0), (1919, 1079)])
def test_bs3_clic_sur_un_ecran_accepte_y_compris_secondaire_gauche(screens, x, y):
    """Coordonnées négatives légitimes : écran secondaire placé à gauche."""
    resolved = _resolve("interaction", "select", params={"x": x, "y": y})
    assert resolved.rejected is False, resolved.rejection_reason
    assert resolved.tool == "window_click"
    assert (resolved.params["x"], resolved.params["y"]) == (x, y)


def test_bs3_outil_clic_hors_ecran_nest_pas_execute(monkeypatch, screens):
    from tools import window_controller as wc

    desk = FakeDesktop(monkeypatch)
    result = wc.window_click(x=5000, y=5000)
    assert desk.clicks == [], "clic hors écran exécuté"
    assert result["success"] is False


def test_bs3_outil_clic_hors_de_la_fenetre_cible_nest_pas_execute(monkeypatch, screens):
    from tools import window_controller as wc

    desk = FakeDesktop(monkeypatch, window_rect=(100, 100, 800, 600))  # x 100..899, y 100..699
    result = wc.window_click(x=1500, y=900, target="bloc-notes")
    assert desk.clicks == [], "clic sur l'écran mais hors de la fenêtre cible exécuté"
    assert result["success"] is False


def test_bs3_outil_clic_dans_la_fenetre_cible_execute(monkeypatch, screens):
    from tools import window_controller as wc

    desk = FakeDesktop(monkeypatch, window_rect=(100, 100, 800, 600))
    result = wc.window_click(x=300, y=200, target="bloc-notes")
    assert result["success"] is True
    assert desk.clicks == [("Sans titre - bloc-notes", 300, 200)]


# --------------------------------------------------------------------------- #
#  BS4 — schémas d'URL en liste blanche
# --------------------------------------------------------------------------- #

BAD_URLS = [
    "file:///C:/Windows/win.ini",
    "FILE:///C:/Users",
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    " javascript:alert(1)",
    "java\tscript:alert(1)",
    "\x01javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "ms-settings:privacy",
    "ftp://example.com/x",
    "http://",
    "https:///chemin",
    "first_result",
    "",
    None,
]


@pytest.fixture(params=[True, False], ids=["extension_connectee", "extension_absente"])
def bridge_state(request, monkeypatch):
    from core import validator as validator_mod

    monkeypatch.setattr(validator_mod, "get_bridge",
                        lambda: SimpleNamespace(is_connected=lambda: request.param))
    return request.param


@pytest.mark.parametrize("url", BAD_URLS)
@pytest.mark.parametrize("verb", ["navigate", "open_tab"])
def test_bs4_url_hors_liste_blanche_refusee(bridge_state, verb, url):
    if verb == "open_tab" and url in ("", None):
        pytest.skip("un nouvel onglet vide est légitime (« ouvre un nouvel onglet » : pas de clé url)")
    resolved = _resolve("web", verb, params={"url": url})
    assert resolved.rejected is True, f"{verb} {url!r} accepté : {resolved.tool} {resolved.params}"


@pytest.mark.parametrize("url", ["https://example.com", "http://localhost:8550/health", "https://fr.wikipedia.org/wiki/Atlas"])
def test_bs4_url_http_https_acceptee(bridge_state, url):
    resolved = _resolve("web", "navigate", params={"url": url})
    assert resolved.rejected is False
    assert url in str(resolved.params)


def test_bs4_nouvel_onglet_vide_accepte(bridge_state):
    assert _resolve("web", "open_tab", params={"url": ""}).rejected is False


class FakeBridge:
    def __init__(self):
        self.sent = []

    def is_connected(self):
        return True

    async def send_command(self, command, params):
        self.sent.append((command, params))
        return {"success": True}


@pytest.mark.parametrize("url", ["file:///C:/Windows/win.ini", "javascript:alert(1)", " JAVASCRIPT:alert(1)"])
@pytest.mark.parametrize("func", ["browser_navigate", "browser_new_tab"])
def test_bs4_outil_bridge_nenvoie_pas_une_url_dangereuse(monkeypatch, func, url):
    from tools import browser_bridge

    bridge = FakeBridge()
    monkeypatch.setattr(browser_bridge, "get_bridge", lambda: bridge)
    result = asyncio.run(getattr(browser_bridge, func)(url))
    assert bridge.sent == [], f"URL {url!r} transmise à l'extension"
    assert result["success"] is False


def test_bs4_outil_bridge_url_https_transmise(monkeypatch):
    from tools import browser_bridge

    bridge = FakeBridge()
    monkeypatch.setattr(browser_bridge, "get_bridge", lambda: bridge)
    asyncio.run(browser_bridge.browser_navigate("https://example.com"))
    asyncio.run(browser_bridge.browser_new_tab(""))
    assert bridge.sent == [("navigate", {"url": "https://example.com"}), ("new_tab", {"url": ""})]
