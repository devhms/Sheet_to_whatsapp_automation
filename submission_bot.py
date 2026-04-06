"""Submission Bot - Monitors Google Sheets and sends WhatsApp notifications."""

import logging
import os
import sys
import time
import json
import hashlib
import re
from typing import Optional
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import Config
from src.logger import setup_logging
from src.messages import format_submission_message
from src.sheet_service import SheetService
from src.whatsapp_service import WhatsAppService

STATUS_COLUMN_HEADER = "Bot Details Sent"
DELIVERY_STATE_COLUMN_HEADER = "Bot Delivery State"
LOCK_FILENAME = ".submission_bot.lock"
JOURNAL_FILENAME = ".delivery_journal.json"
JOURNAL_VERSION = 1
JOURNAL_SAVE_RETRIES = 5
HEARTBEAT_FILENAME = ".bot_heartbeat.json"
EVENT_LOG_FILENAME = ".bot_events.jsonl"
HEARTBEAT_INTERVAL_SECONDS = 10


@dataclass
class RunStats:
    cycles: int = 0
    rows_seen: int = 0
    rows_completed: int = 0
    sends_attempted: int = 0
    sends_succeeded: int = 0
    sends_failed: int = 0
    startup_time: float = 0.0


def _write_json_atomic(path: str, payload: dict) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, sort_keys=True, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def _append_event(path: str, event_type: str, **fields) -> None:
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event_type,
        **fields,
    }
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")
    except Exception as exc:
        logging.getLogger(__name__).warning("Could not append bot event: %s", exc)


def _write_heartbeat(
    path: str,
    pid: int,
    run_stats: RunStats,
    last_error: str | None = None,
) -> None:
    payload = {
        "pid": pid,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "uptime_seconds": int(time.time() - run_stats.startup_time),
        "stats": {
            "cycles": run_stats.cycles,
            "rows_seen": run_stats.rows_seen,
            "rows_completed": run_stats.rows_completed,
            "sends_attempted": run_stats.sends_attempted,
            "sends_succeeded": run_stats.sends_succeeded,
            "sends_failed": run_stats.sends_failed,
        },
        "last_error": last_error or "",
    }
    try:
        _write_json_atomic(path, payload)
    except Exception as exc:
        logging.getLogger(__name__).warning("Could not write bot heartbeat: %s", exc)


def _read_lock_pid(lock_path: str) -> Optional[int]:
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _acquire_lock(lock_path: str) -> Optional[int]:
    """Create a process lock file to prevent duplicate bot instances."""
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        return fd
    except FileExistsError:
        pid = _read_lock_pid(lock_path)
        if pid is not None and not _is_process_running(pid):
            try:
                os.remove(lock_path)
            except OSError:
                return None
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode("utf-8"))
                return fd
            except FileExistsError:
                return None
        return None


def _recover_stale_lock(lock_path: str) -> bool:
    pid = _read_lock_pid(lock_path)
    if pid is None:
        try:
            os.remove(lock_path)
            return True
        except OSError:
            return False

    if not _is_process_running(pid):
        try:
            os.remove(lock_path)
            return True
        except OSError:
            return False

    return False


def _release_lock(fd: Optional[int], lock_path: str) -> None:
    """Release process lock file."""
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass
    if os.path.exists(lock_path):
        try:
            os.remove(lock_path)
        except OSError:
            pass


def _parse_delivery_state(raw_value: str) -> set[str]:
    if not raw_value:
        return set()
    return {item.strip() for item in str(raw_value).split(",") if item.strip()}


def _format_delivery_state(delivered_targets: set[str]) -> str:
    return ", ".join(sorted(delivered_targets))


def _canonicalize_delivered_targets(
    delivered_targets: set[str], config_targets: dict[str, str]
) -> set[str]:
    aliases: dict[str, str] = {}

    for name, number in config_targets.items():
        canonical_name = str(name).strip()
        if not canonical_name:
            continue

        aliases[canonical_name.lower()] = canonical_name

        digits = re.sub(r"\D", "", str(number))
        if digits:
            aliases[digits] = canonical_name
            aliases[f"+{digits}"] = canonical_name

    normalized: set[str] = set()
    for raw in delivered_targets:
        token = str(raw).strip()
        if not token:
            continue

        key = token.lower()
        if key in aliases:
            normalized.add(aliases[key])
            continue

        digits = re.sub(r"\D", "", token)
        if digits in aliases:
            normalized.add(aliases[digits])
            continue
        plus_digits = f"+{digits}" if digits else ""
        if plus_digits and plus_digits in aliases:
            normalized.add(aliases[plus_digits])

    return normalized


def _choose_delivery_target(target_name: str, number: str) -> tuple[str, bool]:
    """Choose safest target route: phone URL first, chat search as fallback."""
    clean_number = str(number).strip()
    if WhatsAppService.is_phone_target(clean_number):
        return clean_number, False

    clean_name = str(target_name).strip()
    if clean_name:
        return clean_name, True

    return clean_number, True


def _journal_load(path: str) -> dict[str, dict[str, object]]:
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        logging.getLogger(__name__).warning("Could not read delivery journal: %s", exc)
        return {}

    if not isinstance(payload, dict):
        return {}

    rows = payload.get("rows", {})
    if not isinstance(rows, dict):
        return {}

    cleaned: dict[str, dict[str, object]] = {}
    for row_id, entry in rows.items():
        if not isinstance(row_id, str) or not isinstance(entry, dict):
            continue

        raw_targets = entry.get("targets", [])
        if not isinstance(raw_targets, list):
            raw_targets = []
        targets = sorted(
            {str(item).strip() for item in raw_targets if str(item).strip()}
        )

        cleaned[row_id] = {
            "targets": targets,
            "done": bool(entry.get("done", False)),
            "updated_at": float(entry.get("updated_at", 0.0) or 0.0),
        }

    return cleaned


def _journal_save(path: str, rows: dict[str, dict[str, object]]) -> None:
    payload = {"version": JOURNAL_VERSION, "rows": rows}
    tmp_path = f"{path}.tmp"
    last_error: Exception | None = None

    for attempt in range(1, JOURNAL_SAVE_RETRIES + 1):
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=True, sort_keys=True, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(min(0.2 * attempt, 1.0))

    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except OSError:
        pass

    raise RuntimeError(f"Could not persist delivery journal: {last_error}")


def _journal_targets(rows: dict[str, dict[str, object]], row_id: str) -> set[str]:
    entry = rows.get(row_id)
    if not entry:
        return set()

    raw_targets = entry.get("targets", [])
    if not isinstance(raw_targets, list):
        return set()

    return {str(item).strip() for item in raw_targets if str(item).strip()}


def _journal_mark_target(
    rows: dict[str, dict[str, object]], row_id: str, target_name: str
) -> bool:
    entry = rows.setdefault(row_id, {"targets": [], "done": False, "updated_at": 0.0})
    raw_targets = entry.get("targets", [])
    if not isinstance(raw_targets, list):
        raw_targets = []
    current = {str(item).strip() for item in raw_targets if str(item).strip()}
    before = set(current)
    current.add(str(target_name).strip())

    changed = current != before
    if changed:
        entry["targets"] = sorted(current)
        entry["updated_at"] = time.time()
    return changed


def _journal_mark_done(rows: dict[str, dict[str, object]], row_id: str) -> bool:
    entry = rows.setdefault(row_id, {"targets": [], "done": False, "updated_at": 0.0})
    if bool(entry.get("done", False)):
        return False

    entry["done"] = True
    entry["updated_at"] = time.time()
    return True


def _row_cell(row_values: list[str], col_idx: int) -> str:
    idx = col_idx - 1
    if idx < 0 or idx >= len(row_values):
        return ""
    return str(row_values[idx]).strip()


def _member_name(row_dict: dict[str, str], sheet_row_num: int) -> str:
    for key in ("Select your name", "Select Your Name"):
        value = str(row_dict.get(key, "")).strip()
        if value:
            return value
    return f"Row {sheet_row_num}"


def _row_identity(sheet_row_num: int, row_dict: dict[str, str]) -> str:
    timestamp = str(row_dict.get("Timestamp", "")).strip()
    name = _member_name(row_dict, sheet_row_num)
    date = str(row_dict.get("Date of Report", "")).strip()

    if timestamp:
        return f"ts|{timestamp}|{name}"

    if name and date:
        return f"nd|{name}|{date}"

    compact: dict[str, str] = {}
    for key in sorted(row_dict):
        if not key or key in (STATUS_COLUMN_HEADER, DELIVERY_STATE_COLUMN_HEADER):
            continue
        val = str(row_dict.get(key, "")).strip()
        if val:
            compact[key] = val

    digest = hashlib.sha1(
        json.dumps(compact, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"hash|{digest}"


def main() -> None:
    config = Config()
    setup_logging(level=config.log_level)
    logger = logging.getLogger(__name__)

    lock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOCK_FILENAME)
    lock_fd = _acquire_lock(lock_path)
    if lock_fd is None:
        if _recover_stale_lock(lock_path):
            lock_fd = _acquire_lock(lock_path)

    if lock_fd is None:
        logger.error(
            "Another bot instance appears to be running. If not, remove lock file: %s",
            lock_path,
        )
        sys.exit(1)

    logger.info("Starting Submission Bot v3.1...")
    logger.info("=" * 60)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    heartbeat_path = os.path.join(base_dir, HEARTBEAT_FILENAME)
    event_log_path = os.path.join(base_dir, EVENT_LOG_FILENAME)
    run_stats = RunStats(startup_time=time.time())
    next_heartbeat_at = 0.0
    last_error_text: str | None = None

    journal_path = os.path.join(base_dir, JOURNAL_FILENAME)
    delivery_journal = _journal_load(journal_path)
    logger.info("Loaded delivery journal rows: %d", len(delivery_journal))
    _append_event(
        event_log_path,
        "bot_started",
        journal_rows=len(delivery_journal),
        targets=list(config.targets.keys()),
    )

    logger.info("Connecting to Google Sheets...")
    sheet_service = SheetService(config.service_account_file)
    worksheet = sheet_service.open_by_url(config.sheet_url)
    logger.info("Connected to sheet: %s", worksheet.title)

    status_col_idx = sheet_service.ensure_column_exists(worksheet, STATUS_COLUMN_HEADER)
    delivery_col_idx = sheet_service.ensure_column_exists(
        worksheet, DELIVERY_STATE_COLUMN_HEADER
    )
    logger.info("Status column '%s' at index %d", STATUS_COLUMN_HEADER, status_col_idx)
    logger.info(
        "Delivery column '%s' at index %d",
        DELIVERY_STATE_COLUMN_HEADER,
        delivery_col_idx,
    )

    logger.info("Initializing WhatsApp...")
    whatsapp = WhatsAppService(
        selenium_data_dir=config.selenium_data_dir,
        qr_timeout=config.whatsapp_qr_timeout,
        allow_ephemeral_fallback=False,
        allow_profile_reset=False,
    )

    try:
        whatsapp.init_browser()
    except Exception as e:
        _append_event(event_log_path, "whatsapp_init_failed", error=str(e))
        _write_heartbeat(
            heartbeat_path,
            os.getpid(),
            run_stats,
            last_error=str(e),
        )
        logger.critical("Failed to initialize WhatsApp: %s", e)
        _release_lock(lock_fd, lock_path)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Bot running! Poll interval: %d sec", config.poll_interval_seconds)
    logger.info("Targets: %s", ", ".join(config.targets.keys()))
    logger.info("=" * 60)

    consecutive_errors = 0
    runtime_delivery_cache: dict[str, set[str]] = {}

    try:
        while True:
            try:
                now = time.time()
                if now >= next_heartbeat_at:
                    _write_heartbeat(
                        heartbeat_path,
                        os.getpid(),
                        run_stats,
                        last_error=last_error_text,
                    )
                    next_heartbeat_at = now + HEARTBEAT_INTERVAL_SECONDS

                if consecutive_errors >= 3:
                    logger.info("Reconnecting to Google Sheets...")
                    sheet_service.reconnect()
                    worksheet = sheet_service.open_by_url(config.sheet_url)
                    consecutive_errors = 0

                headers, data_rows = sheet_service.get_all_data(worksheet)

                if not data_rows:
                    logger.debug("No data rows found. Waiting...")
                    time.sleep(config.poll_interval_seconds)
                    continue

                try:
                    status_col_idx = headers.index(STATUS_COLUMN_HEADER) + 1
                except ValueError:
                    status_col_idx = sheet_service.ensure_column_exists(
                        worksheet, STATUS_COLUMN_HEADER
                    )
                    headers, data_rows = sheet_service.get_all_data(worksheet)

                try:
                    delivery_col_idx = headers.index(DELIVERY_STATE_COLUMN_HEADER) + 1
                except ValueError:
                    delivery_col_idx = sheet_service.ensure_column_exists(
                        worksheet, DELIVERY_STATE_COLUMN_HEADER
                    )
                    headers, data_rows = sheet_service.get_all_data(worksheet)

                target_names = list(config.targets.keys())
                processed_count = 0
                run_stats.cycles += 1

                for i, row_values in enumerate(data_rows):
                    sheet_row_num = i + 2
                    status = _row_cell(row_values, status_col_idx).upper()
                    if status == "TRUE":
                        continue

                    run_stats.rows_seen += 1

                    row_dict = sheet_service.row_to_dict(headers, row_values)
                    member_name = _member_name(row_dict, sheet_row_num)
                    row_id = _row_identity(sheet_row_num, row_dict)
                    logger.info(
                        "Processing row %d: %s (row_id=%s)",
                        sheet_row_num,
                        member_name,
                        row_id,
                    )

                    delivery_raw = _row_cell(row_values, delivery_col_idx)
                    delivered = _parse_delivery_state(delivery_raw)
                    delivered |= runtime_delivery_cache.get(row_id, set())
                    delivered |= _journal_targets(delivery_journal, row_id)
                    delivered = _canonicalize_delivered_targets(
                        delivered, config.targets
                    )

                    pending = [
                        (name, number)
                        for name, number in config.targets.items()
                        if name not in delivered
                    ]

                    logger.info(
                        "Row %d delivery state | delivered=%s | pending=%s",
                        sheet_row_num,
                        sorted(delivered),
                        [name for name, _ in pending],
                    )

                    if not pending:
                        if _journal_mark_done(delivery_journal, row_id):
                            _journal_save(journal_path, delivery_journal)

                        state_value = _format_delivery_state(delivered)
                        updates = {
                            status_col_idx: "TRUE",
                            delivery_col_idx: state_value,
                        }
                        if sheet_service.update_row_cells_safe(
                            worksheet,
                            sheet_row_num,
                            updates,
                        ):
                            logger.info(
                                "Row %d already fully delivered; marked DONE",
                                sheet_row_num,
                            )
                            processed_count += 1
                            run_stats.rows_completed += 1
                            _append_event(
                                event_log_path,
                                "row_marked_done",
                                row_id=row_id,
                                sheet_row=sheet_row_num,
                                via="already_delivered",
                            )
                        continue

                    message = format_submission_message(row_dict, STATUS_COLUMN_HEADER)
                    row_had_failures = False

                    for target_name, number in pending:
                        delivery_target, use_search = _choose_delivery_target(
                            target_name,
                            number,
                        )
                        run_stats.sends_attempted += 1
                        success = whatsapp.send_message(
                            delivery_target,
                            message,
                            use_search=use_search,
                        )

                        if not success and not use_search:
                            fallback_label = str(target_name).strip()
                            if fallback_label and fallback_label != delivery_target:
                                logger.warning(
                                    "Phone route failed for %s; retrying by chat label",
                                    target_name,
                                )
                                success = whatsapp.send_message(
                                    fallback_label,
                                    message,
                                    use_search=True,
                                )

                        if success:
                            run_stats.sends_succeeded += 1
                            delivered.add(target_name)
                            runtime_delivery_cache[row_id] = set(delivered)
                            if _journal_mark_target(
                                delivery_journal, row_id, target_name
                            ):
                                _journal_save(journal_path, delivery_journal)

                            state_value = _format_delivery_state(delivered)
                            if not sheet_service.update_cell_safe(
                                worksheet,
                                sheet_row_num,
                                delivery_col_idx,
                                state_value,
                            ):
                                logger.warning(
                                    "Delivery state update failed for row %d (target=%s)",
                                    sheet_row_num,
                                    target_name,
                                )
                            logger.info("  [OK] Sent to %s", target_name)
                            _append_event(
                                event_log_path,
                                "send_success",
                                row_id=row_id,
                                sheet_row=sheet_row_num,
                                target=target_name,
                            )
                        else:
                            run_stats.sends_failed += 1
                            row_had_failures = True
                            logger.warning("  [FAIL] Failed for %s", target_name)
                            _append_event(
                                event_log_path,
                                "send_failure",
                                row_id=row_id,
                                sheet_row=sheet_row_num,
                                target=target_name,
                            )

                    if all(name in delivered for name in target_names):
                        if _journal_mark_done(delivery_journal, row_id):
                            _journal_save(journal_path, delivery_journal)

                        state_value = _format_delivery_state(delivered)
                        updates = {
                            status_col_idx: "TRUE",
                            delivery_col_idx: state_value,
                        }
                        if sheet_service.update_row_cells_safe(
                            worksheet,
                            sheet_row_num,
                            updates,
                        ):
                            runtime_delivery_cache.pop(row_id, None)
                            logger.info("  [OK] Row %d marked DONE", sheet_row_num)
                            processed_count += 1
                            run_stats.rows_completed += 1
                            _append_event(
                                event_log_path,
                                "row_marked_done",
                                row_id=row_id,
                                sheet_row=sheet_row_num,
                                via="delivered_all_targets",
                            )
                        else:
                            logger.warning(
                                "  [FAIL] Could not mark row %d DONE", sheet_row_num
                            )
                    elif row_had_failures:
                        logger.warning(
                            "  [PENDING] Row %d remains pending targets", sheet_row_num
                        )

                if processed_count:
                    logger.info("Cycle complete: %d row(s) completed", processed_count)
                else:
                    logger.info("Cycle complete: nothing new to process")

                consecutive_errors = 0
                last_error_text = None
                time.sleep(config.poll_interval_seconds)

            except Exception as e:
                consecutive_errors += 1
                logger.error("Loop error (attempt %d): %s", consecutive_errors, e)
                last_error_text = str(e)
                _append_event(
                    event_log_path,
                    "loop_error",
                    attempt=consecutive_errors,
                    error=str(e),
                )
                time.sleep(min(60 * consecutive_errors, 300))

    except KeyboardInterrupt:
        logger.info("Stopping bot (Ctrl+C)")
        _append_event(event_log_path, "bot_stopped", reason="keyboard_interrupt")
    finally:
        _write_heartbeat(
            heartbeat_path,
            os.getpid(),
            run_stats,
            last_error=last_error_text,
        )
        logger.info("Closing browser...")
        whatsapp.close()
        _release_lock(lock_fd, lock_path)
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
