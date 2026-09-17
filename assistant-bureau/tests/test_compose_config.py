"""
Sprints M-bis et B-minimal — protections de la mémoire inscrites dans docker-compose.yml.

Test statique : lit le fichier, n'exécute aucune commande docker.
"""

from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parent.parent / "docker-compose.yml"
DIGEST = "sha256:7605e7b398f96dba833ed1b6272f815b9d33414dde45c68bd246e84447db8591"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_project_name_is_atlas():
    # L'ancien projet implicite « assistant-bureau » ne doit plus être piloté par ce fichier.
    assert _compose()["name"] == "atlas"


def test_chromadb_image_pinned_by_digest_without_pull():
    svc = _compose()["services"]["chromadb"]
    assert svc["image"] == f"chromadb/chroma@{DIGEST}"
    assert svc["pull_policy"] == "never"


def test_chromadb_data_on_external_named_volume():
    compose = _compose()
    svc = compose["services"]["chromadb"]
    assert "atlas_chromadb_data:/data" in svc["volumes"]  # persist_path de l'image (risque L21)
    assert compose["volumes"]["atlas_chromadb_data"]["external"] is True  # `down -v` ne le supprime pas


def test_reset_disabled():
    svc = _compose()["services"]["chromadb"]
    assert "ALLOW_RESET=FALSE" in svc["environment"]
    assert not any("TRUE" in e for e in svc["environment"] if e.startswith("ALLOW_RESET"))
    # Le serveur 1.4.1 n'autorise reset que via `allow_reset: true` dans /config.yaml :
    # aucun fichier ne doit y être monté sans revue.
    assert not any(":/config.yaml" in v for v in svc["volumes"])


def test_docker_ollama_only_on_explicit_profile():
    assert _compose()["services"]["ollama"]["profiles"] == ["docker-ollama"]  # conflit 11434 (L22)
