"""
Configuration commune de la suite (sprint B-minimal, BM5).

Règle : aucun test ne lit ni n'écrit la mémoire ou les données réelles d'Atlas.

- ChromaDB : un serveur jetable (`chroma run`, dossier temporaire, port libre) démarre AVANT la
  collecte (certains modules de test sondent ChromaDB à l'import). Toute connexion
  `chromadb.HttpClient`, quel que soit l'hôte ou le port demandé, est redirigée vers ce serveur.
  S'il ne démarre pas, la redirection vise un port fermé : les tests « live » sont ignorés,
  jamais exécutés contre la production (localhost:8001).
- data/ : les chemins de données des modules sont redirigés vers un projet temporaire, qui
  contient une copie des 4 workflows modèles versionnés et de config/settings.json.
- api/routes.py calcule le chemin de data/ à partir de son propre __file__ (défaut produit,
  à centraliser en B-complet) : le module `pathlib` qu'il voit est remplacé par une copie
  dont Path(routes.__file__) pointe dans le projet temporaire.

Variable d'entrée : ATLAS_TEST_NO_CHROMA=1 simule une machine sans ChromaDB (aucun serveur jetable).

Variables exposées aux tests :
- ATLAS_TEST_CHROMA_URL : URL du serveur jetable (absente s'il n'a pas démarré)
- ATLAS_TEST_ROOT : racine du projet temporaire
"""

from __future__ import annotations

import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import types
import urllib.request

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE_WORKFLOWS = ("demarrage_matin.yaml", "mode_gaming.yaml", "mode_travail.yaml", "nettoyage_systeme.yaml")

_state: dict = {"proc": None, "dirs": []}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_test_chroma() -> int | None:
    if os.environ.get("ATLAS_TEST_NO_CHROMA") == "1":  # simule une machine sans ChromaDB
        return None
    try:
        import chromadb.cli.cli  # noqa: F401
    except Exception:
        return None
    workdir = pathlib.Path(tempfile.mkdtemp(prefix="atlas_tests_chroma_"))
    _state["dirs"].append(workdir)
    data = workdir / "data"
    port = _free_port()
    log = open(workdir / "chroma.log", "w", encoding="utf-8")
    _state["log"] = log
    # CLI lancée dans l'interpréteur courant : un seul processus à arrêter (le lanceur chroma.exe
    # de Windows crée un processus enfant qui survit à terminate() et verrouille les fichiers).
    launcher = "import sys; from chromadb.cli.cli import app; sys.argv[0] = 'chroma'; app()"
    _state["proc"] = subprocess.Popen(
        [sys.executable, "-c", launcher, "run", "--path", str(data), "--host", "127.0.0.1", "--port", str(port)],
        stdout=log, stderr=subprocess.STDOUT,
        env={**os.environ, "ANONYMIZED_TELEMETRY": "FALSE"},
    )
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if _state["proc"].poll() is not None:
            return None
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v2/heartbeat", timeout=1):
                return port
        except Exception:
            time.sleep(0.3)
    return None


def _isolate_chroma(port: int | None) -> None:
    import chromadb

    target = port if port else _free_port()  # port libre non écouté = connexion refusée
    os.environ["ATLAS_TEST_CHROMA_TARGET_PORT"] = str(target)
    def isolated_http_client(*args, **kwargs):
        # Ignore l'hôte et le port demandés : seul le serveur jetable est joignable.
        kwargs.pop("host", None)
        kwargs.pop("port", None)
        return isolated_http_client.original(*args[2:], host="127.0.0.1", port=target, **kwargs)

    isolated_http_client.original = chromadb.HttpClient
    chromadb.HttpClient = isolated_http_client

    import core.memory_manager as mm
    mm.CHROMA_HOST, mm.CHROMA_PORT = "127.0.0.1", target
    mm._instance = None  # un singleton déjà créé pointerait encore vers l'ancienne cible


def _isolate_data() -> pathlib.Path:
    root = pathlib.Path(tempfile.mkdtemp(prefix="atlas_tests_root_"))
    _state["dirs"].append(root)
    data = root / "data"
    (data / "workflows").mkdir(parents=True)
    for name in TEMPLATE_WORKFLOWS:
        shutil.copy2(PROJECT_ROOT / "data" / "workflows" / name, data / "workflows" / name)
    (root / "config").mkdir()
    shutil.copy2(PROJECT_ROOT / "config" / "settings.json", root / "config" / "settings.json")

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
    import api.routes as routes

    atlas_logger.LOG_FILE = data / "atlas_actions.jsonl"
    context_monitor._DB_PATH = data / "habits.db"
    file_indexer.DATA_DIR, file_indexer.INDEX_FILE = data, data / "file_index.json"
    file_organizer.DATA_DIR, file_organizer.HISTORY_FILE = data, data / "file_reorg_history.jsonl"
    scheduler.DATA_DIR, scheduler.SCHEDULES_FILE = data, data / "schedules.json"
    trigger_engine.DATA_DIR, trigger_engine.TRIGGERS_FILE = data, data / "triggers.json"
    workflow_engine.DATA_DIR, workflow_engine.WORKFLOWS_DIR = data, data / "workflows"
    app_launcher.FILE_INDEX_PATH = data / "file_index.json"
    grounding._DEBUG_IMAGE_DIR = str(data / "debug")
    system_config._AUDIT_LOG_PATH = data / "audit_log.jsonl"

    routes_file = pathlib.Path(routes.__file__).resolve()
    fake_routes_file = root / "api" / "routes.py"
    real_path = pathlib.Path

    def redirected_path(*args, **kwargs):
        if len(args) == 1 and not kwargs and real_path(args[0]).resolve() == routes_file:
            return fake_routes_file
        return real_path(*args, **kwargs)

    shim = types.ModuleType("pathlib")
    shim.__dict__.update(pathlib.__dict__)
    shim.Path = redirected_path
    routes.pathlib = shim
    return root


def pytest_configure(config):
    sys.path.insert(0, str(PROJECT_ROOT))
    port = _start_test_chroma()
    if port:
        os.environ["ATLAS_TEST_CHROMA_URL"] = f"http://127.0.0.1:{port}"
    _isolate_chroma(port)
    os.environ["ATLAS_TEST_ROOT"] = str(_isolate_data())


def pytest_report_header(config):
    url = os.environ.get("ATLAS_TEST_CHROMA_URL", "indisponible — tests ChromaDB ignorés")
    return [f"atlas: ChromaDB de test = {url}", f"atlas: données de test = {os.environ.get('ATLAS_TEST_ROOT')}"]


def pytest_unconfigure(config):
    proc = _state.get("proc")
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    if _state.get("log"):
        _state["log"].close()
    for d in _state["dirs"]:
        for _ in range(10):  # Windows libère les fichiers SQLite/HNSW avec un léger délai
            shutil.rmtree(d, ignore_errors=True)
            if not d.exists():
                break
            time.sleep(0.5)
