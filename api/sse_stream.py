"""
Serializes the assistant's event stream as Server-Sent Events. Owns the wire format, the
keep-alive heartbeat that tells the chat window a slow model is still working, and making sure
any unexpected failure still ends the stream with a proper error event. Does not produce events
itself.
"""

from __future__ import annotations

import queue
import threading
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
# A local model can think for minutes before its first word. A comment frame (ignored by SSE
# parsers) every few seconds keeps the connection visibly alive, so the client only gives up
# when the engine itself has gone quiet.
HEARTBEAT_SECONDS = 10.0
HEARTBEAT_FRAME = ": keepalive\n\n"
_END_OF_STREAM = object()


def format_sse(event: ChatEvent) -> str:
    """One named SSE frame."""
    return f"event: {EVENT_NAMES[type(event)]}\ndata: {event.model_dump_json()}\n\n"


def stream_sse(events: Iterator[ChatEvent], heartbeat_seconds: float = HEARTBEAT_SECONDS) -> Generator[str, None, None]:
    """Frames every event, sending a heartbeat whenever the assistant is silent for a while.

    The assistant runs on its own thread so a long, blocking model call can't hold up the
    heartbeat. Closing this generator (the client went away) stops it after its current step."""
    frames: queue.Queue[object] = queue.Queue()
    stop = threading.Event()
    threading.Thread(target=_produce, args=(events, frames, stop), name="chat-events", daemon=True).start()
    try:
        while True:
            try:
                frame = frames.get(timeout=heartbeat_seconds)
            except queue.Empty:
                yield HEARTBEAT_FRAME
                continue
            if frame is _END_OF_STREAM:
                return
            yield str(frame)
    finally:
        stop.set()


def _produce(events: Iterator[ChatEvent], frames: queue.Queue[object], stop: threading.Event) -> None:
    """Moves framed events onto the queue until the stream ends or the reader leaves."""
    try:
        for frame in _framed(events):
            if stop.is_set():
                return
            frames.put(frame)
    finally:
        close = getattr(events, "close", None)
        if close is not None:
            close()
        frames.put(_END_OF_STREAM)


def _framed(events: Iterator[ChatEvent]) -> Iterator[str]:
    """A crash mid-stream becomes an error frame plus a done frame, so the chat window always
    gets something to stop its thinking animation on."""
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
