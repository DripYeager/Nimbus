from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import Mock

import httpx
import pytest
from pytest_mock import MockerFixture

from ui.chat.chat_stream import CONNECT_TIMEOUT_SECONDS, UNREACHABLE_MESSAGE, ChatStream, _message_for

BASE_URL = "http://127.0.0.1:8765"


class FakeThread:
    """Runs the stream's worker inline so its signals fire before the test asserts."""

    def __init__(self, target: Callable[[], None], name: str, daemon: bool) -> None:
        self._target = target

    def start(self) -> None:
        self._target()


class FakeResponse:
    def __init__(self, lines: Iterator[str] | list[str], status_code: int = 200) -> None:
        self._lines = lines
        self.status_code = status_code
        self.closed = False

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400

    def read(self) -> bytes:
        return b""

    def json(self) -> Any:
        raise ValueError("no body")

    def iter_lines(self) -> Iterator[str]:
        yield from self._lines

    def close(self) -> None:
        self.closed = True


def _sse(name: str, data: dict[str, Any]) -> list[str]:
    return [f"event: {name}", f"data: {json.dumps(data)}", ""]


class Recorder:
    def __init__(self, stream: ChatStream) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.failures: list[str] = []
        self.finished = 0
        stream.event_received.connect(lambda name, data: self.events.append((name, data)))
        stream.failed.connect(self.failures.append)
        stream.finished.connect(self._on_finished)

    def _on_finished(self) -> None:
        self.finished += 1


@pytest.fixture
def stream(mocker: MockerFixture) -> ChatStream:
    mocker.patch("ui.chat.chat_stream.threading.Thread", FakeThread)
    return ChatStream()


@pytest.fixture
def recorder(stream: ChatStream) -> Recorder:
    return Recorder(stream)


def _patch_stream(mocker: MockerFixture, response: FakeResponse | None = None, error: Exception | None = None) -> Mock:
    @contextmanager
    def fake_stream(method: str, url: str, json: Any, timeout: httpx.Timeout) -> Iterator[FakeResponse]:
        if error is not None:
            raise error
        yield response

    return mocker.patch("ui.chat.chat_stream.httpx.stream", side_effect=fake_stream)


def test_send_posts_the_message_to_chat(mocker: MockerFixture, stream: ChatStream) -> None:
    http_stream = _patch_stream(mocker, FakeResponse([]))

    stream.send("hello", "c1")

    method, url = http_stream.call_args.args
    assert (method, url) == ("POST", f"{BASE_URL}/chat")
    assert http_stream.call_args.kwargs["json"] == {"text": "hello", "conversation_id": "c1"}


def test_send_uses_the_thinking_timeout_for_reads(mocker: MockerFixture, stream: ChatStream) -> None:
    http_stream = _patch_stream(mocker, FakeResponse([]))

    stream.send("hello", None)

    timeout = http_stream.call_args.kwargs["timeout"]
    assert (timeout.read, timeout.connect) == (120, CONNECT_TIMEOUT_SECONDS)


def test_send_emits_each_event_in_order(mocker: MockerFixture, stream: ChatStream, recorder: Recorder) -> None:
    lines = _sse("started", {"conversation_id": "c1"}) + _sse("token", {"text": "Hi"}) + _sse("done", {})
    _patch_stream(mocker, FakeResponse(lines))

    stream.send("hello", None)

    assert recorder.events == [("started", {"conversation_id": "c1"}), ("token", {"text": "Hi"}), ("done", {})]


def test_send_emits_finished_once_the_stream_ends(
    mocker: MockerFixture, stream: ChatStream, recorder: Recorder
) -> None:
    _patch_stream(mocker, FakeResponse(_sse("done", {})))

    stream.send("hello", None)

    assert (recorder.finished, recorder.failures) == (1, [])


def test_answer_confirmation_posts_the_decision(mocker: MockerFixture, stream: ChatStream) -> None:
    http_stream = _patch_stream(mocker, FakeResponse([]))
    decision = {"call_id": "t1", "approved": True, "always_allow": False}

    stream.answer_confirmation("c1", decision)

    assert http_stream.call_args.args[1] == f"{BASE_URL}/chat/c1/confirm"
    assert http_stream.call_args.kwargs["json"] == decision


def test_send_reports_an_unreachable_engine(mocker: MockerFixture, stream: ChatStream, recorder: Recorder) -> None:
    _patch_stream(mocker, error=httpx.ConnectError("refused"))

    stream.send("hello", None)

    assert recorder.failures == [UNREACHABLE_MESSAGE]
    assert recorder.finished == 1


def test_send_reports_a_slow_model(mocker: MockerFixture, stream: ChatStream, recorder: Recorder) -> None:
    _patch_stream(mocker, error=httpx.ReadTimeout("slow"))

    stream.send("hello", None)

    assert recorder.failures == [_message_for(httpx.ReadTimeout("slow"))]
    assert "stopped responding" in recorder.failures[0]


def test_send_reports_an_http_error_status(mocker: MockerFixture, stream: ChatStream, recorder: Recorder) -> None:
    _patch_stream(mocker, FakeResponse([], status_code=500))

    stream.send("hello", None)

    assert recorder.failures == ["Nimbus's engine returned an error (500)."]


def test_cancel_stops_events_and_suppresses_finished(
    mocker: MockerFixture, stream: ChatStream, recorder: Recorder
) -> None:
    def lines() -> Iterator[str]:
        yield from _sse("token", {"text": "first"})
        stream.cancel()
        yield from _sse("token", {"text": "second"})

    response = FakeResponse(lines())
    _patch_stream(mocker, response)

    stream.send("hello", None)

    assert recorder.events == [("token", {"text": "first"})]
    assert recorder.finished == 0
    assert response.closed


def test_cancel_suppresses_the_failure_of_a_closed_connection(
    mocker: MockerFixture, stream: ChatStream, recorder: Recorder
) -> None:
    def lines() -> Iterator[str]:
        stream.cancel()
        raise httpx.ReadError("connection closed")
        yield ""

    _patch_stream(mocker, FakeResponse(lines()))

    stream.send("hello", None)

    assert (recorder.failures, recorder.finished) == ([], 0)


def test_cancel_is_safe_with_nothing_in_flight(stream: ChatStream) -> None:
    stream.cancel()

    assert stream._current is None


def test_send_cancels_the_previous_request(mocker: MockerFixture, stream: ChatStream) -> None:
    _patch_stream(mocker, FakeResponse([]))
    previous = Mock()
    stream._current = previous

    stream.send("hello", None)

    previous.cancel.assert_called_once()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (httpx.ReadTimeout("slow"), "stopped responding"),
        (httpx.ConnectError("refused"), "Couldn't reach"),
        (OSError("pipe"), "Couldn't reach"),
    ],
)
def test_message_for_explains_the_failure(error: Exception, expected: str) -> None:
    assert expected in _message_for(error)


def test_send_reports_a_malformed_event_instead_of_stopping_silently(
    mocker: MockerFixture, stream: ChatStream, recorder: Recorder
) -> None:
    _patch_stream(mocker, FakeResponse(["event: token", "data: {not json", ""]))

    stream.send("hello", None)

    assert recorder.failures and "couldn't be read" in recorder.failures[0]
    assert recorder.finished == 1


def test_events_from_a_superseded_request_are_dropped(
    mocker: MockerFixture, stream: ChatStream, recorder: Recorder
) -> None:
    _patch_stream(mocker, FakeResponse([]))
    stream._start("/chat", {})
    stale_id = stream._current.request_id
    stream._current = None

    stream._relay_event.emit(stale_id, "token", {"text": "late"})

    assert recorder.events == []
