"""
Sprint E, prélude — garde-fous du nettoyage de la mémoire.

Le nettoyage supprime définitivement des souvenirs. Ses règles sont donc testées ici avec
un client ChromaDB SIMULÉ : aucune base réelle, aucune suppression (règle permanente depuis
l'incident I-1 du sprint M-bis).

Ce qui est vérifié : `atlas_memory` n'est jamais touchée, seuls les artefacts et les
doublons décidés par le brief sont sélectionnés, et c'est bien la plus ancienne occurrence
qui est conservée.
"""

import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from scripts.memory_cleanup import D1_TEST_IDS, PROTECTED, build_plan


class FakeCollection:
    def __init__(self, items):
        self.items = items
        self.deleted: list[str] = []

    def get(self, include=None):
        return {
            "ids": [i["id"] for i in self.items],
            "documents": [i["text"] for i in self.items],
            "metadatas": [i["meta"] for i in self.items],
        }

    def count(self):
        return len(self.items)

    def delete(self, ids):
        self.deleted.extend(ids)


class FakeClient:
    """ChromaDB simulé : il enregistre les suppressions au lieu de les faire."""

    def __init__(self, collections):
        self.collections = {name: FakeCollection(items) for name, items in collections.items()}

    def get_collection(self, name):
        if name not in self.collections:
            raise ValueError(f"collection inconnue : {name}")
        return self.collections[name]


def _item(mid, text, created_at=1.0, category="", extra=None):
    meta = {"category": category, "created_at": created_at}
    meta.update(extra or {})
    return {"id": mid, "text": text, "meta": meta}


@pytest.fixture
def client():
    trois_copies = [_item(f"mem_{i}", "Action 'launch_app' exécutée : steam",
                          created_at=100 + i, category="action_history") for i in range(3)]
    return FakeClient({
        "atlas_memory": [_item("vieux_1", "souvenir historique", 1.0)],
        "atlas_memory_e5": trois_copies + [_item("mem_seul", "souvenir unique", 50.0)],
        "atlas_documents": [
            _item("doc_art", "DOCUMENT_ONLY_MARKER 346ff9"),
            _item("doc_vrai", "Note de projet : architecture de la mémoire"),
        ],
        "atlas_errors": [
            _item("err_art", "intent=interaction cible=jeu_7c8fb0 app=steam"),
            _item(D1_TEST_IDS[0], "intent=interaction cible=Fichier app=cible-d1"),
            _item("err_vrai", "intent=window_mgmt cible=bloc-notes app=Explorateur"),
        ],
    })


def test_atlas_memory_est_protegee(client):
    """La collection d'origine 384 dimensions est le retour arrière : on n'y touche jamais."""
    assert "atlas_memory" in PROTECTED
    plan = build_plan(client)
    assert "atlas_memory" not in plan, "atlas_memory figure dans le plan de suppression"
    assert client.collections["atlas_memory"].deleted == []


def test_conversations_protegees(client):
    assert "atlas_conversations" in PROTECTED
    assert "atlas_conversations" not in build_plan(client)


def test_doublons_la_plus_ancienne_est_conservee(client):
    plan = build_plan(client)
    doomed = plan["atlas_memory_e5"]["delete"]
    assert set(doomed) == {"mem_1", "mem_2"}, f"sélection inattendue : {sorted(doomed)}"
    assert "mem_0" not in doomed, "la plus ancienne doit être conservée"
    assert "mem_seul" not in doomed, "un texte unique ne doit jamais être supprimé"
    assert all("doublon" in raison for raison in doomed.values())


def test_artefacts_et_entrees_de_test_selectionnes_avec_leur_raison(client):
    plan = build_plan(client)
    docs, errs = plan["atlas_documents"]["delete"], plan["atlas_errors"]["delete"]
    assert set(docs) == {"doc_art"}, f"documents : {sorted(docs)}"
    assert set(errs) == {"err_art", D1_TEST_IDS[0]}, f"erreurs : {sorted(errs)}"
    assert "artefact de test" in docs["doc_art"]
    assert "test D1" in errs[D1_TEST_IDS[0]]


def test_rien_de_reel_nest_selectionne(client):
    plan = build_plan(client)
    assert "doc_vrai" not in plan["atlas_documents"]["delete"]
    assert "err_vrai" not in plan["atlas_errors"]["delete"]
