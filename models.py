from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SearchStatus(str, Enum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    MULTIPLE_MATCHES = "MULTIPLE_MATCHES"
    ERROR = "ERROR"


@dataclass(frozen=True)
class PendingPatientRow:
    row_number: int
    first_name: str
    last_name: str
    dob_raw: str
    status_column_name: str
    status_column_index: int

    @property
    def normalized_dob(self) -> str:
        return normalize_dob(self.dob_raw)


@dataclass(frozen=True)
class SearchResult:
    status: SearchStatus
    details: str = ""


@dataclass
class BatchSummary:
    processed: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0


def normalize_name(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def normalize_dob(value: str) -> str:
    candidate = value.strip()
    formats = (
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m-%d-%Y",
        "%m-%d-%y",
        "%Y-%m-%d",
        "%Y/%m/%d",
    )
    for fmt in formats:
        try:
            return datetime.strptime(candidate, fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue
    raise ValueError(f"Unsupported DOB format: {value!r}")
