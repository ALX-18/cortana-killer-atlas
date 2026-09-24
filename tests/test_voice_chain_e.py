"""
Sprint E — la chaîne vocale, testée sur du vrai audio et du vrai code.

La leçon de v6.0.2 : 17 tests verts sur une chaîne vocale morte, parce que tous mockaient
`predict`, `_init_wake_word` ou `_speak_sync`. Ici :

- **E1** : un WAV réel « Hey Atlas » traverse le VRAI `_wake_callback` et le VRAI modèle
  openWakeWord. Rien n'est mocké sauf le flux micro (`sounddevice.InputStream`), pour ne pas
  ouvrir le microphone pendant les tests.
- **E3** : la VRAIE synthèse Piper produit un tableau audio. Seule la sortie haut-parleur
  (`sounddevice.play`) est remplacée, pour que la suite ne parle pas toute seule.

Le fichier `tests/fixtures/hey_atlas_16k.wav` est une synthèse SAPI anglaise du mot d'éveil,
16 kHz mono int16. Le modèle `hey_atlas.onnx` est entraîné sur « Hey Atlas » prononcé en
anglais : mesuré au sprint E, la même phrase par une voix française marque 0,0008.
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
VOICE_MODEL = pathlib.Path(__file__).resolve().parent.parent / "data" / "voices" / "fr_FR-siwis-medium.onnx"

needs_wake_model = pytest.mark.skipif(
    not WAKE_MODEL.exists(), reason="modèle de mot d'éveil absent (scripts/download_voice_models.py)")
needs_voice_model = pytest.mark.skipif(
    not VOICE_MODEL.exists(), reason="voix Piper absente (scripts/download_voice_models.py)")


def read_fixture_frames(frame_length: int = 1280):
    """Découpe le WAV en trames int16, comme le ferait le flux micro."""
    with wave.open(str(FIXTURE), "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return [data[i:i + frame_length] for i in range(0, len(data) - frame_length + 1, frame_length)]


class FakeInputStream:
    """Remplace le flux micro : on récupère le VRAI callback, sans ouvrir le microphone."""

    captured = None

    def __init__(self, *args, callback=None, **kwargs):
        FakeInputStream.captured = callback
        self.kwargs = kwargs

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass


@pytest.fixture
def engine(monkeypatch):
    import sounddevice as sd

    from core.voice_engine import VoiceEngine

    monkeypatch.setattr(sd, "InputStream", FakeInputStream)
    eng = VoiceEngine()
    eng._running = True
    return eng


# --------------------------------------------------------------------------- #
#  E1 — le mot d'éveil, sur du vrai audio
# --------------------------------------------------------------------------- #

@needs_wake_model
def test_e1_mot_deveil_declenche_sur_un_wav_reel(engine):
    """« Hey Atlas » enregistré doit franchir le seuil, en passant par le vrai code.

    Défaut L1 : `_wake_callback` divise l'audio par 32768 alors qu'openWakeWord attend du
    PCM int16. Mesuré au sprint E sur ce fichier : 0,995 en int16, 0,0008 tel quel.
    """
    async def run():
        engine._loop = asyncio.get_running_loop()
        await engine._init_wake_word()
        callback = FakeInputStream.captured
        assert callback is not None, "le flux micro n'a pas été créé"

        best = 0.0
        detected = False
        for frame in read_fixture_frames(engine._wake_frame_length):
            callback(frame.reshape(-1, 1), len(frame), None, None)
            await asyncio.sleep(0)          # laisse le callback déposer la trame
            while not engine._wake_queue.empty():
                audio = engine._wake_queue.get_nowait()
                # Un seul appel au modèle par trame : openWakeWord garde un tampon
                # glissant, l'interroger deux fois fausserait le score.
                if engine._wake_detected(audio[: engine._wake_frame_length]):
                    detected = True
                best = max(best, getattr(engine, "_last_wake_score", 0.0))
        return detected, best

    detected, best = asyncio.run(run())
    assert detected, (
        f"mot d'éveil non détecté sur un WAV réel (meilleur score observé : {best}) — "
        "l'audio n'atteint pas le modèle dans le format attendu"
    )


@needs_wake_model
def test_e1_audio_transmis_au_modele_en_int16(engine):
    """Ce que le callback dépose doit être de l'audio int16, pas du float normalisé."""
    async def run():
        engine._loop = asyncio.get_running_loop()
        await engine._init_wake_word()
        # La trame la plus sonore : le fichier commence par un demi-seconde de silence.
        frames = read_fixture_frames(engine._wake_frame_length)
        frame = max(frames, key=lambda f: int(np.abs(f).max()))
        FakeInputStream.captured(frame.reshape(-1, 1), len(frame), None, None)
        await asyncio.sleep(0)
        return engine._wake_queue.get_nowait()

    audio = asyncio.run(run())
    assert audio.dtype == np.int16, f"audio transmis en {audio.dtype}, openWakeWord attend int16"
    assert np.abs(audio).max() > 1, "amplitude écrasée : l'audio a été normalisé"


# --------------------------------------------------------------------------- #
#  E2 — la transcription, sur GPU, avec du vrai audio
# --------------------------------------------------------------------------- #

def test_e2_transcription_gpu_sur_audio_reel(engine):
    """Le WAV réel doit être transcrit, sur le GPU.

    Défaut L2 : `cublas64_12.dll is not found`. Les bibliothèques CUDA viennent des paquets
    pip nvidia-cublas-cu12 et nvidia-cudnn-cu12, mais CTranslate2 les charge par le chemin
    de recherche du processus : il faut les y déclarer avant de charger le modèle.
    """
    with wave.open(str(FIXTURE), "rb") as w:
        pcm = w.readframes(w.getnframes())

    texte = asyncio.run(engine._transcribe(pcm))
    etat = engine.stt_status()
    assert "atlas" in texte.lower(), f"transcription inattendue : {texte!r}"
    assert etat["device_used"] == "cuda", (
        f"transcription retombée sur '{etat['device_used']}' : {etat.get('cuda_error')}"
    )
    assert etat["cublas_available"] is True


# --------------------------------------------------------------------------- #
#  E5 — une action à confirmation, demandée à la voix
# --------------------------------------------------------------------------- #

def test_e5_action_a_confirmation_est_annoncee_et_affichee(engine, monkeypatch):
    """Aucun blocage silencieux, et surtout aucun « C'est fait » mensonger.

    Le moteur d'exécution est remplacé par un double qui renvoie une demande de
    confirmation : le classifieur et le validateur, eux, tournent pour de vrai. Aucune
    fenêtre n'est fermée pendant ce test.
    """
    import core.intent_engine as ie

    async def fake_execute(self, resolved, context):
        return {"status": "confirmation_required", "confirmation_id": "abc123",
                "reason": "Fermer 'bloc-notes' est une action irréversible.",
                "level": "🟡 DEMANDE"}

    monkeypatch.setattr(ie.get_execution_engine().__class__, "execute", fake_execute)
    notifications = []
    monkeypatch.setattr("tools.notifier.notify",
                        lambda message, title="Atlas", duration_seconds=5:
                        notifications.append((title, message)))

    reponse = asyncio.run(engine._run_text_pipeline("ferme le bloc-notes"))

    assert "c'est fait" not in reponse.lower(), (
        f"Atlas annonce une action faite alors qu'une confirmation est en attente : {reponse!r}"
    )
    assert "confirmation" in reponse.lower(), f"réponse parlée sans mention de confirmation : {reponse!r}"
    assert "écran" in reponse.lower(), f"l'utilisateur n'est pas renvoyé vers l'écran : {reponse!r}"
    assert notifications, "aucune confirmation affichée à l'écran"


# --------------------------------------------------------------------------- #
#  E4 — un indicateur de santé qui dit vrai
# --------------------------------------------------------------------------- #

def test_e4_sante_reflete_la_capacite_reelle_de_la_voix():
    """Défaut C04 : /api/health annonçait « voice: running: true » sur une voix morte.

    L'indicateur doit décrire ce qu'Atlas sait faire — modèle d'éveil chargé, cuBLAS
    disponible, synthèse opérationnelle — et non la simple existence du composant.
    """
    from api.routes import api_health

    data = asyncio.run(api_health())
    voice = data["services"]["voice"]
    for cle in ("wake_word", "stt", "tts", "ok"):
        assert cle in voice, (
            f"/api/health ne dit rien de '{cle}' : il annonce seulement {sorted(voice)}"
        )
    # Ici le moteur vocal n'a pas démarré : la capacité ne peut pas être annoncée acquise.
    assert voice["wake_word"]["loaded"] is False
    assert voice["ok"] is False, "capacité annoncée alors que le mot d'éveil n'est pas chargé"
    assert isinstance(voice.get("degraded_reason"), list) and voice["degraded_reason"], (
        "aucune raison donnée alors que la voix n'est pas opérationnelle"
    )


# --------------------------------------------------------------------------- #
#  E3 — la synthèse vocale, sans mock de _speak_sync
# --------------------------------------------------------------------------- #

@pytest.fixture
def capture_audio(monkeypatch):
    """Capture ce qui serait joué, pour que la suite de tests reste silencieuse."""
    import sounddevice as sd

    played = []
    monkeypatch.setattr(sd, "play", lambda samples, sr, *a, **k: played.append((np.asarray(samples), sr)))
    monkeypatch.setattr(sd, "wait", lambda *a, **k: None)
    return played


@needs_voice_model
def test_e3_piper_produit_du_son(engine, capture_audio):
    """La vraie synthèse Piper doit produire un tableau audio de durée plausible.

    Défaut L3 : piper-tts ≥ 1.3 renvoie un générateur d'AudioChunk ; le code attend un
    tuple, l'exception est avalée, et rien n'est joué.
    """
    engine._speak_sync("Bonjour Alexis, je suis Atlas.")
    assert capture_audio, "aucun son produit : la synthèse a échoué en silence"
    samples, sr = capture_audio[0]
    assert samples.size > 0
    duree = samples.size / sr
    assert 0.5 < duree < 15, f"durée invraisemblable : {duree:.2f} s"


def test_e3_echec_de_synthese_journalise(engine, capture_audio, monkeypatch, caplog):
    """Un échec de synthèse doit se voir dans les journaux, jamais être avalé."""
    import piper.voice as piper_voice

    def boom(*args, **kwargs):
        raise RuntimeError("panne simulée de Piper")

    monkeypatch.setattr(piper_voice.PiperVoice, "load", staticmethod(boom))
    with caplog.at_level("WARNING", logger="atlas.voice"):
        engine._speak_sync("test")
    messages = " ".join(r.message for r in caplog.records)
    assert "Piper" in messages or "piper" in messages, f"échec non journalisé : {caplog.records}"


def test_e3_repli_sapi_quand_piper_echoue(engine, capture_audio, monkeypatch, caplog):
    """Piper en panne : la voix de Windows prend le relais, et ça se voit."""
    import piper.voice as piper_voice

    monkeypatch.setattr(piper_voice.PiperVoice, "load",
                        staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("panne"))))
    with caplog.at_level("WARNING", logger="atlas.voice"):
        spoken = engine._speak_sync("Bonjour")
    messages = " ".join(r.message for r in caplog.records).lower()
    assert "sapi" in messages, f"repli SAPI non annoncé dans les journaux : {messages[:200]}"
    assert spoken is not False, "aucune voix de repli n'a parlé"
