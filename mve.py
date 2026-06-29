from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any

from config import Settings
from models import SearchResult, SearchStatus, normalize_dob, normalize_name


LOGGER = logging.getLogger(__name__)


class MVEFatalError(RuntimeError):
    """An unrecoverable MVE failure that should stop the batch."""


class MVERowError(RuntimeError):
    """A row-level MVE failure that should leave the sheet unchanged."""


class MVEAutomationClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._app = None
        self._desktop = None
        self._keyboard = None
        self._load_windows_dependencies()

    def open_or_focus_mve(self) -> None:
        if self._app is not None:
            return

        application = self._application_cls(backend="uia")
        try:
            application.connect(title_re=self.settings.app_title_re)
            self._app = application
            window = self._wait_for_any_mve_window(timeout=5)
            self._bring_window_to_front(window)
            return
        except Exception:
            pass

        if not os.path.exists(self.settings.app_path):
            raise MVEFatalError(
                f"MVE is not open and APP_PATH does not exist: {self.settings.app_path}"
            )

        try:
            self._app = application.start(self.settings.app_path)
            window = self._wait_for_any_mve_window(timeout=20)
            self._bring_window_to_front(window)
        except Exception as exc:
            raise MVEFatalError(f"Unable to open MVE: {exc}") from exc

    def login_if_needed(self) -> None:
        login_window = self._find_window(
            title_re=self.settings.app_title_re, timeout=3, raise_on_missing=False
        )
        if login_window is None or not self._looks_like_login_window(login_window):
            return

        if not self.settings.mve_username or not self.settings.mve_password:
            raise MVEFatalError(
                "MVE login screen is visible but MVE_USERNAME/MVE_PASSWORD are not set."
            )

        LOGGER.info("MVE login screen detected. Attempting automated sign-in.")
        self._set_login_credentials(
            login_window,
            user_id=self.settings.mve_username,
            password=self.settings.mve_password,
        )
        self._click_button(login_window, "Login")

        try:
            self._wait_for_main_window(timeout=20)
        except Exception as exc:
            raise MVEFatalError("MVE login did not reach the main window.") from exc

    def handle_daily_closing_popup(self) -> None:
        popup = self._find_window(
            title_re=r".*Daily Closing.*", timeout=2, raise_on_missing=False
        )
        if popup is None:
            return

        LOGGER.info("Daily Closing popup detected. Clicking No.")
        try:
            self._click_button(popup, "No")
            time.sleep(0.5)
        except Exception as exc:
            raise MVEFatalError("Daily Closing popup appeared but could not be dismissed.") from exc

    def open_patient_search(self) -> Any:
        main_window = self._wait_for_main_window(timeout=10)
        try:
            self._click_named_control(main_window, "Patients")
        except Exception as exc:
            raise MVEFatalError("Unable to open the Patients screen in MVE.") from exc

        return self._find_window(title_re=r".*Search Patient.*", timeout=10)

    def search_patient(self, first_name: str, last_name: str, dob: str) -> SearchResult:
        search_window = self.open_patient_search()

        self._set_labeled_edit(search_window, "Last name", last_name)
        self._set_labeled_edit(search_window, "First name", first_name)
        self._set_labeled_edit(search_window, "Birth date", normalize_dob(dob))
        self._click_button(search_window, "Search")
        time.sleep(1.0)

        text_dump = "\n".join(self._collect_visible_text(search_window))
        if "0 records found" in text_dump.casefold():
            return SearchResult(status=SearchStatus.NOT_FOUND)

        matches = self._collect_result_matches(search_window, first_name, last_name)
        if len(matches) == 1:
            return SearchResult(status=SearchStatus.FOUND, details=matches[0])
        if len(matches) > 1:
            return SearchResult(
                status=SearchStatus.MULTIPLE_MATCHES,
                details=f"Multiple candidate matches detected: {matches}",
            )

        if self._has_any_result_rows(search_window):
            return SearchResult(
                status=SearchStatus.MULTIPLE_MATCHES,
                details="Search returned rows but no exact single name match was provable.",
            )

        return SearchResult(
            status=SearchStatus.ERROR,
            details="Unable to determine patient search result from the MVE UI.",
        )

    def create_patient(self, first_name: str, last_name: str, dob: str) -> None:
        search_window = self.open_patient_search()

        try:
            self._click_button(search_window, "Add")
        except Exception as exc:
            raise MVERowError("Search Patient window did not allow opening Add Patient.") from exc

        profile_window = self._find_window(title_re=r"Patient:.*", timeout=10)
        try:
            self._set_labeled_edit(profile_window, "First", first_name)
            self._set_labeled_edit(profile_window, "Last", last_name)
            self._set_labeled_edit(profile_window, "Birth date", normalize_dob(dob))
            self._click_named_control(profile_window, "Save")
            time.sleep(1.5)
        except Exception as exc:
            raise MVERowError("Failed while filling or saving the patient profile.") from exc

        blocking_dialog = self._find_window(
            title_re=r".*(Error|Warning|Validation).*", timeout=1, raise_on_missing=False
        )
        if blocking_dialog is not None:
            raise MVERowError(
                "MVE displayed a blocking dialog after Save; patient creation was not confirmed."
            )

    def _load_windows_dependencies(self) -> None:
        if sys.platform != "win32":
            raise MVEFatalError("MVE automation must be executed on Windows.")

        try:
            from pywinauto import Desktop
            from pywinauto.application import Application
            from pywinauto.keyboard import send_keys
        except Exception as exc:
            raise MVEFatalError(
                "pywinauto is required on the Windows worker machine."
            ) from exc

        self._application_cls = Application
        self._desktop = Desktop(backend="uia")
        self._keyboard = send_keys

    def _wait_for_any_mve_window(self, timeout: float) -> Any:
        deadline = time.time() + timeout
        while time.time() < deadline:
            window = self._find_window(
                title_re=self.settings.app_title_re, timeout=1, raise_on_missing=False
            )
            if window is not None:
                return window
        raise MVEFatalError("Timed out waiting for an MVE window to appear.")

    def _wait_for_main_window(self, timeout: float) -> Any:
        deadline = time.time() + timeout
        while time.time() < deadline:
            window = self._find_window(
                title_re=self.settings.app_title_re, timeout=1, raise_on_missing=False
            )
            if window is None:
                continue
            if self._looks_like_login_window(window):
                time.sleep(0.5)
                continue
            self._bring_window_to_front(window)
            return window
        raise MVEFatalError("Timed out waiting for the MVE main window.")

    def _bring_main_window_to_front(self) -> None:
        window = self._wait_for_main_window(timeout=10)
        self._bring_window_to_front(window)

    def _looks_like_login_window(self, window: Any) -> bool:
        visible_text = "\n".join(text.casefold() for text in self._collect_visible_text(window))
        return all(marker in visible_text for marker in ("user id", "password", "login"))

    def _find_window(
        self,
        title_re: str,
        timeout: float,
        raise_on_missing: bool = True,
    ) -> Any | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            window = self._desktop.window(title_re=title_re)
            try:
                if window.exists() and window.is_visible():
                    return window
            except Exception:
                pass
            time.sleep(0.25)

        if raise_on_missing:
            raise MVEFatalError(f"Timed out waiting for window matching {title_re!r}")
        return None

    def _set_labeled_edit(self, window: Any, label: str, value: str) -> None:
        edit = self._find_edit_for_label(window, label)
        if edit is None:
            raise MVEFatalError(f"Could not find an editable field for label '{label}'.")
        self._set_edit_value(window, edit, value)

    def _set_login_credentials(self, window: Any, user_id: str, password: str) -> None:
        user_edit = self._find_edit_for_label(window, "User ID")
        password_edit = self._find_edit_for_label(window, "Password")

        if user_edit is None or password_edit is None:
            ordered_edits = self._ordered_login_edits(window)
            if len(ordered_edits) < 4:
                raise MVEFatalError(
                    "Could not find enough visible editable fields on the MVE login screen."
                )
            user_edit = user_edit or ordered_edits[2]
            password_edit = password_edit or ordered_edits[3]
            LOGGER.info("Falling back to login row order for credential entry.")

        self._set_edit_value(window, user_edit, user_id)
        self._set_edit_value(window, password_edit, password)

    def _set_edit_value(self, window: Any, edit: Any, value: str) -> None:
        self._bring_window_to_front(window)
        edit.set_focus()
        self._keyboard("^a{BACKSPACE}")
        edit.type_keys(value, with_spaces=True, set_foreground=True)

    def _find_edit_for_label(self, window: Any, label: str) -> Any | None:
        expected_label = self._normalize_label_text(label)
        labels = []
        for control in window.descendants():
            try:
                if not control.is_visible():
                    continue
                text = self._normalize_label_text(control.window_text() or "")
                if text == expected_label:
                    labels.append(control)
            except Exception:
                continue

        edits = self._find_visible_edits(window)
        if not labels:
            return edits[0] if len(edits) == 1 else None

        best_match = None
        best_score = None
        for label_control in labels:
            label_rect = label_control.rectangle()
            for edit in edits:
                edit_rect = edit.rectangle()
                vertical_distance = abs(edit_rect.top - label_rect.top)
                horizontal_distance = abs(edit_rect.left - label_rect.right)
                if edit_rect.left + 5 < label_rect.right:
                    continue
                if vertical_distance > 50:
                    continue
                score = (vertical_distance, horizontal_distance)
                if best_score is None or score < best_score:
                    best_score = score
                    best_match = edit
        return best_match

    @staticmethod
    def _normalize_label_text(value: str) -> str:
        return " ".join(value.strip().rstrip(":").split()).casefold()

    def _find_visible_edits(self, window: Any) -> list[Any]:
        return [
            control
            for control in window.descendants(control_type="Edit")
            if self._is_visible(control)
        ]

    def _ordered_login_edits(self, window: Any) -> list[Any]:
        return sorted(
            self._find_visible_edits(window),
            key=lambda control: (control.rectangle().top, control.rectangle().left),
        )

    def _click_button(self, window: Any, title: str) -> None:
        for control_type in ("Button", "SplitButton"):
            try:
                button = window.child_window(title=title, control_type=control_type)
                if button.exists():
                    self._invoke_control(button)
                    return
            except Exception:
                continue
        raise MVEFatalError(f"Could not find button '{title}'.")

    def _click_named_control(self, window: Any, title: str) -> None:
        for control in window.descendants():
            try:
                if not self._is_visible(control):
                    continue
                if (control.window_text() or "").strip().casefold() != title.casefold():
                    continue
                self._invoke_control(control)
                return
            except Exception:
                continue
        raise MVEFatalError(f"Could not find visible control named '{title}'.")

    @staticmethod
    def _invoke_control(control: Any) -> None:
        wrapper = control.wrapper_object()
        try:
            wrapper.invoke()
            return
        except Exception:
            pass
        try:
            wrapper.click_input()
            return
        except Exception:
            pass
        try:
            wrapper.select()
            return
        except Exception as exc:
            raise MVEFatalError(f"Unable to activate control '{wrapper.window_text()}'.") from exc

    def _collect_visible_text(self, window: Any) -> list[str]:
        texts: list[str] = []
        for control in window.descendants():
            try:
                if not self._is_visible(control):
                    continue
                text = (control.window_text() or "").strip()
                if text:
                    texts.append(text)
            except Exception:
                continue
        return texts

    def _collect_result_matches(
        self, search_window: Any, first_name: str, last_name: str
    ) -> list[str]:
        expected_first = normalize_name(first_name)
        expected_last = normalize_name(last_name)
        matches: list[str] = []

        for control in search_window.descendants():
            try:
                if not self._is_visible(control):
                    continue
                text = normalize_name(control.window_text() or "")
                if not text:
                    continue
                if expected_first in text and expected_last in text:
                    matches.append(control.window_text())
            except Exception:
                continue

        return list(dict.fromkeys(matches))

    def _has_any_result_rows(self, search_window: Any) -> bool:
        for control in search_window.descendants():
            try:
                if not self._is_visible(control):
                    continue
                if control.friendly_class_name() in {"ListItem", "DataItem"}:
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _is_visible(control: Any) -> bool:
        try:
            return control.is_visible()
        except Exception:
            return False

    @staticmethod
    def _bring_window_to_front(window: Any) -> None:
        wrapper = window.wrapper_object()
        try:
            wrapper.restore()
        except Exception:
            pass
        wrapper.set_focus()
