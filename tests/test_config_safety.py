import tempfile
import unittest
from pathlib import Path

from src.config import Config


class ConfigSafetyTest(unittest.TestCase):
    def _build_base_config(self, tmp_dir: str) -> dict:
        service_file = Path(tmp_dir) / "service_account.json"
        service_file.write_text("{}", encoding="utf-8")

        return {
            "sheet_name": "X",
            "service_account_file": str(service_file),
            "sheet_url": "https://docs.google.com/spreadsheets/d/abc/edit",
            "targets": {
                "Ibrahim": "+923300301917",
                "Muazzam": "+923055375994",
            },
            "all_members": ["Ibrahim", "Muazzam"],
            "group_target": "",
            "admin_number": "",
            "form_link": "",
            "selenium_data_dir": str(Path(tmp_dir) / "selenium_profile"),
            "poll_interval_seconds": 30,
            "whatsapp_qr_timeout": 300,
            "log_level": "INFO",
        }

    def test_rejects_wrong_target_number(self):
        with tempfile.TemporaryDirectory() as td:
            data = self._build_base_config(td)
            data["targets"]["Muazzam"] = "+923001234567"

            cfg = Config.__new__(Config)
            cfg._config = data

            with self.assertRaises(ValueError):
                cfg._validate()

    def test_rejects_missing_required_target(self):
        with tempfile.TemporaryDirectory() as td:
            data = self._build_base_config(td)
            del data["targets"]["Muazzam"]

            cfg = Config.__new__(Config)
            cfg._config = data

            with self.assertRaises(ValueError):
                cfg._validate()

    def test_rejects_default_browser_user_data_dir(self):
        with tempfile.TemporaryDirectory() as td:
            data = self._build_base_config(td)
            data["selenium_data_dir"] = (
                "C:/Users/hafiz/AppData/Local/BraveSoftware/Brave-Browser/User Data"
            )

            cfg = Config.__new__(Config)
            cfg._config = data

            with self.assertRaises(ValueError):
                cfg._validate()


if __name__ == "__main__":
    unittest.main()
