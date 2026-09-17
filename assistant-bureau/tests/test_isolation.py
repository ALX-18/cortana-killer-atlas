"""
Sprint B-minimal (BM5) — la suite ne vise jamais la mémoire ni les données réelles.

Ces tests vérifient la redirection mise en place par tests/conftest.py. S'ils échouent,
d'autres tests risquent d'écrire dans la production : ne pas les ignorer.
"""

import os
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
REAL_DATA = PROJECT_ROOT / "data"
PROD_CHROMA_PORT = 8001


def _test_root() -> pathlib.Path:
    root = os.environ.get("ATLAS_TEST_ROOT")
    assert root, "tests/conftest.py n'a pas isolé les données"
    return pathlib.Path(root)


def test_chromadb_client_never_targets_production(monkeypatch):
    import chromadb

    captured = {}

    class FakeHttpClient:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

    # On remplace le client d'origine appelé par la redirection, pas la redirection elle-même.
    assert hasattr(chromadb.HttpClient, "original"), "redirection ChromaDB absente (tests/conftest.py)"
    monkeypatch.setattr(chromadb.HttpClient, "original", FakeHttpClient)
    chromadb.HttpClient(host="localhost", port=PROD_CHROMA_PORT)
    chromadb.HttpClient("localhost", PROD_CHROMA_PORT)
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] != PROD_CHROMA_PORT
    assert str(captured["port"]) == os.environ["ATLAS_TEST_CHROMA_TARGET_PORT"]


def test_memory_manager_targets_test_port():
    import core.memory_manager as mm

    assert mm.CHROMA_PORT != PROD_CHROMA_PORT
    assert str(mm.CHROMA_PORT) == os.environ["ATLAS_TEST_CHROMA_TARGET_PORT"]


def test_module_data_paths_are_temporary():
    import core.atlas_logger as atlas_logger
    import core.context_monitor as context_monitor
    import core.file_indexer as file_indexer
    import core.file_organizer as file_organizer
    import core.scheduler as scheduler
    import core.trigger_engine as trigger_engine
    import core.workflow_engine as workflow_engine
    import tools.app_launcher as app_launcher
    import tools.grounding as grounding
    import tools.system_config as system_config

    root = _test_root()
    paths = [
        atlas_logger.LOG_FILE, context_monitor._DB_PATH, file_indexer.INDEX_FILE, file_organizer.HISTORY_FILE,
        scheduler.SCHEDULES_FILE, trigger_engine.TRIGGERS_FILE, workflow_engine.WORKFLOWS_DIR,
        app_launcher.FILE_INDEX_PATH, grounding._DEBUG_IMAGE_DIR, system_config._AUDIT_LOG_PATH,
    ]
    for p in paths:
        p = pathlib.Path(p).resolve()
        assert root.resolve() in p.parents, f"{p} n'est pas dans le dossier de test"
        assert REAL_DATA.resolve() not in p.parents


def test_routes_data_path_is_redirected():
    import api.routes as routes

    root = _test_root()
    fake = routes.pathlib.Path(routes.__file__).resolve().parent.parent / "data" / "atlas_actions.jsonl"
    assert fake.resolve() == (root / "data" / "atlas_actions.jsonl").resolve()
    # Les autres chemins ne sont pas détournés.
    assert routes.pathlib.Path(__file__).resolve() == pathlib.Path(__file__).resolve()


def test_workflow_templates_copied():
    names = sorted(p.name for p in (_test_root() / "data" / "workflows").glob("*.yaml"))
    assert names == ["demarrage_matin.yaml", "mode_gaming.yaml", "mode_travail.yaml", "nettoyage_systeme.yaml"]
