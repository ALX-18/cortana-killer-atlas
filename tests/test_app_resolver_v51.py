import tools.app_launcher as app_launcher
import json


def test_normalize_app_name_handles_accents_and_separators():
    assert app_launcher._normalize_app_name("Bloc-notés") == "bloc notes"
    assert app_launcher._normalize_app_name("VS_Code.exe") == "vs code exe"


def test_resolve_app_candidate_contains_match(monkeypatch):
    monkeypatch.setattr(app_launcher, "_RUNTIME_APP_INDEX", {})

    def _isfile(path):
        return path.endswith("notepad.exe")

    monkeypatch.setattr(app_launcher.os.path, "isfile", _isfile)
    name, path, strategy = app_launcher._resolve_app_candidate("bloc note")

    assert name in {"bloc-notes", "bloc notes", "notepad"}
    assert path.endswith("notepad.exe")
    assert strategy in {"known_contains", "known_exact", "known_fuzzy"}


def test_resolve_app_candidate_runtime_fuzzy(monkeypatch):
    monkeypatch.setattr(
        app_launcher,
        "_RUNTIME_APP_INDEX",
        {
            "microsoft edge": r"C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Microsoft Edge.lnk",
        },
    )

    def _isfile(_):
        return False

    monkeypatch.setattr(app_launcher.os.path, "isfile", _isfile)
    name, path, strategy = app_launcher._resolve_app_candidate("microsft edg")
    assert name == "microsoft edge"
    assert path.endswith("Microsoft Edge.lnk")
    assert strategy == "runtime_fuzzy"


def test_launch_app_unknown_returns_suggestions(monkeypatch):
    monkeypatch.setattr(
        app_launcher,
        "_RUNTIME_APP_INDEX",
        {
            "microsoft edge": "edge.lnk",
            "visual studio code": "code.lnk",
            "bloc notes": "notepad.exe",
        },
    )
    monkeypatch.setattr(app_launcher, "_find_app_path", lambda _: None)

    result = app_launcher.launch_app(name="application introuvable xyz")
    assert result["success"] is False
    assert "Suggestions:" in result["message"]


def test_resolve_from_file_index(monkeypatch, tmp_path):
    idx = tmp_path / "file_index.json"
    payload = {
        "files": [
            {"name": "Visual Studio Code.lnk", "path": r"C:\\Users\\alexis\\Desktop\\Visual Studio Code.lnk", "ext": ".lnk"},
            {"name": "Opera GX.lnk", "path": r"C:\\Users\\alexis\\Desktop\\Opera GX.lnk", "ext": ".lnk"},
        ]
    }
    idx.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(app_launcher, "FILE_INDEX_PATH", idx)

    name, path = app_launcher._resolve_from_file_index("visual studio cod")
    assert name == "visual studio code"
    assert path.endswith("Visual Studio Code.lnk")
