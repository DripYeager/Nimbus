from __future__ import annotations

import httpx
import pytest
from pytest_mock import MockerFixture

from models.schema import SourceRef
from ui.overlay import OverlayWindow
from ui.query_client import UNREACHABLE_MESSAGE, QueryClient, _StreamRequest


@pytest.fixture(autouse=True, scope="session")
def _qapp():
    """QObject/pyqtSignal machinery needs a QApplication instance to exist somewhere."""
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def overlay():
    window = OverlayWindow()
    window.setup()
    yield window
    window.deleteLater()


@pytest.fixture
def client(overlay: OverlayWindow) -> QueryClient:
    query_client = QueryClient(overlay)
    query_client.setup()
    return query_client


def test_setup_wires_query_submitted_to_start(overlay: OverlayWindow, mocker: MockerFixture) -> None:
    # start must be patched before setup() connects the signal — connect() binds to whatever
    # self.start resolves to at connect-time, not a live attribute lookup on every emit.
    query_client = QueryClient(overlay)
    start = mocker.patch.object(query_client, "start")
    query_client.setup()

    overlay.query_submitted.emit("find the invoice")

    start.assert_called_once_with("find the invoice")


def test_setup_wires_dismissed_to_cancel(overlay: OverlayWindow, mocker: MockerFixture) -> None:
    query_client = QueryClient(overlay)
    cancel = mocker.patch.object(query_client, "cancel")
    query_client.setup()

    overlay.dismissed.emit()

    cancel.assert_called_once()


def test_token_received_appends_to_the_overlay(client: QueryClient, overlay: OverlayWindow) -> None:
    overlay.start_thinking()

    client._token_received.emit("hello")

    assert overlay._answer_buffer == "hello"


def test_sources_received_sets_the_overlays_sources(client: QueryClient, overlay: OverlayWindow) -> None:
    sources = [SourceRef(file_name="a.pdf", file_path="C:/a.pdf", score=0.5)]

    client._sources_received.emit(sources)

    assert "a.pdf" in overlay._sources_label.text()


def test_failed_shows_the_error_on_the_overlay(client: QueryClient, overlay: OverlayWindow) -> None:
    overlay.start_thinking()

    client._failed.emit("Ollama is offline")

    assert overlay._status_label.text() == "Ollama is offline"
    assert overlay.is_thinking() is False


def test_start_cancels_any_previous_request_first(client: QueryClient, mocker: MockerFixture) -> None:
    mocker.patch("ui.query_client.threading.Thread")
    first = client._current = mocker.Mock(spec=_StreamRequest)

    client.start("second query")

    first.cancel.assert_called_once()
    assert client._current is not first


def test_cancel_is_safe_when_nothing_is_in_flight(client: QueryClient) -> None:
    client.cancel()

    assert client._current is None


def test_stream_request_cancel_closes_an_open_response(mocker: MockerFixture) -> None:
    client = mocker.Mock(spec=QueryClient)
    request = _StreamRequest("http://127.0.0.1:8765", "hello", client)
    response = mocker.Mock()
    request._response = response

    request.cancel()

    assert request._cancelled is True
    response.close.assert_called_once()


def test_stream_request_dispatches_started_token_and_error_events(mocker: MockerFixture) -> None:
    client = mocker.Mock(spec=QueryClient)
    request = _StreamRequest("http://127.0.0.1:8765", "hello", client)

    request._dispatch("started", {"sources": [{"file_name": "a.pdf", "file_path": "C:/a.pdf", "score": 0.9}]})
    request._dispatch("token", {"text": "chunk"})
    request._dispatch("error", {"message": "boom"})

    client._sources_received.emit.assert_called_once_with([SourceRef(file_name="a.pdf", file_path="C:/a.pdf", score=0.9)])
    client._token_received.emit.assert_called_once_with("chunk")
    client._failed.emit.assert_called_once_with("boom")


def test_run_emits_unreachable_message_on_a_connection_error(mocker: MockerFixture) -> None:
    client = mocker.Mock(spec=QueryClient)
    request = _StreamRequest("http://127.0.0.1:8765", "hello", client)
    mocker.patch("ui.query_client.httpx.stream", side_effect=httpx.ConnectError("refused"))

    request.run()

    client._failed.emit.assert_called_once_with(UNREACHABLE_MESSAGE)


def test_run_suppresses_the_error_when_already_cancelled(mocker: MockerFixture) -> None:
    client = mocker.Mock(spec=QueryClient)
    request = _StreamRequest("http://127.0.0.1:8765", "hello", client)
    request._cancelled = True
    mocker.patch("ui.query_client.httpx.stream", side_effect=httpx.ConnectError("refused"))

    request.run()

    client._failed.emit.assert_not_called()


def test_run_streams_started_and_token_events_end_to_end(mocker: MockerFixture) -> None:
    client = mocker.Mock(spec=QueryClient)
    request = _StreamRequest("http://127.0.0.1:8765", "hello", client)
    fake_lines = [
        "event: started",
        'data: {"intent": "general_qa", "sources": []}',
        "",
        "event: token",
        'data: {"text": "hi"}',
        "",
        "event: done",
        'data: {"used_llm": true, "elapsed_ms": 12}',
    ]
    fake_response = mocker.Mock()
    fake_response.iter_lines.return_value = iter(fake_lines)
    mocker.patch("ui.query_client.httpx.stream").return_value.__enter__.return_value = fake_response

    request.run()

    client._sources_received.emit.assert_called_once_with([])
    client._token_received.emit.assert_called_once_with("hi")
