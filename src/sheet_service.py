"""Google Sheets service with retry-aware operations."""

import logging
import time
from typing import cast

import gspread
import gspread.utils
from gspread.utils import ValueInputOption
from gspread.utils import rowcol_to_a1

logger = logging.getLogger(__name__)


class SheetService:
    """Handle Google Sheets authentication and operations safely."""

    MAX_RETRIES = 5
    INITIAL_RETRY_DELAY_SECONDS = 1.0

    def __init__(self, service_account_file: str) -> None:
        self._service_account_file = service_account_file
        self._client: gspread.Client | None = None

    def _retry(self, operation_name: str, func):
        """Retry transient sheet operations with exponential backoff."""
        delay = self.INITIAL_RETRY_DELAY_SECONDS
        last_error: Exception | None = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return func()
            except Exception as error:
                last_error = error
                if attempt >= self.MAX_RETRIES:
                    break
                logger.warning(
                    "%s failed (attempt %d/%d): %s",
                    operation_name,
                    attempt,
                    self.MAX_RETRIES,
                    error,
                )
                time.sleep(delay)
                delay = min(delay * 2, 20)

        logger.error(
            "%s failed after %d attempts: %s",
            operation_name,
            self.MAX_RETRIES,
            last_error,
        )
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"{operation_name} failed with unknown error")

    def _authenticate(self) -> gspread.Client:
        self._client = self._retry(
            "Authenticate with Google Sheets",
            lambda: gspread.service_account(filename=self._service_account_file),
        )
        logger.info("Authenticated with Google Sheets")
        return self._client

    @property
    def client(self) -> gspread.Client:
        if self._client is None:
            return self._retry("Authenticate with Google Sheets", self._authenticate)
        return self._client

    def reconnect(self) -> None:
        """Force re-authentication."""
        self._client = None
        self._retry("Reconnect Google Sheets client", self._authenticate)

    def open_by_url(self, url: str) -> gspread.worksheet.Worksheet:
        """Open a sheet by URL and return the first worksheet."""
        spreadsheet = self._retry(
            "Open spreadsheet by URL", lambda: self.client.open_by_url(url)
        )
        worksheet = spreadsheet.sheet1
        logger.info("Opened sheet: %s", worksheet.title)
        return worksheet

    def open_by_name(self, name: str) -> gspread.worksheet.Worksheet:
        """Open a sheet by name and return the first worksheet."""
        spreadsheet = self._retry(
            "Open spreadsheet by name", lambda: self.client.open(name)
        )
        worksheet = spreadsheet.sheet1
        logger.info("Opened sheet: %s", worksheet.title)
        return worksheet

    def get_all_data(
        self, worksheet: gspread.worksheet.Worksheet
    ) -> tuple[list[str], list[list[str]]]:
        """Get all worksheet data as (headers, rows)."""
        all_values = self._retry("Fetch worksheet values", worksheet.get_all_values)
        if not all_values:
            return [], []
        headers = all_values[0]
        rows = all_values[1:]
        return headers, rows

    def row_to_dict(self, headers: list[str], row_values: list[str]) -> dict[str, str]:
        """Convert row values to dict keyed by headers."""
        result: dict[str, str] = {}
        for i, header in enumerate(headers):
            result[header] = row_values[i] if i < len(row_values) else ""
        return result

    def ensure_column_exists(
        self, worksheet: gspread.worksheet.Worksheet, column_name: str
    ) -> int:
        """Ensure a column exists and return its 1-based index."""
        headers, _ = self.get_all_data(worksheet)

        if not headers:
            self._retry(
                "Create first header column",
                lambda: worksheet.update_cell(1, 1, column_name),
            )
            logger.info("Created column '%s' at position 1", column_name)
            return 1

        for idx, header in enumerate(headers):
            if header == column_name:
                return idx + 1

        new_col_idx = len(headers) + 1
        self._retry(
            f"Create header column '{column_name}'",
            lambda: worksheet.update_cell(1, new_col_idx, column_name),
        )
        logger.info("Created column '%s' at position %d", column_name, new_col_idx)
        return new_col_idx

    def update_cell_safe(
        self, worksheet: gspread.worksheet.Worksheet, row: int, col: int, value: str
    ) -> bool:
        """Update a single cell with retries; return success status."""
        try:
            self._retry(
                f"Update cell ({row}, {col})",
                lambda: worksheet.update_cell(row, col, value),
            )
            return True
        except Exception as error:
            logger.error("Failed to update cell (%d, %d): %s", row, col, error)
            return False

    def update_row_cells_safe(
        self,
        worksheet: gspread.worksheet.Worksheet,
        row: int,
        values_by_col: dict[int, str],
        value_input_option: ValueInputOption = ValueInputOption.raw,
    ) -> bool:
        """Batch update multiple cells in one row with one API call."""
        if not values_by_col:
            return True

        updates = []
        for col, value in sorted(values_by_col.items()):
            a1 = rowcol_to_a1(row, col)
            updates.append({"range": a1, "values": [[value]]})

        try:
            self._retry(
                f"Batch update row {row} cells",
                lambda: worksheet.batch_update(
                    updates,
                    value_input_option=cast(
                        gspread.utils.ValueInputOption, value_input_option
                    ),
                ),
            )
            return True
        except Exception as error:
            logger.error("Failed to batch update row %d: %s", row, error)
            return False
