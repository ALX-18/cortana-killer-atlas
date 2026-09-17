"""
Sprints M-bis et B-minimal — protections de la mémoire inscrites dans docker-compose.yml.

Test statique : lit le fichier, n'exécute aucune commande docker.
"""

from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parent.parent / "docker-compose.yml"
CHROMA_DIGEST = "sha256:7605e7b398f96dba833ed1b6272f815b9d33414dde45c68bd246e84447db8591"
SEARXNG_DIGEST = "sha256:edf110a2816d8963949d03879c72a7e19c221b5f7bfb7952a33ae073f96ccb18"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_project_name_is_atlas():
    # L'ancien projet implicite « assistant-bureau » ne doit plus être piloté par ce fichier.
    assert _compose()["name"] == "atlas"


def test_images_pinned_by_digest():
    services = _compose()["services"]
    assert services["chromadb"]["image"] == f"chromadb/chroma@{CHROMA_DIGEST}"
    assert services["searxng"]["image"] == f"searxng/searxng@{SEARXNG_DIGEST}"
    # Un digest interdit déjà tout changement de version ; `pull_policy: always` serait inutile,
    # et `never` empêcherait une installation neuve de récupérer l'image (corrigé au sprint C).
    for name in ("chromadb", "searxng"):
        assert services[name].get("pull_policy") in (None, "missing", "if_not_present")


def test_searxng_cache_on_named_volume():
    compose = _compose()
    assert "atlas_searxng_cache:/var/cache/searxng" in compose["services"]["searxng"]["volumes"]
    assert "atlas_searxng_cache" in compose["volumes"]


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
