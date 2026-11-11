"""
The scrolling conversation area: the welcome screen for a new chat, or the column of messages
for the chat on screen, keeping the newest message in view. A column whose reply is still
running can be set aside (detach) and brought back later (attach). Layout only; it never
decides what to say.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QScrollArea, QStackedWidget, QWidget

from core.attachment_format import AttachedItem
from models.chat import HistoryTurn, ShownCode
from ui.chat.conversation_column import ConversationColumn
from ui.chat.empty_state import EmptyState
from ui.chat.message_cards import ConfirmCard
from ui.chat.message_widgets import AssistantMessage

WELCOME_PAGE, CONVERSATION_PAGE = 0, 1


# Within this many pixels of the bottom counts as reading the newest message.
FOLLOW_MARGIN_PX = 40


class ChatView(QStackedWidget):
    """Page 0 is the welcome screen; page 1 is the conversation column."""

    suggestion_clicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        empty = EmptyState(self)
        empty.suggestion_clicked.connect(self.suggestion_clicked)
        self.addWidget(empty)
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("ChatScroll")
        self._scroll.viewport().setAutoFillBackground(False)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.addWidget(self._scroll)
        self._column = self._install(self._new_column())
        # Owned by the view, so a pending scroll can never outlive it.
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(0)
        self._scroll_timer.timeout.connect(self._scroll_to_end)
        # Follow new content only while the user is at the bottom; reading further up stays put.
        self._following = True
        self._scroll.verticalScrollBar().rangeChanged.connect(self._stick_to_bottom)
        self._scroll.verticalScrollBar().valueChanged.connect(self._note_position)

    @property
    def column(self) -> ConversationColumn:
        """The conversation on screen."""
        return self._column

    @property
    def current_reply(self) -> AssistantMessage:
        return self._column.current_reply

    def begin_reply(self) -> None:
        self._column.begin_reply()

    def clear(self) -> None:
        """Back to the welcome screen with an empty conversation."""
        self._column.clear()
        self.setCurrentIndex(WELCOME_PAGE)

    def add_user_message(self, text: str, attachments: tuple[AttachedItem, ...] = ()) -> None:
        self._following = True
        self._column.add_user_message(text, attachments)

    def end_reply(self) -> None:
        self._column.end_reply()

    def add_confirmation(
        self, description: str, can_always_allow: bool = True, code: ShownCode | None = None
    ) -> ConfirmCard:
        return self._column.add_confirmation(description, can_always_allow, code)

    def load_history(self, turns: list[HistoryTurn]) -> None:
        self._following = True
        self._column.load_history(turns)
        self.setCurrentIndex(CONVERSATION_PAGE if self._column.has_messages() else WELCOME_PAGE)

    def detach(self) -> ConversationColumn:
        """Takes the column off screen, still alive and still updatable, and shows a fresh,
        empty one in its place."""
        column = self._column
        self._scroll.takeWidget()
        column.setParent(self)
        column.hide()
        self._column = self._install(self._new_column())
        self.setCurrentIndex(WELCOME_PAGE)
        return column

    def attach(self, column: ConversationColumn) -> None:
        """Puts a detached column back on screen, discarding the one shown now."""
        shown = self._scroll.takeWidget()
        if shown is not None:
            shown.deleteLater()
        self._following = True
        self._column = self._install(column)
        column.show()
        self.setCurrentIndex(CONVERSATION_PAGE if column.has_messages() else WELCOME_PAGE)

    def _new_column(self) -> ConversationColumn:
        column = ConversationColumn()
        column.content_added.connect(self._show_conversation)
        return column

    def _install(self, column: ConversationColumn) -> ConversationColumn:
        self._scroll.setWidget(column)
        return column

    def _show_conversation(self) -> None:
        if self.sender() is self._column:
            self.setCurrentIndex(CONVERSATION_PAGE)

    def _stick_to_bottom(self, _minimum: int, _maximum: int) -> None:
        """Follows new content down, after Qt has finished laying it out, unless the user has
        scrolled up to read (sending a message or opening a chat follows again)."""
        if self._following:
            self._scroll_timer.start()

    def _note_position(self, value: int) -> None:
        self._following = value >= self._scroll.verticalScrollBar().maximum() - FOLLOW_MARGIN_PX

    def _scroll_to_end(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
