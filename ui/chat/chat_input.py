"""
The message box at the bottom of the chat: a growing text field inside a frame that glows
while Nimbus is thinking, a send button, and a bobbing cloud as the busy indicator. Enter
sends, Shift+Enter adds a line. Input only — it emits what the user typed and nothing else.
"""

from __future__ import annotations

from PyQt6.QtCore import QAbstractAnimation, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QHBoxLayout, QPlainTextEdit, QPushButton, QWidget

from ui.theme.motion import build_aura_animation, build_bob_animation, stop_animation
from ui.theme.painting import AuraFrame, CloudGlyph
from ui.theme.tokens import PLACEHOLDER_TEXT

MIN_LINES, MAX_LINES = 1, 5
LINE_HEIGHT_PX = 21
FIELD_PADDING_PX = 14
SEND_BUTTON_SIZE = 34
GLYPH_SIZE = 26


class _MessageField(QPlainTextEdit):
    """A plain-text field where Enter submits and Shift+Enter inserts a newline."""

    submitted = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        is_enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if is_enter and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class ChatInput(AuraFrame):
    """Emits submitted(text) when the user sends a non-empty message."""

    submitted = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._aura: QAbstractAnimation | None = None
        self._bob: QAbstractAnimation | None = None
        self._field = _MessageField(self)
        self._field.setObjectName("ChatInput")
        self._field.setPlaceholderText(PLACEHOLDER_TEXT)
        self._field.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._field.submitted.connect(self._submit)
        self._field.textChanged.connect(self._fit_height)
        self._glyph = CloudGlyph(GLYPH_SIZE, self)
        self._glyph.hide()
        self._send = QPushButton("➤", self)
        self._send.setObjectName("SendButton")
        self._send.setFixedSize(SEND_BUTTON_SIZE, SEND_BUTTON_SIZE)
        self._send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send.setToolTip("Send (Enter)")
        self._send.clicked.connect(self._submit)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 8, 6)
        row.addWidget(self._field, stretch=1)
        row.addWidget(self._glyph, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self._send, alignment=Qt.AlignmentFlag.AlignBottom)
        self._fit_height()

    def focus(self) -> None:
        self._field.setFocus()

    def set_text(self, text: str) -> None:
        self._field.setPlainText(text)

    def set_busy(self, busy: bool) -> None:
        """While busy: glow, bob the cloud, and block sending another message."""
        self._send.setEnabled(not busy)
        self._glyph.setVisible(busy)
        stop_animation(self._aura)
        stop_animation(self._bob)
        if busy:
            self._aura = build_aura_animation(self)
            self._bob = build_bob_animation(self._glyph)
            self._aura.start()
            self._bob.start()
        else:
            self._aura = self._bob = None
            self.glow = 0.0

    def _submit(self) -> None:
        text = self._field.toPlainText().strip()
        if not text or not self._send.isEnabled():
            return
        self._field.clear()
        self.submitted.emit(text)

    def _fit_height(self) -> None:
        """Grows the field with its content, from one line up to MAX_LINES."""
        # A plain-text document measures its height in visual lines, wrapped ones included.
        visual_lines = int(self._field.document().size().height())
        lines = max(MIN_LINES, min(MAX_LINES, visual_lines))
        self._field.setFixedHeight(lines * LINE_HEIGHT_PX + FIELD_PADDING_PX)
