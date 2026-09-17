"""
Memory Ingest — Pipeline d'ingestion de documents (F4 v6.0).

Formats supportés : .txt, .md, .pdf (via pypdf).
Chunking : recursive character text splitter, chunk_size=512, overlap=64.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger("atlas.memory_ingest")

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64

# Séparateurs hiérarchiques (du plus gros au plus fin), façon RecursiveCharacterTextSplitter
_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

_SUPPORTED = {".txt", ".md", ".pdf"}
_MIME = {".txt": "text/plain", ".md": "text/markdown", ".pdf": "application/pdf"}


def is_supported(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _SUPPORTED


def mime_for(path: str) -> str:
    return _MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream")


def extract_text(path: str) -> str:
    """Extrait le texte brut d'un fichier .txt/.md/.pdf."""
    ext = os.path.splitext(path)[1].lower()
    if ext in {".txt", ".md"}:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise RuntimeError("pypdf non installé — ingestion PDF indisponible") from e
        reader = PdfReader(path)
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception as e:
                logger.debug("Extraction page PDF échouée : %s", e)
        return "\n".join(parts)
    raise ValueError(f"Format non supporté : {ext}")


def _split_recursive(text: str, chunk_size: int, separators: list[str]) -> list[str]:
    """Split récursif : essaie le séparateur le plus gros qui passe sous chunk_size."""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    sep = separators[0] if separators else ""
    rest = separators[1:] if len(separators) > 1 else [""]

    if sep == "":
        # Dernier recours : découpe brute par taille
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    pieces = text.split(sep)
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = piece if not current else current + sep + piece
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(piece) > chunk_size:
                chunks.extend(_split_recursive(piece, chunk_size, rest))
                current = ""
            else:
                current = piece
    if current.strip():
        chunks.append(current)
    return [c for c in chunks if c.strip()]


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Découpe le texte en chunks avec chevauchement.
    Le splitter récursif produit les chunks de base, puis on applique l'overlap
    en préfixant chaque chunk de la fin du précédent.
    """
    base = _split_recursive(text, chunk_size, _SEPARATORS)
    if overlap <= 0 or len(base) <= 1:
        return base

    overlapped: list[str] = [base[0]]
    for i in range(1, len(base)):
        prev_tail = base[i - 1][-overlap:]
        overlapped.append(prev_tail + base[i])
    return overlapped


def ingest_file(path: str, memory_manager=None) -> dict:
    """
    Ingère un fichier complet : extraction → chunking → stockage partition documents.
    Retourne {"success", "source", "chunks", "stored", "message"}.
    """
    if not os.path.isfile(path):
        return {"success": False, "source": path, "chunks": 0, "stored": 0,
                "message": "Fichier introuvable."}
    if not is_supported(path):
        return {"success": False, "source": path, "chunks": 0, "stored": 0,
                "message": f"Format non supporté ({os.path.splitext(path)[1]}). Formats: .txt .md .pdf"}

    try:
        text = extract_text(path)
    except Exception as e:
        return {"success": False, "source": path, "chunks": 0, "stored": 0,
                "message": f"Extraction échouée : {e}"}

    if not text.strip():
        return {"success": False, "source": path, "chunks": 0, "stored": 0,
                "message": "Aucun texte extrait du document."}

    chunks = chunk_text(text)
    if memory_manager is None:
        from core.memory_manager import get_memory_manager
        memory_manager = get_memory_manager()

    stored = memory_manager.ingest_document_chunks(
        chunks, source=os.path.basename(path), mime_type=mime_for(path),
    )
    return {
        "success": stored > 0,
        "source": os.path.basename(path),
        "chunks": len(chunks),
        "stored": stored,
        "message": f"{stored}/{len(chunks)} chunks ingérés." if stored else "Aucun chunk stocké (ChromaDB indisponible ?).",
    }
