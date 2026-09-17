"""
core_conversational — Cœur conversationnel cross-platform partagé Atlas / Manman.

Règle absolue : ZÉRO dépendance Windows. Pas de pywin32/pywinauto/comtypes/pycaw/
wmi/pygetwindow, pas d'import des outils Atlas Windows (grounding, window_controller…).
Dépendances autorisées : httpx, chromadb, sentence-transformers (toutes cross-platform).
"""

from .identity import (
    IdentityCard, atlas_identity, ATLAS_BASE_IDENTITY, LANGUAGE_CONSTRAINT,
)
from .llm_client import (
    LLMClient, contains_non_latin_script, LANG_FALLBACK_MESSAGE,
)
from .memory_core import (
    ConversationalMemory, embed_query, embed_passages, embeddings_available,
    EMBED_DIM, DEFAULT_EMBED_MODEL,
)
from .intent_minimal import MinimalClassifier, MinimalIntent

__all__ = [
    "IdentityCard", "atlas_identity", "ATLAS_BASE_IDENTITY", "LANGUAGE_CONSTRAINT",
    "LLMClient", "contains_non_latin_script", "LANG_FALLBACK_MESSAGE",
    "ConversationalMemory", "embed_query", "embed_passages", "embeddings_available",
    "EMBED_DIM", "DEFAULT_EMBED_MODEL",
    "MinimalClassifier", "MinimalIntent",
]
