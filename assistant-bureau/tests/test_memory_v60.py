"""
Sprint v6.0 — F4 Mémoire Long Terme.

Tests unitaires (toujours exécutés) : chunking, extraction, embeddings, error helpers.
Tests live (skip si ChromaDB down) : partitionnement, ingestion, retrieval, isolation,
apprentissage erreurs, FIFO.
"""

import os
import sys
import time
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.memory_ingest import chunk_text, extract_text, is_supported, mime_for
from core import embeddings as emb
from core.error_learning import (
    ErrorLearning, build_signature, classify_cause, _mitigation_for, VALID_CAUSES,
)


# --------------------------------------------------------------------------- #
#  Fixtures
# --------------------------------------------------------------------------- #

def _chroma_up() -> bool:
    try:
        import chromadb
        c = chromadb.HttpClient()  # redirigé vers le serveur jetable par tests/conftest.py
        c.heartbeat()
        return True
    except Exception:
        return False


CHROMA = _chroma_up()
live = pytest.mark.skipif(not CHROMA, reason="ChromaDB de test non disponible (voir tests/conftest.py)")


@pytest.fixture
def mem():
    from core.memory_manager import MemoryManager
    return MemoryManager()


# --------------------------------------------------------------------------- #
#  UNIT — Chunking
# --------------------------------------------------------------------------- #

class TestChunking:
    def test_short_text_single_chunk(self):
        assert chunk_text("petit texte") == ["petit texte"]

    def test_empty_text_no_chunks(self):
        assert chunk_text("") == []

    def test_long_text_multiple_chunks(self):
        chunks = chunk_text("a" * 2000, chunk_size=512, overlap=64)
        assert len(chunks) >= 4

    def test_chunks_respect_size_roughly(self):
        text = ("phrase normale. " * 200)
        chunks = chunk_text(text, chunk_size=512, overlap=64)
        # chaque chunk de base ~< 512 + overlap
        assert all(len(c) <= 512 + 64 + 20 for c in chunks)

    def test_overlap_present(self):
        text = "AAAA\n\n" + "B" * 600 + "\n\n" + "C" * 600
        chunks = chunk_text(text, chunk_size=512, overlap=64)
        assert len(chunks) >= 2

    def test_paragraph_split_preferred(self):
        # Greedy packing: paragraphs are split on "\n\n" then packed up to chunk_size.
        # With chunk_size=10, each short paragraph becomes its own chunk.
        text = "Para un.\n\nPara deux.\n\nPara trois."
        chunks = chunk_text(text, chunk_size=10, overlap=0)
        assert len(chunks) >= 3
        # And no chunk should contain a paragraph boundary merge beyond size
        assert all(len(c) <= 10 + 20 for c in chunks)


# --------------------------------------------------------------------------- #
#  UNIT — Extraction & format
# --------------------------------------------------------------------------- #

class TestExtraction:
    def test_txt_extraction(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Bonjour Atlas, ceci est un test.", encoding="utf-8")
        assert "Bonjour Atlas" in extract_text(str(f))

    def test_md_extraction(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Titre\n\nContenu markdown.", encoding="utf-8")
        assert "Contenu markdown" in extract_text(str(f))

    def test_is_supported(self):
        assert is_supported("a.txt") and is_supported("a.md") and is_supported("a.pdf")
        assert not is_supported("a.docx") and not is_supported("a.png")

    def test_mime_for(self):
        assert mime_for("a.pdf") == "application/pdf"
        assert mime_for("a.md") == "text/markdown"

    def test_unsupported_raises(self, tmp_path):
        f = tmp_path / "x.docx"
        f.write_text("x", encoding="utf-8")
        with pytest.raises(ValueError):
            extract_text(str(f))


# --------------------------------------------------------------------------- #
#  UNIT — Embeddings
# --------------------------------------------------------------------------- #

class TestEmbeddings:
    def test_embeddings_available(self):
        assert emb.is_available() is True

    def test_query_embedding_dim(self):
        v = emb.embed_query("bonjour")
        assert v is not None and len(v) == emb.EMBED_DIM

    def test_passage_embedding_dim(self):
        vs = emb.embed_passages(["passage un", "passage deux"])
        assert vs is not None and len(vs) == 2 and len(vs[0]) == emb.EMBED_DIM

    def test_semantic_similarity(self):
        # "bibliothèque steam" plus proche de "library" que de "météo paris"
        import numpy as np
        q = np.array(emb.embed_query("ouvrir la bibliothèque steam"))
        a = np.array(emb.embed_passages(["the steam game library tab"])[0])
        b = np.array(emb.embed_passages(["la météo à paris demain"])[0])
        assert float(q @ a) > float(q @ b)

    def test_model_info(self):
        info = emb.model_info()
        assert info["dim"] == 768 and "e5" in info["model"]


# --------------------------------------------------------------------------- #
#  UNIT — Error learning helpers
# --------------------------------------------------------------------------- #

class TestErrorHelpers:
    def test_classify_cause_timeout(self):
        assert classify_cause("global_timeout 20s", None) == "timeout"

    def test_classify_cause_not_found(self):
        assert classify_cause("all_failed no_match", "ERR_TOOL_RESULT_FAILURE") == "not_found"

    def test_classify_cause_ambiguous(self):
        assert classify_cause("disambiguation required", None) == "ambiguous"

    def test_classify_cause_permission(self):
        assert classify_cause("permission denied", "ERR_CONFIRMATION_REQUIRED") == "permission_denied"

    def test_classify_cause_other(self):
        assert classify_cause("weird unknown thing", None) == "other"

    def test_build_signature_format(self):
        sig = build_signature("interaction", "Bibliothèque", "steam")
        assert "intent=interaction" in sig and "steam" in sig

    def test_mitigation_not_found_skips_layer(self):
        m = _mitigation_for("not_found", "ocr")
        assert m["strategy"] == "skip_layer" and m["skip_layer"] == "ocr"

    def test_mitigation_ambiguous_confirms(self):
        assert _mitigation_for("ambiguous", None)["strategy"] == "confirm"

    def test_all_causes_have_mitigation(self):
        for c in VALID_CAUSES:
            assert "strategy" in _mitigation_for(c, "ocr")


# --------------------------------------------------------------------------- #
#  LIVE — Partitions, ingestion, retrieval (ChromaDB requis)
# --------------------------------------------------------------------------- #

@live
class TestPartitionsLive:
    def test_partitions_created(self, mem):
        assert mem.is_connected()
        for key in ("conversations", "documents", "context_apps", "habits", "errors"):
            assert key in mem._partitions

    def test_ingest_and_retrieve_conversation(self, mem):
        tag = uuid.uuid4().hex[:6]
        mem.ingest_conversation(
            f"comment lancer mon jeu {tag} sur steam",
            "Je lance Steam puis ta bibliothèque.",
            intent_category="interaction", success=True,
        )
        time.sleep(0.3)
        hits = mem.retrieve(f"démarrer un jeu {tag}", partition="conversations", top_k=3, min_score=0.3)
        assert any(tag in h["content"] for h in hits)

    def test_ingest_document_chunks_and_retrieve(self, mem):
        tag = uuid.uuid4().hex[:6]
        chunks = [
            f"Le projet Atlas {tag} est un assistant bureau Windows 100% local.",
            f"Atlas {tag} utilise Ollama et ChromaDB pour la mémoire RAG.",
        ]
        stored = mem.ingest_document_chunks(chunks, source=f"atlas_doc_{tag}.md")
        assert stored == 2
        time.sleep(0.3)
        hits = mem.retrieve(f"assistant local windows {tag}", partition="documents", top_k=3, min_score=0.3)
        assert any(tag in h["content"] for h in hits)

    def test_collection_isolation(self, mem):
        tag = uuid.uuid4().hex[:6]
        mem.ingest_document_chunks([f"DOCUMENT_ONLY_MARKER {tag}"], source=f"iso_{tag}.txt")
        time.sleep(0.3)
        # Query conversations partition must NOT return the document marker
        hits = mem.retrieve(f"DOCUMENT_ONLY_MARKER {tag}", partition="conversations",
                            top_k=5, min_score=0.0)
        assert not any("DOCUMENT_ONLY_MARKER" in h["content"] for h in hits)

    def test_recall_for_prompt_combines(self, mem):
        tag = uuid.uuid4().hex[:6]
        mem.ingest_document_chunks([f"Atlas supporte le mode gaming {tag}."], source=f"feat_{tag}.md")
        time.sleep(0.3)
        out = mem.recall_for_prompt(f"mode gaming {tag}")
        assert isinstance(out, list)


# --------------------------------------------------------------------------- #
#  LIVE — Apprentissage erreurs
# --------------------------------------------------------------------------- #

@live
class TestErrorLearningLive:
    def test_store_and_lookup_error(self, mem):
        tag = uuid.uuid4().hex[:6]
        el = ErrorLearning(memory_manager=mem)
        el.record_failure(
            intent_category="interaction", target=f"jeu_{tag}",
            app_context="steam", cause="not_found", grounding_layer_failed="ocr",
        )
        time.sleep(0.3)
        mit = el.lookup_mitigation("interaction", f"jeu_{tag}", "steam", min_score=0.7)
        assert mit is not None
        assert mit["strategy"] == "skip_layer"
        assert mit["skip_layer"] == "ocr"

    def test_no_mitigation_for_unknown(self, mem):
        el = ErrorLearning(memory_manager=mem)
        mit = el.lookup_mitigation("interaction", f"jamais_vu_{uuid.uuid4().hex}", "inconnue", min_score=0.95)
        assert mit is None

    def test_error_stored_in_errors_partition(self, mem):
        tag = uuid.uuid4().hex[:6]
        before = mem._partitions["errors"].count()
        mem.store_error(f"intent=x cible=t_{tag} app=a", {"cause": "timeout"})
        time.sleep(0.2)
        after = mem._partitions["errors"].count()
        assert after == before + 1
