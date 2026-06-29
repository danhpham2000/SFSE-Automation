from __future__ import annotations

import logging

from config import Settings
from models import BatchSummary, PendingPatientRow, SearchStatus
from mve import MVEAutomationClient, MVEFatalError, MVERowError
from sheets import GoogleSheetRepository


LOGGER = logging.getLogger(__name__)


class PatientProfileWorkflow:
    def __init__(
        self,
        settings: Settings,
        sheet_repository: GoogleSheetRepository,
        mve_client: MVEAutomationClient,
    ) -> None:
        self.settings = settings
        self.sheet_repository = sheet_repository
        self.mve_client = mve_client

    def run(self, limit: int | None = None) -> BatchSummary:
        batch_limit = limit or self.settings.batch_size
        summary = BatchSummary()

        rows = self.sheet_repository.load_pending_rows(batch_limit)
        LOGGER.info("Loaded %s pending rows from Google Sheets.", len(rows))
        if not rows:
            return summary

        self.mve_client.open_or_focus_mve()
        self.mve_client.login_if_needed()
        self.mve_client.handle_daily_closing_popup()

        for row in rows:
            summary.processed += 1
            try:
                self._process_row(row)
                summary.updated += 1
            except ValueError as exc:
                LOGGER.warning("Row %s skipped: %s", row.row_number, exc)
                summary.skipped += 1
            except MVERowError as exc:
                LOGGER.warning("Row %s left unchanged: %s", row.row_number, exc)
                summary.skipped += 1
            except MVEFatalError:
                summary.failed += 1
                raise
            except Exception as exc:  # pragma: no cover - operational fallback
                LOGGER.exception("Row %s failed unexpectedly: %s", row.row_number, exc)
                summary.failed += 1

        return summary

    def _process_row(self, row: PendingPatientRow) -> None:
        if not row.first_name:
            raise ValueError("First name is missing.")
        if not row.last_name:
            raise ValueError("Last name is missing.")
        if not row.dob_raw:
            raise ValueError("DOB is missing.")

        search_result = self.mve_client.search_patient(
            first_name=row.first_name,
            last_name=row.last_name,
            dob=row.normalized_dob,
        )

        if search_result.status == SearchStatus.FOUND:
            self.sheet_repository.mark_profile_created(row)
            return

        if search_result.status == SearchStatus.NOT_FOUND:
            self.mve_client.create_patient(
                first_name=row.first_name,
                last_name=row.last_name,
                dob=row.normalized_dob,
            )
            confirmation = self.mve_client.search_patient(
                first_name=row.first_name,
                last_name=row.last_name,
                dob=row.normalized_dob,
            )
            if confirmation.status == SearchStatus.FOUND:
                self.sheet_repository.mark_profile_created(row)
                return
            raise MVERowError(
                "Patient creation was attempted, but the follow-up search did not confirm a saved profile."
            )

        if search_result.status == SearchStatus.MULTIPLE_MATCHES:
            raise MVERowError(search_result.details or "Multiple MVE matches found.")

        raise MVERowError(search_result.details or "Search result was unclear.")
