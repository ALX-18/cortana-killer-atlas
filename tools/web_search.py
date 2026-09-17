"""
Web Search — Recherche web avec SearXNG local + fallback DuckDuckGo.
v2.1 — Logging explicite, source_reliability, timeout séparé SearXNG.
"""

import asyncio
import json
import logging
import pathlib
from typing import Any
from urllib.parse import quote_plus

import httpx
from ddgs import DDGS

from core.memory_manager import get_memory_manager

logger = logging.getLogger("atlas.web_search")


def _load_web_config() -> dict[str, Any]:
    cfg_path = pathlib.Path(__file__).resolve().parent.parent / "config" / "settings.json"
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f).get("web", {})


_WEB_CFG = _load_web_config()
SEARXNG_URL = _WEB_CFG.get("searxng_url", "http://localhost:8888")
SEARCH_TIMEOUT = _WEB_CFG.get("search_timeout_seconds", 8)
SEARXNG_TIMEOUT = _WEB_CFG.get("searxng_timeout_seconds", 3)
DDGS_TIMEOUT = _WEB_CFG.get("ddgs_timeout_seconds", 5)
LOG_FAILURES = _WEB_CFG.get("search_log_failures", True)

# Reliability tags
_RELIABILITY = {
    "searxng": "high",
    "duckduckgo": "medium",
    "duckduckgo_fallback": "medium",
    "fallback_link": "low",
}


def _tag_reliability(results: list[dict], source: str, fallback_note: str = "") -> list[dict]:
    """Add source_reliability metadata to each result."""
    reliability = _RELIABILITY.get(source, "unknown")
    for r in results:
        r["source_reliability"] = reliability
        if fallback_note:
            r["fallback_note"] = fallback_note
    return results


async def _search_searxng(query: str, max_results: int) -> list[dict[str, str]]:
    url = f"{SEARXNG_URL}/search"
    params = {
        "q": query,
        "format": "json",
        "language": "fr",
        "safesearch": 1,
    }
    headers = {
        "User-Agent": "Atlas/2.1 (+local assistant)",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=SEARXNG_TIMEOUT) as client:
        resp = await client.get(url, params=params, headers=headers)

        # Explicit status check with logging
        if resp.status_code != 200:
            if LOG_FAILURES:
                logger.warning(
                    "SearXNG HTTP %d pour query='%s' — bascule vers fallback DDG",
                    resp.status_code, query,
                )
            raise httpx.HTTPStatusError(
                f"SearXNG returned {resp.status_code}",
                request=resp.request,
                response=resp,
            )

        data = resp.json()

    results = []
    for item in data.get("results", [])[:max_results]:
        results.append(
            {
                "title": item.get("title", "Sans titre"),
                "url": item.get("url", ""),
                "snippet": item.get("content", "") or item.get("snippet", ""),
                "source": "searxng",
            }
        )
    return results


def _search_duckduckgo_sync(query: str, max_results: int) -> list[dict[str, str]]:
    results = []
    with DDGS(timeout=DDGS_TIMEOUT) as ddgs:
        for item in ddgs.text(query, max_results=max_results):
            results.append(
                {
                    "title": item.get("title", "Sans titre"),
                    "url": item.get("href", ""),
                    "snippet": item.get("body", ""),
                    "source": "duckduckgo",
                }
            )
    return results


async def _search_duckduckgo(query: str, max_results: int) -> list[dict[str, str]]:
    return await asyncio.to_thread(_search_duckduckgo_sync, query, max_results)


async def _log_search_fallback(query: str, stage: str, result: str, error: str | None = None):
    """Write structured fallback/degraded search events to atlas_actions.jsonl."""
    try:
        from core.atlas_logger import log_action

        await log_action(
            user_input=query,
            intent_category="web",
            intent_verb="search",
            tool=f"web_search:{stage}",
            target=query,
            result=result,
            error=error,
            latency_ms=0,
            retry_count=0,
            grounding_layer=None,
            pipeline_stage="web_search",
        )
    except Exception as exc:
        logger.debug("Structured fallback log failed: %s", exc)


async def search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """
    1. Tente SearXNG local (timeout dédié searxng_timeout_seconds)
    2. Si status != 200 OU résultats vides OU exception :
       → logger le problème avec le status code exact
       → passer immédiatement au fallback DDG
       → tagger les résultats avec source="duckduckgo_fallback"
    3. Si DDG échoue aussi → retourner une erreur propre
    4. Sauvegarde l'action en mémoire
    """
    source = "searxng"
    fallback_note = ""
    results: list[dict[str, str]] = []

    # --- SearXNG attempt ---
    try:
        results = await _search_searxng(query, max_results)
        if not results:
            if LOG_FAILURES:
                logger.info("SearXNG: 0 résultat pour '%s', fallback DuckDuckGo", query)
            fallback_note = "SearXNG a retourné 0 résultats"
            source = "duckduckgo_fallback"
            results = await _search_duckduckgo(query, max_results)
            await _log_search_fallback(query, "ddgs_fallback", "success", fallback_note)
    except httpx.HTTPStatusError as exc:
        # Already logged inside _search_searxng
        fallback_note = f"SearXNG HTTP {exc.response.status_code}"
        source = "duckduckgo_fallback"
        try:
            results = await _search_duckduckgo(query, max_results)
            await _log_search_fallback(query, "ddgs_fallback", "success", fallback_note)
        except Exception as ddg_exc:
            if LOG_FAILURES:
                logger.error("DDG fallback échoué aussi : %s", ddg_exc)
            await _log_search_fallback(query, "ddgs_fallback", "failure", str(ddg_exc))
    except Exception as exc:
        if LOG_FAILURES:
            logger.warning(
                "SearXNG indisponible (%s: %s), fallback DuckDuckGo",
                type(exc).__name__, exc,
            )
        fallback_note = f"SearXNG indisponible ({type(exc).__name__})"
        source = "duckduckgo_fallback"
        try:
            results = await _search_duckduckgo(query, max_results)
            await _log_search_fallback(query, "ddgs_fallback", "success", fallback_note)
        except Exception as ddg_exc:
            if LOG_FAILURES:
                logger.error("DDG fallback échoué aussi : %s", ddg_exc)
            await _log_search_fallback(query, "ddgs_fallback", "failure", str(ddg_exc))

    # --- Both failed ---
    if not results:
        source = "fallback_link"
        fallback_note = fallback_note or "Aucun fournisseur de recherche disponible"
        results = [
            {
                "title": f"Recherche web pour : {query}",
                "url": f"https://duckduckgo.com/?q={quote_plus(query)}",
                "snippet": (
                    "La recherche est indisponible. Voici ce que je sais sur ce sujet : "
                    f"je ne peux pas vérifier des sources web en ce moment pour '{query}', "
                    "mais je peux te donner une explication générale si tu veux."
                ),
                "source": source,
            }
        ]
        if LOG_FAILURES:
            logger.error(
                "Recherche web totalement indisponible pour '%s' — tried: [searxng, duckduckgo]",
                query,
            )
        await _log_search_fallback(query, "degraded_total", "failure", fallback_note)

    # --- Tag reliability ---
    _tag_reliability(results, source, fallback_note)

    # --- Save to memory ---
    try:
        mem = get_memory_manager()
        mem.save(
            category="action_history",
            content=f"Recherche effectuée : '{query}'. {len(results)} résultats trouvés via {source}."
            + (f" Note: {fallback_note}" if fallback_note else ""),
            metadata={"query": query, "results": len(results), "source": source},
        )
    except Exception as exc:
        logger.debug("Impossible de sauvegarder la recherche en mémoire: %s", exc)

    return results
