"""
Error Learning — Apprentissage par les erreurs (F4 v6.0).

Mécanisme honnête : ce n'est PAS du reinforcement learning. C'est du retrieval
sémantique + adaptation par règles.

- À chaque action échouée : on stocke une signature (intent + contexte app + cause)
  dans la partition `errors` de ChromaDB.
- Avant chaque action : on interroge `errors` avec la signature courante. Si un
  échec similaire est trouvé (cosine > 0.85), on propose une mitigation :
    1. skip_layer   — sauter la couche grounding qui avait échoué
    2. confirm      — demander confirmation à l'utilisateur
    3. reformulate  — suggérer une reformulation

Causes normalisées : timeout | not_found | ambiguous | permission_denied | other.
"""

import logging
from typing import Optional

logger = logging.getLogger("atlas.error_learning")

VALID_CAUSES = {"timeout", "not_found", "ambiguous", "permission_denied", "other"}
MATCH_THRESHOLD = 0.85


def classify_cause(error_msg: str | None, error_code: str | None = None) -> str:
    """Déduit une cause normalisée depuis le message/code d'erreur."""
    blob = f"{error_msg or ''} {error_code or ''}".lower()
    if "timeout" in blob or "global_timeout" in blob:
        return "timeout"
    if "ambig" in blob or "disambig" in blob:
        return "ambiguous"
    if "permission" in blob or "denied" in blob or "confirmation_required" in blob:
        return "permission_denied"
    if "not found" in blob or "introuvable" in blob or "no_match" in blob or "all_failed" in blob:
        return "not_found"
    return "other"


def build_signature(intent_category: str, target: str, app_context: str) -> str:
    """Construit la signature textuelle embeddée pour le retrieval d'erreurs."""
    target = (target or "").strip()
    app_context = (app_context or "").strip()
    return f"intent={intent_category} cible={target} app={app_context}"


def _mitigation_for(cause: str, grounding_layer_failed: str | None) -> dict:
    """Choisit une mitigation selon la cause de l'échec précédent."""
    if cause == "not_found" and grounding_layer_failed:
        return {
            "strategy": "skip_layer",
            "skip_layer": grounding_layer_failed,
            "message": f"La dernière fois, la couche '{grounding_layer_failed}' a échoué ici. Je l'évite.",
        }
    if cause == "ambiguous":
        return {
            "strategy": "confirm",
            "message": "J'ai déjà hésité sur une cible proche ici. Tu confirmes ?",
        }
    if cause == "timeout":
        return {
            "strategy": "skip_layer",
            "skip_layer": grounding_layer_failed or "vision",
            "message": "La dernière fois ça a dépassé le délai. J'évite la couche lente.",
        }
    if cause == "permission_denied":
        return {
            "strategy": "confirm",
            "message": "Action sensible déjà refusée auparavant. Tu confirmes ?",
        }
    return {
        "strategy": "reformulate",
        "message": "J'ai déjà échoué sur une demande similaire. Peux-tu reformuler ?",
    }


class ErrorLearning:
    """Stocke et récupère les signatures d'échec via la mémoire vectorielle."""

    def __init__(self, memory_manager=None):
        self._mem = memory_manager

    def _mm(self):
        if self._mem is not None:
            return self._mem
        from core.memory_manager import get_memory_manager
        return get_memory_manager()

    def record_failure(
        self,
        intent_category: str,
        target: str,
        app_context: str,
        cause: str,
        grounding_layer_failed: str | None = None,
    ) -> Optional[str]:
        """Stocke un échec dans la partition errors."""
        if cause not in VALID_CAUSES:
            cause = "other"
        sig = build_signature(intent_category, target, app_context)
        meta = {
            "intent_category": intent_category,
            "target": target or "",
            "app_context": app_context or "",
            "cause": cause,
            "grounding_layer_failed": grounding_layer_failed or "",
        }
        err_id = self._mm().store_error(sig, meta)
        if err_id:
            logger.info("[ERROR_LEARN] Échec stocké [%s] cause=%s", sig, cause)
        return err_id

    def lookup_mitigation(
        self,
        intent_category: str,
        target: str,
        app_context: str,
        min_score: float = MATCH_THRESHOLD,
    ) -> Optional[dict]:
        """
        Cherche un échec similaire passé. Si trouvé (score >= min_score),
        retourne une mitigation. Sinon None.
        """
        sig = build_signature(intent_category, target, app_context)
        hits = self._mm().query_errors(sig, top_k=1, min_score=min_score)
        if not hits:
            return None
        hit = hits[0]
        meta = hit.get("metadata", {})
        cause = meta.get("cause", "other")
        layer = meta.get("grounding_layer_failed") or None
        mitigation = _mitigation_for(cause, layer)
        mitigation["matched_score"] = hit["score"]
        mitigation["cause"] = cause
        logger.info(
            "[ERROR_LEARN] Échec similaire trouvé (score=%.2f, cause=%s) → %s",
            hit["score"], cause, mitigation["strategy"],
        )
        return mitigation


_instance: Optional[ErrorLearning] = None


def get_error_learning() -> ErrorLearning:
    global _instance
    if _instance is None:
        _instance = ErrorLearning()
    return _instance
