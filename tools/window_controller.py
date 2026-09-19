"""
Window Controller — Interaction DANS les fenêtres d'applications ouvertes.

Utilise PyAutoGUI + Win32 API pour :
- Trouver / focaliser des fenêtres par titre
- Cliquer, taper du texte, envoyer des raccourcis clavier
- Prendre des captures d'écran d'une fenêtre
"""

import logging
import time
import unicodedata
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
#  B1-bis — contrôles des paramètres d'action
#
#  Fonctions pures, sans effet : le validateur les applique avant exécution, et chaque
#  outil les réapplique, parce que le planificateur horaire, les déclencheurs et les
#  workflows appellent les outils sans passer par le validateur (main._execute_action).
#  Chaque fonction retourne un message d'erreur, vide si le paramètre est acceptable.
# --------------------------------------------------------------------------- #

# Texte à frapper : au-delà, la frappe caractère par caractère dure plusieurs dizaines de
# secondes, pendant lesquelles le premier plan peut changer.
MAX_TYPE_TEXT_CHARS = 2000
# Seuls contrôles admis : saut de ligne et tabulation, qui ont un sens dans un texte.
_ALLOWED_TEXT_CONTROLS = {"\n", "\t"}

VALID_SNAP_POSITIONS = ("left", "right", "top-left", "top-right", "bottom-left", "bottom-right")

_VALID_MOUSE_BUTTONS = {"left", "right", "middle"}
_MAX_CLICKS = 3


def check_type_text(text) -> tuple[str, str]:
    """Contrôle le texte à frapper. Retourne (texte normalisé, erreur).

    pyautogui.typewrite interprète une LISTE comme des noms de touches (["win", "r"]
    ouvre la boîte Exécuter) : seule une chaîne est acceptée. Les caractères de contrôle
    autres que saut de ligne et tabulation (échappement, retour arrière, NUL…) sont refusés.
    """
    if not isinstance(text, str):
        return "", f"texte de type {type(text).__name__}, attendu une chaîne"
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return "", "texte vide"
    if len(text) > MAX_TYPE_TEXT_CHARS:
        return "", f"texte de {len(text)} caractères, maximum {MAX_TYPE_TEXT_CHARS}"
    for ch in text:
        if unicodedata.category(ch) == "Cc" and ch not in _ALLOWED_TEXT_CONTROLS:
            return "", f"caractère de contrôle U+{ord(ch):04X} dans le texte"
    return text, ""


def check_window_title(title) -> tuple[str, str]:
    """Titre de fenêtre non vide. getWindowsWithTitle("") renvoie TOUTES les fenêtres."""
    if not isinstance(title, str) or not title.strip():
        return "", "titre de fenêtre vide ou absent"
    return title.strip(), ""


def _monitor_rects() -> list[tuple[int, int, int, int]]:
    """Rectangles (gauche, haut, droite, bas) de chaque écran, en coordonnées virtuelles.

    Un écran secondaire placé à gauche du principal a des coordonnées négatives.
    """
    if HAS_WIN32:
        try:
            import win32api
            return [tuple(rect) for _, _, rect in win32api.EnumDisplayMonitors()]
        except Exception as e:
            logger.debug("EnumDisplayMonitors indisponible : %s", e)
    width, height = pyautogui.size()
    return [(0, 0, width, height)]


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def check_click_params(x, y, button="left", clicks=1) -> str:
    """Coordonnées entières, sur un écran existant ; bouton et nombre de clics bornés.

    x et y sont obligatoires : sans eux, pyautogui clique là où se trouve la souris.
    """
    if not (_is_int(x) and _is_int(y)):
        return f"coordonnées de clic invalides (x={x!r}, y={y!r}), deux entiers attendus"
    if not any(left <= x < right and top <= y < bottom for left, top, right, bottom in _monitor_rects()):
        return f"point ({x}, {y}) hors de tout écran"
    if button not in _VALID_MOUSE_BUTTONS:
        return f"bouton de souris inconnu : {button!r}"
    if not _is_int(clicks) or not 1 <= clicks <= _MAX_CLICKS:
        return f"nombre de clics invalide : {clicks!r} (1 à {_MAX_CLICKS})"
    return ""


def _refused(message: str) -> dict[str, Any]:
    logger.warning("[WINDOW] Action refusée : %s", message)
    return {"success": False, "message": f"Action refusée : {message}."}


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
        # B1-bis : titre vide → pywinauto chercherait « .*.* » et pygetwindow « » : toute fenêtre.
        title, error = check_window_title(title)
        if error:
            return _refused(error)
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


def _focus_and_verify(target: str):
    """Met la cible au premier plan PUIS vérifie qu'elle y est. Retourne (fenêtre active, refus).

    focus_window peut « réussir » sans que Windows cède le premier plan (protection contre
    le vol de focus d'un processus en arrière-plan) : la frappe partirait alors dans la
    fenêtre qui s'y trouvait. On lit donc la fenêtre réellement active avant d'agir.
    """
    focus_result = _controller.focus_window(target)
    if not focus_result["success"]:
        return None, focus_result
    time.sleep(0.3)
    try:
        active = gw.getActiveWindow()
    except Exception as e:
        logger.debug("getActiveWindow a échoué : %s", e)
        active = None
    active_title = (getattr(active, "title", "") or "") if active else ""
    if not any(alias.lower() in active_title.lower() for alias in _resolve_aliases(target)):
        return None, _refused(
            f"la fenêtre '{target}' n'est pas passée au premier plan "
            f"(premier plan : '{active_title or '?'}'), aucune action effectuée"
        )
    return active, None


def window_type(text: str, target: str | None = None, use_clipboard: bool = False) -> dict[str, Any]:
    """
    Tape du texte dans une fenêtre.

    B1-bis : la cible est obligatoire et vérifiée au premier plan avant la frappe.
    Sans elle, le texte partait dans la fenêtre active, quelle qu'elle soit.
    """
    target, error = check_window_title(target)
    if error:
        return _refused("fenêtre cible absente pour la frappe")
    text, error = check_type_text(text)
    if error:
        return _refused(error)
    _, refusal = _focus_and_verify(target)
    if refusal:
        return refusal
    return _controller.type_text(text, use_clipboard=use_clipboard)


def window_hotkey(*keys: str, target: str | None = None) -> dict[str, Any]:
    """
    Envoie un raccourci clavier.

    B1-bis : la cible est obligatoire et vérifiée au premier plan avant l'envoi.
    """
    target, error = check_window_title(target)
    if error:
        return _refused("fenêtre cible absente pour le raccourci clavier")
    _, refusal = _focus_and_verify(target)
    if refusal:
        return refusal
    return _controller.send_hotkey(*keys)


def window_click(x: int | None = None, y: int | None = None,
                 button: str = "left", clicks: int = 1,
                 target: str | None = None) -> dict[str, Any]:
    """
    Clique à des coordonnées d'écran (absolues).

    B1-bis : le point doit tomber sur un écran existant (les coordonnées négatives d'un
    écran secondaire placé à gauche sont légitimes) et, si une fenêtre cible est nommée,
    dans le rectangle de cette fenêtre une fois au premier plan.
    """
    error = check_click_params(x, y, button, clicks)
    if error:
        return _refused(error)
    if target:
        active, refusal = _focus_and_verify(target)
        if refusal:
            return refusal
        left, top = active.left, active.top
        right, bottom = left + active.width, top + active.height
        if not (left <= x < right and top <= y < bottom):
            return _refused(
                f"point ({x}, {y}) hors de la fenêtre '{active.title}' "
                f"({left}, {top}) → ({right}, {bottom})"
            )
    return _controller.click(x, y, button, clicks)


def window_screenshot(title: str | None = None) -> dict[str, Any]:
    """Capture d'écran d'une fenêtre spécifique ou de l'écran entier."""
    return _controller.take_window_screenshot(title)


def window_get_active() -> dict[str, Any]:
    """Retourne les infos de la fenêtre active."""
    return _controller.get_active_window()


def window_close(title: str) -> dict[str, Any]:
    """Ferme la fenêtre correspondant au titre."""
    title, error = check_window_title(title)
    if error:
        return _refused(error)
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
    title, error = check_window_title(title)
    if error:
        return _refused(error)
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
    title, error = check_window_title(title)
    if error:
        return _refused(error)
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
    title, error = check_window_title(title)
    if error:
        return _refused(error)
    if position not in VALID_SNAP_POSITIONS:
        return _refused(f"position inconnue : {position!r}, attendu l'une de {list(VALID_SNAP_POSITIONS)}")
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
