"""
Sprint B-minimal (BM6) — liste blanche des commandes docker de scripts/backup_memory.py.

Règle issue de l'incident I-1 (sprint M-bis) : un garde-fou se teste avec des commandes
SIMULÉES. Ici, `subprocess` est remplacé dans le module par un faux qui enregistre les appels ;
aucune commande docker n'est jamais exécutée. Le faux est vérifié avant chaque test.
"""

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import backup_memory as bm  # noqa: E402

IMG = "sha256:7605e7b398f96dba833ed1b6272f815b9d33414dde45c68bd246e84447db8591"


@pytest.fixture(autouse=True)
def fake_subprocess(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    fake = types.SimpleNamespace(run=fake_run, TimeoutExpired=Exception)
    # Remplace le module subprocess VU PAR backup_memory uniquement.
    monkeypatch.setattr(bm, "subprocess", fake)
    assert bm.subprocess is fake and bm.subprocess.run is fake_run
    return calls


REFUSED = [
    # l'incident I-1 lui-même
    ("compose", "down"),
    ("compose", "up", "-d"),
    ("compose", "down", "-v"),
    # production
    ("rm", "-f", "atlas_chromadb"),
    ("rm", "assistant_chromadb"),
    ("rm", "-f", "atlas_memcheck_x", "atlas_chromadb"),
    ("stop", "atlas_chromadb"),
    ("kill", "atlas_chromadb"),
    ("restart", "atlas_chromadb"),
    ("start", "atlas_chromadb"),
    ("pause", "atlas_chromadb"),
    ("rename", "atlas_chromadb", "x"),
    ("update", "--restart", "no", "atlas_chromadb"),
    ("volume", "rm", "atlas_chromadb_data"),
    ("volume", "prune", "-f"),
    ("volume", "create", "x"),
    ("system", "prune", "-af"),
    ("image", "rm", IMG),
    ("pull", "chromadb/chroma:latest"),
    ("commit", "atlas_chromadb"),
    # exec arbitraire dans la production
    ("exec", "atlas_chromadb", "sh", "-c", "rm -rf /data"),
    ("exec", "atlas_chromadb", "rm", "-rf", "/data"),
    ("exec", "atlas_chromadb", "sh", "-c", bm.HASH_SCRIPT + "; rm -rf /data"),
    # cp vers le conteneur (écriture)
    ("cp", r"C:\Users\x\data", "atlas_chromadb:/data"),
    ("cp", "atlas_chromadb:/data", "atlas_memcheck_x:/data"),
    # run/create hors cadre
    ("run", "-d", "--name", "atlas_chromadb", "--pull", "never", IMG),
    ("run", "-d", "--name", "atlas_memcheck_x", IMG),                       # sans --pull never
    ("run", "-d", "--pull", "never", IMG),                                  # ni nom jetable ni --rm
    ("run", "--rm", "--pull", "never", "-v", "atlas_chromadb_data:/data", IMG),      # volume en écriture
    ("run", "--rm", "--pull", "always", "-v", "atlas_chromadb_data:/data:ro", IMG),
    ("create", "--pull", "never", "--name", "other", IMG),
    # divers
    (),
    ("login",),
]

ALLOWED = [
    ("inspect", "atlas_chromadb"),
    ("ps", "--format", "{{.Names}}"),
    ("ps", "-a", "--format", "{{.Names}}"),
    ("volume", "inspect", "atlas_chromadb_data"),
    ("exec", "atlas_chromadb", "sh", "-c", bm.HASH_SCRIPT),
    ("exec", "assistant_chromadb", "sh", "-c", bm.CONFIG_SCRIPT),
    ("cp", "atlas_chromadb:/data", r"C:\Users\alexis\Atlas_backups\memoire\x\data"),
    ("run", "-d", "--pull", "never", "--name", "atlas_memcheck_20260917_000000", "-p", "127.0.0.1:8101:8000",
     "-e", "ANONYMIZED_TELEMETRY=FALSE", "-v", r"C:\Temp\w\data:/data", IMG),
    ("run", "--rm", "--pull", "never", "--entrypoint", "sh", "-v", "atlas_chromadb_data:/data:ro", IMG, "-c", "x"),
    ("create", "--pull", "never", "--name", "atlas_memcheck_fill", "-v", "atlas_memcheck_vol:/data", IMG),
    ("rm", "-f", "atlas_memcheck_20260917_000000"),
]


@pytest.mark.parametrize("args", REFUSED, ids=lambda a: " ".join(a) or "<vide>")
def test_refused_commands_never_reach_subprocess(args, fake_subprocess):
    with pytest.raises(bm.GuardRefusal):
        bm.docker(*args)
    assert fake_subprocess == [], "une commande refusée a atteint subprocess.run"


@pytest.mark.parametrize("args", ALLOWED, ids=lambda a: " ".join(a[:3]))
def test_allowed_commands_are_passed_through(args, fake_subprocess):
    bm.docker(*args)
    assert fake_subprocess == [["docker", *args]]


def test_script_calls_are_all_whitelisted():
    """Les commandes réellement construites par le script passent la liste blanche."""
    bm.check_docker_args(("exec", "atlas_chromadb", "sh", "-c", bm.HASH_SCRIPT))
    bm.check_docker_args(("exec", "atlas_chromadb", "sh", "-c", bm.CONFIG_SCRIPT))


def test_backup_uses_only_whitelisted_commands(monkeypatch, tmp_path, fake_subprocess):
    """Parcours `backup` complet avec docker et HTTP simulés : aucune commande refusée."""
    seen = []
    real_check = bm.check_docker_args

    def recording_check(args):
        seen.append(tuple(args))
        real_check(args)

    monkeypatch.setattr(bm, "check_docker_args", recording_check)
    monkeypatch.setattr(bm, "summarize", lambda url: {"version": "1.0.0", "collections": {}})
    monkeypatch.setattr(bm.time, "sleep", lambda s: None)

    def fake_docker_output(cmd, **kwargs):
        sub = cmd[1]
        out = ""
        if sub == "ps":
            out = "atlas_chromadb\n"
        elif sub == "inspect":
            out = '[{"State": {"Running": true}, "Image": "%s", "Config": {"Image": "x"}, "Mounts": []}]' % IMG
        elif sub == "exec" and cmd[-1] == bm.CONFIG_SCRIPT:
            out = 'persist_path: "/data"\nchroma 1.4.1\n'
        elif sub == "cp":
            dest = Path(cmd[-1])
            dest.mkdir(parents=True)
            (dest / "f.bin").write_bytes(b"x")
        elif sub == "exec":
            import hashlib
            out = f"{hashlib.sha256(b'x').hexdigest()}  /data/f.bin\n"
        fake_subprocess.append(list(cmd))
        return types.SimpleNamespace(returncode=0, stdout=out, stderr="")

    monkeypatch.setattr(bm, "subprocess", types.SimpleNamespace(run=fake_docker_output))
    args = types.SimpleNamespace(container=None, dest=str(tmp_path), url="http://fake")
    assert bm.cmd_backup(args) == 0
    assert seen and all(s[0] in ("ps", "inspect", "exec", "cp") for s in seen)
