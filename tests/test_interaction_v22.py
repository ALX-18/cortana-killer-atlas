"""
Tests MVP 2.2 — Interaction Apps
10 tests couvrant window_controller, browser_bridge, et le routage intent_engine.
"""

import asyncio
import json
import sys
import os
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestWindowController(unittest.TestCase):
    """Tests pour tools/window_controller.py"""

    def test_01_import_window_controller(self):
        """Test 1 : Import du module window_controller sans erreur."""
        from tools import window_controller
        self.assertTrue(hasattr(window_controller, "window_find"))
        self.assertTrue(hasattr(window_controller, "window_focus"))
        self.assertTrue(hasattr(window_controller, "window_type"))
        self.assertTrue(hasattr(window_controller, "window_hotkey"))
        self.assertTrue(hasattr(window_controller, "window_click"))
        self.assertTrue(hasattr(window_controller, "window_screenshot"))
        self.assertTrue(hasattr(window_controller, "window_get_active"))
        print("✅ Test 1 PASS — window_controller importé avec toutes les fonctions")

    def test_02_find_window_nonexistent(self):
        """Test 2 : Recherche d'une fenêtre inexistante retourne success=False."""
        from tools.window_controller import window_find
        result = window_find("FenêtreQuiNExistePas_XYZ_12345")
        self.assertIsInstance(result, dict)
        self.assertFalse(result["success"])
        self.assertIn("windows", result)
        self.assertEqual(len(result["windows"]), 0)
        print("✅ Test 2 PASS — fenêtre inexistante détectée correctement")

    def test_03_get_active_window(self):
        """Test 3 : Récupération de la fenêtre active retourne un résultat valide."""
        from tools.window_controller import window_get_active
        result = window_get_active()
        self.assertIsInstance(result, dict)
        # Peut être success=True ou False selon l'environnement
        if result["success"]:
            self.assertIn("title", result)
            print(f"✅ Test 3 PASS — fenêtre active : '{result['title']}'")
        else:
            print("✅ Test 3 PASS — aucune fenêtre active (environnement CI/headless)")

    @patch("tools.window_controller.pyautogui")
    def test_04_type_text_ascii(self, mock_pyautogui):
        """Test 4 : Saisie de texte ASCII utilise typewrite."""
        from tools.window_controller import WindowController
        controller = WindowController()
        result = controller.type_text("hello world")
        self.assertTrue(result["success"])
        mock_pyautogui.typewrite.assert_called_once()
        print("✅ Test 4 PASS — type_text ASCII appelle typewrite")

    @patch("tools.window_controller.pyautogui")
    @patch("tools.window_controller.pyperclip")
    def test_05_type_text_special_chars(self, mock_pyperclip, mock_pyautogui):
        """Test 5 : Saisie de texte avec accents utilise le presse-papier."""
        from tools.window_controller import WindowController
        mock_pyperclip.paste.return_value = ""
        controller = WindowController()
        result = controller.type_text("Héllo wörld café")
        self.assertTrue(result["success"])
        mock_pyperclip.copy.assert_called()
        mock_pyautogui.hotkey.assert_called_with("ctrl", "v")
        print("✅ Test 5 PASS — type_text spécial utilise clipboard")

    @patch("tools.window_controller.pyautogui")
    def test_06_send_hotkey(self, mock_pyautogui):
        """Test 6 : Envoi d'un raccourci clavier."""
        from tools.window_controller import WindowController
        controller = WindowController()
        result = controller.send_hotkey("ctrl", "s")
        self.assertTrue(result["success"])
        self.assertIn("ctrl+s", result["message"])
        mock_pyautogui.hotkey.assert_called_with("ctrl", "s")
        print("✅ Test 6 PASS — hotkey ctrl+s envoyé")


class TestBrowserBridge(unittest.TestCase):
    """Tests pour tools/browser_bridge.py"""

    def test_07_import_browser_bridge(self):
        """Test 7 : Import du module browser_bridge sans erreur."""
        from tools import browser_bridge
        self.assertTrue(hasattr(browser_bridge, "BrowserBridge"))
        self.assertTrue(hasattr(browser_bridge, "browser_navigate"))
        self.assertTrue(hasattr(browser_bridge, "browser_new_tab"))
        self.assertTrue(hasattr(browser_bridge, "browser_ext_click"))
        self.assertTrue(hasattr(browser_bridge, "browser_ext_type"))
        self.assertTrue(hasattr(browser_bridge, "browser_bridge_status"))
        print("✅ Test 7 PASS — browser_bridge importé avec toutes les fonctions")

    def test_08_bridge_status_disconnected(self):
        """Test 8 : Statut du bridge quand aucun client n'est connecté."""
        from tools.browser_bridge import BrowserBridge
        bridge = BrowserBridge(port=19999)  # Port différent pour le test
        self.assertFalse(bridge.is_connected())
        self.assertEqual(bridge.connected_clients, 0)
        print("✅ Test 8 PASS — bridge déconnecté par défaut")

    def test_09_bridge_send_command_no_client(self):
        """Test 9 : Envoi de commande sans client connecté retourne une erreur."""
        from tools.browser_bridge import BrowserBridge

        async def _test():
            bridge = BrowserBridge(port=19998)
            result = await bridge.send_command("navigate", {"url": "https://example.com"})
            self.assertFalse(result["success"])
            self.assertIn("Aucune extension", result["message"])

        asyncio.run(_test())
        print("✅ Test 9 PASS — commande sans client = erreur propre")


class TestIntentEngineRouting(unittest.TestCase):
    """Tests pour le routage intent_engine (MVP 2.2)"""

    def test_10_tool_handlers_v22_registered(self):
        """Test 10 : Les nouveaux handlers MVP 2.2 sont enregistrés dans TOOL_HANDLERS."""
        from core.intent_engine import TOOL_HANDLERS, VALID_ACTIONS

        v22_tools = [
            "window_find", "window_focus", "window_type", "window_hotkey",
            "window_click", "window_screenshot", "window_get_active",
            "browser_navigate", "browser_new_tab", "browser_ext_click",
            "browser_ext_type", "browser_ext_scroll", "browser_ext_get_content",
            "browser_ext_get_url", "browser_bridge_status",
        ]

        missing = []
        for tool in v22_tools:
            if tool not in TOOL_HANDLERS:
                missing.append(tool)
            if tool not in VALID_ACTIONS:
                missing.append(f"{tool} (VALID_ACTIONS)")

        self.assertEqual(len(missing), 0, f"Outils manquants : {missing}")
        print(f"✅ Test 10 PASS — {len(v22_tools)} outils MVP 2.2 enregistrés dans TOOL_HANDLERS")


# --------------------------------------------------------------------------- #
#  Runner
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    print("=" * 60)
    print("  Tests MVP 2.2 — Interaction Apps")
    print("=" * 60)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Charger dans l'ordre
    suite.addTests(loader.loadTestsFromTestCase(TestWindowController))
    suite.addTests(loader.loadTestsFromTestCase(TestBrowserBridge))
    suite.addTests(loader.loadTestsFromTestCase(TestIntentEngineRouting))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 60)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"  Résultat : {passed}/{result.testsRun} tests passés")
    if result.failures:
        print(f"  Échecs : {len(result.failures)}")
    if result.errors:
        print(f"  Erreurs : {len(result.errors)}")
    print("=" * 60)

    sys.exit(0 if result.wasSuccessful() else 1)
