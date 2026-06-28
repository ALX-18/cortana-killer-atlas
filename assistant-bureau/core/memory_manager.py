"""
Memory Manager — Couche mémoire RAG via ChromaDB.

Gère deux types de mémoire :
  - Court terme : conversation en cours (RAM, réinitialisée à la fermeture)
  - Long terme  : habitudes, préférences, historique d'actions, corrections (ChromaDB)
"""

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger("atlas.memory")

# --------------------------------------------------------------------------- #
#  Config
# --------------------------------------------------------------------------- #

def _load_memory_config() -> dict:
    import pathlib
    cfg_path = pathlib.Path(__file__).resolve().parent.parent / "config" / "settings.json"
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f).get("memory", {})

_cfg = _load_memory_config()

CHROMA_HOST: str = _cfg.get("chroma_host", "localhost")
CHROMA_PORT: int = _cfg.get("chroma_port", 8001)
COLLECTION_NAME: str = _cfg.get("collection_name", "atlas_memory")

# Catégories valides (mémoire legacy)
CATEGORIES = {"habit", "preference", "action_history", "correction"}

# --- F4 v6.0 : partitionnement + retrieval ---
_COLL_CFG = _cfg.get("collections", {})
PARTITIONS = {
    "conversations": _COLL_CFG.get("conversations", "atlas_conversations"),
    "documents": _COLL_CFG.get("documents", "atlas_documents"),
    "context_apps": _COLL_CFG.get("context_apps", "atlas_context_apps"),
    "habits": _COLL_CFG.get("habits", "atlas_habits"),
    "errors": _COLL_CFG.get("errors", "atlas_errors"),
}
RETRIEVAL_TOP_K: int = int(_cfg.get("retrieval_top_k", 3))
RETRIEVAL_MIN_SCORE: float = float(_cfg.get("retrieval_min_score", 0.5))
CONVERSATIONS_MAX: int = int(_cfg.get("conversations", {}).get("max_entries", 10000))


# --------------------------------------------------------------------------- #
#  MemoryManager
# --------------------------------------------------------------------------- #

class MemoryManager:
    """
    Interface unifiée pour la mémoire court terme (RAM) et long terme (ChromaDB).
    """

    def __init__(self):
        # -- Court terme (session) --
        self._short_term: list[dict] = []

        # -- Long terme (ChromaDB) --
        self._client: Optional[chromadb.HttpClient] = None
        self._collection = None
        self._partitions: dict[str, Any] = {}   # F4 — collections partitionnées
        self._connected = False
        self._connect()

    # ------------------------------------------------------------------ #
    #  Connexion ChromaDB
    # ------------------------------------------------------------------ #

    def _connect(self):
        """Tente de se connecter à ChromaDB. Fail silencieux si indisponible."""
        try:
            self._client = chromadb.HttpClient(
                host=CHROMA_HOST,
                port=CHROMA_PORT,
            )
            # Test de connexion
            self._client.heartbeat()
            self._collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            # F4 v6.0 — collections partitionnées (embeddings e5 fournis explicitement)
            self._partitions = {}
            for key, coll_name in PARTITIONS.items():
                self._partitions[key] = self._client.get_or_create_collection(
                    name=coll_name,
                    metadata={"hnsw:space": "cosine"},
                )
            self._connected = True
            logger.info(
                "ChromaDB connecté — %s:%d — collection '%s' + %d partitions",
                CHROMA_HOST, CHROMA_PORT, COLLECTION_NAME, len(self._partitions),
            )
        except Exception as e:
            self._connected = False
            logger.warning("ChromaDB indisponible (%s). Mémoire long terme désactivée.", e)

    def is_connected(self) -> bool:
        return self._connected

    def reconnect(self):
        """Retente la connexion à ChromaDB."""
        self._connect()

    # ------------------------------------------------------------------ #
    #  Mémoire court terme (session)
    # ------------------------------------------------------------------ #

    def add_to_session(self, role: str, content: str):
        """Ajoute un message à la conversation en cours."""
        self._short_term.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
        })

    def get_session_history(self, last_n: int = 20) -> list[dict]:
        """Retourne les N derniers messages de la session."""
        return [
            {"role": m["role"], "content": m["content"]}
            for m in self._short_term[-last_n:]
        ]

    def clear_session(self):
        """Réinitialise la conversation en cours."""
        self._short_term.clear()

    # ------------------------------------------------------------------ #
    #  Mémoire long terme — SAVE
    # ------------------------------------------------------------------ #

    def save(
        self,
        category: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> str | None:
        """
        Sauvegarde un souvenir dans ChromaDB.

        category : "habit" | "preference" | "action_history" | "correction"
        content  : description textuelle du souvenir
        metadata : données additionnelles (timestamp, contexte, app, etc.)

        Retourne l'ID du souvenir créé, ou None si échec.
        """
        if not self._connected:
            logger.debug("ChromaDB non connecté — souvenir non sauvegardé")
            return None

        if category not in CATEGORIES:
            logger.warning("Catégorie invalide : '%s'. Valides : %s", category, CATEGORIES)
            return None

        memory_id = f"{category}_{uuid.uuid4().hex[:12]}"

        meta = {
            "category": category,
            "timestamp": datetime.now().isoformat(),
            "created_at": time.time(),
        }
        if metadata:
            # ChromaDB ne supporte que str/int/float/bool dans les métadonnées
            for k, v in metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v
                else:
                    meta[k] = str(v)

        try:
            self._collection.add(
                ids=[memory_id],
                documents=[content],
                metadatas=[meta],
            )
            logger.info("Souvenir sauvegardé [%s] : %s", category, content[:80])
            return memory_id
        except Exception as e:
            logger.error("Erreur sauvegarde mémoire : %s", e)
            return None

    # ------------------------------------------------------------------ #
    #  Mémoire long terme — RECALL
    # ------------------------------------------------------------------ #

    def recall(
        self,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None,
    ) -> list[dict]:
        """
        Recherche les souvenirs les plus pertinents par rapport à une requête.

        Retourne une liste de dicts : {"id": str, "content": str, "category": str, "score": float}
        """
        if not self._connected:
            return []

        try:
            where_filter = {"category": category} if category else None

            results = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter,
            )

            memories = []
            if results and results["documents"] and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    distance = results["distances"][0][i] if results["distances"] else 0
                    memories.append({
                        "id": results["ids"][0][i],
                        "content": doc,
                        "category": meta.get("category", "unknown"),
                        "score": round(1 - distance, 3),  # cosine → similarity
                        "timestamp": meta.get("timestamp", ""),
                    })

            return memories
        except Exception as e:
            logger.error("Erreur recall mémoire : %s", e)
            return []

    def recall_texts(self, query: str, top_k: int = 5) -> list[str]:
        """Version simplifiée de recall — retourne juste les textes."""
        memories = self.recall(query, top_k)
        return [m["content"] for m in memories]

    def recall_for_prompt(self, query: str) -> list[str]:
        """
        F4 v6.0 — Retrieval combiné pour injection dans le system prompt.
        Croise la mémoire legacy + partitions conversations/documents, filtre par
        score, dédoublonne. Vide si rien au-dessus du seuil (injection silencieuse).
        """
        if not self._connected:
            return []
        out: list[str] = []
        seen: set[str] = set()

        # Partitions sémantiques (e5) — documents puis conversations
        for partition in ("documents", "conversations"):
            for hit in self.retrieve(query, partition=partition,
                                     top_k=RETRIEVAL_TOP_K, min_score=RETRIEVAL_MIN_SCORE):
                txt = hit["content"]
                key = txt[:120]
                if key not in seen:
                    seen.add(key)
                    out.append(txt)

        # Mémoire legacy (habitudes/préférences/corrections) — complément
        for txt in self.recall_texts(query, top_k=3):
            key = txt[:120]
            if key not in seen:
                seen.add(key)
                out.append(txt)

        return out[:6]

    # ------------------------------------------------------------------ #
    #  Mémoire long terme — FORGET
    # ------------------------------------------------------------------ #

    def forget(self, memory_id: str) -> bool:
        """Supprime un souvenir spécifique."""
        if not self._connected:
            return False
        try:
            self._collection.delete(ids=[memory_id])
            logger.info("Souvenir supprimé : %s", memory_id)
            return True
        except Exception as e:
            logger.error("Erreur suppression mémoire : %s", e)
            return False

    def forget_category(self, category: str) -> int:
        """Supprime tous les souvenirs d'une catégorie."""
        if not self._connected:
            return 0
        try:
            # Récupérer les IDs de la catégorie
            results = self._collection.get(
                where={"category": category},
            )
            if results["ids"]:
                self._collection.delete(ids=results["ids"])
                logger.info("Supprimé %d souvenirs de catégorie '%s'", len(results["ids"]), category)
                return len(results["ids"])
            return 0
        except Exception as e:
            logger.error("Erreur suppression catégorie : %s", e)
            return 0

    # ------------------------------------------------------------------ #
    #  F4 v6.0 — Partitions : helpers embeddings
    # ------------------------------------------------------------------ #

    def _sanitize_meta(self, metadata: Optional[dict]) -> dict:
        """ChromaDB n'accepte que str/int/float/bool en métadonnée."""
        meta: dict[str, Any] = {}
        for k, v in (metadata or {}).items():
            if v is None:
                continue
            meta[k] = v if isinstance(v, (str, int, float, bool)) else str(v)
        return meta

    def _add_to_partition(
        self,
        partition: str,
        doc_id: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> bool:
        """Ajoute un document à une partition, embeddings e5 si dispo."""
        if not self._connected or partition not in self._partitions:
            return False
        from core import embeddings as emb

        meta = self._sanitize_meta(metadata)
        meta.setdefault("created_at", time.time())
        meta.setdefault("timestamp", datetime.now().isoformat())
        try:
            vecs = emb.embed_passages([content])
            if vecs is not None:
                self._partitions[partition].add(
                    ids=[doc_id], documents=[content],
                    metadatas=[meta], embeddings=vecs,
                )
            else:
                # Dégradation : embedder ChromaDB par défaut
                self._partitions[partition].add(
                    ids=[doc_id], documents=[content], metadatas=[meta],
                )
            return True
        except Exception as e:
            logger.error("Erreur ajout partition '%s' : %s", partition, e)
            return False

    def retrieve(
        self,
        query: str,
        partition: str = "conversations",
        top_k: int = RETRIEVAL_TOP_K,
        min_score: float = RETRIEVAL_MIN_SCORE,
    ) -> list[dict]:
        """
        Recherche dans une partition. Retourne les hits avec score >= min_score.
        Format : {"id", "content", "score", "metadata"}.
        """
        if not self._connected or partition not in self._partitions:
            return []
        from core import embeddings as emb

        coll = self._partitions[partition]
        try:
            qvec = emb.embed_query(query)
            if qvec is not None:
                results = coll.query(query_embeddings=[qvec], n_results=top_k)
            else:
                results = coll.query(query_texts=[query], n_results=top_k)
        except Exception as e:
            logger.error("Erreur retrieve partition '%s' : %s", partition, e)
            return []

        hits: list[dict] = []
        if results and results.get("documents") and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                dist = results["distances"][0][i] if results.get("distances") else 0.0
                score = round(1 - dist, 3)
                if score < min_score:
                    continue
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                hits.append({
                    "id": results["ids"][0][i],
                    "content": doc,
                    "score": score,
                    "metadata": meta,
                })
        return hits

    # ------------------------------------------------------------------ #
    #  F4 — Ingestion conversations (async-friendly, FIFO)
    # ------------------------------------------------------------------ #

    def ingest_conversation(
        self,
        user_msg: str,
        assistant_response: str,
        intent_category: str = "unknown",
        success: bool = True,
    ) -> Optional[str]:
        """Stocke un échange (user, assistant) dans la partition conversations."""
        if not self._connected or not user_msg:
            return None
        conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        content = f"Utilisateur: {user_msg}\nAtlas: {assistant_response}"
        ok = self._add_to_partition(
            "conversations", conv_id, content,
            {"intent_category": intent_category, "success": bool(success),
             "user_msg": user_msg[:500]},
        )
        if not ok:
            return None
        self._fifo_rotate("conversations", CONVERSATIONS_MAX)
        return conv_id

    def _fifo_rotate(self, partition: str, max_entries: int):
        """Supprime les plus anciennes entrées au-delà de max_entries (FIFO)."""
        if not self._connected or partition not in self._partitions:
            return
        coll = self._partitions[partition]
        try:
            total = coll.count()
            if total <= max_entries:
                return
            to_remove = total - max_entries
            # Récupère tout avec created_at, trie, supprime les plus vieux
            alld = coll.get(include=["metadatas"])
            ids = alld.get("ids", [])
            metas = alld.get("metadatas", []) or []
            paired = sorted(
                zip(ids, [m.get("created_at", 0) for m in metas]),
                key=lambda p: p[1],
            )
            old_ids = [pid for pid, _ in paired[:to_remove]]
            if old_ids:
                coll.delete(ids=old_ids)
                logger.info("FIFO rotation '%s' : %d entrées supprimées", partition, len(old_ids))
        except Exception as e:
            logger.debug("FIFO rotation '%s' échec : %s", partition, e)

    # ------------------------------------------------------------------ #
    #  F4 — Ingestion documents (chunks)
    # ------------------------------------------------------------------ #

    def ingest_document_chunks(
        self,
        chunks: list[str],
        source: str,
        mime_type: str = "text/plain",
    ) -> int:
        """Stocke des chunks de document dans la partition documents. Retourne le nb stockés."""
        if not self._connected or not chunks:
            return 0
        stored = 0
        ingested_at = datetime.now().isoformat()
        for idx, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            doc_id = f"doc_{uuid.uuid4().hex[:12]}"
            ok = self._add_to_partition(
                "documents", doc_id, chunk,
                {"source": source, "mime_type": mime_type,
                 "chunk_index": idx, "ingested_at": ingested_at},
            )
            if ok:
                stored += 1
        logger.info("Ingestion document '%s' : %d/%d chunks stockés", source, stored, len(chunks))
        return stored

    # ------------------------------------------------------------------ #
    #  F4 — Errors partition (utilisé par error_learning)
    # ------------------------------------------------------------------ #

    def store_error(self, signature: str, metadata: dict) -> Optional[str]:
        """Stocke une signature d'échec dans la partition errors."""
        if not self._connected:
            return None
        err_id = f"err_{uuid.uuid4().hex[:12]}"
        ok = self._add_to_partition("errors", err_id, signature, metadata)
        return err_id if ok else None

    def query_errors(self, signature: str, top_k: int = 1, min_score: float = 0.85) -> list[dict]:
        """Recherche un échec similaire passé. min_score élevé = match strict."""
        return self.retrieve(signature, partition="errors", top_k=top_k, min_score=min_score)

    # ------------------------------------------------------------------ #
    #  Stats
    # ------------------------------------------------------------------ #

    def stats(self) -> dict[str, Any]:
        """Retourne des statistiques sur la mémoire."""
        result = {
            "connected": self._connected,
            "session_messages": len(self._short_term),
        }
        if self._connected:
            try:
                count = self._collection.count()
                result["total_memories"] = count

                # Compter par catégorie
                for cat in CATEGORIES:
                    try:
                        cat_results = self._collection.get(where={"category": cat})
                        result[f"count_{cat}"] = len(cat_results["ids"])
                    except Exception:
                        result[f"count_{cat}"] = 0

                # F4 — compteurs partitions
                partitions_count = {}
                for key, coll in self._partitions.items():
                    try:
                        partitions_count[key] = coll.count()
                    except Exception:
                        partitions_count[key] = -1
                result["partitions"] = partitions_count
            except Exception:
                result["total_memories"] = -1
        return result


# --------------------------------------------------------------------------- #
#  Singleton
# --------------------------------------------------------------------------- #

_instance: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """Retourne l'instance singleton du MemoryManager."""
    global _instance
    if _instance is None:
        _instance = MemoryManager()
    return _instance
