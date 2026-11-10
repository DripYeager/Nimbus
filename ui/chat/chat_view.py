"""
The scrolling conversation area: shows the welcome screen for a new chat, then stacks user
bubbles, replies and confirmation cards, keeping the newest one in view. Layout only — it never
decides what to say.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from models.chat import ChatMessage
from ui.chat.empty_state import EmptyState
from ui.chat.message_cards import ConfirmCard
from ui.chat.message_widgets import AssistantMessage, UserBubble

MESSAGE_SPACING = 18
# Long lines are hard to read; past this the conversation column stops growing.
MAX_COLUMN_WIDTH = 720


class ChatView(QStackedWidget):
    """Page 0 is the welcome screen; page 1 is the conversation."""

    suggestion_clicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current: AssistantMessage | None = None
        empty = EmptyState(self)
        empty.suggestion_clicked.connect(self.suggestion_clicked)
        self.addWidget(empty)
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("ChatScroll")
        self._scroll.viewport().setAutoFillBackground(False)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content = QWidget()
        self._content.setObjectName("ChatContent")
        self._content.setMaximumWidth(MAX_COLUMN_WIDTH)
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(4, 8, 12, 8)
        self._layout.setSpacing(MESSAGE_SPACING)
        self._layout.addStretch()
        self._scroll.setWidget(self._content)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.addWidget(self._scroll)
        # Owned by the view, so a pending scroll can never outlive it.
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(0)
        self._scroll_timer.timeout.connect(self._scroll_to_end)
        self._scroll.verticalScrollBar().rangeChanged.connect(self._stick_to_bottom)

    @property
    def current_reply(self) -> AssistantMessage:
        """The reply being streamed, created on first use."""
        if self._current is None:
            self._current = AssistantMessage(self._content)
            self._append(self._current)
        return self._current

    def begin_reply(self) -> None:
        """Shows a fresh reply in its thinking state straight away, before anything streams."""
        self.current_reply.start_thinking()

    def clear(self) -> None:
        """Back to the welcome screen with an empty conversation."""
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._current = None
        self.setCurrentIndex(0)

    def add_user_message(self, text: str) -> None:
        """Shows the user's message and starts a fresh reply slot after it."""
        self.end_reply()
        self._append(UserBubble(text, self._content))

    def end_reply(self) -> None:
        """Closes the current reply; one that never got any content is removed."""
        if self._current is None:
            return
        self._current.stop_thinking()
        if self._current.is_empty():
            self._layout.removeWidget(self._current)
            self._current.deleteLater()
        self._current = None

    def add_confirmation(self, description: str) -> ConfirmCard:
        self.end_reply()
        card = ConfirmCard(description, self._content)
        self._append(card)
        return card

    def load_history(self, messages: list[ChatMessage]) -> None:
        """Re-renders a saved conversation."""
        self.clear()
        for message in messages:
            if message.role == "user":
                self.add_user_message(message.content)
            elif message.content.strip():
                self.current_reply.set_text(message.content)
                self.end_reply()

    def _append(self, widget: QWidget) -> None:
        """Adds widget above the bottom stretch and switches to the conversation page."""
        self._layout.insertWidget(self._layout.count() - 1, widget)
        self.setCurrentIndex(1)

    def _stick_to_bottom(self, _minimum: int, _maximum: int) -> None:
        """Follows new content down, after Qt has finished laying it out."""
        self._scroll_timer.start()

    def _scroll_to_end(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
