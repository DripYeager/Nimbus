"""
The small cards inside a reply: a tool step ("✓ Searched your files"), a source-file card that
opens the file, and the approve/decline card for actions. Display only — clicks are reported
through signals or handed to the OS to open.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from models.schema import SourceRef
from ui.theme.line_icons import line_icon, line_pixmap
from ui.theme.tokens import CLOUD_GOLD, DANGER, GI_ORANGE, SUCCESS, TEXT_FAINT, TEXT_ON_GOLD

STEP_ICONS = {
    "running": ("loader-circle", CLOUD_GOLD),
    "done": ("check", SUCCESS),
    "failed": ("circle-alert", DANGER),
    "denied": ("x", DANGER),
    "info": ("sparkles", CLOUD_GOLD),
}
FILE_ICONS = {
    ".pdf": "file-text",
    ".docx": "file-text",
    ".doc": "file-text",
    ".txt": "file-text",
    ".md": "file-text",
    ".xlsx": "file-spreadsheet",
    ".xls": "file-spreadsheet",
    ".csv": "file-spreadsheet",
    ".pptx": "presentation",
    ".png": "file-image",
    ".jpg": "file-image",
    ".jpeg": "file-image",
    ".msg": "mail",
    ".eml": "mail",
}
STEP_ICON_SIZE = 14
SOURCE_ICON_SIZE = 18
SOURCE_CARD_MAX_WIDTH = 460


class ToolStep(QWidget):
    """One line in a reply's activity log, updated in place as the step finishes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon = QLabel(self)
        self._text = QLabel(self)
        self._text.setObjectName("ToolStepText")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self._icon)
        row.addWidget(self._text)
        row.addStretch()

    def update_step(self, label: str, status: str) -> None:
        icon, color = STEP_ICONS.get(status, STEP_ICONS["info"])
        self._icon.setPixmap(line_pixmap(icon, color, STEP_ICON_SIZE))
        self._text.setText(label)
        self._text.setProperty("status", status)
        self._text.style().unpolish(self._text)
        self._text.style().polish(self._text)


class SourceCard(QPushButton):
    """A file the answer came from: type icon, name and folder; clicking opens it."""

    def __init__(self, source: SourceRef, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SourceCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Open {source.file_path}")
        self.setMaximumWidth(SOURCE_CARD_MAX_WIDTH)
        self._path = source.file_path
        path = Path(source.file_path)
        icon = QLabel(self)
        icon.setPixmap(line_pixmap(FILE_ICONS.get(path.suffix.lower(), "file"), GI_ORANGE, SOURCE_ICON_SIZE))
        name = QLabel(source.file_name, self)
        name.setObjectName("SourceName")
        folder = QLabel(path.parent.name or str(path.parent), self)
        folder.setObjectName("SourceFolder")
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(name)
        text.addWidget(folder)
        opener = QLabel(self)
        opener.setPixmap(line_pixmap("external-link", TEXT_FAINT, STEP_ICON_SIZE))
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)
        row.addWidget(icon)
        row.addLayout(text, stretch=1)
        row.addWidget(opener)
        self.setMinimumHeight(48)
        self.clicked.connect(self._open)

    def _open(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._path))


class ConfirmCard(QFrame):
    """Asks before an action runs: Allow once, Always allow, or Don't."""

    decided = pyqtSignal(bool, bool)

    def __init__(self, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ConfirmCard")
        title_icon = QLabel(self)
        title_icon.setPixmap(line_pixmap("zap", GI_ORANGE, STEP_ICON_SIZE))
        title = QLabel("NIMBUS WANTS TO", self)
        title.setObjectName("ConfirmTitle")
        heading = QHBoxLayout()
        heading.setSpacing(6)
        heading.addWidget(title_icon)
        heading.addWidget(title)
        heading.addStretch()
        text = QLabel(description, self)
        text.setObjectName("ConfirmText")
        text.setWordWrap(True)
        self._buttons = QHBoxLayout()
        self._buttons.setSpacing(8)
        self._add_button("Allow", "primary", approved=True, always=False)
        self._add_button("Always allow", "", approved=True, always=True)
        self._add_button("Don't", "ghost", approved=False, always=False)
        self._buttons.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addLayout(heading)
        layout.addWidget(text)
        layout.addLayout(self._buttons)

    def _add_button(self, text: str, variant: str, approved: bool, always: bool) -> None:
        button = QPushButton(text, self)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if variant:
            button.setProperty("variant", variant)
        if approved and not always:
            button.setIcon(line_icon("check", TEXT_ON_GOLD, STEP_ICON_SIZE))
            button.setIconSize(QSize(STEP_ICON_SIZE, STEP_ICON_SIZE))
        button.clicked.connect(lambda: self._decide(approved, always))
        self._buttons.addWidget(button)

    def _decide(self, approved: bool, always: bool) -> None:
        """Locks the card so a double click can't answer twice, then reports the choice."""
        for index in range(self._buttons.count()):
            widget = self._buttons.itemAt(index).widget()
            if widget is not None:
                widget.setEnabled(False)
        self.decided.emit(approved, always)
