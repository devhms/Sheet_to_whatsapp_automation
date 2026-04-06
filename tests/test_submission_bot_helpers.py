import json
import os
import tempfile
import unittest
from pathlib import Path

import submission_bot as sb


class SubmissionBotHelpersTest(unittest.TestCase):
    def test_choose_delivery_target_prefers_phone(self):
        target, use_search = sb._choose_delivery_target("Ibrahim", "+923300301917")
        self.assertEqual(target, "+923300301917")
        self.assertFalse(use_search)

    def test_choose_delivery_target_uses_name_when_number_invalid(self):
        target, use_search = sb._choose_delivery_target("Muazzam", "not-a-phone")
        self.assertEqual(target, "Muazzam")
        self.assertTrue(use_search)

    def test_canonicalize_targets_from_mixed_tokens(self):
        config_targets = {
            "Ibrahim": "+923300301917",
            "Muazzam": "+923055375994",
        }
        mixed = {
            "Ibrahim",
            "+923055375994",
            "923300301917",
            "muazzam",
            "unknown",
        }

        normalized = sb._canonicalize_delivered_targets(mixed, config_targets)
        self.assertEqual(normalized, {"Ibrahim", "Muazzam"})

    def test_journal_roundtrip_and_targets(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "journal.json")
            row_id = "ts|2026-04-06 01:00:00|Yahya"
            rows = sb._journal_load(path)

            changed = sb._journal_mark_target(rows, row_id, "Ibrahim")
            self.assertTrue(changed)
            sb._journal_save(path, rows)

            loaded = sb._journal_load(path)
            targets = sb._journal_targets(loaded, row_id)
            self.assertEqual(targets, {"Ibrahim"})

            self.assertTrue(sb._journal_mark_done(loaded, row_id))
            self.assertFalse(sb._journal_mark_done(loaded, row_id))

    def test_row_identity_prefers_timestamp(self):
        row = {
            "Timestamp": "04/04/2026 22:25:40",
            "Select your name": "Yahya Salman",
            "Date of Report": "2026-04-04",
        }
        rid = sb._row_identity(51, row)
        self.assertEqual(rid, "ts|04/04/2026 22:25:40|Yahya Salman")

    def test_row_identity_fallback_hash(self):
        row = {
            "A": "x",
            "B": "y",
            "Bot Details Sent": "FALSE",
            "Bot Delivery State": "Ibrahim",
        }
        rid = sb._row_identity(10, row)
        self.assertTrue(rid.startswith("hash|"))

    def test_delivery_state_parse_and_format(self):
        parsed = sb._parse_delivery_state("Ibrahim, Muazzam,  ")
        self.assertEqual(parsed, {"Ibrahim", "Muazzam"})
        formatted = sb._format_delivery_state(parsed)
        self.assertIn("Ibrahim", formatted)
        self.assertIn("Muazzam", formatted)

    def test_heartbeat_and_event_log_writes(self):
        with tempfile.TemporaryDirectory() as td:
            hb = os.path.join(td, "heartbeat.json")
            ev = os.path.join(td, "events.jsonl")

            stats = sb.RunStats(startup_time=0.0)
            sb._write_heartbeat(hb, 1234, stats, last_error="none")
            self.assertTrue(Path(hb).exists())

            data = json.loads(Path(hb).read_text(encoding="utf-8"))
            self.assertEqual(data["pid"], 1234)
            self.assertIn("stats", data)

            sb._append_event(ev, "test_event", key="value")
            lines = Path(ev).read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            evt = json.loads(lines[0])
            self.assertEqual(evt["event"], "test_event")
            self.assertEqual(evt["key"], "value")

    def test_write_json_atomic_creates_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "atomic.json")
            sb._write_json_atomic(path, {"ok": True, "x": 1})
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
