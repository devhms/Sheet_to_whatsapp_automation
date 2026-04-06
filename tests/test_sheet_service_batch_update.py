import unittest
from unittest.mock import MagicMock

from src.sheet_service import SheetService


class SheetServiceBatchUpdateTest(unittest.TestCase):
    def test_update_row_cells_safe_uses_single_batch_call(self):
        svc = SheetService("service_account.json")
        worksheet = MagicMock()

        ok = svc.update_row_cells_safe(
            worksheet,
            row=10,
            values_by_col={3: "A", 5: "B"},
        )

        self.assertTrue(ok)
        worksheet.batch_update.assert_called_once()
        args, kwargs = worksheet.batch_update.call_args
        updates = args[0]
        self.assertEqual(len(updates), 2)
        self.assertEqual(updates[0]["range"], "C10")
        self.assertEqual(updates[1]["range"], "E10")
        self.assertIn("value_input_option", kwargs)


if __name__ == "__main__":
    unittest.main()
