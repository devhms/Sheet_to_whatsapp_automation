"""Configuration manager with validation and .env support."""

import json
import os
import logging
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

STRICT_TARGETS = {
    "Ibrahim": "+923300301917",
    "Muazzam": "+923055375994",
}

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    """Centralized configuration with env var overrides."""

    def __init__(self) -> None:
        self._config = self._load_config()
        self._apply_env_overrides()
        self._validate()

    @staticmethod
    def _load_config() -> dict[str, Any]:
        config_file = BASE_DIR / "config.json"
        if not config_file.exists():
            raise FileNotFoundError(f"config.json not found at {config_file}")
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _apply_env_overrides(self) -> None:
        env_map = {
            "GOOGLE_SERVICE_ACCOUNT_FILE": "service_account_file",
            "GOOGLE_SHEET_URL": "sheet_url",
            "WHATSAPP_GROUP_TARGET": "group_target",
            "WHATSAPP_ADMIN_NUMBER": "admin_number",
            "WHATSAPP_QR_TIMEOUT": "whatsapp_qr_timeout",
            "POLL_INTERVAL_SECONDS": "poll_interval_seconds",
            "FORM_LINK": "form_link",
            "LOG_LEVEL": "log_level",
            "SELENIUM_DATA_DIR": "selenium_data_dir",
        }

        for env_key, config_key in env_map.items():
            raw_env_val = os.environ.get(env_key)
            if raw_env_val is None:
                continue

            env_val = raw_env_val.strip()
            if not env_val:
                continue

            if config_key == "sheet_url" and self._is_placeholder_sheet_url(env_val):
                logger.warning(
                    "Ignoring GOOGLE_SHEET_URL placeholder value from environment. "
                    "Set GOOGLE_SHEET_URL to a real sheet URL or leave it unset."
                )
                continue

            if config_key in ("whatsapp_qr_timeout", "poll_interval_seconds"):
                try:
                    self._config[config_key] = int(env_val)
                except ValueError:
                    logger.warning("Invalid integer value for %s: %s", env_key, env_val)
            else:
                self._config[config_key] = env_val

        targets_env = os.environ.get("TARGETS")
        if targets_env:
            if os.environ.get("ALLOW_TARGETS_ENV_OVERRIDE", "").strip() == "1":
                targets = {}
                for pair in targets_env.split(","):
                    if ":" in pair:
                        name, number = pair.strip().split(":", 1)
                        targets[name.strip()] = number.strip()
                self._config["targets"] = targets
            else:
                logger.warning(
                    "Ignoring TARGETS from .env for safety. Edit config.json targets instead. "
                    "Set ALLOW_TARGETS_ENV_OVERRIDE=1 to enable override."
                )

        members_env = os.environ.get("ALL_MEMBERS")
        if members_env:
            self._config["all_members"] = [
                m.strip() for m in members_env.split(",") if m.strip()
            ]

    @staticmethod
    def _is_placeholder_sheet_url(value: str) -> bool:
        if "YOUR_SHEET_ID" in value.upper():
            return True
        return False

    def _validate(self) -> None:
        service_file = self.service_account_file
        if not Path(service_file).exists():
            raise FileNotFoundError(
                f"Service account file not found: {service_file}\n"
                f"Place credentials.json or service_account.json in project root."
            )

        sheet_url = str(self._config.get("sheet_url", "")).strip()
        if not sheet_url:
            raise ValueError("sheet_url is required in config.json or GOOGLE_SHEET_URL")

        if not self.targets:
            raise ValueError("At least one valid target is required in config.targets")

        clean_targets = self.targets
        if set(clean_targets.keys()) != set(STRICT_TARGETS.keys()):
            raise ValueError(
                "targets must include exactly Ibrahim and Muazzam for safety"
            )

        for name, required_number in STRICT_TARGETS.items():
            actual = clean_targets.get(name, "")
            if self._normalize_phone(actual) != self._normalize_phone(required_number):
                raise ValueError(
                    f"Target mismatch for {name}. Expected {required_number}, got {actual}"
                )

        poll_interval = self.poll_interval_seconds
        if poll_interval <= 0:
            raise ValueError("poll_interval_seconds must be greater than 0")

        selenium_dir = self.selenium_data_dir
        blocked_markers = [
            os.path.join("BraveSoftware", "Brave-Browser", "User Data").lower(),
            os.path.join("Google", "Chrome", "User Data").lower(),
            os.path.join("Microsoft", "Edge", "User Data").lower(),
        ]
        norm = os.path.normcase(os.path.normpath(selenium_dir)).lower()
        if any(marker in norm for marker in blocked_markers):
            raise ValueError(
                "selenium_data_dir must point to a dedicated automation profile "
                "outside default browser User Data directories"
            )

    @staticmethod
    def _normalize_phone(value: str) -> str:
        digits = re.sub(r"\D", "", str(value))
        return f"+{digits}" if digits else ""

    @staticmethod
    def _clean_targets(raw_targets: dict[str, Any]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for name, value in raw_targets.items():
            clean_name = str(name).strip()
            clean_value = Config._normalize_phone(str(value).strip())
            if not clean_name or not clean_value:
                continue
            cleaned[clean_name] = clean_value
        return cleaned

    @property
    def service_account_file(self) -> str:
        val = self._config.get("service_account_file", "")
        if val and Path(val).exists():
            return val
        fallback = BASE_DIR / "credentials.json"
        if fallback.exists():
            return str(fallback)
        fallback2 = BASE_DIR / "service_account.json"
        if fallback2.exists():
            return str(fallback2)
        return str(BASE_DIR / "service_account.json")

    @property
    def sheet_name(self) -> str:
        return self._config["sheet_name"]

    @property
    def sheet_url(self) -> str:
        return self._config["sheet_url"]

    @property
    def targets(self) -> dict[str, str]:
        raw_targets = self._config.get("targets", {})
        if not isinstance(raw_targets, dict):
            return {}
        return self._clean_targets(raw_targets)

    @property
    def all_members(self) -> list[str]:
        return self._config.get("all_members", [])

    @property
    def group_target(self) -> str:
        return self._config["group_target"]

    @property
    def admin_number(self) -> str:
        return self._config["admin_number"]

    @property
    def form_link(self) -> str:
        return self._config.get("form_link", "")

    @property
    def poll_interval_seconds(self) -> int:
        return self._config.get("poll_interval_seconds", 30)

    @property
    def whatsapp_qr_timeout(self) -> int:
        return self._config.get("whatsapp_qr_timeout", 300)

    @property
    def log_level(self) -> str:
        return self._config.get("log_level", "INFO")

    @property
    def selenium_data_dir(self) -> str:
        configured = str(self._config.get("selenium_data_dir", "")).strip()
        if configured:
            chosen = os.path.expandvars(os.path.expanduser(configured))
        else:
            chosen = os.path.join(os.path.expanduser("~"), ".jamiat_bot_selenium_data")

        os.makedirs(chosen, exist_ok=True)
        return chosen

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)
