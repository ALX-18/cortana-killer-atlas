"""
Browser Bridge — Pont WebSocket entre Atlas et l'extension navigateur.

Architecture :
- Atlas lance un serveur WebSocket sur le port 9999
- L'extension navigateur (content script) se connecte en tant que client
- Atlas envoie des commandes (navigate, click, type, scroll, get_content)
- L'extension exécute et renvoie le résultat

Le bridge supporte plusieurs navigateurs simultanément.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Optional

import websockets
from websockets.asyncio.server import Server, ServerConnection

logger = logging.getLogger("atlas.browser_bridge")


# --------------------------------------------------------------------------- #
#  Browser Bridge
# --------------------------------------------------------------------------- #

class BrowserBridge:
    """Pont WebSocket entre Atlas et les extensions navigateur."""

    def __init__(self, port: int = 9999):
        self.port = port
        self._server: Optional[Server] = None
        self._connections: dict[str, ServerConnection] = {}  # client_id → ws
        self._pending_responses: dict[str, asyncio.Future] = {}  # request_id → future
        self._running = False

    # ----------- Lifecycle ----------- #

    async def start(self):
        """Démarre le serveur WebSocket."""
        if self._running:
            logger.warning("Browser bridge déjà en cours d'exécution")
            return

        try:
            self._server = await websockets.serve(
                self._handle_connection,
                "127.0.0.1",
                self.port,
            )
            self._running = True
            logger.info("🔌 Browser Bridge WebSocket démarré sur ws://127.0.0.1:%d", self.port)
        except OSError as e:
            logger.error("Impossible de démarrer le Browser Bridge sur le port %d : %s", self.port, e)
            raise

    async def stop(self):
        """
        Arrête le serveur WebSocket.

        v5.1 corrective : Python 3.12 + ProactorEventLoop sur Windows lève parfois
        une AssertionError dans `_attach`/`_sockets is not None` lors du teardown
        des sockets WebSocket. Bug latent de CPython, on log et on continue.
        """
        if not self._server:
            return

        # 1) Cancel any pending response futures so awaiters don't hang
        for req_id, future in list(self._pending_responses.items()):
            if not future.done():
                try:
                    future.set_exception(ConnectionError("Bridge stopping"))
                except Exception:
                    pass
            self._pending_responses.pop(req_id, None)

        # 2) Close server with tolerant cleanup (Windows Proactor bug mitigation)
        try:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("[shutdown] Bridge wait_closed timeout (2s) — continuing")
        except (AssertionError, RuntimeError) as e:
            # Known Python 3.12 + Proactor + Windows socket cleanup issue
            logger.warning(
                "[shutdown] Socket cleanup non-fatal error (Python 3.12 Windows): %s", e,
            )
        except Exception as e:
            logger.warning("[shutdown] Bridge stop unexpected: %s", e)
        finally:
            self._running = False
            self._connections.clear()
            self._server = None
            logger.info("🔌 Browser Bridge arrêté.")

    def is_connected(self) -> bool:
        """Vérifie si au moins une extension navigateur est connectée."""
        return len(self._connections) > 0

    @property
    def connected_clients(self) -> int:
        """Nombre de clients connectés."""
        return len(self._connections)

    # ----------- WebSocket handler ----------- #

    async def _handle_connection(self, websocket: ServerConnection):
        """Gère une connexion entrante d'une extension navigateur."""
        client_id = str(uuid.uuid4())[:8]
        self._connections[client_id] = websocket
        # Track which request IDs belong to this client
        self._client_requests: dict[str, set[str]] = getattr(self, '_client_requests', {})
        self._client_requests[client_id] = set()
        logger.info("🌐 Extension navigateur connectée (client_id=%s)", client_id)

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(client_id, data)
                except json.JSONDecodeError:
                    logger.warning("Message non-JSON reçu du client %s : %s", client_id, message[:100])
        except websockets.exceptions.ConnectionClosed:
            logger.info("🔌 Extension navigateur déconnectée (client_id=%s)", client_id)
        finally:
            self._connections.pop(client_id, None)
            # Résoudre uniquement les futures en attente pour CE client
            client_reqs = self._client_requests.pop(client_id, set())
            for req_id in client_reqs:
                future = self._pending_responses.pop(req_id, None)
                if future and not future.done():
                    future.set_exception(ConnectionError("Extension navigateur déconnectée"))

    async def _handle_message(self, client_id: str, data: dict):
        """Traite un message reçu de l'extension."""
        msg_type = data.get("type", "")

        if msg_type == "response":
            # Réponse à une commande envoyée par Atlas
            request_id = data.get("request_id", "")
            if request_id in self._pending_responses:
                future = self._pending_responses.pop(request_id)
                if not future.done():
                    future.set_result(data.get("result", {}))
            else:
                logger.debug("Réponse sans request_id correspondant : %s", request_id)

        elif msg_type == "event":
            # Événement spontané de l'extension (page change, etc.)
            logger.debug("Événement navigateur : %s", data.get("event", "unknown"))

        elif msg_type == "ping":
            # Heartbeat
            ws = self._connections.get(client_id)
            if ws:
                await ws.send(json.dumps({"type": "pong"}))

        else:
            logger.debug("Message inconnu du client %s : %s", client_id, msg_type)

    # ----------- Envoi de commandes ----------- #

    async def send_command(self, command: str, params: dict = None, timeout: float = 10.0) -> dict[str, Any]:
        """
        Envoie une commande à l'extension navigateur connectée.
        Attend la réponse avec timeout.

        Args:
            command: Nom de la commande (navigate, click, type, scroll, get_content, etc.)
            params: Paramètres de la commande
            timeout: Timeout en secondes

        Returns:
            Résultat de la commande ou erreur
        """
        if not self._connections:
            return {"success": False, "message": "Aucune extension navigateur connectée. Installez l'extension Atlas."}

        # Prendre le premier client connecté
        client_id = next(iter(self._connections))
        ws = self._connections[client_id]

        request_id = str(uuid.uuid4())[:12]
        message = {
            "type": "command",
            "request_id": request_id,
            "command": command,
            "params": params or {},
        }

        # Créer le future pour la réponse
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_responses[request_id] = future
        # Associer la requête à ce client pour le cleanup
        client_reqs = getattr(self, '_client_requests', {})
        if client_id in client_reqs:
            client_reqs[client_id].add(request_id)

        try:
            await ws.send(json.dumps(message))
            result = await asyncio.wait_for(future, timeout=timeout)
            return {"success": True, "result": result}
        except asyncio.TimeoutError:
            self._pending_responses.pop(request_id, None)
            return {"success": False, "message": f"Timeout ({timeout}s) — l'extension n'a pas répondu."}
        except ConnectionError as e:
            self._pending_responses.pop(request_id, None)
            return {"success": False, "message": f"Connexion perdue avec l'extension : {e}"}
        except Exception as e:
            self._pending_responses.pop(request_id, None)
            return {"success": False, "message": f"Erreur bridge : {e}"}


# --------------------------------------------------------------------------- #
#  Instance globale
# --------------------------------------------------------------------------- #

_bridge: Optional[BrowserBridge] = None


def get_bridge() -> BrowserBridge:
    """Retourne l'instance globale du bridge (lazy init)."""
    global _bridge
    if _bridge is None:
        _bridge = BrowserBridge()
    return _bridge


# --------------------------------------------------------------------------- #
#  Fonctions publiques (utilisées par intent_engine)
# --------------------------------------------------------------------------- #

async def browser_navigate(url: str) -> dict[str, Any]:
    """Navigue vers une URL dans l'onglet actif de l'extension."""
    bridge = get_bridge()
    if not bridge.is_connected():
        return {"success": False, "message": "Extension navigateur non connectée."}
    return await bridge.send_command("navigate", {"url": url})


async def browser_new_tab(url: str = "") -> dict[str, Any]:
    """Ouvre un nouvel onglet dans le navigateur connecté."""
    bridge = get_bridge()
    if not bridge.is_connected():
        return {"success": False, "message": "Extension navigateur non connectée."}
    return await bridge.send_command("new_tab", {"url": url})


async def browser_ext_click(selector: str) -> dict[str, Any]:
    """Clique sur un élément dans la page active via l'extension."""
    bridge = get_bridge()
    if not bridge.is_connected():
        return {"success": False, "message": "Extension navigateur non connectée."}
    return await bridge.send_command("click", {"selector": selector})


async def browser_ext_type(selector: str, text: str) -> dict[str, Any]:
    """Tape du texte dans un champ de la page active via l'extension."""
    bridge = get_bridge()
    if not bridge.is_connected():
        return {"success": False, "message": "Extension navigateur non connectée."}
    return await bridge.send_command("type", {"selector": selector, "text": text})


async def browser_ext_scroll(direction: str = "down", amount: int = 500) -> dict[str, Any]:
    """Scroll dans la page active via l'extension."""
    bridge = get_bridge()
    if not bridge.is_connected():
        return {"success": False, "message": "Extension navigateur non connectée."}
    return await bridge.send_command("scroll", {"direction": direction, "amount": amount})


async def browser_ext_get_content(selector: str = "body") -> dict[str, Any]:
    """Récupère le contenu texte d'un élément de la page."""
    bridge = get_bridge()
    if not bridge.is_connected():
        return {"success": False, "message": "Extension navigateur non connectée."}
    return await bridge.send_command("get_content", {"selector": selector})


async def browser_ext_get_url() -> dict[str, Any]:
    """Récupère l'URL de l'onglet actif."""
    bridge = get_bridge()
    if not bridge.is_connected():
        return {"success": False, "message": "Extension navigateur non connectée."}
    return await bridge.send_command("get_url", {})


def browser_bridge_status() -> dict[str, Any]:
    """Retourne l'état de la connexion bridge."""
    bridge = get_bridge()
    return {
        "success": True,
        "connected": bridge.is_connected(),
        "clients": bridge.connected_clients,
        "port": bridge.port,
    }
