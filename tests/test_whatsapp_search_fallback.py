import unittest
from unittest.mock import MagicMock
import tempfile
import os

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys

from src.whatsapp_service import WhatsAppService, WhatsAppSelectors


class WhatsAppSearchFallbackTest(unittest.TestCase):
    def test_chat_title_match_allows_contains(self):
        self.assertTrue(WhatsAppService._matches_chat_title("Muazzam", "muazzam Ijt"))
        self.assertTrue(
            WhatsAppService._matches_chat_title("Ibrahim Salman", "Ibrahim")
        )

    def test_ensure_whatsapp_tab_ready_does_not_reload_if_on_whatsapp(self):
        svc = WhatsAppService("C:/tmp/wa-profile", qr_timeout=10)

        driver = MagicMock()
        driver.current_url = "https://web.whatsapp.com/"
        svc._driver = driver

        svc._ensure_whatsapp_tab_ready()

        driver.get.assert_not_called()

    def test_ensure_whatsapp_tab_ready_opens_once_if_not_on_whatsapp(self):
        svc = WhatsAppService("C:/tmp/wa-profile", qr_timeout=10)

        driver = MagicMock()
        driver.current_url = "about:blank"
        svc._driver = driver

        svc._ensure_whatsapp_tab_ready()

        driver.get.assert_called_once_with("https://web.whatsapp.com")

    def test_open_search_box_uses_shortcuts_after_initial_timeout(self):
        svc = WhatsAppService("C:/tmp/wa-profile", qr_timeout=10)

        active = MagicMock()
        body = MagicMock()

        driver = MagicMock()
        driver.switch_to.active_element = active
        driver.find_element.return_value = body
        svc._driver = driver

        calls = {"count": 0}

        def fake_find(locators, timeout=20, require_clickable=False):
            calls["count"] += 1
            if calls["count"] == 1:
                raise TimeoutException("search not visible")

            self.assertEqual(locators, WhatsAppSelectors.SEARCH_BOX)
            self.assertTrue(require_clickable)
            return MagicMock()

        svc._find_first_element = fake_find  # type: ignore[assignment]

        result = svc._open_search_box(timeout=20)

        self.assertIsNotNone(result)
        active.send_keys.assert_called()
        sent = active.send_keys.call_args[0][0]
        self.assertIn(Keys.CONTROL, sent)
        self.assertNotEqual(sent, Keys.CONTROL + "f")

    def test_open_search_box_tries_trigger_before_shortcuts(self):
        svc = WhatsAppService("C:/tmp/wa-profile", qr_timeout=10)

        driver = MagicMock()
        svc._driver = driver

        trigger = MagicMock()
        search_box = MagicMock()
        calls = {"count": 0}

        def fake_find(locators, timeout=20, require_clickable=False):
            calls["count"] += 1
            if calls["count"] == 1:
                self.assertEqual(locators, WhatsAppSelectors.SEARCH_BOX)
                raise TimeoutException("search collapsed")
            if calls["count"] == 2:
                self.assertEqual(locators, WhatsAppSelectors.SEARCH_TRIGGER)
                self.assertTrue(require_clickable)
                return trigger
            if calls["count"] == 3:
                self.assertEqual(locators, WhatsAppSelectors.SEARCH_BOX)
                self.assertTrue(require_clickable)
                return search_box
            raise AssertionError("Unexpected extra call")

        svc._find_first_element = fake_find  # type: ignore[assignment]

        result = svc._open_search_box(timeout=20)

        self.assertIs(result, search_box)
        trigger.click.assert_called_once()
        driver.switch_to.active_element.send_keys.assert_not_called()

    def test_fallback_moves_to_secondary_profile(self):
        with tempfile.TemporaryDirectory() as td:
            primary = os.path.join(td, "wa-profile")
            svc = WhatsAppService(
                primary,
                qr_timeout=10,
                allow_ephemeral_fallback=True,
            )

            calls = []

            def fake_start(profile_dir):
                calls.append(profile_dir)
                if profile_dir and str(profile_dir).endswith("wa-profile"):
                    raise RuntimeError("devtoolsactiveport")
                return MagicMock()

            svc._start_driver = fake_start  # type: ignore[assignment]
            svc._wait_for_login = MagicMock()  # type: ignore[assignment]

            driver = svc.init_browser()

            self.assertIsNotNone(driver)
            self.assertGreaterEqual(len(calls), 2)
            self.assertTrue(
                any(str(c).endswith("wa-profile_backup") for c in calls if c)
            )

    def test_profile_hint_prefers_last_working_profile(self):
        with tempfile.TemporaryDirectory() as td:
            primary = os.path.join(td, "wa-profile")
            secondary = f"{primary}_backup"
            os.makedirs(secondary, exist_ok=True)

            svc = WhatsAppService(
                primary,
                qr_timeout=10,
                allow_ephemeral_fallback=False,
            )

            with open(f"{primary}_active_profile.txt", "w", encoding="utf-8") as f:
                f.write(secondary)

            calls = []

            def fake_start(profile_dir):
                calls.append(profile_dir)
                return MagicMock()

            svc._start_driver = fake_start  # type: ignore[assignment]
            svc._wait_for_login = MagicMock()  # type: ignore[assignment]
            svc.init_browser()

            self.assertGreaterEqual(len(calls), 1)
            self.assertEqual(calls[0], secondary)


if __name__ == "__main__":
    unittest.main()
