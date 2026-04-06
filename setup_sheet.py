"""Setup Sheet - Apply formulas to Google Sheet columns."""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import Config
from src.logger import setup_logging
from src.sheet_service import SheetService

logger = logging.getLogger(__name__)


def main() -> None:
    config = Config()
    setup_logging(level=config.log_level)

    logger.info("Connecting to Google Sheets...")
    sheet_service = SheetService(config.service_account_file)
    worksheet = sheet_service.open_by_url(config.sheet_url)

    all_values = worksheet.get_all_values()
    total_rows = len(all_values)

    if total_rows < 2:
        logger.warning("Sheet is empty or only has headers")
        return

    logger.info("Found %d rows (including header)", total_rows)

    headers = ["Salah Integrity", "Status Flag", "Daily Score"]
    logger.info("Writing headers to L1:N1...")
    worksheet.update(range_name="L1:N1", values=[headers])

    formulas = []
    for i in range(2, total_rows + 1):
        row_formulas = [
            f'=COUNTIF(D{i}:H{i}, "*Missed*")',
            f'=IF(L{i}>0, "🔴 CRITICAL", IF(J{i}<2, "🟡 WARNING", "🟢 PASSED"))',
            f'=(COUNTIF(D{i}:H{i}, "Offered*")*15) + IF(J{i}>2, 15, 0) + K{i}',
        ]
        formulas.append(row_formulas)

    range_str = f"L2:N{total_rows}"
    logger.info("Applying formulas to %s...", range_str)
    from gspread.utils import ValueInputOption

    worksheet.update(
        range_name=range_str,
        values=formulas,
        value_input_option=ValueInputOption.user_entered,
    )

    logger.info("Formulas applied to all rows")
    logger.info("Existing data in columns A-K was NOT touched")


if __name__ == "__main__":
    main()
