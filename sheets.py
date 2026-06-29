from __future__ import annotations

import logging
from typing import Iterable

import gspread

from config import Settings
from models import PendingPatientRow


LOGGER = logging.getLogger(__name__)


class GoogleSheetRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = gspread.service_account(filename=str(settings.credentials_file))
        self._worksheet = (
            self._client.open_by_key(settings.sheet_id).worksheet(settings.worksheet_name)
        )

    def load_pending_rows(self, limit: int) -> list[PendingPatientRow]:
        all_rows = self._worksheet.get_all_values()
        header_row_number, header_map = self._find_header_row(all_rows)
        data_rows = all_rows[header_row_number:]

        pending: list[PendingPatientRow] = []
        status_key = self._resolve_status_header(header_map)

        for reverse_index, row in enumerate(reversed(data_rows), start=1):
            offset = header_row_number + len(data_rows) - reverse_index + 1
            values = self._row_to_map(header_map, row)
            status_value = values.get(status_key, "").strip().upper()
            if status_value not in {"", "N"}:
                continue

            pending.append(
                PendingPatientRow(
                    row_number=offset,
                    first_name=values.get(self.settings.first_column, "").strip(),
                    last_name=values.get(self.settings.last_column, "").strip(),
                    dob_raw=values.get(self.settings.dob_column, "").strip(),
                    status_column_name=status_key,
                    status_column_index=header_map[status_key],
                )
            )
            if len(pending) >= limit:
                break

        return pending

    def mark_profile_created(self, row: PendingPatientRow) -> None:
        LOGGER.info(
            "Updating sheet row %s column '%s' to Y",
            row.row_number,
            row.status_column_name,
        )
        self._worksheet.update_cell(row.row_number, row.status_column_index, "Y")

    def _find_header_row(self, rows: Iterable[list[str]]) -> tuple[int, dict[str, int]]:
        required = {
            self._normalize_header(self.settings.first_column),
            self._normalize_header(self.settings.last_column),
            self._normalize_header(self.settings.dob_column),
        }
        allowed_status = {
            self._normalize_header(name) for name in self.settings.status_columns
        }

        for index, row in enumerate(rows, start=1):
            normalized = {
                self._normalize_header(value): column_number
                for column_number, value in enumerate(row, start=1)
                if value.strip()
            }
            if required.issubset(normalized) and normalized.keys() & allowed_status:
                header_map = {
                    self.settings.first_column: normalized[
                        self._normalize_header(self.settings.first_column)
                    ],
                    self.settings.last_column: normalized[
                        self._normalize_header(self.settings.last_column)
                    ],
                    self.settings.dob_column: normalized[
                        self._normalize_header(self.settings.dob_column)
                    ],
                }
                for status_name in self.settings.status_columns:
                    key = self._normalize_header(status_name)
                    if key in normalized:
                        header_map[status_name] = normalized[key]
                return index, header_map

        raise ValueError("Could not locate a valid header row in the worksheet.")

    def _resolve_status_header(self, header_map: dict[str, int]) -> str:
        for column_name in self.settings.status_columns:
            if column_name in header_map:
                return column_name
        raise ValueError("Worksheet is missing both supported MVE status columns.")

    @staticmethod
    def _normalize_header(value: str) -> str:
        return " ".join(value.strip().casefold().split())

    @staticmethod
    def _row_to_map(header_map: dict[str, int], row_values: list[str]) -> dict[str, str]:
        return {
            header: row_values[column_index - 1] if column_index - 1 < len(row_values) else ""
            for header, column_index in header_map.items()
        }
