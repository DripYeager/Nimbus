"""
Drives the on-screen conversations: sends what the user types, routes each streamed event to
the conversation it belongs to, handles approve/decline cards, and switches between new and
saved chats. Only one reply runs at a time, and switching chats never stops it: the running
conversation is set aside, keeps filling in off screen, and comes back when reopened. The glue
between ChatStream and the widgets; it draws nothing itself.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from core.attachment_format import AttachedItem
from models.chat import Attachment, ChatMessage, ShownCode
from models.schema import IndexStatus, SourceRef
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.chat.chat_input import ChatInput
from ui.chat.chat_stream import ChatStream
from ui.chat.chat_view import ChatView
from ui.chat.code_block import StepDetail
from ui.chat.conversation_column import ConversationColumn

STILL_LEARNING_ID = "index-progress"
BUSY_ELSEWHERE_MESSAGE = "Nimbus is still answering in another chat. Wait for it to finish, or stop it first."


class ChatSession(QObject):
    """Owns which conversation is on screen, which one is running, and the input's busy state.
    Emits status_received(IndexStatus, is_cloud) whenever a reply starts, for the header."""

    status_received = pyqtSignal(object, bool)
    attachment_changed = pyqtSignal(object)

    def __init__(self, view: ChatView, chat_input: ChatInput, api: ApiClient, stream: ChatStream) -> None:
        super().__init__()
        self._view = view
        self._input = chat_input
        self._api = api
        self._stream = stream
        self._conversation_id: str | None = None
        self._attachment: Attachment | None = None
        # The conversation whose reply is streaming, and its column (on screen or set aside).
        self._running_id: str | None = None
        self._running: ConversationColumn | None = None
        # A conversation taken off screen while it was running (or still waiting on a card).
        self._set_aside: ConversationColumn | None = None
        self._set_aside_id: str | None = None
        # Bumped whenever the on-screen chat changes, so a history load that finishes late
        # can't paint itself over the chat the user has since switched to.
        self._shown_generation = 0

    def connect_signals(self) -> None:
        """Wires the input, the welcome chips and the stream to this session."""
        self._input.submitted.connect(self.send)
        self._input.stop_requested.connect(self.stop)
        self._view.suggestion_clicked.connect(self.send)
        self._stream.event_received.connect(self._handle_event)
        self._stream.failed.connect(self._fail)
        self._stream.finished.connect(self._finish)

    def attach(self, attachment: Attachment | None) -> None:
        """Hands something to the next question (None takes it back)."""
        self._attachment = attachment
        self.attachment_changed.emit(attachment)

    def send(self, text: str) -> None:
        """Shows the message and streams the reply, unless a reply is already running. Whatever
        is attached goes with this message and is then cleared."""
        if self._input.is_busy():
            return
        attachment, self._attachment = self._attachment, None
        attached = (AttachedItem(attachment.name, attachment.path),) if attachment else ()
        self._view.add_user_message(text, attached)
        self._view.begin_reply()
        self._start_running(self._conversation_id)
        self._stream.send(text, self._conversation_id, attachment)
        if attachment is not None:
            self.attachment_changed.emit(None)

    def new_chat(self) -> None:
        """Shows the welcome state for a new conversation; a running reply carries on."""
        self._leave_current()
        self._conversation_id = None
        self._invalidate_pending_load()

    def open_conversation(self, conversation_id: str) -> None:
        """Shows a chat: the running one straight from memory, any other loaded from disk."""
        if self._set_aside is not None and conversation_id == self._set_aside_id:
            self._view.attach(self._set_aside)
            self._set_aside, self._set_aside_id = None, None
            self._input.set_answering_elsewhere(False)
            self._conversation_id = conversation_id
            self._invalidate_pending_load()
            return
        if conversation_id == self._running_id and self._view.column is self._running:
            # Already on screen and still answering; reloading would hide the live reply.
            return
        self._leave_current()
        # Set before the load returns, so a message typed while it is in flight joins this chat
        # and not the one that was on screen before.
        self._conversation_id = conversation_id
        generation = self._invalidate_pending_load()
        column = self._view.column

        def _show(messages: list[ChatMessage]) -> None:
            if generation != self._shown_generation:
                return
            if column.has_messages():
                # The user sent something while this loaded: keep it, with the history above.
                column.insert_history(messages)
            else:
                self._view.load_history(messages)

        def _error(message: str) -> None:
            if generation != self._shown_generation:
                return
            # The chat can't be opened (deleted, say), so don't keep sending into it.
            if self._conversation_id == conversation_id:
                self._conversation_id = None
            self._show_load_error(message)

        run_in_background(lambda: self._api.conversation(conversation_id), _show, _error)

    def _invalidate_pending_load(self) -> int:
        """Drops whichever history load is in flight; returns the new generation."""
        self._shown_generation += 1
        return self._shown_generation

    def stop(self) -> None:
        """The stop button: ends the running reply and keeps what it had written so far. Closing
        the stream tells the engine, which stops the model after its current step and still
        saves the question. Hiding the window, opening Settings or switching chats never does."""
        if self._running is None:
            return
        self._stream.cancel()
        self._running.current_reply.mark_stopped()
        self._finish()

    def _start_running(self, conversation_id: str | None) -> None:
        self._running = self._view.column
        self._running_id = conversation_id
        self._input.set_busy(True)

    def _leave_current(self) -> None:
        """Clears the screen for another chat; a running conversation is set aside, not lost."""
        if self._running is not None and self._view.column is self._running:
            self._drop_set_aside()
            self._set_aside, self._set_aside_id = self._view.detach(), self._running_id
            self._input.set_answering_elsewhere(True)
        else:
            self._view.clear()

    def _drop_set_aside(self) -> None:
        if self._set_aside is not None:
            self._set_aside.deleteLater()
        self._set_aside, self._set_aside_id = None, None

    def _handle_event(self, name: str, data: dict[str, Any]) -> None:
        """Routes one streamed event to the widget it belongs to."""
        column = self._running
        if column is None:
            return
        # current_reply creates the reply widget on first use, so only touch it for events that
        # draw into it; otherwise "started"/"confirm"/"done" would leave empty replies behind.
        if name == "started":
            self._on_started(column, data)
        elif name == "token":
            column.current_reply.append_text(data["text"])
        elif name == "tool":
            column.current_reply.show_tool(data["call_id"], data["label"], data["status"], step_detail(data))
        elif name == "sources":
            column.current_reply.set_sources([SourceRef(**item) for item in data["sources"]])
        elif name == "confirm":
            self._ask_confirmation(column, data)
        elif name == "error":
            column.current_reply.show_error(data["message"])

    def _on_started(self, column: ConversationColumn, data: dict[str, Any]) -> None:
        """Remembers the conversation, updates the header, and flags a still-running index."""
        self._running_id = data["conversation_id"]
        if column is self._view.column:
            self._conversation_id = self._running_id
        elif column is self._set_aside:
            self._set_aside_id = self._running_id
        status = IndexStatus(**data["index_status"])
        self.status_received.emit(status, bool(data["is_cloud"]))
        if status.pending_files:
            percent = int(status.progress_ratio * 100)
            label = f"Still learning your files ({percent}%), so some may not be searchable yet"
            column.current_reply.show_tool(STILL_LEARNING_ID, label, "info")

    def _ask_confirmation(self, column: ConversationColumn, data: dict[str, Any]) -> None:
        """Shows an approve/decline card; the answer resumes the paused turn."""
        call_id = data["call_id"]
        conversation_id = self._running_id
        code = ShownCode(**data["code"]) if data.get("code") else None
        card = column.add_confirmation(data["description"], bool(data.get("can_always_allow", True)), code)

        def _decided(approved: bool, always: bool) -> None:
            if self._input.is_busy():
                column.current_reply.show_error(BUSY_ELSEWHERE_MESSAGE)
                column.end_reply()
                card.reopen()
                return
            column.begin_reply()
            self._running = column
            self._running_id = conversation_id
            self._input.set_busy(True)
            decision = {"call_id": call_id, "approved": approved, "always_allow": always}
            self._stream.answer_confirmation(conversation_id, decision)

        card.decided.connect(_decided)

    def _fail(self, message: str) -> None:
        if self._running is not None:
            self._running.current_reply.show_error(message)
        self._finish()

    def _show_load_error(self, message: str) -> None:
        self._view.current_reply.show_error(message)
        self._view.end_reply()

    def _finish(self) -> None:
        """The stream ended: close the reply and unlock the input. A conversation that was set
        aside stays in memory only if a card in it still waits for an answer; otherwise reopening
        it from History loads the saved copy."""
        column, self._running = self._running, None
        if column is not None:
            column.end_reply()
        if column is not None and column is self._set_aside and not column.has_open_card():
            self._drop_set_aside()
        self._running_id = None
        self._input.set_answering_elsewhere(False)
        self._input.set_busy(False)
        self._input.focus()


def step_detail(data: dict[str, Any]) -> StepDetail | None:
    """The code and output a "tool" event carries, for code and command steps."""
    code = data.get("code")
    output = data.get("output")
    if not code and output is None:
        return None
    return StepDetail(code=ShownCode(**code) if code else None, output=output)
