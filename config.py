from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SHEET_ID = "151QhieSXw5XMbtK5U-xxZqdcmdscsf4exTSe9Gc-d8M"
DEFAULT_WORKSHEET_NAME = "Sheet1"
DEFAULT_APP_PATH = r"C:\Program Files (x86)\My Vision Express\My Vision Express.exe"
DEFAULT_APP_TITLE_RE = r".*Vision.*Express.*"


@dataclass(frozen=True)
class Settings:
    mve_username: str | None
    mve_password: str | None
    login_user_edit_index: int
    login_password_edit_index: int
    sheet_id: str
    worksheet_name: str
    credentials_file: Path
    app_path: str
    app_title_re: str
    batch_size: int
    first_column: str
    last_column: str
    dob_column: str
    status_columns: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mve_username=os.getenv("MVE_USERNAME"),
            mve_password=os.getenv("MVE_PASSWORD"),
            login_user_edit_index=int(os.getenv("MVE_LOGIN_USER_EDIT_INDEX", "3")),
            login_password_edit_index=int(
                os.getenv("MVE_LOGIN_PASSWORD_EDIT_INDEX", "4")
            ),
            sheet_id=os.getenv("SHEET_ID", DEFAULT_SHEET_ID),
            worksheet_name=os.getenv("WORKSHEET_NAME", DEFAULT_WORKSHEET_NAME),
            credentials_file=Path(
                os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
            ),
            app_path=os.getenv("APP_PATH", DEFAULT_APP_PATH),
            app_title_re=os.getenv("APP_TITLE_RE", DEFAULT_APP_TITLE_RE),
            batch_size=int(os.getenv("MAX_ROWS_PER_RUN", "5")),
            first_column=os.getenv("COL_FIRST", "First"),
            last_column=os.getenv("COL_LAST", "Last"),
            dob_column=os.getenv("COL_DOB", "DOB"),
            status_columns=(
                os.getenv("COL_STATUS", "MVE Profile Added Y/N"),
                os.getenv("COL_STATUS_ALT", "MVE Profiled Added Y/N"),
            ),
        )
