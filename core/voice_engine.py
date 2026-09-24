"""Voice engine for Atlas v4.0 (Wake word -> STT -> Intent -> TTS)."""

import asyncio
import json
import logging
import pathlib
import re
import tempfile
import time
from typing import Optional

import numpy as np

logger = logging.getLogger("atlas.voice")


def ensure_cuda_libraries() -> tuple[bool, str]:
    """Rend cuBLAS et cuDNN chargeables par CTranslate2. Retourne (disponible, détail).

    E2 / L2 : la transcription GPU échouait sur « cublas64_12.dll is not found ». Les DLL
    viennent des paquets pip `nvidia-cublas-cu12` et `nvidia-cudnn-cu12` — décision du
    superviseur, pour ne pas imposer le CUDA Toolkit complet. CTranslate2 les charge par le
    chemin de recherche du processus : `os.add_dll_directory` ne suffit pas, il faut aussi
    les déclarer dans PATH, avant le premier chargement du modèle.
    """
    import os

    try:
        import nvidia
    except Exception as e:
        return False, f"paquets pip nvidia-* absents ({e})"

    dirs = []
    for base in getattr(nvidia, "__path__", []):
        for sub in pathlib.Path(base).glob("*/bin"):
            if sub.is_dir() and any(sub.glob("*.dll")):
                dirs.append(str(sub))
    if not dirs:
        return False, "aucun répertoire de DLL nvidia trouvé"

    current = os.environ.get("PATH", "")
    missing = [d for d in dirs if d not in current]
    if missing:
        os.environ["PATH"] = os.pathsep.join(missing) + os.pathsep + current
    for d in dirs:
        try:
            os.add_dll_directory(d)
        except Exception:
            pass
    cublas = any(pathlib.Path(d).joinpath("cublas64_12.dll").exists() for d in dirs)
    return cublas, ("cuBLAS et cuDNN déclarés : " + ", ".join(dirs)) if cublas \
        else "cublas64_12.dll introuvable dans les paquets nvidia"


def _load_voice_config() -> dict:
    cfg_path = pathlib.Path(__file__).resolve().parent.parent / "config" / "settings.json"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("voice", {})


class VoiceEngine:
    """
    Voice pipeline: wake word -> STT -> intent pipeline -> TTS.

    Runs in a dedicated listener task and never blocks text endpoints.
    """

    def __init__(self, systray=None):
        self._config = _load_voice_config()
        self.enabled = bool(self._config.get("enabled", False))

        self._systray = systray
        self._running = False
        self._listener_task: Optional[asyncio.Task] = None

        self._wake_model = None
        self._wake_stream = None
        self._wake_queue: asyncio.Queue[np.ndarray] = asyncio.Queue()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._wake_threshold = float(self._config.get("wake_word_threshold", 0.5))
        self._wake_word_model = str(self._config.get("wake_word_model", "hey_mycroft"))
        self._wake_score_key = self._wake_word_model
        self._wake_sample_rate = 16000
        self._wake_frame_length = 1280
        self._last_wake_ts = 0.0

        self._whisper_model = None
        self._piper_voice = None
        self._tts_backend = None       # piper | sapi | aucun — dernier moyen ayant parlé
        self._last_wake_score = 0.0
        self._activity = "repos"       # repos | écoute | réfléchit | parle (indicateur visuel)
        self._stt_device_used = None   # cuda | cpu — ce qui a réellement servi
        self._stt_error = None
        self._cublas_available = None

    async def start(self):
        """Start wake-word listener when voice is enabled."""
        if self._running:
            return
        if not self.enabled:
            logger.info("VoiceEngine disabled by config.")
            return

        self._loop = asyncio.get_running_loop()
        await self._init_wake_word()

        self._running = True
        self._listener_task = asyncio.create_task(self._listen_loop())
        # E2 : le premier appel au modèle de transcription coûte une dizaine de secondes
        # (chargement, noyaux CUDA, détecteur de voix). On le paie au démarrage, en tâche
        # de fond, pour que la première commande de l'utilisateur soit rapide.
        asyncio.create_task(self._prewarm_stt())
        self._set_activity("idle")
        logger.info("VoiceEngine started.")

    async def stop(self):
        """Stop listener and release resources."""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        try:
            if self._wake_stream is not None:
                self._wake_stream.stop()
                self._wake_stream.close()
        except Exception:
            pass
        self._wake_stream = None

        self._wake_model = None

        self._set_activity("idle")
        logger.info("VoiceEngine stopped.")

    # Sprint E — demande d'Alexis : savoir quand Atlas écoute, dans la fenêtre comme dans
    # la zone de notification. Une seule source d'état pour les deux.
    _ACTIVITY_LABELS = {"idle": "repos", "listening": "écoute",
                        "processing": "réfléchit", "speaking": "parle"}

    def _set_activity(self, state: str) -> None:
        self._activity = self._ACTIVITY_LABELS.get(state, state)
        if self._systray:
            try:
                self._systray.set_state(state)
            except Exception as e:
                logger.debug("Systray indisponible : %s", e)

    @property
    def activity(self) -> str:
        return self._activity

    def _resolve_wake_word_model(self) -> tuple[str, bool]:
        """
        Resolve the configured wake_word_model into a reference usable by openwakeword.

        Returns (model_ref, is_custom_path):
        - is_custom_path=True: model_ref is an absolute filesystem path to a local
          .onnx/.tflite file (e.g. the custom "Hey Atlas" model), resolved relative
          to the project root when given as a relative path.
        - is_custom_path=False: model_ref is a bare openwakeword built-in keyword
          (e.g. "hey_mycroft"), downloadable on demand via openwakeword.utils.
        """
        value = self._wake_word_model
        looks_like_path = ("/" in value) or ("\\" in value) or value.endswith((".onnx", ".tflite"))
        if not looks_like_path:
            return value, False

        path = pathlib.Path(value)
        if not path.is_absolute():
            path = pathlib.Path(__file__).resolve().parent.parent / path
        return str(path), True

    async def _init_wake_word(self):
        """Initialize OpenWakeWord and audio input stream for wake detection."""
        try:
            import sounddevice as sd
            try:
                from openwakeword.model import Model
            except Exception:
                from openwakeword import Model
            try:
                from openwakeword import utils as oww_utils
            except Exception:
                oww_utils = None
        except Exception as e:
            raise RuntimeError(f"Voice dependencies missing (openwakeword/sounddevice): {e}")

        model_ref, is_custom_path = self._resolve_wake_word_model()

        if is_custom_path:
            if not pathlib.Path(model_ref).exists():
                raise RuntimeError(
                    f"Modele wake word custom introuvable: {model_ref}. "
                    "Lancer 'python scripts/download_voice_models.py' pour le telecharger avant le premier demarrage."
                )
            try:
                self._wake_model = Model(wakeword_models=[model_ref], inference_framework="onnx")
            except TypeError:
                self._wake_model = Model(wakeword_models=[model_ref])
            self._wake_score_key = pathlib.Path(model_ref).stem
        else:
            # openwakeword built-in keywords are fully local and keyless.
            model_loaded = False
            model_error = None
            for attempt in range(2):
                try:
                    try:
                        self._wake_model = Model(wakeword_models=[model_ref], inference_framework="onnx")
                    except TypeError:
                        self._wake_model = Model(wakeword_models=[model_ref])
                    model_loaded = True
                    break
                except Exception as e:
                    model_error = e
                    err_msg = str(e)
                    # First retry only: try to auto-download model assets when files are missing.
                    if attempt == 0 and oww_utils is not None and ("NO_SUCHFILE" in err_msg or "File doesn't exist" in err_msg):
                        try:
                            logger.info("OpenWakeWord model missing, downloading assets for '%s'...", model_ref)
                            m = re.match(r"^(?P<base>.+)_v\d+(?:\.\d+)?$", model_ref)
                            model_name = model_ref if m else f"{model_ref}_v0.1"
                            oww_utils.download_models(model_names=[model_name])
                            logger.info("OpenWakeWord model assets downloaded for '%s'.", model_ref)
                            continue
                        except Exception as download_error:
                            model_error = download_error
                    break

            if not model_loaded:
                raise RuntimeError(f"OpenWakeWord initialization failed: {model_error}")
            self._wake_score_key = model_ref

        self._wake_sample_rate = int(getattr(self._wake_model, "sample_rate", 16000))
        self._wake_frame_length = int(getattr(self._wake_model, "audio_window_size", 1280))

        def _wake_callback(indata, frames, _time_info, status):
            if status:
                return
            try:
                if self._loop and self._running:
                    # E1 / L1 : openWakeWord attend du PCM int16 brut. Diviser par 32768
                    # écrasait l'amplitude et le score tombait à 0,0008 au lieu de 0,995 —
                    # le mot d'éveil ne pouvait structurellement pas se déclencher.
                    pcm = np.array(indata, dtype=np.int16).reshape(-1)
                    self._loop.call_soon_threadsafe(self._wake_queue.put_nowait, pcm)
            except Exception as e:
                logger.debug("Wake callback error: %s", e)

        self._wake_stream = sd.InputStream(
            samplerate=self._wake_sample_rate,
            blocksize=self._wake_frame_length,
            channels=1,
            dtype="int16",
            callback=_wake_callback,
        )
        self._wake_stream.start()

    def _wake_score(self, audio_int16: np.ndarray) -> float:
        """Score du modèle de mot d'éveil pour une trame (PCM int16)."""
        if self._wake_model is None:
            return 0.0
        scores = self._wake_model.predict(np.asarray(audio_int16, dtype=np.int16))
        if isinstance(scores, dict):
            if self._wake_score_key in scores:
                score = float(scores[self._wake_score_key])
            else:
                score = float(max(scores.values())) if scores else 0.0
        elif isinstance(scores, (list, tuple, np.ndarray)):
            score = float(np.max(scores)) if len(scores) else 0.0
        else:
            score = float(scores or 0.0)
        return score

    def _wake_detected(self, audio_int16: np.ndarray) -> bool:
        """Return True when wake word score crosses threshold."""
        if self._wake_model is None:
            return False

        score = self._wake_score(audio_int16)
        self._last_wake_score = score

        now = time.monotonic()
        if score >= self._wake_threshold and (now - self._last_wake_ts) > 1.5:
            self._last_wake_ts = now
            return True
        return False

    async def _listen_loop(self):
        """Continuously process wake-word frames from audio callback."""
        self._set_activity("idle")

        while self._running:
            try:
                frame_audio = await asyncio.wait_for(self._wake_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            if self._wake_model is None:
                continue

            if frame_audio.size < self._wake_frame_length:
                continue

            try:
                if self._wake_detected(frame_audio[: self._wake_frame_length]):
                    await self._on_wake_word()
            except Exception as e:
                logger.debug("Wake processing error: %s", e)

    async def _on_wake_word(self):
        """Wake-word callback pipeline."""
        self._set_activity("listening")

        # E7 : sans ces traces, impossible de mesurer quoi que ce soit après une séance au
        # micro — ni le nombre de déclenchements, ni la latence, ni ce qu'Atlas a compris.
        t_wake = time.monotonic()
        logger.info("[VOIX] Mot d'éveil détecté (score=%.3f, seuil=%.2f) — j'écoute.",
                    self._last_wake_score, self._wake_threshold)
        try:
            audio = await self._record_audio()
            t_record = time.monotonic()
            text = await self._transcribe(audio)
            t_stt = time.monotonic()
            logger.info("[VOIX] Transcription (%.2fs, %s) : %r",
                        t_stt - t_record, self._stt_device_used, text)

            if not text.strip():
                await self._speak("Je n'ai rien entendu.")
                logger.info("[VOIX] Cycle terminé sans transcription — total %.1fs",
                            time.monotonic() - t_wake)
                return

            self._set_activity("processing")

            response_text = await self._run_text_pipeline(text)
            t_think = time.monotonic()
            self._set_activity("speaking")
            await self._speak(response_text)
            t_speak = time.monotonic()
            logger.info(
                "[VOIX] Cycle : écoute %.1fs + transcription %.2fs + réflexion %.1fs + "
                "parole %.1fs = %.1fs depuis le mot d'éveil (moteur=%s) — réponse : %r",
                t_record - t_wake, t_stt - t_record, t_think - t_stt, t_speak - t_think,
                t_speak - t_wake, self._tts_backend, response_text[:120],
            )
        except Exception as e:
            logger.error("Voice pipeline error: %s", e, exc_info=True)
            if self._systray:
                self._systray.set_state("error")
            try:
                await self._speak("J'ai rencontre une erreur sur la commande vocale.")
            except Exception:
                pass
        finally:
            self._set_activity("idle")

    async def _record_audio(self) -> bytes:
        """Record mic input until silence or max duration, returns PCM16 bytes."""
        return await asyncio.to_thread(self._record_audio_sync)

    def _record_audio_sync(self) -> bytes:
        import sounddevice as sd

        sample_rate = 16000
        max_secs = int(self._config.get("max_recording_seconds", 10))
        silence_secs = float(self._config.get("silence_threshold_seconds", 1.5))

        chunk_samples = int(sample_rate * 0.1)
        max_chunks = int(max_secs / 0.1)
        silence_chunks_required = int(max(1.0, silence_secs / 0.1))

        chunks = []
        silent_chunks = 0
        speech_seen = False

        with sd.InputStream(samplerate=sample_rate, channels=1, dtype="int16", blocksize=chunk_samples) as stream:
            for _ in range(max_chunks):
                data, _ = stream.read(chunk_samples)
                chunk = np.array(data, dtype=np.int16).reshape(-1)
                chunks.append(chunk)

                level = float(np.abs(chunk).mean())
                if level > 500.0:
                    speech_seen = True
                    silent_chunks = 0
                else:
                    if speech_seen:
                        silent_chunks += 1
                        if silent_chunks >= silence_chunks_required:
                            break

        if not chunks:
            return b""
        audio = np.concatenate(chunks).astype(np.int16)
        return audio.tobytes()

    async def _transcribe(self, audio: bytes) -> str:
        """Transcribe recorded audio using faster-whisper int8."""
        if not audio:
            return ""

        try:
            from faster_whisper import WhisperModel
        except Exception as e:
            raise RuntimeError(f"faster-whisper unavailable: {e}")

        if self._whisper_model is None:
            model_name = self._config.get("stt_model", "base")
            device = self._config.get("stt_device", "cuda")
            if device == "cuda":
                ok, detail = ensure_cuda_libraries()
                self._cublas_available = ok
                if not ok:
                    logger.warning("[VOIX] CUDA indisponible (%s)", detail)
                else:
                    logger.info("[VOIX] %s", detail)
            try:
                self._whisper_model = WhisperModel(model_name, device=device, compute_type="int8")
                self._stt_device_used = device
                self._stt_error = None
            except Exception as e:
                # E2 : le repli processeur est acceptable, le repli SILENCIEUX ne l'est pas.
                # Sur cette chaîne, le processeur coûte ~5 s par phrase contre 0,1 s sur GPU.
                self._stt_error = f"{type(e).__name__}: {e}"
                logger.error("[VOIX] Transcription sur '%s' impossible (%s) — repli processeur, "
                             "la réponse sera nettement plus lente.", device, self._stt_error)
                self._whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8")
                self._stt_device_used = "cpu"

        audio_np = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        language = self._config.get("stt_language", "fr")

        segments, _ = self._whisper_model.transcribe(audio_np, language=language, vad_filter=True)
        text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
        return text.strip()

    async def _speak(self, text: str):
        """Speak response with Piper TTS."""
        if not text:
            return
        await asyncio.to_thread(self._speak_sync, text)

    def _speak_sync(self, text: str) -> bool:
        """Dit le texte à voix haute. Retourne True si une voix a parlé.

        E3 / L3 : trois défauts corrigés ici.
        - piper-tts >= 1.3 renvoie un itérable d'AudioChunk ; le code attendait un tuple.
        - L'exception était avalée par un `except Exception: pass`, donc personne ne savait
          que la voix était muette.
        - Le repli décidé au sprint 0 (voix Windows SAPI) n'avait jamais été implémenté.
        """
        if not text:
            return False
        if self._speak_piper(text):
            return True
        logger.warning("[VOIX] Piper indisponible — repli sur la voix Windows (SAPI).")
        if self._speak_sapi(text):
            self._tts_backend = "sapi"
            return True
        logger.error("[VOIX] Aucune synthèse disponible : ni Piper, ni SAPI. Atlas reste muet.")
        self._tts_backend = "aucun"
        return False

    def _speak_piper(self, text: str) -> bool:
        """Synthèse Piper. Journalise tout échec au lieu de l'avaler."""
        import sounddevice as sd

        model_name = self._config.get("tts_voice", "fr_FR-siwis-medium")
        model_path = (pathlib.Path(__file__).resolve().parent.parent
                      / "data" / "voices" / f"{model_name}.onnx")
        if not model_path.exists():
            logger.warning("[VOIX] Modèle Piper introuvable : %s", model_path)
            return False
        try:
            from piper.voice import PiperVoice

            if self._piper_voice is None:
                self._piper_voice = PiperVoice.load(str(model_path))
            voice = self._piper_voice
            chunks = list(voice.synthesize(text))
            if not chunks:
                logger.warning("[VOIX] Piper n'a produit aucun échantillon pour : %s", text[:60])
                return False
            samples = np.concatenate([np.asarray(c.audio_int16_array, dtype=np.int16)
                                      for c in chunks])
            sample_rate = getattr(chunks[0], "sample_rate", None) or voice.config.sample_rate
            if samples.size == 0:
                logger.warning("[VOIX] Piper a produit un flux vide.")
                return False
            sd.play(samples, sample_rate)
            sd.wait()
            self._tts_backend = "piper"
            return True
        except Exception as e:
            self._piper_voice = None
            logger.warning("[VOIX] Échec de la synthèse Piper (%s) : %s", type(e).__name__, e)
            return False

    def _speak_sapi(self, text: str) -> bool:
        """Repli sur la voix intégrée de Windows. Aucun modèle, aucune VRAM."""
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
            engine.stop()
            logger.info("[VOIX] Phrase dite par la voix Windows (SAPI) : %s", text[:60])
            return True
        except Exception as e:
            logger.error("[VOIX] Repli SAPI indisponible (%s) : %s", type(e).__name__, e)
            return False

    async def _prewarm_stt(self) -> None:
        """Charge le modèle de transcription et déclenche ses initialisations coûteuses."""
        try:
            silence = np.zeros(int(0.5 * 16000), dtype=np.int16).tobytes()
            start = time.monotonic()
            await self._transcribe(silence)
            logger.info("[VOIX] Transcription préchauffée en %.1fs (device=%s)",
                        time.monotonic() - start, self._stt_device_used)
        except Exception as e:
            logger.warning("[VOIX] Préchauffage de la transcription impossible : %s", e)

    def _announce_on_screen(self, titre: str, message: str) -> None:
        """Rend visible à l'écran ce que la voix ne peut pas résoudre (E5)."""
        if self._systray:
            try:
                self._systray.set_state("error")
            except Exception as e:
                logger.debug("Systray indisponible : %s", e)
        try:
            from tools.notifier import notify

            resultat = notify(message, title=f"Atlas — {titre}")
            if asyncio.iscoroutine(resultat):
                asyncio.ensure_future(resultat)
        except Exception as e:
            logger.error("[VOIX] Impossible d'afficher '%s' à l'écran : %s", titre, e)

    def stt_status(self) -> dict:
        """État réel de la transcription, pour /api/health (E4)."""
        if self._cublas_available is None:
            available, detail = ensure_cuda_libraries()
        else:
            available, detail = self._cublas_available, None
        return {
            "device_configured": self._config.get("stt_device", "cuda"),
            "device_used": self._stt_device_used,     # None tant qu'aucune transcription
            "cublas_available": bool(available),
            "cuda_error": self._stt_error,
            "model": self._config.get("stt_model", "base"),
            "ok": bool(available) or self._stt_device_used == "cpu",
            "detail": detail,
        }

    def wake_status(self) -> dict:
        """État réel du mot d'éveil, pour /api/health (E4)."""
        model_ref, is_path = self._resolve_wake_word_model()
        present = pathlib.Path(model_ref).exists() if is_path else True
        return {
            "model": model_ref,
            "model_present": present,
            "loaded": self._wake_model is not None,
            "threshold": self._wake_threshold,
            "last_score": round(float(self._last_wake_score), 4),
            "ok": present and self._wake_model is not None,
        }

    def tts_status(self) -> dict:
        """État réel de la synthèse, pour /api/health (E4)."""
        model_name = self._config.get("tts_voice", "fr_FR-siwis-medium")
        model_path = (pathlib.Path(__file__).resolve().parent.parent
                      / "data" / "voices" / f"{model_name}.onnx")
        try:
            import piper  # noqa: F401
            piper_ok = model_path.exists()
        except Exception:
            piper_ok = False
        try:
            import pyttsx3  # noqa: F401
            sapi_ok = True
        except Exception:
            sapi_ok = False
        return {
            "piper_ready": piper_ok,
            "piper_model": str(model_path) if piper_ok else None,
            "sapi_fallback_available": sapi_ok,
            "backend_last_used": self._tts_backend,
            "ok": piper_ok or sapi_ok,
        }

    async def _run_text_pipeline(self, text: str) -> str:
        """Run existing text pipeline and return short spoken response."""
        from core.context_monitor import collect_context
        from core.intent_classifier import get_classifier
        from core.memory_manager import get_memory_manager
        from core.ollama_client import generate_speech_response
        from core.planner import get_planner
        from core.validator import get_validator
        from core.intent_engine import get_execution_engine
        from core.world_state import get_world_state

        context = collect_context()
        context["user_input"] = text

        mem = get_memory_manager()
        memories = mem.recall_texts(text, top_k=5)
        mem.add_to_session("user", text)

        ws = get_world_state()
        ws.update_from_context(context)
        ws.add_to_history("user", text)

        classifier = get_classifier()
        validator = get_validator()
        engine = get_execution_engine()

        intent = classifier.classify(text, context)

        if intent.category == "conversation" or intent.confidence < 0.5:
            resp = await generate_speech_response(text, context, memories=memories)
            mem.add_to_session("assistant", resp)
            ws.add_to_history("assistant", resp)
            return resp

        if intent.is_complex:
            planner = get_planner()
            plan = await planner.plan(intent, context)
            results = await engine.execute_plan(plan, context)
        else:
            resolved = validator.resolve(intent, context)
            result = await engine.execute(resolved, context)
            results = [{"tool": resolved.tool, "params": resolved.params, **result}]

        summaries = []
        for item in results:
            statut = item.get("status")
            # E5 : une action qui exige une confirmation ne peut pas être confirmée à la
            # voix aujourd'hui. Le pire serait de répondre « C'est fait » : c'est ce que
            # faisait ce code, faute de message à résumer.
            if statut == "confirmation_required":
                raison = item.get("reason") or item.get("message") or ""
                logger.warning("[VOIX] Confirmation impossible à la voix : %s", raison)
                self._announce_on_screen(
                    "Confirmation requise",
                    f"{raison} Réponds à l'écran pour valider ou annuler.".strip(),
                )
                summaries.append(
                    "Cette action nécessite une confirmation à l'écran. "
                    "Je ne l'ai pas exécutée."
                )
                continue
            if statut == "blocked":
                summaries.append(item.get("message") or "Action refusée.")
                continue
            res = item.get("result", {})
            if isinstance(res, dict):
                msg = res.get("message", "")
            else:
                msg = str(res)[:200]
            if not msg and statut == "error":
                msg = item.get("message") or "L'action a échoué."
            if msg:
                summaries.append(msg)

        response = " ; ".join(summaries) if summaries else "C'est fait."
        mem.add_to_session("assistant", response)
        ws.add_to_history("assistant", response)
        return response


_voice_engine: VoiceEngine | None = None


def get_voice_engine(systray=None) -> VoiceEngine:
    global _voice_engine
    if _voice_engine is None:
        _voice_engine = VoiceEngine(systray=systray)
    return _voice_engine
