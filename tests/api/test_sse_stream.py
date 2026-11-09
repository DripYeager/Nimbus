from __future__ import annotations

from collections.abc import Iterator

from api.sse_stream import UNEXPECTED_ERROR_MESSAGE, format_sse, stream_sse
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
