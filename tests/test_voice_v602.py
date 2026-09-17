"""v6.0.2 Voice sprint tests — F1 Voix Partie 1 (wake word custom path + download_voice_models)."""

import sys
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def reset_voice_singleton():
    import core.voice_engine as ve_mod

    ve_mod._voice_engine = None
    yield
    ve_mod._voice_engine = None


def _voice_cfg(**overrides):
    cfg = {
        "enabled": True,
        "wake_word_model": "hey_mycroft",
        "wake_word_threshold": 0.5,
        "stt_model": "base",
        "stt_language": "fr",
        "stt_device": "cuda",
        "tts_voice": "fr_FR-siwis-medium",
        "max_recording_seconds": 10,
        "silence_threshold_seconds": 1.5,
    }
    cfg.update(overrides)
    return cfg


# --- wake word model resolution --------------------------------------------------


def test_01_resolve_wake_word_model_bare_keyword(monkeypatch):
    from core import voice_engine as ve

    monkeypatch.setattr(ve, "_load_voice_config", lambda: _voice_cfg(wake_word_model="hey_mycroft"))
    engine = ve.VoiceEngine()

    model_ref, is_custom = engine._resolve_wake_word_model()
    assert model_ref == "hey_mycroft"
    assert is_custom is False


def test_02_resolve_wake_word_model_relative_path(monkeypatch):
    from core import voice_engine as ve
    import pathlib

    monkeypatch.setattr(
        ve, "_load_voice_config", lambda: _voice_cfg(wake_word_model="models/wakewords/hey_atlas.onnx")
    )
    engine = ve.VoiceEngine()

    model_ref, is_custom = engine._resolve_wake_word_model()
    project_root = pathlib.Path(ve.__file__).resolve().parent.parent
    assert is_custom is True
    assert model_ref == str(project_root / "models" / "wakewords" / "hey_atlas.onnx")


def test_03_resolve_wake_word_model_absolute_path_passthrough(monkeypatch, tmp_path):
    from core import voice_engine as ve

    abs_path = tmp_path / "custom" / "hey_atlas.onnx"
    monkeypatch.setattr(ve, "_load_voice_config", lambda: _voice_cfg(wake_word_model=str(abs_path)))
    engine = ve.VoiceEngine()

    model_ref, is_custom = engine._resolve_wake_word_model()
    assert is_custom is True
    assert model_ref == str(abs_path)


# --- _init_wake_word with custom path ---------------------------------------------


@pytest.mark.asyncio
async def test_04_init_wake_word_custom_path_missing_raises_actionable_error(monkeypatch, tmp_path):
    from core import voice_engine as ve

    missing = tmp_path / "models" / "wakewords" / "hey_atlas.onnx"
    monkeypatch.setattr(ve, "_load_voice_config", lambda: _voice_cfg(wake_word_model=str(missing)))

    fake_sd = SimpleNamespace(InputStream=lambda **_kwargs: SimpleNamespace(start=lambda: None))
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    monkeypatch.setitem(sys.modules, "openwakeword", SimpleNamespace(Model=object))
    monkeypatch.setitem(sys.modules, "openwakeword.model", SimpleNamespace(Model=object))

    engine = ve.VoiceEngine()
    with pytest.raises(RuntimeError) as excinfo:
        await engine._init_wake_word()

    assert "download_voice_models.py" in str(excinfo.value)
    assert str(missing) in str(excinfo.value)


@pytest.mark.asyncio
async def test_05_init_wake_word_custom_path_loads_and_sets_score_key(monkeypatch, tmp_path):
    from core import voice_engine as ve

    model_path = tmp_path / "models" / "wakewords" / "hey_atlas.onnx"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"fake-onnx-bytes")

    monkeypatch.setattr(ve, "_load_voice_config", lambda: _voice_cfg(wake_word_model=str(model_path)))

    created = {}

    class FakeModel:
        def __init__(self, wakeword_models=None, inference_framework=None):
            created["wakeword_models"] = wakeword_models
            self.sample_rate = 16000
            self.audio_window_size = 1280

    fake_sd = SimpleNamespace(InputStream=lambda **_kwargs: SimpleNamespace(start=lambda: None))
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    monkeypatch.setitem(sys.modules, "openwakeword", SimpleNamespace(Model=FakeModel))
    monkeypatch.setitem(sys.modules, "openwakeword.model", SimpleNamespace(Model=FakeModel))

    engine = ve.VoiceEngine()
    await engine._init_wake_word()

    assert engine._wake_score_key == "hey_atlas"
    assert created["wakeword_models"] == [str(model_path)]


# --- wake detection scoring --------------------------------------------------------


def test_06_wake_detected_uses_score_key_for_dict_scores(monkeypatch):
    from core import voice_engine as ve
    import numpy as np

    monkeypatch.setattr(ve, "_load_voice_config", lambda: _voice_cfg())
    engine = ve.VoiceEngine()
    engine._wake_score_key = "hey_atlas"
    engine._wake_threshold = 0.5

    class FakeModel:
        def predict(self, _audio):
            return {"hey_atlas": 0.9, "some_other_model": 0.99}

    engine._wake_model = FakeModel()
    assert engine._wake_detected(np.zeros(1280, dtype=np.float32)) is True


def test_07_wake_not_detected_below_threshold(monkeypatch):
    from core import voice_engine as ve
    import numpy as np

    monkeypatch.setattr(ve, "_load_voice_config", lambda: _voice_cfg())
    engine = ve.VoiceEngine()
    engine._wake_score_key = "hey_atlas"
    engine._wake_threshold = 0.5

    class FakeModel:
        def predict(self, _audio):
            return {"hey_atlas": 0.1}

    engine._wake_model = FakeModel()
    assert engine._wake_detected(np.zeros(1280, dtype=np.float32)) is False


# --- config regression --------------------------------------------------------------


def test_08_settings_json_voice_section_updated_for_sprint():
    import json
    import pathlib

    cfg_path = pathlib.Path(__file__).resolve().parent.parent / "config" / "settings.json"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)

    voice_cfg = cfg["voice"]
    assert voice_cfg["enabled"] is True
    assert voice_cfg["tts_voice"] == "fr_FR-siwis-medium"
    assert voice_cfg["wake_word_model"] == "models/wakewords/hey_atlas.onnx"


# --- scripts/download_voice_models.py ------------------------------------------------


def test_09_download_file_skips_existing(monkeypatch, tmp_path):
    import scripts.download_voice_models as dvm

    dest = tmp_path / "existing.onnx"
    dest.write_bytes(b"already-here")

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("requests.get should not be called when file already exists")

    monkeypatch.setattr(dvm.requests, "get", _fail_if_called)
    dvm.download_file("https://example.invalid/file.onnx", dest)
    assert dest.read_bytes() == b"already-here"


def test_10_download_file_downloads_and_writes(monkeypatch, tmp_path):
    import scripts.download_voice_models as dvm

    dest = tmp_path / "sub" / "new.onnx"
    payload = b"x" * 2000

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=1 << 16):
            yield payload

    monkeypatch.setattr(dvm.requests, "get", lambda *_a, **_k: FakeResponse())
    dvm.download_file("https://example.invalid/new.onnx", dest, min_bytes=100)

    assert dest.exists()
    assert dest.read_bytes() == payload
    assert not dest.with_suffix(dest.suffix + ".part").exists()


def test_11_download_file_rejects_too_small_download(monkeypatch, tmp_path):
    import scripts.download_voice_models as dvm

    dest = tmp_path / "tiny.onnx"

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=1 << 16):
            yield b"too-small"

    monkeypatch.setattr(dvm.requests, "get", lambda *_a, **_k: FakeResponse())

    with pytest.raises(RuntimeError):
        dvm.download_file("https://example.invalid/tiny.onnx", dest, min_bytes=10_000)

    assert not dest.exists()
    assert not dest.with_suffix(dest.suffix + ".part").exists()


def test_12_download_wake_word_model_uses_expected_url_and_dest(monkeypatch, tmp_path):
    import scripts.download_voice_models as dvm

    monkeypatch.setattr(dvm, "WAKE_WORD_DIR", tmp_path / "models" / "wakewords")
    calls = []
    monkeypatch.setattr(dvm, "download_file", lambda url, dest, min_bytes=1: calls.append((url, dest, min_bytes)))

    assert dvm.download_wake_word_model() is True
    assert len(calls) == 1
    url, dest, min_bytes = calls[0]
    assert url == f"{dvm.WAKE_WORD_BASE_URL}/hey_atlas.onnx"
    assert dest == tmp_path / "models" / "wakewords" / "hey_atlas.onnx"
    assert min_bytes == 10_000


def test_13_download_piper_voice_downloads_onnx_and_json(monkeypatch, tmp_path):
    import scripts.download_voice_models as dvm

    monkeypatch.setattr(dvm, "PIPER_VOICE_DIR", tmp_path / "data" / "voices")
    calls = []
    monkeypatch.setattr(dvm, "download_file", lambda url, dest, min_bytes=1: calls.append((url, dest, min_bytes)))

    assert dvm.download_piper_voice() is True
    assert len(calls) == 2
    urls = {c[0] for c in calls}
    assert f"{dvm.PIPER_VOICE_BASE_URL}/fr_FR-siwis-medium.onnx" in urls
    assert f"{dvm.PIPER_VOICE_BASE_URL}/fr_FR-siwis-medium.onnx.json" in urls


def test_14_download_openwakeword_support_models_handles_import_error(monkeypatch):
    import builtins
    import scripts.download_voice_models as dvm

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "openwakeword.utils" or name == "openwakeword":
            raise ImportError("openwakeword not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    assert dvm.download_openwakeword_support_models() is False


def test_15_download_openwakeword_support_models_calls_with_sentinel(monkeypatch):
    import scripts.download_voice_models as dvm

    calls = []
    fake_utils = SimpleNamespace(download_models=lambda model_names: calls.append(model_names))
    monkeypatch.setitem(sys.modules, "openwakeword.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "openwakeword", SimpleNamespace(utils=fake_utils))

    assert dvm.download_openwakeword_support_models() is True
    assert calls == [[dvm._OWW_SUPPORT_ONLY_SENTINEL]]


def test_16_main_returns_nonzero_when_a_step_fails(monkeypatch):
    import scripts.download_voice_models as dvm

    monkeypatch.setattr(dvm, "download_openwakeword_support_models", lambda: True)
    monkeypatch.setattr(dvm, "download_wake_word_model", lambda: False)
    monkeypatch.setattr(dvm, "download_piper_voice", lambda: True)

    assert dvm.main() == 1


def test_17_main_returns_zero_when_all_succeed(monkeypatch):
    import scripts.download_voice_models as dvm

    monkeypatch.setattr(dvm, "download_openwakeword_support_models", lambda: True)
    monkeypatch.setattr(dvm, "download_wake_word_model", lambda: True)
    monkeypatch.setattr(dvm, "download_piper_voice", lambda: True)

    assert dvm.main() == 0
