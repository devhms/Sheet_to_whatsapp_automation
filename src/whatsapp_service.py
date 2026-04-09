"""WhatsApp service using Selenium with robust selectors and recovery logic."""

import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Optional

import pyperclip
from selenium import webdriver
from selenium.common.exceptions import (
    InvalidSessionIdException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

logger = logging.getLogger(__name__)

PHONE_PATTERN = re.compile(r"^\+?\d[\d\s\-()]{6,}$")


class WhatsAppSelectors:
    """Selector sets for WhatsApp Web UI variants."""

    CHAT_READY = [
        (By.ID, "side"),
        (By.ID, "pane-side"),
        (By.CSS_SELECTOR, '[data-testid="chat-list"]'),
        (By.CSS_SELECTOR, '[data-testid="chat-list-search"]'),
    ]

    SEARCH_BOX = [
        (By.XPATH, '//div[@id="side"]//div[@contenteditable="true"][@data-tab="3"]'),
        (By.XPATH, '//div[@id="side"]//div[@role="textbox"][@contenteditable="true"]'),
        (
            By.CSS_SELECTOR,
            '[data-testid="chat-list-search"] div[contenteditable="true"]',
        ),
        (
            By.CSS_SELECTOR,
            'div[role="textbox"][contenteditable="true"][aria-placeholder*="Search"]',
        ),
        (
            By.CSS_SELECTOR,
            '[aria-label="Search input textbox"]',
        ),
        (
            By.CSS_SELECTOR,
            'div[role="textbox"][contenteditable="true"][aria-label*="Search or start"]',
        ),
        (
            By.CSS_SELECTOR,
            'div[role="textbox"][contenteditable="true"][aria-label*="Search"]',
        ),
        (
            By.XPATH,
            '//div[@role="textbox"][@contenteditable="true"][contains(@aria-placeholder,"Search")]',
        ),
        (
            By.XPATH,
            '//div[@role="textbox"][@contenteditable="true"][contains(@aria-label,"Search or start")]',
        ),
        (By.XPATH, '//div[@aria-label="Search input textbox"]'),
        (
            By.CSS_SELECTOR,
            'input[placeholder*="Search or start"]',
        ),
        (
            By.CSS_SELECTOR,
            'input[aria-label*="Search"]',
        ),
        (By.CSS_SELECTOR, 'input[type="search"]'),
        (
            By.XPATH,
            '//input[contains(@placeholder,"Search or start")]',
        ),
        (
            By.XPATH,
            '//input[contains(@aria-label,"Search")]',
        ),
    ]

    SEARCH_TRIGGER = [
        (By.CSS_SELECTOR, '#side [data-testid="chat-list-search"]'),
        (
            By.XPATH,
            '//div[@id="side"]//*[@data-icon="search"]/ancestor::*[@role="button"][1]',
        ),
        (By.XPATH, '//div[@id="side"]//button[contains(@aria-label,"Search")]'),
    ]

    MESSAGE_BOX = [
        (By.XPATH, '//footer//div[@contenteditable="true"][@data-tab="10"]'),
        (By.XPATH, '//footer//div[@role="textbox"][@contenteditable="true"]'),
        (By.CSS_SELECTOR, '[data-testid="conversation-compose-box-input"]'),
    ]

    CHAT_TITLE = [
        (By.CSS_SELECTOR, 'header [data-testid="conversation-info-header-chat-title"]'),
        (
            By.CSS_SELECTOR,
            'header [data-testid="conversation-header"] span[dir="auto"]',
        ),
        (By.CSS_SELECTOR, "header span[title]"),
        (By.XPATH, '//header//*[contains(@class,"copyable-text")]//span[@dir="auto"]'),
        (By.XPATH, '//header//span[@dir="auto"]'),
        (By.XPATH, "//header//h1//span"),
    ]


class WhatsAppService:
    """Handle WhatsApp Web automation with recovery and retries."""

    def __init__(
        self,
        selenium_data_dir: str,
        qr_timeout: int = 300,
        allow_ephemeral_fallback: bool = False,
        allow_profile_reset: bool = False,
    ) -> None:
        self._selenium_data_dir = selenium_data_dir
        self._secondary_profile_dir = f"{selenium_data_dir}_backup"
        self._profile_hint_file = f"{selenium_data_dir}_active_profile.txt"
        self._qr_timeout = qr_timeout
        self._allow_ephemeral_fallback = allow_ephemeral_fallback
        self._allow_profile_reset = allow_profile_reset
        self._driver: Optional[webdriver.Chrome] = None
        self._max_send_attempts = 3
        self._temp_profile_dir: Optional[str] = None

    @staticmethod
    def is_phone_target(target: str) -> bool:
        """Return True if the target looks like a phone number."""
        return bool(PHONE_PATTERN.match(str(target).strip()))

    @staticmethod
    def _find_brave() -> str:
        """Find Brave browser executable path."""
        brave_paths = [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe",
        ]
        for path in brave_paths:
            expanded = os.path.expandvars(path)
            if os.path.exists(expanded):
                return expanded
        return "brave"

    @staticmethod
    def _is_session_lost(exc: Exception) -> bool:
        """Detect lost or invalid Selenium session exceptions."""
        if isinstance(exc, InvalidSessionIdException):
            return True

        text = str(exc).lower()
        indicators = [
            "invalid session id",
            "session deleted",
            "not connected to devtools",
            "disconnected",
            "target window already closed",
            "chrome not reachable",
        ]
        return any(token in text for token in indicators)

    def _driver_or_raise(self) -> webdriver.Chrome:
        if not self._driver:
            raise RuntimeError("Browser not initialized")
        return self._driver

    def _cleanup_profile_locks(self, profile_dir: str) -> None:
        """Remove stale Chromium lock files to avoid profile startup crashes."""
        for base_dir in (profile_dir, os.path.join(profile_dir, "Default")):
            for name in (
                "SingletonLock",
                "SingletonCookie",
                "SingletonSocket",
                "lockfile",
            ):
                path = os.path.join(base_dir, name)
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    @staticmethod
    def _kill_stale_chromedriver_processes() -> None:
        """Kill orphaned chromedriver processes that can break new sessions."""
        if os.name != "nt":
            return

        try:
            result = subprocess.run(
                ["taskkill", "/F", "/IM", "chromedriver.exe", "/T"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if result.returncode == 0:
                logger.info("Cleared stale chromedriver.exe processes")
        except Exception as exc:
            logger.debug("Could not cleanup stale chromedriver processes: %s", exc)

    def _reset_corrupted_profile(self, profile_dir: str) -> bool:
        """Move corrupted profile aside and recreate clean profile directory."""
        if not profile_dir:
            return False

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_dir = f"{profile_dir}_broken_{timestamp}"

        try:
            if os.path.isdir(profile_dir):
                os.replace(profile_dir, backup_dir)
                logger.warning(
                    "Moved corrupted profile to backup: %s",
                    backup_dir,
                )
            os.makedirs(profile_dir, exist_ok=True)
            return True
        except OSError as exc:
            logger.warning(
                "Could not rotate profile directory (%s). Trying cleanup in place.",
                exc,
            )

        try:
            shutil.rmtree(profile_dir, ignore_errors=True)
            os.makedirs(profile_dir, exist_ok=True)
            logger.warning("Recreated profile directory after cleanup: %s", profile_dir)
            return True
        except OSError as exc:
            logger.error("Could not recreate profile directory: %s", exc)
            return False

    @staticmethod
    def _is_startup_crash(exc: Exception) -> bool:
        text = str(exc).lower()
        indicators = (
            "devtoolsactiveport",
            "session not created",
            "unable to receive message from renderer",
            "not connected to devtools",
            "chrome not reachable",
        )
        return any(token in text for token in indicators)

    def _build_options(self, profile_dir: str | None) -> webdriver.ChromeOptions:
        options = webdriver.ChromeOptions()
        options.binary_location = self._find_brave()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        if profile_dir:
            options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--remote-debugging-port=0")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-features=RendererCodeIntegrity")
        options.add_argument("--disable-sync")
        options.add_argument("--disable-translate")
        options.add_argument("--metrics-recording-only")
        options.add_argument("--no-first-run")
        options.add_argument("--safebrowsing-disable-auto-update")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        return options

    @staticmethod
    def _norm_path(path: str) -> str:
        return os.path.normcase(os.path.normpath(path))

    def _load_profile_hint(self) -> str | None:
        try:
            with open(self._profile_hint_file, "r", encoding="utf-8") as f:
                hinted = f.read().strip()
        except OSError:
            return None

        if not hinted:
            return None
        if not os.path.isdir(hinted):
            return None
        return hinted

    def _save_profile_hint(self, profile_dir: str) -> None:
        try:
            with open(self._profile_hint_file, "w", encoding="utf-8") as f:
                f.write(profile_dir)
        except OSError as exc:
            logger.debug("Could not persist active profile hint: %s", exc)

    def _start_driver(self, profile_dir: str | None) -> webdriver.Chrome:
        options = self._build_options(profile_dir)
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(90)
        return driver

    def _start_driver_no_navigation(self, profile_dir: str | None) -> webdriver.Chrome:
        """Start browser without immediate navigation (startup fallback)."""
        options = self._build_options(profile_dir)
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(90)
        return driver

    def _has_any_locator(self, locators: list[tuple[str, str]]) -> bool:
        driver = self._driver_or_raise()
        for by, selector in locators:
            try:
                if driver.find_elements(by, selector):
                    return True
            except WebDriverException:
                continue
        return False

    def _ensure_whatsapp_tab_ready(self, timeout: int = 20) -> None:
        """Open WhatsApp Web only if current tab is not already on it."""
        driver = self._driver_or_raise()
        current_url = str(getattr(driver, "current_url", "") or "").lower()
        if "web.whatsapp.com" in current_url:
            return

        logger.info("Opening WhatsApp Web in current tab")
        driver.get("https://web.whatsapp.com")

    def _find_first_element(
        self,
        locators: list[tuple[str, str]],
        timeout: int = 20,
        require_clickable: bool = False,
    ):
        """Find first available element from locator list."""
        driver = self._driver_or_raise()
        deadline = time.time() + timeout

        while time.time() < deadline:
            for by, selector in locators:
                try:
                    elements = driver.find_elements(by, selector)
                except WebDriverException:
                    elements = []

                if not elements:
                    continue

                element = elements[0]
                if require_clickable and not (
                    element.is_displayed() and element.is_enabled()
                ):
                    continue
                return element

            time.sleep(0.4)

        raise TimeoutException(f"Element not found for locators: {locators}")

    def init_browser(self) -> webdriver.Chrome:
        """Initialize Brave browser and wait for WhatsApp login."""
        logger.info("Initializing Brave browser...")

        if self._driver:
            self.close()

        self._kill_stale_chromedriver_processes()

        os.makedirs(self._selenium_data_dir, exist_ok=True)
        self._cleanup_profile_locks(self._selenium_data_dir)

        startup_errors = []
        attempts: list[tuple[str, Optional[str], bool]] = [
            ("primary persistent profile", self._selenium_data_dir, False),
            ("secondary persistent profile", self._secondary_profile_dir, False),
        ]

        preferred_profile = self._load_profile_hint()
        if preferred_profile:
            preferred_norm = self._norm_path(preferred_profile)
            attempts.sort(
                key=lambda item: (
                    0 if item[1] and self._norm_path(item[1]) == preferred_norm else 1
                )
            )
            logger.info(
                "Preferred persistent profile hint found: %s", preferred_profile
            )

        if self._allow_ephemeral_fallback:
            attempts.extend(
                [
                    ("temporary profile directory", "__TEMP__", True),
                    ("no profile", None, False),
                ]
            )

        started_persistent_profile: str | None = None

        for label, profile_dir, is_temp in attempts:
            active_profile_dir = profile_dir
            if profile_dir == "__TEMP__":
                self._cleanup_temp_profile_dir()
                self._temp_profile_dir = tempfile.mkdtemp(prefix="jamiat_bot_profile_")
                active_profile_dir = self._temp_profile_dir

            try:
                if active_profile_dir:
                    os.makedirs(active_profile_dir, exist_ok=True)
                    self._cleanup_profile_locks(active_profile_dir)

                logger.info("Starting browser using %s", label)
                self._driver = self._start_driver(active_profile_dir)
                if is_temp:
                    logger.warning(
                        "Using temporary profile fallback; scan QR once for this run"
                    )
                elif label == "secondary persistent profile":
                    logger.warning(
                        "Using secondary profile fallback: %s",
                        self._secondary_profile_dir,
                    )
                if active_profile_dir and not is_temp:
                    started_persistent_profile = active_profile_dir
                break
            except Exception as exc:
                startup_errors.append(f"{label}: {exc}")
                if is_temp:
                    self._cleanup_temp_profile_dir()
                self._driver = None

                if not self._is_startup_crash(exc):
                    logger.error("Browser startup failed (%s): %s", label, exc)
                    self.close()
                    raise

                recovered = False
                if (
                    label == "primary persistent profile"
                    and active_profile_dir
                    and self._allow_profile_reset
                ):
                    logger.error(
                        "Persistent profile startup failed. Attempting one-time "
                        "self-heal by recreating profile directory."
                    )
                    recovered = self._reset_corrupted_profile(active_profile_dir)
                    if recovered:
                        try:
                            self._cleanup_profile_locks(active_profile_dir)
                            self._driver = self._start_driver_no_navigation(
                                active_profile_dir
                            )
                            logger.warning(
                                "Profile was reset and browser started. "
                                "Scan WhatsApp QR once to restore session."
                            )
                            break
                        except Exception as retry_exc:
                            startup_errors.append(
                                f"{label} after profile reset: {retry_exc}"
                            )
                            self._driver = None

                logger.warning(
                    "Browser startup failed (%s). Trying next mode...",
                    label,
                )
                continue

        if not self._driver:
            details = " | ".join(startup_errors)
            self.close()
            raise RuntimeError(f"Unable to start Brave in all startup modes: {details}")

        self._ensure_whatsapp_tab_ready(timeout=25)

        logger.info("Waiting for WhatsApp login (timeout: %ds)...", self._qr_timeout)
        self._wait_for_login()
        if started_persistent_profile:
            self._save_profile_hint(started_persistent_profile)
        logger.info("Logged in to WhatsApp!")
        return self._driver

    def _wait_for_login(self) -> None:
        """Wait until WhatsApp is in logged-in state."""
        deadline = time.time() + self._qr_timeout
        next_progress_log = time.time()

        while time.time() < deadline:
            if self._has_any_locator(WhatsAppSelectors.CHAT_READY):
                return

            now = time.time()
            if now >= next_progress_log:
                remaining = max(0, int(deadline - now))
                logger.info(
                    "Waiting for WhatsApp login... %ds remaining (scan QR if needed)",
                    remaining,
                )
                next_progress_log = now + 15

            time.sleep(1)

        raise TimeoutException("Login timed out. Please scan the QR code manually.")

    def _recover_session(self) -> bool:
        """Try recovering browser session after disconnection."""
        logger.warning("Attempting session recovery...")
        try:
            self.close()
            self.init_browser()
            return True
        except Exception as exc:
            logger.error("Session recovery failed: %s", exc)
            return False

    def _send_via_search(self, target: str) -> None:
        """Open chat via search box (for groups/contact names)."""
        search_box = self._open_search_box(timeout=20)
        search_box.click()
        search_box.send_keys(Keys.CONTROL + "a")
        search_box.send_keys(Keys.BACKSPACE)
        time.sleep(0.2)

        pyperclip.copy(target)
        search_box.send_keys(Keys.CONTROL + "v")
        time.sleep(1)
        search_box.send_keys(Keys.ENTER)
        self._wait_for_chat_title(target, timeout=15)

    def _open_search_box(self, timeout: int = 20):
        """Open the left sidebar search and return its textbox element."""
        driver = self._driver_or_raise()

        try:
            return self._find_first_element(
                WhatsAppSelectors.SEARCH_BOX,
                timeout=5,
                require_clickable=True,
            )
        except TimeoutException:
            pass

        try:
            trigger = self._find_first_element(
                WhatsAppSelectors.SEARCH_TRIGGER,
                timeout=4,
                require_clickable=True,
            )
            trigger.click()
            time.sleep(0.25)
            return self._find_first_element(
                WhatsAppSelectors.SEARCH_BOX,
                timeout=6,
                require_clickable=True,
            )
        except TimeoutException:
            pass
        except Exception:
            pass

        for keys in (
            (Keys.CONTROL, Keys.ALT, Keys.SHIFT, "f"),
            (Keys.CONTROL, Keys.ALT, "/"),
        ):
            try:
                action = "".join(keys)
                logger.debug("Trying search shortcut: %s", keys)
                driver.switch_to.active_element.send_keys(action)
            except Exception:
                try:
                    driver.find_element(By.TAG_NAME, "body").send_keys("".join(keys))
                except Exception:
                    continue

            try:
                return self._find_first_element(
                    WhatsAppSelectors.SEARCH_BOX,
                    timeout=4,
                    require_clickable=True,
                )
            except TimeoutException:
                continue

        return self._find_first_element(
            WhatsAppSelectors.SEARCH_BOX,
            timeout=timeout,
            require_clickable=True,
        )

    def _get_current_chat_title(self) -> str:
        driver = self._driver_or_raise()
        for by, selector in WhatsAppSelectors.CHAT_TITLE:
            try:
                elements = driver.find_elements(by, selector)
            except WebDriverException:
                elements = []

            if not elements:
                continue

            element = elements[0]
            title = (element.get_attribute("title") or element.text or "").strip()
            if title:
                return title

        return ""

    @staticmethod
    def _matches_chat_title(expected: str, actual: str) -> bool:
        expected_clean = expected.strip().lower()
        actual_clean = actual.strip().lower()
        if not expected_clean or not actual_clean:
            return False

        if expected_clean == actual_clean:
            return True

        if expected_clean in actual_clean or actual_clean in expected_clean:
            return True

        expected_digits = re.sub(r"\D", "", expected_clean)
        actual_digits = re.sub(r"\D", "", actual_clean)
        if expected_digits and actual_digits and expected_digits == actual_digits:
            return True

        return False

    def _wait_for_chat_title(self, expected: str, timeout: int = 15) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            title = self._get_current_chat_title()
            if self._matches_chat_title(expected, title):
                return
            time.sleep(0.5)

        current = self._get_current_chat_title()
        driver = self._driver_or_raise()
        try:
            driver.save_screenshot("chat_title_mismatch.png")
        except Exception:
            pass
        raise TimeoutException(
            f"Chat title mismatch. Expected '{expected}', found '{current}'"
        )

    def _wait_chat_ready_for_send(self, timeout: int = 25) -> None:
        """Ensure message composer is ready before typing."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self._find_first_element(
                    WhatsAppSelectors.MESSAGE_BOX,
                    timeout=2,
                    require_clickable=True,
                )
                return
            except TimeoutException:
                pass

            driver = self._driver_or_raise()
            page_text = (driver.page_source or "").lower()
            blockers = [
                "phone number shared via url is invalid",
                "invalid phone number",
                "use whatsapp web on your phone",
                "couldn\u2019t find",
                "couldn't find",
            ]
            if any(token in page_text for token in blockers):
                raise RuntimeError(
                    "Target chat did not open (invalid or unavailable target)"
                )

            time.sleep(0.5)

        raise TimeoutException("Chat composer did not become ready in time")

    def _type_and_send(self, message: str) -> None:
        """Type multiline message and send."""
        message_box = self._find_first_element(
            WhatsAppSelectors.MESSAGE_BOX,
            timeout=30,
            require_clickable=True,
        )

        parts = message.split("\n")
        for i, part in enumerate(parts):
            if part.strip():
                pyperclip.copy(part)
                message_box.send_keys(Keys.CONTROL + "v")
            if i < len(parts) - 1:
                message_box.send_keys(Keys.SHIFT + Keys.ENTER)

        time.sleep(0.2)
        message_box.send_keys(Keys.ENTER)

    def send_message(self, target: str, message: str, use_search: bool = True) -> bool:
        """Send WhatsApp message with retries and session recovery."""
        target = str(target).strip()
        if not target:
            logger.error("Empty target provided")
            return False

        for attempt in range(1, self._max_send_attempts + 1):
            try:
                if not self._driver:
                    self.init_browser()

                self._send_via_search(target)

                self._wait_chat_ready_for_send(timeout=25)
                self._type_and_send(message)
                logger.info("Message sent to %s", target)
                return True

            except Exception as exc:
                logger.warning(
                    "Send attempt %d/%d failed for %s: %s",
                    attempt,
                    self._max_send_attempts,
                    target,
                    exc,
                )
                try:
                    driver = self._driver_or_raise()
                    driver.save_screenshot(f"send_failure_{target}_{attempt}.png")
                except Exception:
                    pass

                if self._is_session_lost(exc):
                    if not self._recover_session():
                        return False

                if (
                    "Element not found for locators" in str(exc)
                    and "Search" in str(exc)
                    and self._driver
                ):
                    try:
                        logger.warning(
                            "Retrying in-app search after search-box miss for %s",
                            target,
                        )
                        self._open_search_box(timeout=8)
                    except Exception as refresh_exc:
                        logger.warning("Search-box recovery failed: %s", refresh_exc)

                if attempt < self._max_send_attempts:
                    time.sleep(min(2 * attempt, 6))

        logger.error("Failed to send message to %s after retries", target)
        return False

    def close(self) -> None:
        """Close the browser session safely."""
        if self._driver:
            try:
                self._driver.quit()
                logger.info("Browser closed")
            except Exception as e:
                logger.warning("Error closing browser: %s", e)
            finally:
                self._driver = None

        self._cleanup_temp_profile_dir()

    def _cleanup_temp_profile_dir(self) -> None:
        if self._temp_profile_dir and os.path.isdir(self._temp_profile_dir):
            shutil.rmtree(self._temp_profile_dir, ignore_errors=True)
        self._temp_profile_dir = None

    @property
    def driver(self) -> Optional[webdriver.Chrome]:
        return self._driver
