"""
The chat-history page: recent conversations, newest first, with open and delete. Loads the
list from the API in the background. Display and selection only.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from models.chat import ConversationSummary
from ui.api_client import ApiClient
from ui.background_call import run_in_background


class HistoryPanel(QWidget):
    """Emits opened(conversation_id) or back() — the window switches pages."""

    opened = pyqtSignal(str)
    back = pyqtSignal()

    def __init__(self, api: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._list = QListWidget(self)
        self._list.setObjectName("HistoryList")
        self._list.itemActivated.connect(self._open_item)
        self._list.itemClicked.connect(self._open_item)
        self._message = QLabel(self)
        self._message.setProperty("role", "muted")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(self._toolbar())
        layout.addWidget(self._message)
        layout.addWidget(self._list, stretch=1)

    def refresh(self) -> None:
        """Reloads the list from the API."""
        self._message.setText("Loading…")
        run_in_background(self._api.conversations, self._show, self._message.setText)

    def _toolbar(self) -> QHBoxLayout:
        back = QPushButton("← Back to chat", self)
        back.clicked.connect(self.back)
        delete = QPushButton("Delete selected", self)
        delete.setProperty("variant", "danger")
        delete.clicked.connect(self._delete_selected)
        row = QHBoxLayout()
        row.addWidget(back)
        row.addStretch()
        row.addWidget(delete)
        return row

    def _show(self, conversations: list[ConversationSummary]) -> None:
        self._list.clear()
        self._message.setText("" if conversations else "No chats yet.")
        for conversation in conversations:
            item = QListWidgetItem(f"{conversation.title}\n{conversation.updated_at:%d %b %Y, %H:%M}")
            item.setData(Qt.ItemDataRole.UserRole, conversation.id)
            self._list.addItem(item)

    def _open_item(self, item: QListWidgetItem) -> None:
        self.opened.emit(item.data(Qt.ItemDataRole.UserRole))

    def _delete_selected(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        conversation_id = item.data(Qt.ItemDataRole.UserRole)
        run_in_background(
            lambda: self._api.delete_conversation(conversation_id), lambda _: self.refresh(), self._message.setText
        )
