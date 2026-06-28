"""
Embeddings — Façade Atlas vers core_conversational.memory_core (v6.0.1).

La logique d'embedding e5 est désormais dans le package cross-platform
core_conversational. Ce module conserve l'API historique (is_available,
embed_query, embed_passages, model_info) pour compatibilité Atlas.
"""

from core_conversational.memory_core import (
    embed_query, embed_passages, embeddings_available as is_available,
    EMBED_DIM, DEFAULT_EMBED_MODEL as DEFAULT_MODEL,
)

__all__ = ["embed_query", "embed_passages", "is_available", "model_info",
           "EMBED_DIM", "DEFAULT_MODEL"]


def model_info() -> dict:
    """Infos diagnostic (compat Atlas)."""
    return {
        "available": is_available(),
        "model": DEFAULT_MODEL,
        "dim": EMBED_DIM,
    }
