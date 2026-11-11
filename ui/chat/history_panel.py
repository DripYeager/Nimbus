"""
The chat-history page: a search box and recent conversations, newest first, each with its own
delete button. Loads the list from the API in the background and filters it as you type.
Display and selection only; the window handles navigation.
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from models.chat import ConversationSummary
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.theme.line_icons import line_icon, line_pixmap
from ui.theme.tokens import DANGER, GI_ORANGE, TEXT_FAINT, TEXT_MUTED

ROW_ICON_SIZE = 18
SEARCH_ICON_SIZE = 16
DELETE_CONFIRM_MS = 3000
CONFIRM_DELETE_TEXT = "Delete?"


class ConversationRow(QPushButton):
    """One saved chat: icon, title and date, with a delete button on the right."""

    delete_requested = pyqtSignal(str)

    def __init__(self, conversation: ConversationSummary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ConversationRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.conversation_id = conversation.id
        self.title = conversation.title
        icon = QLabel(self)
        icon.setPixmap(line_pixmap("message-square", GI_ORANGE, ROW_ICON_SIZE))
        title = QLabel(conversation.title, self)
        title.setObjectName("ConversationTitle")
        date = QLabel(f"{conversation.updated_at:%d %b %Y · %H:%M}", self)
        date.setObjectName("ConversationDate")
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(title)
        text.addWidget(date)
        self._build_delete()
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 8, 10)
        row.setSpacing(12)
        row.addWidget(icon)
        row.addLayout(text, stretch=1)
        row.addWidget(self._delete)
        self.setMinimumHeight(56)

    def _build_delete(self) -> None:
        """The trash button; a first click turns it into "Delete?" for a few seconds."""
        self._delete = QToolButton(self)
        self._delete.setObjectName("DeleteChat")
        self._delete.setIconSize(QSize(ROW_ICON_SIZE - 2, ROW_ICON_SIZE - 2))
        self._delete.clicked.connect(self._on_delete_clicked)
        self._disarm = QTimer(self)
        self._disarm.setSingleShot(True)
        self._disarm.setInterval(DELETE_CONFIRM_MS)
        self._disarm.timeout.connect(self._show_trash)
        self._show_trash()

    def _on_delete_clicked(self) -> None:
        """The first click asks ("Delete?"); a second one within a few seconds deletes."""
        if self._disarm.isActive():
            self._disarm.stop()
            self.delete_requested.emit(self.conversation_id)
            return
        self._delete.setIcon(QIcon())
        self._delete.setText(CONFIRM_DELETE_TEXT)
        self._delete.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._delete.setToolTip("Click again to delete this chat")
        self._disarm.start()

    def _show_trash(self) -> None:
        self._delete.setText("")
        self._delete.setIcon(line_icon("trash-2", TEXT_FAINT, ROW_ICON_SIZE - 2, hover_color=DANGER))
        self._delete.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._delete.setToolTip("Delete this chat")


class HistoryPanel(QWidget):
    """Emits opened(conversation_id) when a chat is picked."""

    opened = pyqtSignal(str)

    def __init__(self, api: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._rows: list[ConversationRow] = []
        self._search = QLineEdit(self)
        self._search.setObjectName("HistorySearch")
        self._search.setPlaceholderText("Search your chats")
        self._search.addAction(
            line_icon("search", TEXT_MUTED, SEARCH_ICON_SIZE), QLineEdit.ActionPosition.LeadingPosition
        )
        self._search.textChanged.connect(self._filter)
        self._message = QLabel(self)
        self._message.setObjectName("HistoryEmpty")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list = QVBoxLayout()
        self._list.setSpacing(4)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(12)
        layout.addWidget(self._search)
        layout.addWidget(self._message)
        layout.addWidget(self._scrolling_list(), stretch=1)

    def refresh(self) -> None:
        """Reloads the list from the API."""
        self._message.setText("Loading…")
        self._message.show()
        run_in_background(self._api.conversations, self._show, self._message.setText)

    def _scrolling_list(self) -> QScrollArea:
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 6, 0)
        column.addLayout(self._list)
        column.addStretch()
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(holder)
        return scroll

    def _show(self, conversations: list[ConversationSummary]) -> None:
        for row in self._rows:
            row.deleteLater()
        self._rows = []
        for conversation in conversations:
            row = ConversationRow(conversation, self)
            row.clicked.connect(lambda _=False, cid=conversation.id: self.opened.emit(cid))
            row.delete_requested.connect(self._delete)
            self._list.addWidget(row)
            self._rows.append(row)
        self._message.setText("No chats yet. Your conversations will show up here.")
        self._message.setVisible(not conversations)
        self._filter(self._search.text())

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        for row in self._rows:
            row.setVisible(needle in row.title.lower())

    def _delete(self, conversation_id: str) -> None:
        run_in_background(
            lambda: self._api.delete_conversation(conversation_id), lambda _: self.refresh(), self._show_error
        )

    def _show_error(self, message: str) -> None:
        """The message line is hidden while chats are listed, so unhide it for the error."""
        self._message.setText(message)
        self._message.show()
