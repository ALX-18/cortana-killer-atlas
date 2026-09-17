"""
Web Reader — Lecture et résumé de pages web.
"""

import json
import logging
import pathlib
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from core.ollama_client import BASE_URL, MODEL, TEMPERATURE

logger = logging.getLogger("atlas.web_reader")


def _load_web_config() -> dict[str, Any]:
    cfg_path = pathlib.Path(__file__).resolve().parent.parent / "config" / "settings.json"
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f).get("web", {})


_WEB_CFG = _load_web_config()
READER_MAX_CHARS = _WEB_CFG.get("reader_max_chars", 8000)
READ_TIMEOUT = _WEB_CFG.get("search_timeout_seconds", 8)


def _is_valid_http_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in {"http", "https"} and bool(p.netloc)
    except Exception:
        return False


def _clean_html(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    for selector in [".ad", ".ads", "[id*='ad']", "[class*='cookie']", "[class*='banner']"]:
        for tag in soup.select(selector):
            tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else "Sans titre"

    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = " ".join(main.get_text(separator=" ", strip=True).split())
    return title, text


async def read_url(url: str, max_chars: int = READER_MAX_CHARS) -> dict[str, Any]:
    """
    Lit une URL, nettoie le HTML et retourne le contenu texte.
    """
    if not _is_valid_http_url(url):
        return {
            "success": False,
            "url": url,
            "error": "URL invalide. Utilise un lien http/https complet.",
        }

    try:
        try:
            async with httpx.AsyncClient(timeout=READ_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url)
        except httpx.ConnectError as exc:
            if "certificate verify failed" not in str(exc).lower():
                raise
            logger.warning("TLS verify failed for %s, retrying with verify=False", url)
            async with httpx.AsyncClient(timeout=READ_TIMEOUT, follow_redirects=True, verify=False) as client:
                resp = await client.get(url)

        if resp.status_code >= 400:
            return {
                "success": False,
                "url": url,
                "error": f"HTTP {resp.status_code}",
            }

        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type:
            return {
                "success": False,
                "url": url,
                "error": f"Contenu non HTML: {content_type}",
            }

        title, text = _clean_html(resp.text)
        original = text
        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True

        return {
            "success": True,
            "url": url,
            "title": title,
            "content": text,
            "word_count": len(original.split()),
            "truncated": truncated,
        }
    except httpx.TimeoutException:
        return {"success": False, "url": url, "error": "Timeout lors du chargement de la page."}
    except httpx.HTTPError as exc:
        return {"success": False, "url": url, "error": f"Erreur HTTP: {exc}"}
    except Exception as exc:
        logger.error("read_url error for %s: %s", url, exc, exc_info=True)
        return {"success": False, "url": url, "error": f"Erreur inattendue: {exc}"}


async def summarize_url(url: str, max_chars: int = READER_MAX_CHARS) -> dict[str, Any]:
    """
    Lit puis résume une page avec Ollama.
    """
    page = await read_url(url, max_chars=max_chars)
    if not page.get("success"):
        return page

    system_prompt = (
        f"Tu as lu la page suivante : {page['url']}\n"
        f"Titre : {page['title']}\n"
        f"Contenu ({page['word_count']} mots{', tronqué' if page['truncated'] else ''}) :\n"
        f"{page['content']}\n\n"
        "Résume les points clés en français, de façon concise et utile pour l'utilisateur."
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Fais un résumé clair en 5 points maximum."},
        ],
        "stream": False,
        "options": {"temperature": TEMPERATURE},
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{BASE_URL}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        summary = data.get("message", {}).get("content", "").strip()
        return {
            **page,
            "summary": summary,
            "message": f"Résumé de '{page['title']}' prêt.",
        }
    except Exception as exc:
        logger.error("summarize_url error for %s: %s", url, exc, exc_info=True)
        return {
            **page,
            "summary": "",
            "message": "Lecture réussie mais résumé indisponible pour le moment.",
            "summary_error": str(exc),
        }
