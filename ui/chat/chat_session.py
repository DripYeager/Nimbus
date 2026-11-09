"""
Drives one on-screen conversation: sends what the user types, routes each streamed event to
the right widget, handles approve/decline cards, and switches between new and saved chats.
The glue between ChatStream and the widgets — it draws nothing itself.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from models.chat import ChatMessage
from models.schema import IndexStatus, SourceRef
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.chat.chat_input import ChatInput
from ui.chat.chat_stream import ChatStream
from ui.chat.chat_view import ChatView

STILL_LEARNING_ID = "index-progress"


class ChatSession(QObject):
    """Owns the current conversation id and the busy state of the input. Emits
    status_received(IndexStatus, is_cloud) whenever a reply starts, for the header."""

    status_received = pyqtSignal(object, bool)

    def __init__(self, view: ChatView, chat_input: ChatInput, api: ApiClient, stream: ChatStream) -> None:
        super().__init__()
        self._view = view
        self._input = chat_input
        self._api = api
        self._stream = stream
        self._conversation_id: str | None = None

    def connect_signals(self) -> None:
        """Wires the input, the welcome chips and the stream to this session."""
        self._input.submitted.connect(self.send)
        self._view.suggestion_clicked.connect(self.send)
        self._stream.event_received.connect(self._handle_event)
        self._stream.failed.connect(self._fail)
        self._stream.finished.connect(self._finish)

    def send(self, text: str) -> None:
        """Shows the message and streams the reply."""
        self._view.add_user_message(text)
        self._input.set_busy(True)
        self._stream.send(text, self._conversation_id)

    def new_chat(self) -> None:
        """Abandons the current conversation and shows the welcome state."""
        self._stream.cancel()
        self._conversation_id = None
        self._view.clear()
        self._input.set_busy(False)

    def open_conversation(self, conversation_id: str) -> None:
        """Loads a saved chat and continues it."""
        self._stream.cancel()
        self._input.set_busy(False)

        def _show(messages: list[ChatMessage]) -> None:
            self._conversation_id = conversation_id
            self._view.load_history(messages)

        run_in_background(lambda: self._api.conversation(conversation_id), _show, self._fail)

    def cancel(self) -> None:
        """Stops listening to an in-flight reply (the window was hidden)."""
        self._stream.cancel()
        self._input.set_busy(False)

    def _handle_event(self, name: str, data: dict[str, Any]) -> None:
        """Routes one streamed event to the widget it belongs to."""
        # current_reply creates the reply widget on first use, so only touch it for events that
        # draw into it — otherwise "started"/"confirm"/"done" would leave empty replies behind.
        if name == "started":
            self._on_started(data)
        elif name == "token":
            self._view.current_reply.append_text(data["text"])
        elif name == "tool":
            self._view.current_reply.show_tool(data["call_id"], data["label"], data["status"])
        elif name == "sources":
            self._view.current_reply.set_sources([SourceRef(**item) for item in data["sources"]])
        elif name == "confirm":
            self._ask_confirmation(data)
        elif name == "error":
            self._view.current_reply.show_error(data["message"])

    def _on_started(self, data: dict[str, Any]) -> None:
        """Remembers the conversation, updates the header, and flags a still-running index."""
        self._conversation_id = data["conversation_id"]
        status = IndexStatus(**data["index_status"])
        self.status_received.emit(status, bool(data["is_cloud"]))
        if status.pending_files:
            percent = int(status.progress_ratio * 100)
            label = f"Still learning your files ({percent}%) — some may not be searchable yet"
            self._view.current_reply.show_tool(STILL_LEARNING_ID, label, "info")

    def _ask_confirmation(self, data: dict[str, Any]) -> None:
        """Shows an approve/decline card; the answer resumes the paused turn."""
        call_id = data["call_id"]
        card = self._view.add_confirmation(data["description"])
        self._view.end_reply()

        def _decided(approved: bool, always: bool) -> None:
            self._input.set_busy(True)
            decision = {"call_id": call_id, "approved": approved, "always_allow": always}
            self._stream.answer_confirmation(self._conversation_id, decision)

        card.decided.connect(_decided)

    def _fail(self, message: str) -> None:
        self._view.current_reply.show_error(message)
        self._finish()

    def _finish(self) -> None:
        """The stream ended: unlock the input and close the reply."""
        self._input.set_busy(False)
        self._input.focus()
        self._view.end_reply()
