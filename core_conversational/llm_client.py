"""
LLM Client — Client Ollama cross-platform (httpx pur). Aucune dépendance Windows.

Fournit la génération + la garde linguistique (anti-dérive non-latine, P2 v6.0.1).
Partagé entre Atlas (Windows) et Manman (Mac).
"""

import json
import re
from typing import AsyncGenerator, Optional

import httpx

# --- Détection de scripts non-latins (dérive linguistique) ---
_NON_LATIN_RE = re.compile(
    r"[一-鿿"   # CJK unified (chinois)
    r"぀-ゟ"    # hiragana
    r"゠-ヿ"    # katakana
    r"가-힯"    # hangul (coréen)
    r"Ѐ-ӿ"    # cyrillique
    r"؀-ۿ]"   # arabe
)

LANG_FALLBACK_MESSAGE = "Je suis désolé, j'ai eu un souci, peux-tu reformuler ?"


def contains_non_latin_script(text: str) -> bool:
    """True si le texte contient des caractères CJK/cyrillique/arabe."""
    return bool(_NON_LATIN_RE.search(text or ""))


class LLMClient:
    """Client de chat Ollama minimal et cross-platform."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:7b",
        temperature: float = 0.7,
        keep_alive: str = "10m",
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.keep_alive = keep_alive
        self.timeout = timeout

    def _payload(self, system_prompt: str, user_message: str,
                 history: Optional[list[dict]] = None) -> dict:
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {"temperature": self.temperature},
        }

    async def stream(
        self, system_prompt: str, user_message: str,
        history: Optional[list[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        """Yield les tokens en streaming."""
        payload = self._payload(system_prompt, user_message, history)
        url = f"{self.base_url}/api/chat"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break

    async def _complete_raw(self, system_prompt: str, user_message: str,
                            history: Optional[list[dict]] = None) -> str:
        parts: list[str] = []
        async for tok in self.stream(system_prompt, user_message, history):
            parts.append(tok)
        return "".join(parts)

    async def complete(self, system_prompt: str, user_message: str,
                       history: Optional[list[dict]] = None) -> str:
        """
        Génération complète avec garde linguistique :
        dérive non-latine → retry FR strict → fallback générique.
        """
        result = await self._complete_raw(system_prompt, user_message, history)
        if not contains_non_latin_script(result):
            return result

        retry_msg = (
            f"{user_message}\n\nIMPORTANT : réponds UNIQUEMENT en français, sans aucun "
            "caractère chinois, japonais, coréen, cyrillique ou arabe."
        )
        result2 = await self._complete_raw(system_prompt, retry_msg, history)
        if not contains_non_latin_script(result2):
            return result2
        return LANG_FALLBACK_MESSAGE
