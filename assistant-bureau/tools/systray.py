"""Atlas systray icon management (Windows)."""

import logging
import threading

logger = logging.getLogger("atlas.systray")


class AtlasSystray:
    """System tray icon with Atlas state and actions."""

    def __init__(self, on_open=None, on_toggle_voice=None, on_quit=None):
        self._on_open = on_open
        self._on_toggle_voice = on_toggle_voice
        self._on_quit = on_quit

        self._state = "idle"
        self._running = False

        self._icon = None
        self._thread = None
        self._voice_enabled = False

        self._pystray = None
        self._PIL_Image = None
        self._PIL_ImageDraw = None

        try:
            import pystray
            from PIL import Image, ImageDraw

            self._pystray = pystray
            self._PIL_Image = Image
            self._PIL_ImageDraw = ImageDraw
        except Exception as e:
            logger.warning("Systray dependencies unavailable: %s", e)

    def start(self):
        """Start systray in a dedicated thread (pystray is blocking)."""
        if self._running:
            return
        if self._pystray is None:
            logger.warning("Systray disabled because pystray/Pillow is unavailable.")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_blocking, daemon=True)
        self._thread.start()
        logger.info("Systray started.")

    def stop(self):
        """Stop systray icon and thread loop."""
        self._running = False
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
        self._icon = None

    def set_state(self, state: str):
        """Set visual state: idle | listening | processing | error."""
        self._state = state
        if self._icon is not None:
            try:
                self._icon.icon = self._build_icon(state)
                self._icon.title = f"Atlas ({state})"
            except Exception:
                pass

    def set_voice_enabled(self, enabled: bool):
        self._voice_enabled = bool(enabled)
        if self._icon is not None:
            try:
                self._icon.menu = self._build_menu()
                self._icon.update_menu()
            except Exception:
                pass

    def _run_blocking(self):
        self._icon = self._pystray.Icon(
            "Atlas",
            self._build_icon(self._state),
            "Atlas",
            self._build_menu(),
        )
        self._icon.run()

    def _build_menu(self):
        Menu = self._pystray.Menu
        MenuItem = self._pystray.MenuItem

        voice_label = "Voix OFF" if self._voice_enabled else "Voix ON"

        return Menu(
            MenuItem("Ouvrir", self._on_menu_open),
            MenuItem(voice_label, self._on_menu_toggle_voice),
            MenuItem("Quitter", self._on_menu_quit),
        )

    def _on_menu_open(self, _icon=None, _item=None):
        if callable(self._on_open):
            self._on_open()

    def _on_menu_toggle_voice(self, _icon=None, _item=None):
        self._voice_enabled = not self._voice_enabled
        if callable(self._on_toggle_voice):
            self._on_toggle_voice(self._voice_enabled)
        if self._icon is not None:
            self._icon.menu = self._build_menu()
            self._icon.update_menu()

    def _on_menu_quit(self, _icon=None, _item=None):
        if callable(self._on_quit):
            self._on_quit()
        self.stop()

    def _build_icon(self, state: str):
        """Build a small square icon with color by state."""
        color_map = {
            "idle": (70, 130, 180),
            "listening": (46, 204, 113),
            "processing": (243, 156, 18),
            "error": (231, 76, 60),
        }
        color = color_map.get(state, color_map["idle"])

        image = self._PIL_Image.new("RGB", (64, 64), (25, 25, 30))
        draw = self._PIL_ImageDraw.Draw(image)
        draw.ellipse((10, 10, 54, 54), fill=color)
        draw.rectangle((28, 16, 36, 48), fill=(245, 245, 245))
        return image
