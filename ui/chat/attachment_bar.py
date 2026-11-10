"""
The strip above the message box for anything handed to Nimbus with a question. It either
offers what's on the clipboard ("Use what I copied"), or shows the attached file, text or
screenshot as a removable pill with a few one-click questions about it. Display only; the
chat session decides what's attached.
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QToolButton, QWidget

from models.chat import Attachment
from ui.chat.attachment_preview import image_preview
from ui.theme.line_icons import line_icon
from ui.theme.tokens import GI_ORANGE, TEXT, TEXT_MUTED

ICON_SIZE = 15
MAX_SUGGESTIONS = 3
BAR_PREVIEW_WIDTH = 96
BAR_PREVIEW_HEIGHT = 54
SCREENSHOT_NAME = "Screenshot"
COPIED_TEXT_NAME = "Copied text"
FILE_SUGGESTIONS = ("Summarize it", "What are the key dates and deadlines?", "Who is mentioned?")
TEXT_SUGGESTIONS = ("Explain this", "Summarize this", "Translate this to English")
SCREENSHOT_SUGGESTIONS = ("What does this say?", "Explain this error", "Summarize this")


def suggestions_for(attachment: Attachment) -> tuple[str, ...]:
    """One-click questions that fit what was attached."""
    if attachment.name == SCREENSHOT_NAME:
        return SCREENSHOT_SUGGESTIONS
    return FILE_SUGGESTIONS if attachment.path else TEXT_SUGGESTIONS


def describe_offer(character_count: int) -> str:
    return f"Use what I copied ({character_count:,} characters)"


class AttachmentBar(QWidget):
    """Hidden until there's something to offer or show."""

    offer_accepted = pyqtSignal()
    offer_dismissed = pyqtSignal()
    removed = pyqtSignal()
    suggestion_clicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(4, 0, 4, 0)
        self._row.setSpacing(8)
        self._offering = False
        self.hide()

    def is_offering(self) -> bool:
        return self._offering

    def offer_clipboard(self, character_count: int) -> None:
        """Offers the copied text; does nothing while something is already attached."""
        if self.isVisible() and not self._offering:
            return
        self._reset()
        self._offering = True
        accept = self._chip(describe_offer(character_count), "clipboard", "AttachmentOffer")
        accept.clicked.connect(self.offer_accepted)
        self._row.addWidget(self._close_button("Not now", self.offer_dismissed))
        self._row.addStretch()
        self.show()

    def show_attachment(self, attachment: Attachment | None) -> None:
        """The attached item and its suggestions, or nothing for None."""
        self._reset()
        if attachment is None:
            self.hide()
            return
        preview = image_preview(attachment.path, BAR_PREVIEW_WIDTH, BAR_PREVIEW_HEIGHT, self)
        if preview is not None:
            self._row.addWidget(preview)
        icon = "scan" if attachment.name == SCREENSHOT_NAME else "paperclip"
        self._chip(attachment.name, icon, "AttachmentPill").setEnabled(False)
        self._row.addWidget(self._close_button("Remove", self.removed))
        for text in suggestions_for(attachment)[:MAX_SUGGESTIONS]:
            chip = self._chip(text, "sparkles", "AttachmentSuggestion")
            chip.clicked.connect(lambda _=False, t=text: self.suggestion_clicked.emit(t))
        self._row.addStretch()
        self.show()

    def clear(self) -> None:
        self._reset()
        self.hide()

    def _reset(self) -> None:
        self._offering = False
        while self._row.count():
            item = self._row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _chip(self, text: str, icon: str, role: str) -> QPushButton:
        chip = QPushButton(text, self)
        chip.setObjectName(role)
        chip.setIcon(line_icon(icon, GI_ORANGE, ICON_SIZE))
        chip.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self._row.addWidget(chip)
        return chip

    def _close_button(self, tooltip: str, signal: pyqtSignal) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("MessageAction")
        button.setIcon(line_icon("x", TEXT_MUTED, ICON_SIZE, hover_color=TEXT))
        button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(signal)
        return button
