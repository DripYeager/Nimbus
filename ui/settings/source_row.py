"""
One source folder drawn as a card: folder icon, path, its file counts, a "Read contents"
switch and a remove button. Owns that one row's widgets; the list of folders belongs to
SourcesEditor.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ui.settings.label_roles import styled_label
from ui.settings.section_layout import CARD_ROW_SPACING, GAP, icon_tile
from ui.theme.line_icons import line_icon
from ui.theme.tokens import CLOUD_GOLD, DANGER, ICON_SIZE, TEXT_MUTED
from ui.widgets.toggle_switch import ToggleSwitch

NEW_FOLDER_COUNTS = "Counted after you save"
READ_CONTENTS_TEXT = "Read contents"
REMOVE_TOOLTIP = "Stop learning this folder"
ROW_MARGINS = (12, 12, 8, 12)
ICON_BUTTON_SIZE = 32


class _PathLabel(QLabel):
    """A one-line path that elides in the middle when space runs out, with the full path as tooltip."""

    def __init__(self, path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path = path
        self.setObjectName("RowTitle")
        self.setToolTip(path)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(path)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.setText(self.fontMetrics().elidedText(self._path, Qt.TextElideMode.ElideMiddle, self.width()))


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
        self.counts_label = styled_label(NEW_FOLDER_COUNTS, "muted")
        remove_button = _remove_button()
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        self._build_layout(remove_button)

    def _build_layout(self, remove_button: QPushButton) -> None:
        """Icon, path over counts, then the switch and trash on the right."""
        text_column = QVBoxLayout()
        text_column.setSpacing(2)
        text_column.addWidget(_PathLabel(self.path))
        text_column.addWidget(self.counts_label)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(*ROW_MARGINS)
        layout.setSpacing(CARD_ROW_SPACING)
        layout.addWidget(icon_tile("folder-open", CLOUD_GOLD))
        layout.addLayout(text_column, 1)
        layout.addWidget(styled_label(READ_CONTENTS_TEXT, "muted"))
        layout.addWidget(self.contents_switch)
        layout.addSpacing(GAP // 2)
        layout.addWidget(remove_button)

    def to_setting(self) -> dict[str, Any]:
        return {"path": self.path, "include_contents": self.contents_switch.isChecked()}
