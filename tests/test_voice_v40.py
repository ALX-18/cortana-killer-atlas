"""v4.0 Voice & Presence tests."""

import asyncio
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def reset_voice_singleton():
    import core.voice_engine as ve_mod

    ve_mod._voice_engine = None
    yield
    ve_mod._voice_engine = None


def _voice_cfg(enabled=True):
    return {
        "enabled": enabled,
        "wake_word_model": "hey_mycroft",
        "wake_word_threshold": 0.5,
        "stt_model": "base",
        "stt_language": "fr",
        "stt_device": "cuda",
        "tts_voice": "fr_FR-upmc-medium",
        "max_recording_seconds": 10,
        "silence_threshold_seconds": 1.5,
    }


@pytest.mark.asyncio
async def test_01_voice_engine_instantiates_disabled(monkeypatch):
    from core import voice_engine as ve

    monkeypatch.setattr(ve, "_load_voice_config", lambda: _voice_cfg(enabled=False))
    engine = ve.VoiceEngine()
    assert engine is not None
    assert engine.enabled is False


@pytest.mark.asyncio
async def test_02_voice_engine_start_starts_listener(monkeypatch):
    from core import voice_engine as ve

    monkeypatch.setattr(ve, "_load_voice_config", lambda: _voice_cfg(enabled=True))

    async def fake_init(self):
        self._wake_model = SimpleNamespace()
        self._wake_sample_rate = 16000
        self._wake_frame_length = 512
        self._wake_stream = SimpleNamespace(stop=lambda: None, close=lambda: None)

    async def fake_listen(self):
        while self._running:
            await asyncio.sleep(0.05)

    monkeypatch.setattr(ve.VoiceEngine, "_init_wake_word", fake_init)
    monkeypatch.setattr(ve.VoiceEngine, "_listen_loop", fake_listen)

    engine = ve.VoiceEngine()
    await engine.start()
    assert engine._running is True
    assert engine._listener_task is not None
    await engine.stop()


@pytest.mark.asyncio
async def test_03_voice_engine_stop_clean(monkeypatch):
    from core import voice_engine as ve

    monkeypatch.setattr(ve, "_load_voice_config", lambda: _voice_cfg(enabled=True))

    async def fake_init(self):
        self._wake_model = SimpleNamespace()
        self._wake_stream = SimpleNamespace(stop=lambda: None, close=lambda: None)

    async def fake_listen(self):
        while self._running:
            await asyncio.sleep(0.05)

    monkeypatch.setattr(ve.VoiceEngine, "_init_wake_word", fake_init)
    monkeypatch.setattr(ve.VoiceEngine, "_listen_loop", fake_listen)

    engine = ve.VoiceEngine()
    await engine.start()
    await engine.stop()
    assert engine._running is False


@pytest.mark.asyncio
async def test_04_transcribe_returns_string(monkeypatch):
    from core import voice_engine as ve

    monkeypatch.setattr(ve, "_load_voice_config", lambda: _voice_cfg(enabled=True))

    class FakeSegment:
        def __init__(self, text):
            self.text = text

    class FakeWhisperModel:
        def __init__(self, *_args, **_kwargs):
            pass

        def transcribe(self, _audio_np, **_kwargs):
            return [FakeSegment("bonjour atlas")], None

    fake_fw = SimpleNamespace(WhisperModel=FakeWhisperModel)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_fw)

    engine = ve.VoiceEngine()
    text = await engine._transcribe((b"\x00\x01") * 1600)
    assert isinstance(text, str)
    assert text.strip() != ""


@pytest.mark.asyncio
async def test_05_speak_executes_without_error(monkeypatch):
    from core import voice_engine as ve

    monkeypatch.setattr(ve, "_load_voice_config", lambda: _voice_cfg(enabled=True))

    engine = ve.VoiceEngine()
    called = {"ok": False}

    def fake_speak_sync(self, text):
        assert text
        called["ok"] = True

    monkeypatch.setattr(ve.VoiceEngine, "_speak_sync", fake_speak_sync)
    await engine._speak("Salut")
    assert called["ok"] is True


@pytest.mark.asyncio
async def test_06_full_pipeline_mock(monkeypatch):
    from core import voice_engine as ve

    monkeypatch.setattr(ve, "_load_voice_config", lambda: _voice_cfg(enabled=True))

    class FakeSystray:
        def __init__(self):
            self.states = []

        def set_state(self, state):
            self.states.append(state)

    systray = FakeSystray()
    engine = ve.VoiceEngine(systray=systray)

    async def fake_record(self):
        return b"audio"

    async def fake_transcribe(self, _audio):
        return "ouvre vscode"

    async def fake_pipeline(self, _text):
        return "c est fait"

    spoken = {"text": ""}

    async def fake_speak(self, text):
        spoken["text"] = text

    monkeypatch.setattr(ve.VoiceEngine, "_record_audio", fake_record)
    monkeypatch.setattr(ve.VoiceEngine, "_transcribe", fake_transcribe)
    monkeypatch.setattr(ve.VoiceEngine, "_run_text_pipeline", fake_pipeline)
    monkeypatch.setattr(ve.VoiceEngine, "_speak", fake_speak)

    await engine._on_wake_word()
    assert spoken["text"] == "c est fait"
    assert "listening" in systray.states
    assert "processing" in systray.states


def test_07_systray_instantiates():
    from tools.systray import AtlasSystray

    tray = AtlasSystray()
    assert tray is not None


def test_08_systray_set_state():
    from tools.systray import AtlasSystray

    tray = AtlasSystray()
    tray.set_state("idle")
    assert tray._state == "idle"
    tray.set_state("listening")
    assert tray._state == "listening"
    tray.set_state("processing")
    assert tray._state == "processing"
    tray.set_state("error")
    assert tray._state == "error"


@pytest.mark.asyncio
async def test_09_voice_disabled_no_text_pipeline_impact(monkeypatch):
    from core import voice_engine as ve

    monkeypatch.setattr(ve, "_load_voice_config", lambda: _voice_cfg(enabled=False))

    async def should_not_be_called(_self):
        raise AssertionError("_init_wake_word should not run when voice is disabled")

    monkeypatch.setattr(ve.VoiceEngine, "_init_wake_word", should_not_be_called)

    engine = ve.VoiceEngine()
    await engine.start()
    assert engine._running is False
    assert engine._listener_task is None


def test_10_gpu_absent_warning_no_crash(monkeypatch, caplog):
    import main

    class FakeCuda:
        @staticmethod
        def is_available():
            return False

    fake_torch = SimpleNamespace(cuda=FakeCuda())
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    caplog.clear()
    main._warn_if_voice_gpu_missing(True)
    assert "aucun GPU CUDA detecte" in caplog.text


@pytest.mark.asyncio
async def test_11_voice_response_has_no_markdown(monkeypatch):
    from core import ollama_client as oc

    async def fake_chat_full(*_args, **_kwargs):
        return "**OK** - voici `code` #titre"

    monkeypatch.setattr(oc, "chat_full", fake_chat_full)
    response = await oc.generate_speech_response("test", context={})

    assert "**" not in response
    assert "`" not in response
    assert "#" not in response


@pytest.mark.asyncio
async def test_12_voice_engine_restart_with_enabled_true(monkeypatch):
    from core import voice_engine as ve

    monkeypatch.setattr(ve, "_load_voice_config", lambda: _voice_cfg(enabled=True))

    calls = {"init": 0}

    async def fake_init(self):
        calls["init"] += 1
        self._wake_model = SimpleNamespace()
        self._wake_stream = SimpleNamespace(stop=lambda: None, close=lambda: None)

    async def fake_listen(self):
        while self._running:
            await asyncio.sleep(0.05)

    monkeypatch.setattr(ve.VoiceEngine, "_init_wake_word", fake_init)
    monkeypatch.setattr(ve.VoiceEngine, "_listen_loop", fake_listen)

    engine = ve.VoiceEngine()
    await engine.start()
    await engine.stop()
    await engine.start()
    await engine.stop()

    assert calls["init"] == 2
