from __future__ import annotations

import threading
import time
from collections.abc import Iterator

from api.sse_stream import HEARTBEAT_FRAME, UNEXPECTED_ERROR_MESSAGE, format_sse, stream_sse
from core.exceptions import ConversationNotFoundError
from core.sse import parse_sse_events
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
from models.schema import IndexStatus


def _names(frames: list[str]) -> list[str]:
    return [name for name, _ in parse_sse_events("".join(frames).splitlines())]


def test_format_sse_writes_a_named_frame() -> None:
    assert format_sse(ChatToken(text="hi")) == 'event: token\ndata: {"text":"hi"}\n\n'


def test_format_sse_names_every_event_type() -> None:
    events: list[ChatEvent] = [
        ChatStarted(conversation_id="c", index_status=IndexStatus(), is_cloud=False),
        ChatToken(text="x"),
        ToolActivity(call_id="1", tool="search_files", label="Searched", status="done"),
        ChatSources(sources=[]),
        ConfirmationNeeded(call_id="1", tool="open_app", description="Open Spotify"),
        ChatDone(used_llm=True, elapsed_ms=5),
        ChatFailed(message="nope"),
    ]
    names = _names([format_sse(e) for e in events])

    assert names == ["started", "token", "tool", "sources", "confirm", "done", "error"]


def test_stream_sse_frames_each_event_in_order() -> None:
    frames = list(stream_sse(iter([ChatToken(text="a"), ChatDone(used_llm=True, elapsed_ms=1)])))

    assert _names(frames) == ["token", "done"]


def test_stream_sse_ends_a_crashed_stream_with_error_and_done() -> None:
    def crashing() -> Iterator[ChatEvent]:
        yield ChatToken(text="partial")
        raise RuntimeError("bug")

    frames = list(stream_sse(crashing()))

    parsed = list(parse_sse_events("".join(frames).splitlines()))
    assert [name for name, _ in parsed] == ["token", "error", "done"]
    assert parsed[1][1] == {"message": UNEXPECTED_ERROR_MESSAGE}


def test_stream_sse_passes_a_domain_error_message_through() -> None:
    def _events():
        raise ConversationNotFoundError("There's no chat with id x.")
        yield  # pragma: no cover

    frames = list(stream_sse(_events()))

    assert "There's no chat with id x." in frames[0]
    assert frames[1].startswith("event: done")


def test_stream_sse_sends_heartbeats_while_the_assistant_is_silent() -> None:
    def slow() -> Iterator[ChatEvent]:
        time.sleep(0.25)
        yield ChatDone(used_llm=True, elapsed_ms=1)

    frames = list(stream_sse(slow(), heartbeat_seconds=0.05))

    assert HEARTBEAT_FRAME in frames
    assert frames[-1].startswith("event: done")


def test_stream_sse_sends_no_heartbeat_when_events_flow() -> None:
    frames = list(stream_sse(iter([ChatToken(text="a"), ChatDone(used_llm=True, elapsed_ms=1)]), heartbeat_seconds=5))

    assert HEARTBEAT_FRAME not in frames


def test_stream_sse_stops_the_assistant_when_the_reader_leaves() -> None:
    closed = threading.Event()

    def endless() -> Iterator[ChatEvent]:
        try:
            while True:
                yield ChatToken(text="a")
        finally:
            closed.set()

    frames = stream_sse(endless())
    next(frames)
    frames.close()

    assert closed.wait(timeout=2)


def test_stream_sse_still_ends_when_closing_the_assistant_fails() -> None:
    class BrokenClose:
        def __iter__(self) -> Iterator[ChatEvent]:
            return iter([ChatDone(used_llm=True, elapsed_ms=1)])

        def close(self) -> None:
            raise RuntimeError("saving the turn failed")

    frames = list(stream_sse(BrokenClose(), heartbeat_seconds=0.05))  # type: ignore[arg-type]

    assert frames[-1].startswith("event: done")
