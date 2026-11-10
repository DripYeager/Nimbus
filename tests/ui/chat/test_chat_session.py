from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QLabel
from pytest_mock import MockerFixture

from core.exceptions import NimbusError
from models.chat import ChatMessage
from models.schema import IndexStatus
from ui.api_client import ApiClient
from ui.chat.chat_input import ChatInput
from ui.chat.chat_session import STILL_LEARNING_ID, ChatSession
from ui.chat.chat_stream import ChatStream
from ui.chat.chat_view import ChatView
from ui.chat.message_cards import ConfirmCard, SourceCard
from ui.chat.message_widgets import AssistantMessage


def _synchronous(fn: Any, ok: Any, err: Any = None) -> None:
    try:
        result = fn()
    except NimbusError as e:
        if err is not None:
            err(str(e))
        return
    ok(result)


def _started(conversation_id: str = "c1", is_cloud: bool = False, **status: Any) -> dict[str, Any]:
    return {"conversation_id": conversation_id, "index_status": status, "is_cloud": is_cloud}


@pytest.fixture
def view() -> ChatView:
    return ChatView()


@pytest.fixture
def chat_input() -> ChatInput:
    return ChatInput()


@pytest.fixture
def stream(mocker: MockerFixture) -> Mock:
    return mocker.Mock(spec=ChatStream)


@pytest.fixture
def api(mocker: MockerFixture) -> Mock:
    return mocker.Mock(spec=ApiClient)


@pytest.fixture
def session(mocker: MockerFixture, view: ChatView, chat_input: ChatInput, api: Mock, stream: Mock) -> ChatSession:
    mocker.patch("ui.chat.chat_session.run_in_background", side_effect=_synchronous)
    return ChatSession(view, chat_input, api, stream)


def _is_busy(chat_input: ChatInput) -> bool:
    return not chat_input._send.isEnabled()


def _errors(view: ChatView) -> list[str]:
    return [label.text() for label in view.findChildren(QLabel) if label.objectName() == "ErrorLine"]


def test_send_shows_the_message_and_streams_the_reply(
    session: ChatSession, view: ChatView, stream: Mock, chat_input: ChatInput
) -> None:
    session.send("Find my resume")

    stream.send.assert_called_once_with("Find my resume", None)
    assert (view.currentIndex(), _is_busy(chat_input)) == (1, True)


def test_send_shows_the_reply_thinking_straight_away(session: ChatSession, view: ChatView) -> None:
    session.send("Find my resume")

    assert not view.current_reply._thinking.isHidden()


def test_send_continues_the_started_conversation(session: ChatSession, stream: Mock) -> None:
    session._handle_event("started", _started("c42"))

    session.send("And another thing")

    stream.send.assert_called_once_with("And another thing", "c42")


def test_connect_signals_sends_on_input_submit(session: ChatSession, chat_input: ChatInput, stream: Mock) -> None:
    session.connect_signals()

    chat_input.submitted.emit("hello")

    stream.send.assert_called_once_with("hello", None)


def test_connect_signals_sends_on_suggestion_click(session: ChatSession, view: ChatView, stream: Mock) -> None:
    session.connect_signals()

    view.suggestion_clicked.emit("Open Notepad")

    stream.send.assert_called_once_with("Open Notepad", None)


def test_handle_event_started_reports_status_for_the_header(session: ChatSession) -> None:
    received: list[tuple[IndexStatus, bool]] = []
    session.status_received.connect(lambda status, is_cloud: received.append((status, is_cloud)))

    session._handle_event("started", _started(is_cloud=True, cataloged_files=9))

    [(status, is_cloud)] = received
    assert (status.cataloged_files, is_cloud) == (9, True)


def test_handle_event_started_flags_an_unfinished_index(session: ChatSession, view: ChatView) -> None:
    session._handle_event("started", _started(content_files=4, indexed_files=1, pending_files=3))

    step = view.current_reply._steps[STILL_LEARNING_ID]
    assert "Still learning your files (25%)" in step._text.text()


def test_handle_event_started_adds_no_step_when_indexing_is_done(session: ChatSession, view: ChatView) -> None:
    session._handle_event("started", _started(content_files=4, indexed_files=4))

    assert view._current is None


def test_handle_event_token_streams_into_the_reply(session: ChatSession, view: ChatView) -> None:
    session._handle_event("token", {"text": "Hello "})
    session._handle_event("token", {"text": "there"})

    assert view.current_reply._markdown == "Hello there"


def test_handle_event_tool_shows_and_updates_one_step(session: ChatSession, view: ChatView) -> None:
    session._handle_event("tool", {"call_id": "t1", "label": "Searching files", "status": "running"})
    session._handle_event("tool", {"call_id": "t1", "label": "Searching files", "status": "done"})

    steps = view.current_reply._steps
    assert (len(steps), steps["t1"]._text.property("status")) == (1, "done")


def test_handle_event_sources_adds_source_cards(session: ChatSession, view: ChatView) -> None:
    sources = [{"file_name": "cv.pdf", "file_path": "C:/Docs/cv.pdf", "score": 0.9}]

    session._handle_event("sources", {"sources": sources})

    cards = view.current_reply.findChildren(SourceCard)
    assert [c.toolTip() for c in cards] == ["Open C:/Docs/cv.pdf"]


def test_handle_event_error_shows_the_message(session: ChatSession, view: ChatView) -> None:
    session._handle_event("error", {"message": "Model offline"})

    assert _errors(view) == ["Model offline"]


def test_handle_event_ignores_unknown_events(session: ChatSession, view: ChatView) -> None:
    session._handle_event("done", {"used_llm": True, "elapsed_ms": 10})

    assert view._current is None


def _confirm(session: ChatSession, view: ChatView) -> ConfirmCard:
    session._handle_event("started", _started("c7"))
    session._handle_event("confirm", {"call_id": "t9", "tool": "open_app", "description": "Open Notepad"})
    return view.findChild(ConfirmCard)


def test_handle_event_confirm_shows_a_card_and_closes_the_reply(session: ChatSession, view: ChatView) -> None:
    card = _confirm(session, view)

    assert card is not None
    assert view._current is None


def test_handle_event_confirm_leaves_no_empty_reply_behind(session: ChatSession, view: ChatView) -> None:
    _confirm(session, view)

    assert view._content.findChildren(AssistantMessage) == []


@pytest.mark.parametrize(("approved", "always"), [(True, False), (True, True), (False, False)])
def test_confirmation_answer_resumes_the_turn(
    session: ChatSession, view: ChatView, stream: Mock, approved: bool, always: bool
) -> None:
    card = _confirm(session, view)

    card.decided.emit(approved, always)

    stream.answer_confirmation.assert_called_once_with(
        "c7", {"call_id": "t9", "approved": approved, "always_allow": always}
    )


def test_confirmation_answer_shows_a_thinking_reply(session: ChatSession, view: ChatView) -> None:
    card = _confirm(session, view)

    card.decided.emit(True, False)

    assert not view.current_reply._thinking.isHidden()


def test_confirmation_answer_locks_the_input(session: ChatSession, view: ChatView, chat_input: ChatInput) -> None:
    card = _confirm(session, view)
    session._finish()

    card.decided.emit(True, False)

    assert _is_busy(chat_input)


def test_finish_unlocks_the_input_and_closes_the_reply(
    session: ChatSession, view: ChatView, chat_input: ChatInput
) -> None:
    session.send("hi")
    session._handle_event("token", {"text": "Hello"})

    session._finish()

    assert (_is_busy(chat_input), view._current) == (False, None)


def test_finish_drops_a_reply_that_never_got_content(session: ChatSession, view: ChatView) -> None:
    session.send("hi")

    session._finish()

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)

    assert view._content.findChildren(AssistantMessage) == []


def test_fail_keeps_the_error_on_a_reply_with_no_text(
    session: ChatSession, view: ChatView, chat_input: ChatInput
) -> None:
    session.send("hi")
    reply = view.current_reply

    session._fail("Couldn't reach Nimbus's engine.")

    assert view._layout.indexOf(reply) >= 0
    assert [label.text() for label in reply.findChildren(QLabel) if label.objectName() == "ErrorLine"] == [
        "Couldn't reach Nimbus's engine."
    ]


def test_fail_unlocks_the_input(session: ChatSession, chat_input: ChatInput) -> None:
    session.send("hi")

    session._fail("Couldn't reach Nimbus's engine.")

    assert not _is_busy(chat_input)


def test_new_chat_cancels_and_resets(session: ChatSession, view: ChatView, stream: Mock) -> None:
    session.send("hi")
    session._handle_event("started", _started("c1"))

    session.new_chat()

    stream.cancel.assert_called_once()
    assert view.currentIndex() == 0
    session.send("fresh")
    stream.send.assert_called_with("fresh", None)


def test_open_conversation_loads_and_continues_it(
    session: ChatSession, view: ChatView, api: Mock, stream: Mock
) -> None:
    api.conversation.return_value = [ChatMessage(role="user", content="hi")]

    session.open_conversation("c5")
    session.send("more")

    api.conversation.assert_called_once_with("c5")
    stream.send.assert_called_once_with("more", "c5")


def test_open_conversation_shows_a_load_error(session: ChatSession, view: ChatView, api: Mock) -> None:
    api.conversation.side_effect = NimbusError("Chat not found")

    session.open_conversation("missing")

    assert _errors(view) == ["Chat not found"]


def test_cancel_stops_the_stream_and_unlocks_the_input(
    session: ChatSession, stream: Mock, chat_input: ChatInput
) -> None:
    session.send("hi")

    session.cancel()

    stream.cancel.assert_called_once()
    assert not _is_busy(chat_input)
