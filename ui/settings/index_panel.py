"""
The live indexing strip on the Sources tab: a power bar, a one-line status, and Pause/Resume
and Rebuild buttons. Polls the engine only while visible. Owns presentation of index progress;
the indexing itself happens in the engine.
"""

from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QHideEvent, QShowEvent
from PyQt6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout, QWidget

from models.schema import IndexStatus
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.settings.label_roles import set_role, styled_label
from ui.theme.painting import PowerBar

REFRESH_INTERVAL_MS = 2000
REBUILD_QUESTION = (
    "Rebuild the index from scratch? Nimbus will re-read every file in your folders. "
    "Search keeps working while it does, but results may be incomplete for a while."
)


def describe_index_status(status: IndexStatus) -> str:
    """One human line for the current progress, e.g. "Indexed 1,240 of 5,600 files · 3 failed"."""
    if status.is_paused:
        return "Paused"
    if status.is_scanning:
        return "Scanning…"
    text = f"Indexed {status.indexed_files:,} of {status.content_files:,} files"
    if status.failed_files:
        text += f" · {status.failed_files:,} failed"
    return text


class IndexPanel(QWidget):
    """Shows indexing progress and lets the user pause, resume or rebuild."""

    def __init__(self, api: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._is_paused = False
        self._is_refreshing = False
        self._bar = PowerBar()
        self._status = styled_label("Checking the index…", "muted")
        self._pause_button = QPushButton("Pause")
        self._rebuild_button = QPushButton("Rebuild")
        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_INTERVAL_MS)
        self._build_layout()
        self._timer.timeout.connect(self.refresh)
        self._pause_button.clicked.connect(self._toggle_pause)
        self._rebuild_button.clicked.connect(self._confirm_rebuild)

    def _build_layout(self) -> None:
        """Status line and buttons on one row, the bar underneath."""
        row = QHBoxLayout()
        row.addWidget(self._status, 1)
        row.addWidget(self._pause_button)
        row.addWidget(self._rebuild_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        layout.addWidget(self._bar)

    def refresh(self) -> None:
        """Fetches the latest status, skipping the tick if the previous request hasn't returned."""
        if self._is_refreshing:
            return
        self._is_refreshing = True
        run_in_background(self._api.index_status, self._show_status, self._show_error)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh()
        self._timer.start()

    def hideEvent(self, event: QHideEvent) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _show_status(self, status: IndexStatus) -> None:
        self._is_refreshing = False
        self._is_paused = status.is_paused
        self._bar.set_ratio(status.progress_ratio)
        self._status.setText(describe_index_status(status))
        set_role(self._status, "muted")
        self._pause_button.setText("Resume" if status.is_paused else "Pause")

    def _show_error(self, message: str) -> None:
        self._is_refreshing = False
        self._status.setText(message)
        set_role(self._status, "error")

    def _toggle_pause(self) -> None:
        paused = not self._is_paused
        run_in_background(lambda: self._api.set_paused(paused), self._show_status, self._show_error)

    def _confirm_rebuild(self) -> None:
        answer = QMessageBox.question(self, "Rebuild index", REBUILD_QUESTION)
        if answer == QMessageBox.StandardButton.Yes:
            run_in_background(self._api.rebuild_index, self._show_status, self._show_error)
