"""
One conversation's messages, top to bottom: user bubbles, replies and confirmation cards. A
column can be taken off screen while its reply is still streaming and put back later, which is
how switching chats leaves a running answer untouched. Layout only; it never decides what to
say.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from core.attachment_format import AttachedItem, split_attachments
from models.chat import ChatMessage
from ui.chat.message_cards import ConfirmCard
from ui.chat.message_widgets import AssistantMessage, UserBubble

MESSAGE_SPACING = 18
# Long lines are hard to read; past this the conversation column stops growing.
MAX_COLUMN_WIDTH = 720


class ConversationColumn(QWidget):
    """Emits content_added whenever a message is added, so its view can leave the welcome screen."""

    content_added = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ChatContent")
        self.setMaximumWidth(MAX_COLUMN_WIDTH)
        self._current: AssistantMessage | None = None
        self._cards: list[ConfirmCard] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 8, 12, 8)
        self._layout.setSpacing(MESSAGE_SPACING)
        self._layout.addStretch()

    @property
    def current_reply(self) -> AssistantMessage:
        """The reply being streamed, created on first use."""
        if self._current is None:
            self._current = AssistantMessage(self)
            self._append(self._current)
        return self._current

    def has_messages(self) -> bool:
        return self._layout.count() > 1

    def has_open_card(self) -> bool:
        """True while an approve/decline card here still waits for an answer."""
        return any(card.is_open() for card in self._cards)

    def begin_reply(self) -> None:
        """Shows a fresh reply in its thinking state straight away, before anything streams."""
        self.current_reply.start_thinking()

    def clear(self) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._current = None
        self._cards.clear()

    def add_user_message(self, text: str, attachments: tuple[AttachedItem, ...] = ()) -> None:
        """Shows the user's message and starts a fresh reply slot after it."""
        self.end_reply()
        self._append(UserBubble(text, self, attachments))

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
        card = ConfirmCard(description, self)
        self._cards.append(card)
        self._append(card)
        return card

    def load_history(self, messages: list[ChatMessage]) -> None:
        """Re-renders a saved conversation."""
        self.clear()
        for message in messages:
            if message.role == "user":
                # A saved message carries its attachment's full text; show a tag instead.
                text, items = split_attachments(message.content)
                self.add_user_message(text, tuple(items))
            elif message.content.strip():
                self.current_reply.set_text(message.content)
                self.end_reply()

    def insert_history(self, messages: list[ChatMessage]) -> None:
        """Puts a saved conversation above what's already shown: a message the user sent while
        the history was still loading, and its (possibly still streaming) reply."""
        shown = [self._layout.takeAt(0).widget() for _ in range(self._layout.count() - 1)]
        current, cards = self._current, list(self._cards)
        self._current = None
        self.load_history(messages)
        for widget in shown:
            if widget is not None:
                self._layout.insertWidget(self._layout.count() - 1, widget)
        self._current = current
        self._cards.extend(cards)

    def _append(self, widget: QWidget) -> None:
        """Adds widget above the bottom stretch."""
        self._layout.insertWidget(self._layout.count() - 1, widget)
        self.content_added.emit()
