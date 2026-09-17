"""
Notifier — Notifications Windows natives via plyer.

MVP 3.0 : Utilisé par le Workflow Engine et le Trigger Engine
pour informer l'utilisateur d'événements.
"""

import logging

logger = logging.getLogger("atlas.notifier")


async def notify(message: str, title: str = "Atlas", duration_seconds: int = 5):
    """Notification Windows native via plyer."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            timeout=duration_seconds,
            app_name="Atlas",
        )
        logger.info("🔔 Notification : %s — %s", title, message)
        return {"success": True, "message": f"Notification affichée : {message}"}
    except Exception as e:
        logger.error("Erreur notification : %s", e)
        return {"success": False, "message": f"Erreur notification : {e}"}
