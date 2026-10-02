"""
Sprint F / F3 — la conversation continue, délibérée.

Constat du sprint E : la file audio n'était jamais vidée. Tout ce que le micro captait
pendant qu'Atlas enregistrait, réfléchissait et PARLAIT s'accumulait, puis était analysé
au retour au repos — 17 réveils sur 29 sont partis moins de 0,2 s après la fin d'un cycle.
Alexis appréciait l'effet (enchaîner sans redire « Hey Atlas ») : on le garde, mais construit.

Ce que ces tests exigent :
  - la file est vidée APRÈS la parole : Atlas ne réagit pas à ce qu'il a entendu en parlant ;
  - une fenêtre de suite bornée prend la question suivante sans mot d'éveil ;
  - cette fenêtre est visible, distincte du repos ;
  - un « oui » dans cette fenêtre ne valide JAMAIS une confirmation.

Le micro et le haut-parleur sont simulés ; le modèle de mot d'éveil, lui, est le vrai.
"""

import asyncio
import pathlib
import sys
import wave

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "hey_atlas_16k.wav"
WAKE_MODEL = pathlib.Path(__file__).resolve().parent.parent / "models" / "wakewords" / "hey_atlas.onnx"
needs_wake_model = pytest.mark.skipif(not WAKE_MODEL.exists(), reason="modèle de mot d'éveil absent")

PAROLE = b"\x01\x00" * 16000   # une seconde « parlée » (le contenu importe peu : _transcribe est simulé)


class FakeInputStream:
    captured = None

    def __init__(self, *args, callback=None, **kwargs):
        FakeInputStream.captured = callback

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass


def fixture_frames(n=1280):
    with wave.open(str(FIXTURE), "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return [data[i:i + n] for i in range(0, len(data) - n + 1, n)]


@pytest.fixture
def engine(monkeypatch):
    import sounddevice as sd

    from core.voice_engine import VoiceEngine

    monkeypatch.setattr(sd, "InputStream", FakeInputStream)
    eng = VoiceEngine()
    eng._running = True
    return eng


def script(engine, monkeypatch, transcriptions, reponses=None, on_speak=None):
    """Pilote un cycle vocal : ce que le micro « entend », ce qu'Atlas répond.

    Renvoie le journal des appels : enregistrements (avec leur délai d'attente), textes
    traités, phrases dites, et activité observée pendant chaque enregistrement.
    """
    journal = {"records": [], "traites": [], "dits": [], "activites": []}
    textes = list(transcriptions)

    async def record(wait_for_speech=None):
        journal["records"].append(wait_for_speech)
        journal["activites"].append(engine.activity)
        return PAROLE if textes and textes[0] else b""

    async def transcribe(audio):
        return textes.pop(0) if textes else ""

    async def pipeline(texte):
        journal["traites"].append(texte)
        return (reponses or {}).get(texte, f"réponse à « {texte} »")

    async def speak(texte):
        journal["dits"].append(texte)
        if on_speak:
            await on_speak()

    monkeypatch.setattr(engine, "_record_audio", record)
    monkeypatch.setattr(engine, "_transcribe", transcribe)
    monkeypatch.setattr(engine, "_run_text_pipeline", pipeline)
    monkeypatch.setattr(engine, "_speak", speak)
    return journal


# --------------------------------------------------------------------------- #
#  Atlas ne réagit pas à ce qu'il a entendu en parlant
# --------------------------------------------------------------------------- #

@needs_wake_model
def test_f3_pas_de_reveil_sur_le_son_capte_pendant_la_parole(engine, monkeypatch):
    """Pendant qu'Atlas parle, le micro capte un « Hey Atlas » (sa propre voix, la pièce).

    Vrai modèle openWakeWord, vrai rappel audio. Avant : ces trames attendaient dans la
    file et déclenchaient un réveil dès le retour au repos (score 0,995 sur ce fichier).
    """
    async def run():
        engine._loop = asyncio.get_running_loop()
        await engine._init_wake_word()

        async def micro_pendant_la_parole():
            for frame in fixture_frames(engine._wake_frame_length):
                FakeInputStream.captured(frame.reshape(-1, 1), len(frame), None, None)
            await asyncio.sleep(0)

        script(engine, monkeypatch, ["quelle heure il est"], on_speak=micro_pendant_la_parole)
        await engine._on_wake_word()

        reveils = 0
        while not engine._wake_queue.empty():
            frame = engine._wake_queue.get_nowait()
            if engine._wake_detected(frame[: engine._wake_frame_length]):
                reveils += 1
        return reveils

    reveils = asyncio.run(run())
    assert reveils == 0, f"{reveils} réveil(s) sur du son capté pendant qu'Atlas parlait"


# --------------------------------------------------------------------------- #
#  La fenêtre de suite
# --------------------------------------------------------------------------- #

def test_f3_la_fenetre_de_suite_prend_la_question_suivante(engine, monkeypatch):
    journal = script(engine, monkeypatch, ["quelle heure il est", "et demain", ""])
    asyncio.run(engine._on_wake_word())
    assert journal["traites"] == ["quelle heure il est", "et demain"], (
        f"seule la première question a été traitée : {journal['traites']}"
    )


def test_f3_la_fenetre_de_suite_est_bornee(engine, monkeypatch):
    import core.voice_engine as voice_mod

    journal = script(engine, monkeypatch, ["quelle heure il est", ""])
    asyncio.run(engine._on_wake_word())
    assert len(journal["records"]) >= 2, "aucune écoute de suite après la réponse"
    FOLLOW_UP_SECONDS = getattr(voice_mod, "FOLLOW_UP_SECONDS", None)
    assert journal["records"][0] is None, "la première écoute suit le mot d'éveil, sans délai imposé"
    assert journal["records"][1] == FOLLOW_UP_SECONDS, (
        f"écoute de suite sans délai borné : {journal['records']}"
    )
    assert 3 <= FOLLOW_UP_SECONDS <= 10
    assert engine.activity == "repos", "sans parole dans la fenêtre, retour au mot d'éveil"
    assert journal["traites"] == ["quelle heure il est"]


def test_f3_la_fenetre_de_suite_se_voit(engine, monkeypatch):
    journal = script(engine, monkeypatch, ["quelle heure il est", ""])
    asyncio.run(engine._on_wake_word())
    assert len(journal["activites"]) >= 2, "aucune écoute de suite"
    assert journal["activites"][0] == "écoute"
    assert journal["activites"][1] == "suite", (
        f"pendant la fenêtre de suite, l'indicateur affiche {journal['activites'][1]!r} "
        "— l'utilisateur ne peut pas savoir qu'Atlas l'écoute encore"
    )


def test_f3_une_parole_continue_ne_rouvre_pas_la_fenetre_indefiniment(engine, monkeypatch):
    """Une télévision allumée parle sans arrêt : la fenêtre de suite ne doit pas faire
    d'Atlas un micro ouvert qui répond à la pièce."""
    import core.voice_engine as voice_mod

    plafond = getattr(voice_mod, "MAX_FOLLOW_UPS", None)
    journal = script(engine, monkeypatch, [f"phrase {i}" for i in range(40)])
    asyncio.run(engine._on_wake_word())
    assert plafond is not None, "aucun plafond d'enchaînements défini"
    assert len(journal["traites"]) == plafond + 1, (
        f"{len(journal['traites'])} phrases traitées d'affilée sans mot d'éveil"
    )
    assert engine.activity == "repos"


# --------------------------------------------------------------------------- #
#  Interdiction : la fenêtre de suite ne valide aucune confirmation
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("oui", ["oui", "Oui.", "ok vas-y", "confirme", "d'accord"])
def test_f3_un_oui_dans_la_fenetre_de_suite_ne_valide_pas_la_confirmation(engine, monkeypatch, oui):
    """Si un « oui » capté ici pouvait valider une action, on aurait construit la
    confirmation vocale sans aucune de ses protections (rapport E, annexe A)."""
    import core.intent_engine as ie
    from core import confirmation

    executes = []
    monkeypatch.setitem(ie.TOOL_HANDLERS, "window_close",
                        lambda args: executes.append(args) or {"success": True, "message": "fermée"})
    confirmation._pending.clear()
    attente = ie.request_confirmation("window_close", {"title": "Steam"}, {}, "fermer une fenêtre")
    cid = attente["confirmation_id"]

    journal = script(engine, monkeypatch, ["ferme la fenêtre Steam", oui, ""],
                     reponses={"ferme la fenêtre Steam":
                               "Cette action nécessite une confirmation à l'écran. Je ne l'ai pas exécutée."})
    asyncio.run(engine._on_wake_word())

    assert executes == [], "la fenêtre a été fermée sur un « oui » dit à la voix"
    assert cid in confirmation._pending, "la confirmation a été consommée"
    assert oui not in journal["traites"], "le « oui » a été traité comme une commande"
    assert any("écran" in d for d in journal["dits"][1:]), (
        f"le « oui » n'a pas reçu de réponse explicite : {journal['dits']}"
    )
    confirmation._pending.clear()
