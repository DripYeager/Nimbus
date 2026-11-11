"""
The user's message: right-aligned in a gi-orange bubble, with a tag (and a thumbnail for images)
for each attachment. Plain text only, so what was typed is what's shown, and a long paste shows
its first lines with "Show all" rather than a wall of text. Display only.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.attachment_format import AttachedItem
from ui.chat.attachment_preview import image_preview
from ui.theme.line_icons import line_pixmap
from ui.theme.tokens import TEXT_ON_ORANGE

USER_BUBBLE_MAX_WIDTH = 520
BUBBLE_PADDING_PX = 32
BUBBLE_TEXT_SLACK_PX = 8
# Must match QLabel#UserText's font-size in the stylesheet.
USER_TEXT_PX = 14
TAG_ICON_SIZE = 13
BUBBLE_PREVIEW_WIDTH = 260
BUBBLE_PREVIEW_HEIGHT = 170
# A pasted wall of text shows this many lines until "Show all".
PREVIEW_LINES = 12
LESS_TEXT = "Show less"


class UserBubble(QWidget):
    """The user's message, right-aligned in a gi-orange bubble, with a tag for each attachment."""

    def __init__(self, text: str, parent: QWidget | None = None, attachments: tuple[AttachedItem, ...] = ()) -> None:
        super().__init__(parent)
        bubble = QFrame(self)
        bubble.setObjectName("UserBubble")
        lines = text.splitlines()
        self._full = text
        self._preview = "\n".join(lines[:PREVIEW_LINES]) + "\n..." if len(lines) > PREVIEW_LINES else text
        self._label = _text_label(self._preview, bubble)
        inner = QVBoxLayout(bubble)
        inner.setContentsMargins(16, 10, 16, 10)
        inner.addWidget(self._label)
        self._toggle: QPushButton | None = None
        if self._preview != text:
            self._toggle = _toggle_button(f"Show all {len(lines)} lines", bubble)
            self._toggle.clicked.connect(self.toggle)
            inner.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignRight)
        for item in attachments:
            preview = image_preview(item.path, BUBBLE_PREVIEW_WIDTH, BUBBLE_PREVIEW_HEIGHT, bubble)
            if preview is not None:
                inner.addWidget(preview)
            inner.addLayout(_attachment_tag(item.name, bubble))
        bubble.setMaximumWidth(USER_BUBBLE_MAX_WIDTH)
        row = QHBoxLayout(self)
        row.setContentsMargins(60, 0, 0, 0)
        row.addStretch()
        row.addWidget(bubble)

    def toggle(self) -> None:
        """Opens or closes a long message."""
        if self._toggle is None:
            return
        expanded = self._label.text() == self._preview
        self._label.setText(self._full if expanded else self._preview)
        self._toggle.setText(LESS_TEXT if expanded else f"Show all {len(self._full.splitlines())} lines")


def _text_label(text: str, parent: QWidget) -> QLabel:
    label = QLabel(parent)
    label.setObjectName("UserText")
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setText(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    # A wrapping QLabel otherwise collapses to its narrowest width; size it to the text.
    text_width = _text_width(text, USER_TEXT_PX) + BUBBLE_TEXT_SLACK_PX
    label.setMinimumWidth(min(text_width, USER_BUBBLE_MAX_WIDTH - BUBBLE_PADDING_PX))
    return label


def _toggle_button(text: str, parent: QWidget) -> QPushButton:
    button = QPushButton(text, parent)
    button.setObjectName("BubbleLink")
    button.setFlat(True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _attachment_tag(name: str, parent: QWidget) -> QHBoxLayout:
    """A paperclip and the attachment's name, inside the user's bubble."""
    icon = QLabel(parent)
    icon.setPixmap(line_pixmap("paperclip", TEXT_ON_ORANGE, TAG_ICON_SIZE))
    label = QLabel(name, parent)
    label.setObjectName("AttachmentTag")
    label.setTextFormat(Qt.TextFormat.PlainText)
    row = QHBoxLayout()
    row.setSpacing(6)
    row.addWidget(icon)
    row.addWidget(label)
    row.addStretch()
    return row


def _text_width(text: str, pixel_size: int) -> int:
    """Width of the longest line of text at the given font size."""
    font = QFont()
    font.setPixelSize(pixel_size)
    metrics = QFontMetrics(font)
    return max(metrics.horizontalAdvance(line) for line in text.splitlines() or [""])
