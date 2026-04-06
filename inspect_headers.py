"""Inspect sheet headers - utility script."""

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

    try:
        sheet_service = SheetService(config.service_account_file)
        worksheet = sheet_service.open_by_url(config.sheet_url)
        headers, _ = sheet_service.get_all_data(worksheet)

        logger.info("Connection successful!")
        logger.info("Headers found:")
        for i, h in enumerate(headers):
            logger.info("  %d: %s", i, h)

    except Exception as e:
        logger.error("Error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
