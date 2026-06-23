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

# Catégories valides
CATEGORIES = {"habit", "preference", "action_history", "correction"}


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
            self._connected = True
            logger.info("ChromaDB connecté — %s:%d — collection '%s'", CHROMA_HOST, CHROMA_PORT, COLLECTION_NAME)
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
