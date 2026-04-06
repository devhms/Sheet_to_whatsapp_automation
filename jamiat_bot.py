"""Jamiat Bot - Ghost Hunter, Red Flag Scanner, and Reminder modules."""

import argparse
import datetime as dt
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import Config
from src.logger import setup_logging
from src.messages import (
    format_missing_report_message,
    format_red_flag_alert,
    format_reminder_message,
)
from src.sheet_service import SheetService
from src.whatsapp_service import WhatsAppService

logger = logging.getLogger(__name__)

SALAH_COLUMNS = [
    "Salah Record [Fajr]",
    "Salah Record [Dhuhr]",
    "Salah Record [Asr]",
    "Salah Record [Maghrib]",
    "Salah Record [Isha]",
]

DATE_FORMATS = [
    "%m/%d/%Y",
    "%m/%d/%y",
    "%Y-%m-%d",
    "%d/%m/%Y",
]


def _extract_member_name(row_dict: dict[str, str]) -> str:
    for key in ("Select your name", "Select Your Name"):
        value = str(row_dict.get(key, "")).strip()
        if value:
            return value
    return "Unknown"


def _extract_report_date(row_dict: dict[str, str]) -> dt.date | None:
    raw = str(row_dict.get("Date of Report", row_dict.get("Timestamp", ""))).strip()
    if not raw:
        return None

    date_token = raw.split(" ")[0].strip()
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(date_token, fmt).date()
        except ValueError:
            continue
    return None


def _today() -> dt.date:
    return dt.datetime.now().date()


def run_ghost_hunter(config: Config, whatsapp: WhatsAppService) -> None:
    logger.info("Running GHOST HUNTER module")

    if not config.group_target.strip():
        logger.error("group_target is empty in config. Ghost hunter aborted.")
        return

    sheet_service = SheetService(config.service_account_file)
    worksheet = sheet_service.open_by_url(config.sheet_url)
    headers, data_rows = sheet_service.get_all_data(worksheet)

    today = _today()
    logger.info("Checking submissions for: %s", today.isoformat())

    submitted_names: set[str] = set()
    for row_values in data_rows:
        row_dict = sheet_service.row_to_dict(headers, row_values)
        report_date = _extract_report_date(row_dict)
        if report_date != today:
            continue

        name = _extract_member_name(row_dict)
        if name and name != "Unknown":
            submitted_names.add(name)

    all_members = set(config.all_members)
    missing_members = sorted(all_members - submitted_names)

    if missing_members:
        logger.warning("Missing reports: %s", missing_members)
        msg = format_missing_report_message(missing_members)
        whatsapp.send_message(config.group_target, msg, use_search=True)
    else:
        logger.info("Everyone has submitted!")


def run_red_flag_scanner(config: Config, whatsapp: WhatsAppService) -> None:
    logger.info("Running RED FLAG SCANNER module")

    if not config.admin_number.strip():
        logger.error("admin_number is empty in config. Scanner aborted.")
        return

    sheet_service = SheetService(config.service_account_file)
    worksheet = sheet_service.open_by_url(config.sheet_url)
    headers, data_rows = sheet_service.get_all_data(worksheet)

    today = _today()
    status_col_idx = sheet_service.ensure_column_exists(worksheet, "Admin_Notified")

    for i, row_values in enumerate(data_rows):
        row_dict = sheet_service.row_to_dict(headers, row_values)
        report_date = _extract_report_date(row_dict)
        if report_date != today:
            continue

        name = _extract_member_name(row_dict)
        already_notified = str(row_dict.get("Admin_Notified", "")).strip().lower() == "true"

        missed_prayers: list[str] = []
        for col in SALAH_COLUMNS:
            value = str(row_dict.get(col, "")).strip()
            if "offered" not in value.lower():
                missed_prayers.append(col.replace("Salah Record ", ""))

        if missed_prayers and not already_notified:
            logger.warning("Red flag found for: %s", name)
            alert_msg = format_red_flag_alert(name, missed_prayers)
            sent = whatsapp.send_message(config.admin_number, alert_msg, use_search=False)
            if sent:
                sheet_service.update_cell_safe(worksheet, i + 2, status_col_idx, "TRUE")
                logger.info("Updated Admin_Notified for %s", name)
            else:
                logger.warning("Failed to notify admin for %s", name)
        elif missed_prayers and already_notified:
            logger.debug("Skipping %s (already notified)", name)


def run_reminder(config: Config, whatsapp: WhatsAppService) -> None:
    logger.info("Running MORNING BELL reminder module")

    if not config.group_target.strip():
        logger.error("group_target is empty in config. Reminder aborted.")
        return

    msg = format_reminder_message(config.form_link)
    whatsapp.send_message(config.group_target, msg, use_search=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Jamiat Management System Bot")
    parser.add_argument("mode", choices=["ghost", "scanner", "reminder"], help="Mode to run")
    args = parser.parse_args()

    config = Config()
    setup_logging(level=config.log_level)

    whatsapp = WhatsAppService(
        selenium_data_dir=config.selenium_data_dir,
        qr_timeout=config.whatsapp_qr_timeout,
    )

    try:
        whatsapp.init_browser()

        if args.mode == "ghost":
            run_ghost_hunter(config, whatsapp)
        elif args.mode == "scanner":
            run_red_flag_scanner(config, whatsapp)
        elif args.mode == "reminder":
            run_reminder(config, whatsapp)

    except Exception as e:
        logger.error("Bot error: %s", e)
        raise
    finally:
        whatsapp.close()


if __name__ == "__main__":
    main()
