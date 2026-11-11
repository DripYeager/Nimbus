"""
The message box at the bottom of the chat: a pill-shaped composer whose border glows like
charging ki while Nimbus is working, a growing text field, and a round button that sends, or
stops the reply while one is running. Enter sends, Shift+Enter adds a line. Input only; it
emits what the user asked for and nothing else.
"""

from __future__ import annotations

from PyQt6.QtCore import QAbstractAnimation, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QTextCursor
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QToolButton, QWidget

from ui.theme.line_icons import line_icon, line_pixmap
from ui.theme.motion import build_aura_animation, stop_animation
from ui.theme.painting import AuraFrame
from ui.theme.tokens import GI_ORANGE, PLACEHOLDER_TEXT, TEXT, TEXT_MUTED, TEXT_ON_ORANGE

MIN_LINES, MAX_LINES = 1, 5
LINE_HEIGHT_PX = 21
FIELD_PADDING_PX = 14
SEND_BUTTON_SIZE = 38
SEND_ICON_SIZE = 18
SPARK_ICON_SIZE = 18
STOP_ICON_SIZE = 14
SEND_TIP = "Send (Enter)"
STOP_TIP = "Stop the reply"
MIC_ICON_SIZE = 18
MIC_TIP = "Speak instead of typing (Ctrl+M). Transcribed on this PC; the audio never leaves it."
LISTENING_TIP = "Listening… pause to finish, or click to stop"
HINT_MS = 8000
ELSEWHERE_PLACEHOLDER = "Nimbus is still answering in another chat. You can send once it's done."


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
    """Emits submitted(text) when the user sends a non-empty message, and stop_requested when
    they press the button while a reply is running."""

    submitted = pyqtSignal(str)
    stop_requested = pyqtSignal()
    voice_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._aura: QAbstractAnimation | None = None
        self._busy = False
        self._field = _MessageField(self)
        self._field.setObjectName("ChatInput")
        self._field.setPlaceholderText(PLACEHOLDER_TEXT)
        # The field grows up to MAX_LINES; past that the wheel still scrolls without a bar.
        self._field.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._field.submitted.connect(self._submit)
        self._field.textChanged.connect(self._fit_height)
        spark = QLabel(self)
        spark.setPixmap(line_pixmap("sparkles", GI_ORANGE, SPARK_ICON_SIZE))
        # Owned, so a pending reset can never outlive the field it changes.
        self._hint_reset = QTimer(self)
        self._hint_reset.setSingleShot(True)
        self._hint_reset.setInterval(HINT_MS)
        self._hint_reset.timeout.connect(lambda: self._field.setPlaceholderText(PLACEHOLDER_TEXT))
        self._mic = QToolButton(self)
        self._mic.setObjectName("MicButton")
        self._mic.setIconSize(QSize(MIC_ICON_SIZE, MIC_ICON_SIZE))
        self._mic.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mic.clicked.connect(self.voice_requested)
        self.set_listening(False)
        self._send = QPushButton(self)
        self._send.setObjectName("SendButton")
        self._send.setFixedSize(SEND_BUTTON_SIZE, SEND_BUTTON_SIZE)
        self._send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send.clicked.connect(self._on_button)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 7, 7, 7)
        row.setSpacing(10)
        row.addWidget(spark, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self._field, stretch=1)
        row.addWidget(self._mic, alignment=Qt.AlignmentFlag.AlignBottom)
        row.addWidget(self._send, alignment=Qt.AlignmentFlag.AlignBottom)
        self._show_button_mode()
        self._fit_height()

    def focus(self) -> None:
        self._field.setFocus()

    def add_dictation(self, text: str) -> None:
        """Adds spoken words after whatever is already typed, ready to edit or send."""
        current = self._field.toPlainText().rstrip()
        self._field.setPlainText(f"{current} {text}".strip())
        self._field.moveCursor(QTextCursor.MoveOperation.End)
        self.focus()

    def set_listening(self, listening: bool) -> None:
        """An orange microphone while it listens, a quiet one otherwise."""
        self._mic.setIcon(line_icon("mic", GI_ORANGE if listening else TEXT_MUTED, MIC_ICON_SIZE, hover_color=TEXT))
        self._mic.setToolTip(LISTENING_TIP if listening else MIC_TIP)

    def show_hint(self, text: str) -> None:
        """A short message in the empty field (why voice input failed, say) until typing starts."""
        self._field.setPlaceholderText(text)
        self._hint_reset.start()

    def clear_hint(self) -> None:
        self._hint_reset.stop()
        self._field.setPlaceholderText(PLACEHOLDER_TEXT)

    def set_text(self, text: str) -> None:
        self._field.setPlainText(text)

    def set_answering_elsewhere(self, elsewhere: bool) -> None:
        """Explains why sending is blocked while a reply runs in a chat that isn't on screen."""
        self._field.setPlaceholderText(ELSEWHERE_PLACEHOLDER if elsewhere else PLACEHOLDER_TEXT)

    def is_busy(self) -> bool:
        return self._busy

    def set_busy(self, busy: bool) -> None:
        """While busy: pulse the border glow, turn the send button into a stop button, and
        block sending another message (typing ahead is still fine)."""
        self._busy = busy
        self._show_button_mode()
        stop_animation(self._aura)
        if busy:
            self._aura = build_aura_animation(self)
            self._aura.start()
        else:
            self._aura = None
            self.glow = 0.0

    def _on_button(self) -> None:
        if self._busy:
            self.stop_requested.emit()
        else:
            self._submit()

    def _show_button_mode(self) -> None:
        """An up arrow to send, or a square to stop, like any modern chat app."""
        if self._busy:
            self._send.setIcon(line_icon("square", TEXT_ON_ORANGE, STOP_ICON_SIZE))
            self._send.setIconSize(QSize(STOP_ICON_SIZE, STOP_ICON_SIZE))
        else:
            self._send.setIcon(line_icon("arrow-up", TEXT_ON_ORANGE, SEND_ICON_SIZE))
            self._send.setIconSize(QSize(SEND_ICON_SIZE, SEND_ICON_SIZE))
        self._send.setToolTip(STOP_TIP if self._busy else SEND_TIP)

    def _submit(self) -> None:
        text = self._field.toPlainText().strip()
        if not text or self._busy:
            return
        self._field.clear()
        self.submitted.emit(text)

    def _fit_height(self) -> None:
        """Grows the field with its content, from one line up to MAX_LINES."""
        # A plain-text document measures its height in visual lines, wrapped ones included.
        visual_lines = int(self._field.document().size().height())
        lines = max(MIN_LINES, min(MAX_LINES, visual_lines))
        self._field.setFixedHeight(lines * LINE_HEIGHT_PX + FIELD_PADDING_PX)
