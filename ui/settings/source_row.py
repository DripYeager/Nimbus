"""
One source folder drawn as a card: folder icon, path, a live progress line ("Reading
report.pdf… · 980 of 1,240 read") with a slim progress bar and an energy orb that pulses while
this folder is being indexed, a "Read contents" switch and a remove button. Owns that one row's
widgets; the list of folders belongs to SourcesEditor.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from models.schema import SourceSummary
from ui.settings.label_roles import styled_label
from ui.settings.section_layout import CARD_ROW_SPACING, GAP, icon_tile
from ui.theme.energy import EnergyOrb
from ui.theme.line_icons import line_icon
from ui.theme.tokens import CLOUD_GOLD, DANGER, ICON_SIZE, TEXT_MUTED
from ui.widgets.toggle_switch import ToggleSwitch

NEW_FOLDER_COUNTS = "Counted after you save"
READ_CONTENTS_TEXT = "Read contents"
REMOVE_TOOLTIP = "Stop learning this folder"
ROW_MARGINS = (12, 12, 8, 12)
ICON_BUTTON_SIZE = 32
ORB_SIZE = 16
PROGRESS_STEPS = 1000


def describe_source_counts(summary: SourceSummary) -> str:
    """The status line under a folder, e.g. "Reading report.pdf… · 980 of 1,240 read"."""
    if not summary.exists:
        return "Folder not found"
    if not summary.include_contents:
        return f"{summary.file_count:,} files · names only"
    read = f"{summary.indexed_count:,} of {summary.content_count:,} read"
    if summary.is_active and summary.current_file:
        return f"Reading {summary.current_file}… · {read}"
    if summary.pending_count:
        return f"{read} · {summary.pending_count:,} waiting"
    text = f"{summary.file_count:,} files · all read"
    if summary.failed_count:
        text += f" · {summary.failed_count:,} couldn't be read"
    return text


class _ElidedLabel(QLabel):
    """One line that never asks for more width than it gets: when space runs out it trims the
    middle ("Reading site_alerts…xlsx… · 387 of 11,339 read"), and the tooltip shows it all. A
    long file name in the status line used to stretch the whole Settings page sideways."""

    def __init__(self, text: str, role: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if role:
            self.setProperty("role", role)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._full = ""
        self.set_full_text(text)

    def full_text(self) -> str:
        return self._full

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._fit()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit()

    def _fit(self) -> None:
        self.setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle, max(self.width(), 1)))


def _remove_button() -> QPushButton:
    """An icon-only trash button that turns red on hover."""
    button = QPushButton()
    button.setObjectName("IconButton")
    button.setIcon(line_icon("trash-2", TEXT_MUTED, ICON_SIZE, hover_color=DANGER))
    button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
    button.setFixedSize(ICON_BUTTON_SIZE, ICON_BUTTON_SIZE)
    button.setToolTip(REMOVE_TOOLTIP)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class SourceRow(QFrame):
    """One folder; emits remove_requested(self) when its trash button is clicked."""

    remove_requested = pyqtSignal(object)

    def __init__(self, path: str, include_contents: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self.setObjectName("FolderRow")
        self.contents_switch = ToggleSwitch()
        self.contents_switch.setChecked(include_contents)
        self.contents_switch.setToolTip("Off: searchable by file name only")
        self.counts_label = _ElidedLabel(NEW_FOLDER_COUNTS, "muted")
        self.progress = QProgressBar()
        self.progress.setObjectName("FolderProgress")
        self.progress.setRange(0, PROGRESS_STEPS)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        self.orb = EnergyOrb(ORB_SIZE)
        self.orb.setToolTip("Nimbus is reading this folder right now")
        self.orb.hide()
        remove_button = _remove_button()
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        self._build_layout(remove_button)

    def _build_layout(self, remove_button: QPushButton) -> None:
        """Icon, path over counts, then the switch and trash on the right."""
        status_line = QHBoxLayout()
        status_line.setSpacing(6)
        status_line.addWidget(self.orb)
        status_line.addWidget(self.counts_label, 1)
        text_column = QVBoxLayout()
        text_column.setSpacing(4)
        title = _ElidedLabel(self.path)
        title.setObjectName("RowTitle")
        text_column.addWidget(title)
        text_column.addLayout(status_line)
        text_column.addWidget(self.progress)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(*ROW_MARGINS)
        layout.setSpacing(CARD_ROW_SPACING)
        layout.addWidget(icon_tile("folder-open", CLOUD_GOLD))
        layout.addLayout(text_column, 1)
        layout.addWidget(styled_label(READ_CONTENTS_TEXT, "muted"))
        layout.addWidget(self.contents_switch)
        layout.addSpacing(GAP // 2)
        layout.addWidget(remove_button)

    def set_summary(self, summary: SourceSummary) -> None:
        """Shows this folder's latest progress: status line, bar while work remains, orb while active."""
        self.counts_label.set_full_text(describe_source_counts(summary))
        working = summary.include_contents and summary.exists and summary.pending_count > 0
        self.progress.setVisible(working)
        self.progress.setValue(int(summary.progress_ratio * PROGRESS_STEPS))
        self.orb.setVisible(summary.is_active)
        if summary.is_active:
            self.orb.start()
        else:
            self.orb.stop()

    def to_setting(self) -> dict[str, Any]:
        return {"path": self.path, "include_contents": self.contents_switch.isChecked()}
