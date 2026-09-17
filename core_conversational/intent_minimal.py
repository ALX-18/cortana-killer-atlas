"""
Intent Minimal — Classifieur conversationnel léger (cross-platform).

Pour Manman (conversationnel pur) : distingue conversation vs question méta vs
demande de mémoire. Aucun routage d'outil Windows. Aucune dépendance Windows.
"""

import re
import unicodedata
from dataclasses import dataclass


def _normalize(text: str) -> str:
    s = (text or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class MinimalIntent:
    category: str   # conversation | memory_recall | memory_save | question
    confidence: float
    raw: str


_MEMORY_SAVE = ("souviens", "retiens", "note que", "rappelle-toi", "rappelle toi", "memorise", "mémorise")
_MEMORY_RECALL = ("tu te souviens", "qu'est-ce que je t'ai dit", "rappelle-moi", "rappelle moi",
                  "tu te rappelles", "qu'avais-je dit", "c'était quoi")
_OPINION = ("penses", "crois", "trouves", "estimes", "imagines", "qu'en penses")


class MinimalClassifier:
    """Classifieur conversationnel minimal pour fork Manman."""

    def classify(self, user_input: str) -> MinimalIntent:
        raw = (user_input or "").strip()
        n = _normalize(raw)

        # recall (phrases plus spécifiques) avant save (mots-clés génériques)
        if any(m in n for m in _MEMORY_RECALL):
            return MinimalIntent("memory_recall", 0.9, raw)
        if any(m in n for m in _MEMORY_SAVE):
            return MinimalIntent("memory_save", 0.9, raw)

        is_question = raw.rstrip().endswith("?") or n.startswith(("que ", "qu'", "est-ce", "pourquoi", "comment"))
        if is_question and any(o in n for o in _OPINION):
            return MinimalIntent("question", 0.85, raw)

        return MinimalIntent("conversation", 0.8, raw)
