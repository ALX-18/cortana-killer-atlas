"""
Browser Controller — Navigation pilotée via Playwright.
"""

import json
import logging
import pathlib
from typing import Any

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger("atlas.browser")


def _load_web_config() -> dict[str, Any]:
    cfg_path = pathlib.Path(__file__).resolve().parent.parent / "config" / "settings.json"
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f).get("web", {})


_WEB_CFG = _load_web_config()
BROWSER_TIMEOUT_MS = int(_WEB_CFG.get("browser_action_timeout_seconds", 30) * 1000)


class BrowserController:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def _ensure_ready(self):
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        if self._browser is None:
            self._browser = await self._playwright.chromium.launch(headless=False)
        if self._context is None:
            self._context = await self._browser.new_context()
        if self._page is None:
            self._page = await self._context.new_page()
        self._page.set_default_timeout(BROWSER_TIMEOUT_MS)

    async def open_url(self, url: str):
        await self._ensure_ready()
        logger.info("Browser open_url: %s", url)
        await self._page.goto(url, timeout=BROWSER_TIMEOUT_MS, wait_until="domcontentloaded")
        return {"success": True, "url": self._page.url, "message": f"Navigateur ouvert sur {self._page.url}"}

    async def click(self, selector: str):
        await self._ensure_ready()
        logger.info("Browser click: %s", selector)
        try:
            await self._page.click(selector, timeout=BROWSER_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            await self._page.get_by_text(selector).first.click(timeout=BROWSER_TIMEOUT_MS)
        return {"success": True, "message": f"Clic effectué sur '{selector}'"}

    async def type_text(self, selector: str, text: str):
        await self._ensure_ready()
        logger.info("Browser type_text: %s", selector)
        await self._page.fill(selector, text, timeout=BROWSER_TIMEOUT_MS)
        return {"success": True, "message": f"Texte saisi dans '{selector}'"}

    async def scroll(self, direction: str, amount: int):
        await self._ensure_ready()
        amount = max(100, int(amount))
        delta = amount if direction.lower() == "down" else -amount
        await self._page.mouse.wheel(0, delta)
        return {"success": True, "message": f"Scroll {direction} de {amount}px"}

    async def get_current_url(self) -> str:
        await self._ensure_ready()
        return self._page.url

    async def close(self):
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._page = None
        return {"success": True, "message": "Navigateur piloté fermé."}


_BROWSER = BrowserController()


async def browser_open(url: str):
    return await _BROWSER.open_url(url)


async def browser_click(selector: str):
    return await _BROWSER.click(selector)


async def browser_type(selector: str, text: str):
    return await _BROWSER.type_text(selector, text)


async def browser_scroll(direction: str, amount: int):
    return await _BROWSER.scroll(direction, amount)


async def browser_current_url():
    current = await _BROWSER.get_current_url()
    return {"success": True, "url": current, "message": f"URL active: {current}"}


async def browser_close():
    return await _BROWSER.close()
