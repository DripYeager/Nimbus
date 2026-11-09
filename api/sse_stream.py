"""
Serializes the assistant's event stream as Server-Sent Events. Owns the wire format, and makes
sure any unexpected failure still ends the stream with a proper error event. Does not produce
events itself.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator

from pydantic import BaseModel

from core.exceptions import NimbusError
from core.logger import get_logger
from models.chat import (
    ChatDone,
    ChatEvent,
    ChatFailed,
    ChatSources,
    ChatStarted,
    ChatToken,
    ConfirmationNeeded,
    ToolActivity,
)

logger = get_logger(__name__)

EVENT_NAMES: dict[type[BaseModel], str] = {
    ChatStarted: "started",
    ChatToken: "token",
    ToolActivity: "tool",
    ChatSources: "sources",
    ConfirmationNeeded: "confirm",
    ChatDone: "done",
    ChatFailed: "error",
}
UNEXPECTED_ERROR_MESSAGE = "Something went wrong on Nimbus's side. Details are in the log file."


def format_sse(event: ChatEvent) -> str:
    """One named SSE frame."""
    return f"event: {EVENT_NAMES[type(event)]}\ndata: {event.model_dump_json()}\n\n"


def stream_sse(events: Iterator[ChatEvent]) -> Generator[str, None, None]:
    """Frames every event. A crash mid-stream becomes an error frame plus a done frame, so the
    chat window always gets something to stop its thinking animation on."""
    try:
        for event in events:
            yield format_sse(event)
    except NimbusError as e:
        # Raised before the chat service could turn it into an event (e.g. an unknown chat id);
        # its message is written for the user, so pass it through.
        yield format_sse(ChatFailed(message=str(e)))
        yield format_sse(ChatDone(used_llm=False, elapsed_ms=0))
    except Exception:
        logger.exception("Chat stream crashed")
        yield format_sse(ChatFailed(message=UNEXPECTED_ERROR_MESSAGE))
        yield format_sse(ChatDone(used_llm=False, elapsed_ms=0))
