"""
Handles one chat request end to end: opens or creates the conversation, tries the instant
fast path, otherwise runs the assistant, saves every new message, and streams events back.
Also resumes a turn after the user approves or declines an action. Composes the pieces; the
loop, tools, storage and HTTP layer each live in their own modules.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator

from config.settings import get_settings
from config.settings_store import save_user_settings
from core.agent import Agent, pending_tool_calls
from core.attachments import attach
from core.conversation_store import ConversationStore
from core.exceptions import NimbusError
from core.fast_path import FastPath
from core.logger import get_logger
from models.chat import (
    ChatDone,
    ChatEvent,
    ChatFailed,
    ChatMessage,
    ChatRequest,
    ChatSources,
    ChatStarted,
    ChatToken,
    ConfirmationNeeded,
    ConfirmRequest,
)
from models.schema import IndexStatus
from tools.registry import approval_group

logger = get_logger(__name__)

SKIPPED_MESSAGE = "Not run: the user sent a new message instead of answering. Don't retry unless asked."


class ChatService:
    """The single entry point the API uses for chatting."""

    def __init__(
        self,
        store: ConversationStore,
        agent: Agent,
        fast_path: FastPath,
        index_status: Callable[[], IndexStatus],
    ) -> None:
        self._store = store
        self._agent = agent
        self._fast_path = fast_path
        self._index_status = index_status

    def send(self, request: ChatRequest) -> Iterator[ChatEvent]:
        """Streams the reply to one new user message."""
        start = time.monotonic()
        conversation_id = request.conversation_id or self._store.create(request.text)
        self._store.require(conversation_id)
        yield self._started(conversation_id)
        self._skip_unanswered_actions(conversation_id)
        content = attach(request.text, request.attachment) if request.attachment else request.text
        user_message = ChatMessage(role="user", content=content)
        # A question about an attachment always needs the model, never a canned shortcut.
        fast = None if request.attachment else self._fast_path.try_answer(request.text)
        if fast is not None:
            self._store.append(conversation_id, [user_message, ChatMessage(role="assistant", content=fast.text)])
            yield ChatToken(text=fast.text)
            if fast.sources:
                yield ChatSources(sources=fast.sources)
            yield ChatDone(used_llm=False, elapsed_ms=_elapsed_ms(start))
            return
        history = [*self._store.load(conversation_id), user_message]
        yield from self._run_agent(conversation_id, history, None, start)

    def confirm(self, conversation_id: str, decision: ConfirmRequest) -> Iterator[ChatEvent]:
        """Resumes a paused turn with the user's answer to a confirmation card."""
        start = time.monotonic()
        history = self._store.load(conversation_id)
        if decision.call_id not in {c.id for c in pending_tool_calls(history)}:
            yield ChatFailed(message="That action is no longer waiting for an answer.")
            return
        if decision.approved and decision.always_allow:
            self._always_allow(history, decision.call_id)
        yield self._started(conversation_id)
        yield from self._run_agent(conversation_id, history, decision, start)

    def _run_agent(
        self, conversation_id: str, history: list[ChatMessage], decision: ConfirmRequest | None, start: float
    ) -> Iterator[ChatEvent]:
        """Runs the assistant, saving whatever it added even if it failed partway."""
        saved_count = len(self._store.load(conversation_id))
        awaiting = False
        try:
            for event in self._agent.run(history, decision):
                awaiting = awaiting or isinstance(event, ConfirmationNeeded)
                yield event
        except NimbusError as e:
            logger.warning("Assistant turn failed", extra={"error": str(e)})
            yield ChatFailed(message=str(e))
        finally:
            self._store.append(conversation_id, history[saved_count:])
        yield ChatDone(used_llm=True, elapsed_ms=_elapsed_ms(start), awaiting_confirmation=awaiting)

    def _skip_unanswered_actions(self, conversation_id: str) -> None:
        """A new message while an approval card is still open means the user moved on. The
        waiting calls get a "skipped" result, otherwise they'd run on the next turn, and model
        APIs reject a history with tool calls that never got an answer."""
        pending = pending_tool_calls(self._store.load(conversation_id))
        if pending:
            skipped = [
                ChatMessage(role="tool", content=SKIPPED_MESSAGE, tool_call_id=call.id, tool_name=call.name)
                for call in pending
            ]
            self._store.append(conversation_id, skipped)

    def _started(self, conversation_id: str) -> ChatStarted:
        return ChatStarted(
            conversation_id=conversation_id,
            index_status=self._index_status(),
            is_cloud=get_settings().is_cloud_provider,
        )

    def _always_allow(self, history: list[ChatMessage], call_id: str) -> None:
        """Remembers "always allow" for the tool behind call_id, and for any tool that shares its
        setting (allowing Word files allows spreadsheets too: Settings shows one switch)."""
        tool = next(c.name for c in pending_tool_calls(history) if c.id == call_id)
        allowed = get_settings().auto_approved_tools
        missing = [name for name in approval_group(tool) if name not in allowed]
        if missing:
            save_user_settings({"auto_approved_tools": [*allowed, *missing]})


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)
