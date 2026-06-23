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
        self._wake_sample_rate = 16000
        self._wake_frame_length = 1280
        self._last_wake_ts = 0.0

        self._whisper_model = None

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
        if self._systray:
            self._systray.set_state("idle")
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

        if self._systray:
            self._systray.set_state("idle")
        logger.info("VoiceEngine stopped.")

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

        # openwakeword is fully local and keyless.
        model_loaded = False
        model_error = None
        for attempt in range(2):
            try:
                try:
                    self._wake_model = Model(wakeword_models=[self._wake_word_model], inference_framework="onnx")
                except TypeError:
                    self._wake_model = Model(wakeword_models=[self._wake_word_model])
                model_loaded = True
                break
            except Exception as e:
                model_error = e
                err_msg = str(e)
                # First retry only: try to auto-download model assets when files are missing.
                if attempt == 0 and oww_utils is not None and ("NO_SUCHFILE" in err_msg or "File doesn't exist" in err_msg):
                    try:
                        logger.info("OpenWakeWord model missing, downloading assets for '%s'...", self._wake_word_model)
                        m = re.match(r"^(?P<base>.+)_v\d+(?:\.\d+)?$", self._wake_word_model)
                        model_name = self._wake_word_model if m else f"{self._wake_word_model}_v0.1"
                        oww_utils.download_models(model_names=[model_name])
                        logger.info("OpenWakeWord model assets downloaded for '%s'.", self._wake_word_model)
                        continue
                    except Exception as download_error:
                        model_error = download_error
                break

        if not model_loaded:
            raise RuntimeError(f"OpenWakeWord initialization failed: {model_error}")

        self._wake_sample_rate = int(getattr(self._wake_model, "sample_rate", 16000))
        self._wake_frame_length = int(getattr(self._wake_model, "audio_window_size", 1280))

        def _wake_callback(indata, frames, _time_info, status):
            if status:
                return
            try:
                if self._loop and self._running:
                    pcm = np.array(indata, dtype=np.int16).reshape(-1)
                    audio_f32 = pcm.astype(np.float32) / 32768.0
                    self._loop.call_soon_threadsafe(self._wake_queue.put_nowait, audio_f32)
            except Exception:
                pass

        self._wake_stream = sd.InputStream(
            samplerate=self._wake_sample_rate,
            blocksize=self._wake_frame_length,
            channels=1,
            dtype="int16",
            callback=_wake_callback,
        )
        self._wake_stream.start()

    def _wake_detected(self, audio_f32: np.ndarray) -> bool:
        """Return True when wake word score crosses threshold."""
        if self._wake_model is None:
            return False

        scores = self._wake_model.predict(audio_f32)
        if isinstance(scores, dict):
            if self._wake_word_model in scores:
                score = float(scores[self._wake_word_model])
            else:
                score = float(max(scores.values())) if scores else 0.0
        elif isinstance(scores, (list, tuple, np.ndarray)):
            score = float(np.max(scores)) if len(scores) else 0.0
        else:
            score = float(scores or 0.0)

        now = time.monotonic()
        if score >= self._wake_threshold and (now - self._last_wake_ts) > 1.5:
            self._last_wake_ts = now
            return True
        return False

    async def _listen_loop(self):
        """Continuously process wake-word frames from audio callback."""
        if self._systray:
            self._systray.set_state("idle")

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
        if self._systray:
            self._systray.set_state("listening")

        try:
            audio = await self._record_audio()
            text = await self._transcribe(audio)

            if not text.strip():
                await self._speak("Je n'ai rien entendu.")
                return

            if self._systray:
                self._systray.set_state("processing")

            response_text = await self._run_text_pipeline(text)
            await self._speak(response_text)
        except Exception as e:
            logger.error("Voice pipeline error: %s", e, exc_info=True)
            if self._systray:
                self._systray.set_state("error")
            try:
                await self._speak("J'ai rencontre une erreur sur la commande vocale.")
            except Exception:
                pass
        finally:
            if self._systray:
                self._systray.set_state("idle")

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
            self._whisper_model = WhisperModel(model_name, device=device, compute_type="int8")

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

    def _speak_sync(self, text: str):
        import sounddevice as sd

        # Prefer piper-tts python API if available.
        try:
            from piper.voice import PiperVoice

            model_name = self._config.get("tts_voice", "fr_FR-upmc-medium")
            model_path = pathlib.Path(__file__).resolve().parent.parent / "data" / "voices" / f"{model_name}.onnx"
            if not model_path.exists():
                logger.warning("Piper model not found: %s", model_path)
                return

            voice = PiperVoice.load(str(model_path))
            audio = voice.synthesize(text)
            if isinstance(audio, tuple):
                samples, sample_rate = audio
            else:
                samples, sample_rate = audio, 22050
            sd.play(samples, sample_rate)
            sd.wait()
            return
        except Exception:
            pass

        # Fallback to piper executable if available locally.
        try:
            import subprocess

            model_name = self._config.get("tts_voice", "fr_FR-upmc-medium")
            model_path = pathlib.Path(__file__).resolve().parent.parent / "data" / "voices" / f"{model_name}.onnx"
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as out_wav:
                out_path = out_wav.name

            cmd = [
                "piper",
                "--model",
                str(model_path),
                "--output_file",
                out_path,
            ]
            subprocess.run(cmd, input=text, text=True, capture_output=True, check=False)

            # Play generated wav if present.
            if pathlib.Path(out_path).exists():
                import wave

                with wave.open(out_path, "rb") as wf:
                    frames = wf.readframes(wf.getnframes())
                    sr = wf.getframerate()
                    channels = wf.getnchannels()
                arr = np.frombuffer(frames, dtype=np.int16)
                if channels > 1:
                    arr = arr.reshape(-1, channels)
                sd.play(arr, sr)
                sd.wait()
            pathlib.Path(out_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("TTS unavailable: %s", e)

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
            res = item.get("result", {})
            if isinstance(res, dict):
                msg = res.get("message", "")
            else:
                msg = str(res)[:200]
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
