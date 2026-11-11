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
from models.chat import HistoryTurn, ShownCode
from ui.chat.code_block import StepDetail
from ui.chat.message_cards import ConfirmCard
from ui.chat.message_widgets import AssistantMessage
from ui.chat.user_bubble import UserBubble

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
                # Hidden at once: deletion waits for the event loop, and until then the old
                # messages would still paint under whatever is shown next.
                item.widget().hide()
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
        self._current.flush()
        if self._current.is_empty():
            self._layout.removeWidget(self._current)
            self._current.deleteLater()
        self._current = None

    def add_confirmation(
        self, description: str, can_always_allow: bool = True, code: ShownCode | None = None
    ) -> ConfirmCard:
        self.end_reply()
        card = ConfirmCard(description, self, can_always_allow, code)
        self._cards.append(card)
        self._append(card)
        return card

    def load_history(self, turns: list[HistoryTurn]) -> None:
        """Re-renders a saved conversation: each reply with its steps, as it looked live."""
        self.clear()
        for turn in turns:
            if turn.role == "user":
                # A saved message carries its attachment's full text; show a tag instead.
                text, items = split_attachments(turn.text)
                self.add_user_message(text, tuple(items))
                continue
            if not turn.text.strip() and not turn.steps:
                continue
            reply = self.current_reply
            reply.hide_time()
            for step in turn.steps:
                detail = StepDetail(code=step.code, output=step.output) if step.code else None
                reply.show_tool(step.call_id, step.label, step.status, detail)
            if turn.text.strip():
                reply.set_text(turn.text)
            self.end_reply()

    def skip_open_cards(self) -> None:
        """The user moved on without answering: open cards stop waiting (the engine skips
        those actions too), so a late click can't send a stale answer."""
        for card in self._cards:
            if card.is_open():
                card.mark_skipped()

    def insert_history(self, turns: list[HistoryTurn]) -> None:
        """Puts a saved conversation above what's already shown: a message the user sent while
        the history was still loading, and its (possibly still streaming) reply."""
        shown = [self._layout.takeAt(0).widget() for _ in range(self._layout.count() - 1)]
        current, cards = self._current, list(self._cards)
        self._current = None
        self.load_history(turns)
        for widget in shown:
            if widget is not None:
                self._layout.insertWidget(self._layout.count() - 1, widget)
        self._current = current
        self._cards.extend(cards)

    def _append(self, widget: QWidget) -> None:
        """Adds widget above the bottom stretch."""
        self._layout.insertWidget(self._layout.count() - 1, widget)
        self.content_added.emit()
