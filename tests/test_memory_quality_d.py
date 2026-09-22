"""
Sprint D — qualité de la mémoire.

D4 : un seul modèle d'embedding à l'écriture comme à la lecture (e5, 768 dimensions).
     `atlas_memory` était écrite sans embeddings, donc vectorisée par le modèle par défaut
     de ChromaDB (all-MiniLM-L6-v2, anglophone, 384 dimensions), alors que les partitions
     utilisent e5 multilingue. Deux espaces vectoriels dans la même base.
D5 : déduplication à l'écriture — 219 copies exactes s'étaient accumulées.
D8 : seuil de pertinence sur le chemin historique, qui n'en appliquait aucun. Un souvenir
     hors sujet était injecté dans le prompt à chaque question (symptôme C07).

Tests live : ChromaDB jetable de tests/conftest.py. Jamais la base réelle.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import embeddings as emb


def _chroma_up() -> bool:
    try:
        import chromadb
        chromadb.HttpClient().heartbeat()
        return True
    except Exception:
        return False


live = pytest.mark.skipif(not _chroma_up(), reason="ChromaDB de test non disponible")


@pytest.fixture
def mem():
    """MemoryManager neuf sur une collection legacy vierge, dans le ChromaDB de test."""
    import uuid as _uuid

    import core.memory_manager as mm_mod

    name = f"atlas_memory_test_{_uuid.uuid4().hex[:8]}"
    saved = mm_mod.COLLECTION_NAME
    mm_mod.COLLECTION_NAME = name
    manager = mm_mod.MemoryManager()
    yield manager
    try:
        manager._client.delete_collection(name)
    except Exception:
        pass
    mm_mod.COLLECTION_NAME = saved


def _stored_dim(manager, memory_id) -> int:
    got = manager._collection.get(ids=[memory_id], include=["embeddings"])
    return len(got["embeddings"][0])


# --------------------------------------------------------------------------- #
#  D4 — un seul modèle d'embedding
# --------------------------------------------------------------------------- #

@live
def test_d4_ecriture_avec_embedding_e5(mem):
    """Le souvenir écrit doit porter un vecteur e5, comme les partitions."""
    mid = mem.save("habit", "Alexis ouvre Discord tous les matins vers 9 h")
    assert mid, "souvenir non écrit"
    assert _stored_dim(mem, mid) == emb.EMBED_DIM, (
        f"vecteur de dimension {_stored_dim(mem, mid)} au lieu de {emb.EMBED_DIM} : "
        "ce n'est pas e5, c'est l'embedder par défaut de ChromaDB"
    )


@live
def test_d4_lecture_avec_embedding_e5(mem, monkeypatch):
    """Le rappel doit interroger avec un vecteur e5, pas laisser ChromaDB vectoriser."""
    mem.save("habit", "Alexis joue à Helldivers 2 le soir")
    calls = []
    real = emb.embed_query
    monkeypatch.setattr(emb, "embed_query", lambda q: calls.append(q) or real(q))
    mem.recall("à quoi joue Alexis ?", top_k=3)
    assert calls, "recall n'a pas utilisé e5 : la requête a été vectorisée par ChromaDB"


@live
def test_d4_pas_decriture_si_e5_indisponible(mem, monkeypatch):
    """Sans e5, mieux vaut ne rien écrire que mélanger deux espaces vectoriels."""
    monkeypatch.setattr(emb, "embed_passages", lambda texts: None)
    before = mem._collection.count()
    result = mem.save("habit", "souvenir écrit sans le bon modèle")
    assert result is None, "souvenir écrit malgré l'absence du modèle e5"
    assert mem._collection.count() == before, "la collection a été modifiée"


@live
def test_d4_pas_de_rappel_si_e5_indisponible(mem, monkeypatch):
    """Sans e5, une requête vectorisée par un autre modèle ne veut rien dire."""
    mem.save("habit", "Alexis utilise Docker Desktop")
    monkeypatch.setattr(emb, "embed_query", lambda q: None)
    assert mem.recall("docker", top_k=3) == []


# --------------------------------------------------------------------------- #
#  D5 — déduplication à l'écriture
# --------------------------------------------------------------------------- #

@live
def test_d5_texte_identique_non_duplique(mem):
    texte = "Action 'launch_app' exécutée. Args: {\"name\": \"steam\"}. Résultat: 'steam' lancé."
    first = mem.save("action_history", texte)
    second = mem.save("action_history", texte)
    assert mem._collection.count() == 1, (
        f"{mem._collection.count()} copies du même texte : c'est ainsi que 219 doublons "
        "se sont accumulés"
    )
    assert second == first, "l'identifiant du souvenir existant doit être renvoyé"


@live
def test_d5_textes_differents_tous_conserves(mem):
    mem.save("action_history", "Action 'launch_app' : steam")
    mem.save("action_history", "Action 'launch_app' : discord")
    assert mem._collection.count() == 2


@live
def test_d5_meme_texte_categories_differentes_conserve(mem):
    mem.save("habit", "Alexis utilise Steam")
    mem.save("action_history", "Alexis utilise Steam")
    assert mem._collection.count() == 2, "deux catégories, deux souvenirs distincts"


# --------------------------------------------------------------------------- #
#  D8 — seuil de pertinence sur le chemin historique
# --------------------------------------------------------------------------- #

@live
def test_d8_souvenir_hors_sujet_non_rappele(mem):
    """Symptôme C07 : une question sans rapport ramenait quand même un souvenir."""
    mem.save("action_history", "Action 'get_diagnostics' exécutée. CPU 12 %, RAM 43 %.")
    hits = mem.recall("Quelle est ma recette de crêpes préférée ?", top_k=5)
    assert hits == [], f"souvenir hors sujet rappelé : {[(h['score'], h['content'][:50]) for h in hits]}"


@live
def test_d8_le_seuil_est_bien_un_reglage_et_non_un_filtre_aveugle(mem):
    """Le seuil doit filtrer par score, et rien d'autre.

    Mesuré au sprint D : sur ce corpus, une paire pertinente marque 0,81 et une paire sans
    rapport 0,80. Les scores e5 ne séparent pas les deux en valeur absolue ; le seuil retenu
    (0,82) est un compromis, pas une garantie. Ce test vérifie donc le mécanisme.
    """
    mem.save("habit", "Alexis ouvre Discord tous les matins")
    assert mem.recall("Est-ce que j'utilise Discord ?", top_k=5, min_score=0.75), (
        "sous un seuil bas, le souvenir pertinent doit être rappelé"
    )
    assert mem.recall("Est-ce que j'utilise Discord ?", top_k=5, min_score=0.95) == [], (
        "sous un seuil très haut, plus rien ne doit passer"
    )


@live
def test_d8_injection_prompt_vide_si_rien_de_pertinent(mem):
    """recall_for_prompt ne doit rien injecter quand rien n'est pertinent."""
    mem.save("action_history", "Action 'launch_app' exécutée : steam")
    injected = mem.recall_for_prompt("Quel est mon numéro de sécurité sociale ?")
    assert injected == [], f"{len(injected)} souvenir(s) injecté(s) sans rapport : {injected[:2]}"


@live
def test_d8_seuil_lu_dans_la_configuration(mem):
    import core.memory_manager as mm_mod

    assert mm_mod.RETRIEVAL_MIN_SCORE == 0.82, (
        "valeur calibrée au sprint D sur la base réelle (voir RAPPORT_SPRINT_D, D8)"
    )
    mem.save("habit", "Alexis utilise Opera GX")
    for hit in mem.recall("navigateur", top_k=5):
        assert hit["score"] >= mm_mod.RETRIEVAL_MIN_SCORE
