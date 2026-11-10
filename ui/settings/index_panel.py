"""
The live indexing card on the Sources section: an energy orb that pulses while Nimbus is
reading, a scouter-style power-level readout, a one-line status, and Pause/Resume and Rebuild
buttons. Polls the engine only while visible. Owns presentation of index progress; the
indexing itself happens in the engine.
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, QTimer
from PyQt6.QtGui import QHideEvent, QShowEvent
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout, QWidget

from models.schema import IndexStatus
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.settings.label_roles import set_role, styled_label
from ui.settings.section_layout import CARD_PADDING, CARD_ROW_SPACING, GAP
from ui.theme.energy import EnergyOrb, PowerLevelReadout
from ui.theme.line_icons import line_icon
from ui.theme.tokens import ICON_SIZE, TEXT

REFRESH_INTERVAL_MS = 2000
ORB_SIZE = 48
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


def _icon_button(text: str, icon: str) -> QPushButton:
    button = QPushButton(text)
    button.setIcon(line_icon(icon, TEXT, ICON_SIZE - 2))
    button.setIconSize(QSize(ICON_SIZE - 2, ICON_SIZE - 2))
    return button


class IndexPanel(QFrame):
    """Shows indexing progress and lets the user pause, resume or rebuild."""

    def __init__(self, api: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("IndexCard")
        self._api = api
        self._is_paused = False
        self._is_refreshing = False
        self._is_working = False
        self._orb = EnergyOrb(ORB_SIZE)
        self._readout = PowerLevelReadout()
        self._status = styled_label("Checking the index…", "muted")
        self._pause_button = _icon_button("Pause", "pause")
        self._rebuild_button = _icon_button("Rebuild", "refresh-cw")
        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_INTERVAL_MS)
        self._build_layout()
        self._timer.timeout.connect(self.refresh)
        self._pause_button.clicked.connect(self._toggle_pause)
        self._rebuild_button.clicked.connect(self._confirm_rebuild)

    def _build_layout(self) -> None:
        """Orb, then readout over status, then the two buttons."""
        text_column = QVBoxLayout()
        text_column.setSpacing(GAP // 2)
        text_column.addWidget(self._readout)
        text_column.addWidget(self._status)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        layout.setSpacing(CARD_ROW_SPACING)
        layout.addWidget(self._orb)
        layout.addLayout(text_column, 1)
        layout.addWidget(self._pause_button)
        layout.addWidget(self._rebuild_button)

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
        self._orb.stop()
        super().hideEvent(event)

    def _show_status(self, status: IndexStatus) -> None:
        self._is_refreshing = False
        self._is_paused = status.is_paused
        self._readout.set_progress(status.indexed_files, status.progress_ratio)
        self._status.setText(describe_index_status(status))
        set_role(self._status, "muted")
        self._show_pause_state(status.is_paused)
        self._show_activity(status.is_busy and not status.is_paused)

    def _show_pause_state(self, is_paused: bool) -> None:
        self._pause_button.setText("Resume" if is_paused else "Pause")
        icon = "play" if is_paused else "pause"
        self._pause_button.setIcon(line_icon(icon, TEXT, ICON_SIZE - 2))

    def _show_activity(self, is_working: bool) -> None:
        """The orb charges while files are still being read and rests once everything is done."""
        self._is_working = is_working
        if is_working:
            self._orb.start()
        else:
            self._orb.stop()

    def _show_error(self, message: str) -> None:
        self._is_refreshing = False
        self._status.setText(message)
        set_role(self._status, "error")
        self._show_activity(False)

    def _toggle_pause(self) -> None:
        paused = not self._is_paused
        run_in_background(lambda: self._api.set_paused(paused), self._show_status, self._show_error)

    def _confirm_rebuild(self) -> None:
        answer = QMessageBox.question(self, "Rebuild index", REBUILD_QUESTION)
        if answer == QMessageBox.StandardButton.Yes:
            run_in_background(self._api.rebuild_index, self._show_status, self._show_error)
