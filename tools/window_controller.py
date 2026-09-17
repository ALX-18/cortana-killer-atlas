"""
Window Controller — Interaction DANS les fenêtres d'applications ouvertes.

Utilise PyAutoGUI + Win32 API pour :
- Trouver / focaliser des fenêtres par titre
- Cliquer, taper du texte, envoyer des raccourcis clavier
- Prendre des captures d'écran d'une fenêtre
"""

import logging
import time
from typing import Any

import pyautogui
import pygetwindow as gw
import pyperclip

logger = logging.getLogger("atlas.window_controller")

# Sécurité PyAutoGUI
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.15

# --------------------------------------------------------------------------- #
#  Win32 helpers (optionnels — fallback si pygetwindow échoue)
# --------------------------------------------------------------------------- #

try:
    import win32gui
    import win32con
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    logger.warning("pywin32 non disponible — certaines fonctions de fenêtre seront limitées")

try:
    from pywinauto import Application as PywinautoApplication
    HAS_PYWINAUTO = True
except ImportError:
    HAS_PYWINAUTO = False

# --------------------------------------------------------------------------- #
#  Alias FR/EN pour les noms d'applications courantes
# --------------------------------------------------------------------------- #

_WINDOW_ALIASES: dict[str, list[str]] = {
    "notepad": ["bloc-notes", "bloc notes", "notepad"],
    "bloc-notes": ["bloc-notes", "bloc notes", "notepad"],
    "bloc notes": ["bloc-notes", "bloc notes", "notepad"],
    "task manager": ["gestionnaire des tâches", "task manager"],
    "gestionnaire des tâches": ["gestionnaire des tâches", "task manager"],
    "calculator": ["calculatrice", "calculator"],
    "calculatrice": ["calculatrice", "calculator"],
    "file explorer": ["explorateur de fichiers", "file explorer", "explorer"],
    "explorateur de fichiers": ["explorateur de fichiers", "file explorer", "explorer"],
    "settings": ["paramètres", "settings"],
    "paramètres": ["paramètres", "settings"],
    "discord": ["discord", "discord.exe"],
    "opera gx": ["opera gx", "opera", "opera internet browser"],
    "opera": ["opera gx", "opera", "opera internet browser"],
}


def _resolve_aliases(title: str) -> list[str]:
    """Retourne une liste de variantes à chercher pour le titre donné."""
    key = title.lower().strip()
    if key in _WINDOW_ALIASES:
        return _WINDOW_ALIASES[key]
    return [title]


def _enum_windows_by_title(title_fragment: str) -> list[dict]:
    """Enumère toutes les fenêtres dont le titre contient le fragment (Win32)."""
    if not HAS_WIN32:
        return []
    results = []
    title_lower = title_fragment.lower()

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            text = win32gui.GetWindowText(hwnd)
            if text and title_lower in text.lower():
                rect = win32gui.GetWindowRect(hwnd)
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                results.append({
                    "hwnd": hwnd,
                    "title": text,
                    "pid": pid,
                    "rect": {"left": rect[0], "top": rect[1], "right": rect[2], "bottom": rect[3]},
                })
        return True

    win32gui.EnumWindows(callback, None)
    return results


# --------------------------------------------------------------------------- #
#  Classe principale
# --------------------------------------------------------------------------- #

class WindowController:
    """Contrôleur pour interagir avec les fenêtres d'applications Windows."""

    # ------- Recherche / Focus ------- #

    @staticmethod
    def find_window(title: str) -> dict[str, Any]:
        """
        Recherche une fenêtre par titre (partiel).
        Retourne les fenêtres correspondantes.
        """
        for alias in _resolve_aliases(title):
            # Essai avec pygetwindow
            try:
                windows = gw.getWindowsWithTitle(alias)
                if windows:
                    matches = []
                    for w in windows:
                        matches.append({
                            "title": w.title,
                            "left": w.left,
                            "top": w.top,
                            "width": w.width,
                            "height": w.height,
                            "visible": w.visible,
                            "minimized": w.isMinimized,
                        })
                    return {"success": True, "windows": matches, "count": len(matches)}
            except Exception as e:
                logger.debug("pygetwindow find failed for '%s', trying Win32: %s", alias, e)

            # Fallback Win32
            win32_results = _enum_windows_by_title(alias)
            if win32_results:
                return {"success": True, "windows": win32_results, "count": len(win32_results)}

        return {"success": False, "message": f"Aucune fenêtre trouvée contenant '{title}'.", "windows": []}

    @staticmethod
    def focus_window(title: str) -> dict[str, Any]:
        """
        Met au premier plan la fenêtre correspondant au titre.
        Gère les cas minimisés et les restrictions Win32.
        """
        retries = [0.2, 0.5, 1.0]
        for attempt, delay in enumerate(retries, start=1):
            for alias in _resolve_aliases(title):
                # 1) pywinauto attempt
                if HAS_PYWINAUTO:
                    try:
                        app = PywinautoApplication(backend="uia").connect(title_re=f".*{alias}.*", timeout=1)
                        window = app.top_window()
                        window.set_focus()
                        time.sleep(0.2)
                        return {
                            "success": True,
                            "message": f"Fenêtre '{window.window_text()}' mise au premier plan (pywinauto).",
                        }
                    except Exception as e:
                        logger.debug("pywinauto focus failed for '%s' (attempt %d): %s", alias, attempt, e)

                # 2) pygetwindow attempt
                try:
                    windows = gw.getWindowsWithTitle(alias)
                    if windows:
                        w = windows[0]
                        if w.isMinimized:
                            w.restore()
                            time.sleep(0.2)
                        w.activate()
                        time.sleep(0.2)
                        return {
                            "success": True,
                            "message": f"Fenêtre '{w.title}' mise au premier plan (pygetwindow).",
                        }
                except Exception as e:
                    logger.debug("pygetwindow focus failed for '%s' (attempt %d): %s", alias, attempt, e)

                # 3) Win32 fallback
                if HAS_WIN32:
                    try:
                        win32_results = _enum_windows_by_title(alias)
                        if win32_results:
                            hwnd = win32_results[0]["hwnd"]
                            if win32gui.IsIconic(hwnd):
                                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                            win32gui.SetForegroundWindow(hwnd)
                            time.sleep(0.2)
                            return {
                                "success": True,
                                "message": f"Fenêtre '{win32_results[0]['title']}' mise au premier plan (Win32 fallback).",
                            }
                    except Exception as e:
                        logger.debug("Win32 focus fallback failed for '%s' (attempt %d): %s", alias, attempt, e)

            if attempt < len(retries):
                time.sleep(delay)

        return {"success": False, "message": f"Aucune fenêtre trouvée pour '{title}'."}

    # ------- Actions clavier ------- #

    @staticmethod
    def type_text(text: str, interval: float = 0.02, use_clipboard: bool = False) -> dict[str, Any]:
        """
        Tape du texte dans la fenêtre active.
        
        Args:
            text: Texte à taper
            interval: Délai entre chaque caractère
            use_clipboard: Force l'utilisation du presse-papier (pour caractères spéciaux / accents)
        """
        try:
            # Détecter les caractères non-ASCII → forcer le clipboard
            has_special = any(ord(c) > 127 for c in text)
            if has_special or use_clipboard:
                # Méthode clipboard : plus fiable pour les accents/spéciaux
                old_clipboard = ""
                try:
                    old_clipboard = pyperclip.paste()
                except Exception:
                    pass

                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.1)

                # Restaurer le presse-papier précédent
                try:
                    pyperclip.copy(old_clipboard)
                except Exception:
                    pass

                return {"success": True, "message": f"Texte collé ({len(text)} caractères) via presse-papier."}
            else:
                pyautogui.typewrite(text, interval=interval)
                return {"success": True, "message": f"Texte tapé ({len(text)} caractères)."}

        except Exception as e:
            return {"success": False, "message": f"Erreur saisie texte : {e}"}

    @staticmethod
    def send_hotkey(*keys: str) -> dict[str, Any]:
        """
        Envoie un raccourci clavier (ex: 'ctrl', 'c' → Ctrl+C).
        
        Args:
            keys: Touches du raccourci (ex: 'ctrl', 'shift', 'n')
        """
        try:
            pyautogui.hotkey(*keys)
            time.sleep(0.1)
            combo = "+".join(keys)
            return {"success": True, "message": f"Raccourci '{combo}' envoyé."}
        except Exception as e:
            return {"success": False, "message": f"Erreur raccourci : {e}"}

    # ------- Actions souris ------- #

    @staticmethod
    def click(x: int | None = None, y: int | None = None, button: str = "left", clicks: int = 1) -> dict[str, Any]:
        """
        Clique à la position indiquée (ou position actuelle si x/y absents).
        
        Args:
            x: Coordonnée X (pixels)
            y: Coordonnée Y (pixels)
            button: 'left', 'right', ou 'middle'
            clicks: Nombre de clics (1=simple, 2=double)
        """
        try:
            if x is not None and y is not None:
                pyautogui.click(x=x, y=y, button=button, clicks=clicks)
                return {"success": True, "message": f"Clic {button} à ({x}, {y}) — {clicks}x."}
            else:
                pyautogui.click(button=button, clicks=clicks)
                pos = pyautogui.position()
                return {"success": True, "message": f"Clic {button} à la position actuelle ({pos.x}, {pos.y}) — {clicks}x."}
        except Exception as e:
            return {"success": False, "message": f"Erreur clic : {e}"}

    # ------- Fenêtre active ------- #

    @staticmethod
    def get_active_window() -> dict[str, Any]:
        """Retourne les informations sur la fenêtre actuellement active."""
        try:
            w = gw.getActiveWindow()
            if w:
                return {
                    "success": True,
                    "title": w.title,
                    "left": w.left,
                    "top": w.top,
                    "width": w.width,
                    "height": w.height,
                }
            return {"success": False, "message": "Aucune fenêtre active détectée."}
        except Exception as e:
            return {"success": False, "message": f"Erreur : {e}"}

    # ------- Screenshot ------- #

    @staticmethod
    def take_window_screenshot(title: str | None = None) -> dict[str, Any]:
        """
        Capture d'écran d'une fenêtre spécifique ou de l'écran entier.
        
        Args:
            title: Titre de la fenêtre à capturer (None = écran entier)
        """
        try:
            if title:
                windows = gw.getWindowsWithTitle(title)
                if not windows:
                    return {"success": False, "message": f"Fenêtre '{title}' non trouvée pour la capture."}
                w = windows[0]
                if w.isMinimized:
                    w.restore()
                    time.sleep(0.5)
                region = (w.left, w.top, w.width, w.height)
                screenshot = pyautogui.screenshot(region=region)
            else:
                screenshot = pyautogui.screenshot()

            # Sauvegarder dans data/
            import pathlib
            data_dir = pathlib.Path(__file__).parent.parent / "data" / "screenshots"
            data_dir.mkdir(parents=True, exist_ok=True)
            filename = f"screenshot_{int(time.time())}.png"
            filepath = data_dir / filename
            screenshot.save(str(filepath))

            return {
                "success": True,
                "message": f"Capture sauvegardée : {filepath.name}",
                "path": str(filepath),
                "size": {"width": screenshot.width, "height": screenshot.height},
            }
        except Exception as e:
            return {"success": False, "message": f"Erreur capture : {e}"}


# --------------------------------------------------------------------------- #
#  Fonctions publiques (utilisées par intent_engine)
# --------------------------------------------------------------------------- #

_controller = WindowController()


def window_find(title: str) -> dict[str, Any]:
    """Recherche des fenêtres par titre."""
    return _controller.find_window(title)


def window_focus(title: str) -> dict[str, Any]:
    """Met au premier plan une fenêtre."""
    return _controller.focus_window(title)


def window_type(text: str, target: str | None = None, use_clipboard: bool = False) -> dict[str, Any]:
    """
    Tape du texte dans une fenêtre.
    Si target est spécifié, focalise d'abord la fenêtre.
    """
    if target:
        focus_result = _controller.focus_window(target)
        if not focus_result["success"]:
            return focus_result
        time.sleep(0.3)
    return _controller.type_text(text, use_clipboard=use_clipboard)


def window_hotkey(*keys: str, target: str | None = None) -> dict[str, Any]:
    """
    Envoie un raccourci clavier.
    Si target est spécifié, focalise d'abord la fenêtre.
    """
    if target:
        focus_result = _controller.focus_window(target)
        if not focus_result["success"]:
            return focus_result
        time.sleep(0.3)
    return _controller.send_hotkey(*keys)


def window_click(x: int | None = None, y: int | None = None,
                 button: str = "left", clicks: int = 1,
                 target: str | None = None) -> dict[str, Any]:
    """
    Clique dans une fenêtre.
    Si target est spécifié, focalise d'abord la fenêtre.
    """
    if target:
        focus_result = _controller.focus_window(target)
        if not focus_result["success"]:
            return focus_result
        time.sleep(0.3)
    return _controller.click(x, y, button, clicks)


def window_screenshot(title: str | None = None) -> dict[str, Any]:
    """Capture d'écran d'une fenêtre spécifique ou de l'écran entier."""
    return _controller.take_window_screenshot(title)


def window_get_active() -> dict[str, Any]:
    """Retourne les infos de la fenêtre active."""
    return _controller.get_active_window()


def window_close(title: str) -> dict[str, Any]:
    """Ferme la fenêtre correspondant au titre."""
    for alias in _resolve_aliases(title):
        try:
            windows = gw.getWindowsWithTitle(alias)
            if windows:
                w = windows[0]
                w.close()
                time.sleep(0.5)
                return {"success": True, "message": f"Fenêtre '{w.title}' fermée."}
        except Exception:
            pass
        # Fallback Win32
        if HAS_WIN32:
            win32_results = _enum_windows_by_title(alias)
            if win32_results:
                hwnd = win32_results[0]["hwnd"]
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                time.sleep(0.5)
                return {"success": True, "message": f"Fenêtre '{win32_results[0]['title']}' fermée (Win32)."}
    return {"success": False, "message": f"Aucune fenêtre trouvée pour '{title}'."}


def window_minimize(title: str) -> dict[str, Any]:
    """Minimise la fenêtre correspondant au titre."""
    for alias in _resolve_aliases(title):
        try:
            windows = gw.getWindowsWithTitle(alias)
            if windows:
                w = windows[0]
                w.minimize()
                time.sleep(0.3)
                return {"success": True, "message": f"Fenêtre '{w.title}' minimisée."}
        except Exception:
            pass
        if HAS_WIN32:
            win32_results = _enum_windows_by_title(alias)
            if win32_results:
                hwnd = win32_results[0]["hwnd"]
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                time.sleep(0.3)
                return {"success": True, "message": f"Fenêtre '{win32_results[0]['title']}' minimisée (Win32)."}
    return {"success": False, "message": f"Aucune fenêtre trouvée pour '{title}'."}


def window_maximize(title: str) -> dict[str, Any]:
    """Maximise la fenêtre correspondant au titre."""
    for alias in _resolve_aliases(title):
        try:
            windows = gw.getWindowsWithTitle(alias)
            if windows:
                w = windows[0]
                w.maximize()
                time.sleep(0.3)
                return {"success": True, "message": f"Fenêtre '{w.title}' maximisée."}
        except Exception:
            pass
        if HAS_WIN32:
            win32_results = _enum_windows_by_title(alias)
            if win32_results:
                hwnd = win32_results[0]["hwnd"]
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                time.sleep(0.3)
                return {"success": True, "message": f"Fenêtre '{win32_results[0]['title']}' maximisée (Win32)."}
    return {"success": False, "message": f"Aucune fenêtre trouvée pour '{title}'."}


def window_list() -> dict[str, Any]:
    """Liste toutes les fenêtres visibles."""
    if HAS_WIN32:
        results = []

        def callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title.strip():
                    rect = win32gui.GetWindowRect(hwnd)
                    results.append({
                        "hwnd": hwnd,
                        "title": title,
                        "rect": {"left": rect[0], "top": rect[1], "right": rect[2], "bottom": rect[3]},
                    })
            return True

        win32gui.EnumWindows(callback, None)
        return {"success": True, "windows": results, "count": len(results)}

    # Fallback pygetwindow
    all_windows = gw.getAllWindows()
    windows = [{"title": w.title, "visible": w.visible} for w in all_windows if w.title.strip() and w.visible]
    return {"success": True, "windows": windows, "count": len(windows)}


def window_snap(title: str, position: str = "left") -> dict[str, Any]:
    """
    Snap une fenêtre à gauche ou à droite de l'écran.
    position: 'left' | 'right' | 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right'
    """
    screen_w, screen_h = pyautogui.size()

    snap_positions = {
        "left": (0, 0, screen_w // 2, screen_h),
        "right": (screen_w // 2, 0, screen_w // 2, screen_h),
        "top-left": (0, 0, screen_w // 2, screen_h // 2),
        "top-right": (screen_w // 2, 0, screen_w // 2, screen_h // 2),
        "bottom-left": (0, screen_h // 2, screen_w // 2, screen_h // 2),
        "bottom-right": (screen_w // 2, screen_h // 2, screen_w // 2, screen_h // 2),
    }

    if position not in snap_positions:
        return {"success": False, "message": f"Position invalide : '{position}'. Valides : {list(snap_positions.keys())}"}

    x, y, w, h = snap_positions[position]

    for alias in _resolve_aliases(title):
        try:
            windows = gw.getWindowsWithTitle(alias)
            if windows:
                win = windows[0]
                if win.isMinimized:
                    win.restore()
                    time.sleep(0.3)
                win.moveTo(x, y)
                win.resizeTo(w, h)
                return {"success": True, "message": f"Fenêtre '{win.title}' snappée en position '{position}'."}
        except Exception:
            pass
        if HAS_WIN32:
            win32_results = _enum_windows_by_title(alias)
            if win32_results:
                hwnd = win32_results[0]["hwnd"]
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    time.sleep(0.3)
                win32gui.MoveWindow(hwnd, x, y, w, h, True)
                return {"success": True, "message": f"Fenêtre snappée en position '{position}' (Win32)."}

    return {"success": False, "message": f"Aucune fenêtre trouvée pour '{title}'."}
