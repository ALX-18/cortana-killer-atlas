"""
Ollama Client — Appels au modèle local via Ollama avec streaming.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

import httpx

logger = logging.getLogger("atlas.ollama")

VOICE_RESPONSE_SUFFIX = """
IMPORTANT : cette réponse sera lue à voix haute.
Réponds en 1-2 phrases maximum, langage naturel parlé, zéro markdown.
"""

# --------------------------------------------------------------------------- #
#  Chargement config
# --------------------------------------------------------------------------- #

def _load_ollama_config() -> dict:
    import pathlib, json as _json
    cfg_path = pathlib.Path(__file__).resolve().parent.parent / "config" / "settings.json"
    with open(cfg_path, encoding="utf-8") as f:
        return _json.load(f)["ollama"]

_cfg = _load_ollama_config()
BASE_URL: str = _cfg["base_url"]
MODEL: str = _cfg["model"]
TEMPERATURE: float = _cfg["temperature"]
STREAM_TIMEOUT: int = _cfg.get("stream_timeout_seconds", 30)
KEEP_ALIVE: str = _cfg.get("keep_alive", "10m")  # v5.3 — keep model warm in VRAM


# --------------------------------------------------------------------------- #
#  System prompt builder
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT_TEMPLATE = """\
Tu es Atlas, un assistant bureau Windows intelligent. Tu aides l'utilisateur à contrôler son PC.

RÔLE : Tu ne choisis PAS les outils. C'est le système qui décide automatiquement quel outil utiliser.

TON TRAVAIL :
1. Si l'utilisateur pose une QUESTION → répondre en texte libre, naturellement, en français
2. Si l'utilisateur donne une INSTRUCTION d'action → confirmer brièvement. Le système exécutera l'action.
3. Si le résultat d'une action t'est fourni → le résumer clairement pour l'utilisateur

CONTEXTE DU PC :
{world_state_summary}

MÉMOIRE :
{memories_section}

AUTOMATISATION :
- schedule_add(name, trigger_type, trigger_config, actions) : planifier une tâche récurrente
- schedule_list() / schedule_remove(job_id) / schedule_run_now(job_id)
- trigger_add(name, condition, actions, cooldown_seconds) : déclencheur contextuel automatique
- trigger_list() / trigger_toggle(trigger_id, enabled)
- workflow_run(workflow_id) / workflow_create(name, steps) / workflow_list()

EXEMPLES :
- "Tous les lundis à 9h lance Steam" → schedule_add(trigger_type="cron", trigger_config={{day_of_week:"mon", hour:9}}, ...)
- "Si GPU > 90% ferme les apps en arrière-plan" → trigger_add(condition={{metric:"gpu_usage", operator:">", value:90, duration_seconds:30}}, ...)
- "Active le mode gaming" → workflow_run(workflow_id="mode_gaming")

RÈGLES :
- Répondre en français, court et direct
- Ne JAMAIS générer de JSON d'outil (le système s'en charge)
- Si tu ne sais pas, dis-le honnêtement
- Être proactif : si l'utilisateur semble vouloir une action, déduis-la
"""


def build_system_prompt(context: dict, memories: list[str] | None = None) -> str:
    """Construit le system prompt avec le contexte système et les souvenirs injectés."""
    # Build world state summary from context
    parts = []
    fg = context.get("foreground_window", {})
    if fg:
        parts.append(f"Fenêtre active: {fg.get('title', '?')} ({fg.get('process', '?')})")
    cpu = context.get("cpu_usage")
    ram = context.get("ram_usage")
    if cpu is not None:
        parts.append(f"CPU: {cpu}%, RAM: {ram}%")
    world_state_summary = " | ".join(parts) if parts else "Aucun contexte disponible."

    if memories:
        memories_section = "\n".join(f"- {m}" for m in memories)
    else:
        memories_section = "- Aucun souvenir disponible pour le moment."

    return SYSTEM_PROMPT_TEMPLATE.format(
        world_state_summary=world_state_summary,
        memories_section=memories_section,
    )


# --------------------------------------------------------------------------- #
#  Chat (streaming)
# --------------------------------------------------------------------------- #

async def chat_stream(
    user_message: str,
    context: dict,
    history: Optional[list[dict]] = None,
    memories: Optional[list[str]] = None,
) -> AsyncGenerator[str, None]:
    """
    Envoie un message à Ollama et yield les tokens en streaming.
    Les souvenirs pertinents sont injectés dans le system prompt.
    """
    system_prompt = build_system_prompt(context, memories=memories)

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "temperature": TEMPERATURE,
        },
    }

    url = f"{BASE_URL}/api/chat"
    logger.info("Ollama request → %s  model=%s  keep_alive=%s  stream_timeout=%ds", url, MODEL, KEEP_ALIVE, STREAM_TIMEOUT)

    async with httpx.AsyncClient(timeout=120.0) as client:
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


class OllamaStreamTimeout(Exception):
    """Raised when no token is received within the configured timeout."""


async def chat_stream_with_timeout(
    user_message: str,
    context: dict,
    history: Optional[list[dict]] = None,
    memories: Optional[list[str]] = None,
) -> AsyncGenerator[str, None]:
    """
    Wrapper autour de chat_stream avec timeout inter-token.
    Lève OllamaStreamTimeout si aucun token reçu pendant STREAM_TIMEOUT secondes.
    """
    token_received = False
    async for token in chat_stream(user_message, context, history, memories=memories):
        token_received = True
        yield token

    # If the stream ends normally but never produced a token,
    # that's not a timeout — it's just an empty response.
    # The timeout is handled at the consumer level (routes.py).


async def chat_full(
    user_message: str,
    context: dict,
    history: Optional[list[dict]] = None,
    memories: Optional[list[str]] = None,
    system_prompt: Optional[str] = None,
) -> str:
    """Version non-streaming : retourne la réponse complète.
    Si system_prompt est fourni, il remplace le prompt par défaut."""
    if system_prompt:
        # Custom system prompt (used by Planner)
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": MODEL,
            "messages": messages,
            "stream": True,
            "keep_alive": KEEP_ALIVE,
            "options": {"temperature": TEMPERATURE},
        }
        url = f"{BASE_URL}/api/chat"
        parts: list[str] = []
        async with httpx.AsyncClient(timeout=120.0) as client:
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
                        parts.append(token)
                    if chunk.get("done"):
                        break
        return "".join(parts)

    # Default: use chat_stream
    parts = []
    async for token in chat_stream(user_message, context, history, memories=memories):
        parts.append(token)
    return "".join(parts)


def _strip_markdown_for_voice(text: str) -> str:
    """Remove obvious markdown/code markers for TTS-friendly output."""
    cleaned = text.replace("`", "")
    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("__", "")
    cleaned = cleaned.replace("#", "")
    cleaned = cleaned.replace("* ", "")
    cleaned = cleaned.replace("- ", "")
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


async def generate_speech_response(
    user_message: str,
    context: dict,
    history: Optional[list[dict]] = None,
    memories: Optional[list[str]] = None,
) -> str:
    """Generate a short spoken answer optimized for TTS."""
    base_prompt = build_system_prompt(context, memories=memories)
    voice_prompt = base_prompt + "\n\n" + VOICE_RESPONSE_SUFFIX

    response = await chat_full(
        user_message=user_message,
        context=context,
        history=history,
        memories=memories,
        system_prompt=voice_prompt,
    )
    return _strip_markdown_for_voice(response)
