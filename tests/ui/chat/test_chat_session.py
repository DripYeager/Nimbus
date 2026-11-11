from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QLabel
from pytest_mock import MockerFixture

from core.exceptions import NimbusError
from models.chat import Attachment, ConfirmationNeeded, ConversationView, HistoryTurn
from models.schema import IndexStatus
from ui.api_client import ApiClient
from ui.chat.chat_input import ELSEWHERE_PLACEHOLDER, ChatInput
from ui.chat.chat_session import BUSY_HERE_MESSAGE, STILL_LEARNING_ID, ChatSession
from ui.chat.chat_stream import ChatStream
from ui.chat.chat_view import ChatView
from ui.chat.message_cards import ConfirmCard, SourceCard
from ui.chat.message_widgets import STOPPED_TEXT, AssistantMessage
from ui.chat.user_bubble import UserBubble
from ui.theme.tokens import PLACEHOLDER_TEXT


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
    return chat_input.is_busy()


def _errors(view: ChatView) -> list[str]:
    return [label.text() for label in view.findChildren(QLabel) if label.objectName() == "ErrorLine"]


def test_send_shows_the_message_and_streams_the_reply(
    session: ChatSession, view: ChatView, stream: Mock, chat_input: ChatInput
) -> None:
    session.send("Find my resume")

    stream.send.assert_called_once_with("Find my resume", None, None)
    assert (view.currentIndex(), _is_busy(chat_input)) == (1, True)


def test_send_shows_the_reply_thinking_straight_away(session: ChatSession, view: ChatView) -> None:
    session.send("Find my resume")

    assert not view.current_reply._thinking.isHidden()


def test_send_continues_the_started_conversation(session: ChatSession, stream: Mock) -> None:
    session.send("q")
    session._handle_event("started", _started("c42"))
    session._finish()

    session.send("And another thing")

    stream.send.assert_called_with("And another thing", "c42", None)


def test_connect_signals_sends_on_input_submit(session: ChatSession, chat_input: ChatInput, stream: Mock) -> None:
    session.connect_signals()

    chat_input.submitted.emit("hello")

    stream.send.assert_called_once_with("hello", None, None)


def test_connect_signals_sends_on_suggestion_click(session: ChatSession, view: ChatView, stream: Mock) -> None:
    session.connect_signals()

    view.suggestion_clicked.emit("Open Notepad")

    stream.send.assert_called_once_with("Open Notepad", None, None)


def test_handle_event_started_reports_status_for_the_header(session: ChatSession) -> None:
    received: list[tuple[IndexStatus, bool]] = []
    session.status_received.connect(lambda status, is_cloud: received.append((status, is_cloud)))
    session.send("q")

    session._handle_event("started", _started(is_cloud=True, cataloged_files=9))

    [(status, is_cloud)] = received
    assert (status.cataloged_files, is_cloud) == (9, True)


def test_handle_event_started_flags_an_unfinished_index(session: ChatSession, view: ChatView) -> None:
    session.send("q")
    session._handle_event("started", _started(content_files=4, indexed_files=1, pending_files=3))

    step = view.current_reply._steps[STILL_LEARNING_ID]
    assert "Still learning your files (25%)" in step._text.text()


def test_handle_event_started_adds_no_step_when_indexing_is_done(session: ChatSession, view: ChatView) -> None:
    session.send("q")
    session._handle_event("started", _started(content_files=4, indexed_files=4))

    assert STILL_LEARNING_ID not in view.current_reply._steps


def test_handle_event_token_streams_into_the_reply(session: ChatSession, view: ChatView) -> None:
    session.send("q")
    session._handle_event("token", {"text": "Hello "})
    session._handle_event("token", {"text": "there"})

    assert view.current_reply._markdown == "Hello there"


def test_handle_event_tool_shows_and_updates_one_step(session: ChatSession, view: ChatView) -> None:
    session.send("q")
    session._handle_event("tool", {"call_id": "t1", "label": "Searching files", "status": "running"})
    session._handle_event("tool", {"call_id": "t1", "label": "Searching files", "status": "done"})

    steps = view.current_reply._steps
    assert (len(steps), steps["t1"]._text.property("status")) == (1, "done")


def test_handle_event_sources_adds_source_cards(session: ChatSession, view: ChatView) -> None:
    sources = [{"file_name": "cv.pdf", "file_path": "C:/Docs/cv.pdf", "score": 0.9}]
    session.send("q")

    session._handle_event("sources", {"sources": sources})

    cards = view.current_reply.findChildren(SourceCard)
    assert [c.toolTip() for c in cards] == ["Open C:/Docs/cv.pdf"]


def test_handle_event_error_shows_the_message(session: ChatSession, view: ChatView) -> None:
    session.send("q")
    session._handle_event("error", {"message": "Model offline"})

    assert _errors(view) == ["Model offline"]


def test_handle_event_ignores_unknown_events(session: ChatSession, view: ChatView) -> None:
    session.send("q")
    session._handle_event("done", {"used_llm": True, "elapsed_ms": 10})

    assert view.current_reply.is_empty()


def _confirm(session: ChatSession, view: ChatView) -> ConfirmCard:
    session._handle_event("started", _started("c7"))
    session._handle_event("confirm", {"call_id": "t9", "tool": "open_app", "description": "Open Notepad"})
    # The turn pauses: the engine ends the stream, then the user answers.
    session._finish()
    return view.findChild(ConfirmCard)


def test_handle_event_confirm_shows_a_card_and_closes_the_reply(session: ChatSession, view: ChatView) -> None:
    session.send("q")
    card = _confirm(session, view)

    assert card is not None
    assert view.column._current is None


def test_handle_event_confirm_leaves_no_empty_reply_behind(session: ChatSession, view: ChatView) -> None:
    _confirm(session, view)

    assert view.column.findChildren(AssistantMessage) == []


@pytest.mark.parametrize(("approved", "always"), [(True, False), (True, True), (False, False)])
def test_confirmation_answer_resumes_the_turn(
    session: ChatSession, view: ChatView, stream: Mock, approved: bool, always: bool
) -> None:
    session.send("q")
    card = _confirm(session, view)

    card.decided.emit(approved, always)

    stream.answer_confirmation.assert_called_once_with(
        "c7", {"call_id": "t9", "approved": approved, "always_allow": always}
    )


def test_confirmation_answer_shows_a_thinking_reply(session: ChatSession, view: ChatView) -> None:
    session.send("q")
    card = _confirm(session, view)

    card.decided.emit(True, False)

    assert not view.current_reply._thinking.isHidden()


def test_confirmation_answer_locks_the_input(session: ChatSession, view: ChatView, chat_input: ChatInput) -> None:
    session.send("q")
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

    assert (_is_busy(chat_input), view.column._current) == (False, None)


def test_finish_drops_a_reply_that_never_got_content(session: ChatSession, view: ChatView) -> None:
    session.send("hi")

    session._finish()

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)

    assert view.column.findChildren(AssistantMessage) == []


def test_fail_keeps_the_error_on_a_reply_with_no_text(
    session: ChatSession, view: ChatView, chat_input: ChatInput
) -> None:
    session.send("hi")
    reply = view.current_reply

    session._fail("Couldn't reach Nimbus's engine.")

    assert view.column._layout.indexOf(reply) >= 0
    assert [label.text() for label in reply.findChildren(QLabel) if label.objectName() == "ErrorLine"] == [
        "Couldn't reach Nimbus's engine."
    ]


def test_fail_unlocks_the_input(session: ChatSession, chat_input: ChatInput) -> None:
    session.send("hi")

    session._fail("Couldn't reach Nimbus's engine.")

    assert not _is_busy(chat_input)


def test_new_chat_resets_the_screen_but_keeps_the_reply_running(
    session: ChatSession, view: ChatView, stream: Mock, chat_input: ChatInput
) -> None:
    session.send("hi")
    session._handle_event("started", _started("c1"))

    session.new_chat()

    stream.cancel.assert_not_called()
    assert (view.currentIndex(), _is_busy(chat_input)) == (0, True)


def test_new_chat_blocks_sending_until_the_running_reply_finishes(session: ChatSession, stream: Mock) -> None:
    session.send("hi")
    session._handle_event("started", _started("c1"))
    session.new_chat()

    session.send("fresh")

    stream.send.assert_called_once_with("hi", None, None)


def test_new_chat_after_the_reply_finishes_starts_a_fresh_conversation(session: ChatSession, stream: Mock) -> None:
    session.send("hi")
    session._handle_event("started", _started("c1"))
    session.new_chat()
    session._finish()

    session.send("fresh")

    stream.send.assert_called_with("fresh", None, None)


def test_set_aside_reply_keeps_streaming_and_comes_back(session: ChatSession, view: ChatView, api: Mock) -> None:
    session.send("hi")
    session._handle_event("started", _started("c1"))
    running = view.column
    session.new_chat()

    session._handle_event("token", {"text": "Still going"})
    session.open_conversation("c1")

    assert (view.column is running, running.current_reply._markdown) == (True, "Still going")
    api.conversation_view.assert_not_called()


def test_finished_set_aside_reply_reloads_from_history(session: ChatSession, view: ChatView, api: Mock) -> None:
    api.conversation_view.return_value = ConversationView(turns=[])
    session.send("hi")
    session._handle_event("started", _started("c1"))
    session.new_chat()
    session._finish()

    session.open_conversation("c1")

    api.conversation_view.assert_called_once_with("c1")


def test_open_conversation_loads_and_continues_it(
    session: ChatSession, view: ChatView, api: Mock, stream: Mock
) -> None:
    api.conversation_view.return_value = ConversationView(turns=[HistoryTurn(role="user", text="hi")])

    session.open_conversation("c5")
    session.send("more")

    api.conversation_view.assert_called_once_with("c5")
    stream.send.assert_called_once_with("more", "c5", None)


def test_a_late_history_load_does_not_replace_the_chat_opened_after_it(
    session: ChatSession, mocker: MockerFixture, view: ChatView
) -> None:
    pending: list[Any] = []
    mocker.patch("ui.chat.chat_session.run_in_background", side_effect=lambda _fn, ok, _err=None: pending.append(ok))

    session.open_conversation("old")
    session.open_conversation("new")
    pending[1](ConversationView(turns=[HistoryTurn(role="user", text="the new one")]))
    pending[0](ConversationView(turns=[HistoryTurn(role="user", text="the old one")]))

    shown = [label.text() for label in view.findChildren(QLabel) if label.objectName() == "UserText"]
    assert (session._conversation_id, shown) == ("new", ["the new one"])


def test_a_message_sent_while_history_loads_joins_that_chat(
    session: ChatSession, mocker: MockerFixture, stream: Mock
) -> None:
    mocker.patch("ui.chat.chat_session.run_in_background", lambda *_args, **_kwargs: None)

    session.open_conversation("c5")
    session.send("more")

    stream.send.assert_called_once_with("more", "c5", None)


def test_open_conversation_shows_a_load_error(session: ChatSession, view: ChatView, api: Mock) -> None:
    api.conversation_view.side_effect = NimbusError("Chat not found")

    session.open_conversation("missing")

    assert _errors(view) == ["Chat not found"]


def test_stop_cancels_the_stream_and_unlocks_the_input(
    session: ChatSession, stream: Mock, chat_input: ChatInput
) -> None:
    session.send("hi")

    session.stop()

    stream.cancel.assert_called_once()
    assert not _is_busy(chat_input)


def test_stop_keeps_the_partial_answer_and_notes_it(session: ChatSession, view: ChatView) -> None:
    session.send("hi")
    session._handle_event("token", {"text": "Half an ans"})
    reply = view.current_reply

    session.stop()

    stopped = [label.text() for label in reply.findChildren(QLabel) if label.objectName() == "StoppedLine"]
    assert (reply.has_text(), stopped) == (True, [STOPPED_TEXT])


def test_stop_does_nothing_when_no_reply_is_running(session: ChatSession, stream: Mock) -> None:
    session.stop()

    stream.cancel.assert_not_called()


def test_stop_button_in_the_input_stops_the_reply(session: ChatSession, stream: Mock, chat_input: ChatInput) -> None:
    session.connect_signals()
    session.send("hi")

    chat_input.stop_requested.emit()

    stream.cancel.assert_called_once()


def test_new_chat_while_running_explains_why_sending_is_blocked(session: ChatSession, chat_input: ChatInput) -> None:
    session.send("hi")

    session.new_chat()

    assert chat_input._field.placeholderText() == ELSEWHERE_PLACEHOLDER


def test_finish_restores_the_normal_placeholder(session: ChatSession, chat_input: ChatInput) -> None:
    session.send("hi")
    session.new_chat()

    session._finish()

    assert chat_input._field.placeholderText() == PLACEHOLDER_TEXT


def test_sending_a_new_message_skips_an_open_card(session: ChatSession, view: ChatView, stream: Mock) -> None:
    session.send("q")
    card = _confirm(session, view)
    session.send("another")

    card.decided.emit(True, False)

    stream.answer_confirmation.assert_not_called()
    assert card.is_skipped() and not card.is_open()


def test_confirmation_answer_waits_while_this_chat_is_answering(
    session: ChatSession, view: ChatView, stream: Mock
) -> None:
    session.send("q")
    card = _confirm(session, view)
    session._start_running("c7")

    card.decided.emit(True, False)

    stream.answer_confirmation.assert_not_called()
    assert card.is_open()
    assert view.column.findChild(QLabel, "ErrorLine").text() == BUSY_HERE_MESSAGE


def test_switching_away_keeps_a_chat_whose_card_waits(session: ChatSession, view: ChatView, api: Mock) -> None:
    session.send("q")
    card = _confirm(session, view)
    session._conversation_id = "c7"

    session.new_chat()
    session.open_conversation("c7")

    assert view.findChild(ConfirmCard) is card and card.is_open()
    api.conversation_view.assert_not_called()


def test_reopening_a_chat_shows_the_card_it_still_waits_on(
    session: ChatSession, view: ChatView, api: Mock, stream: Mock
) -> None:
    pending = ConfirmationNeeded(call_id="t1", tool="run_command", description="Run a PowerShell command")
    api.conversation_view.return_value = ConversationView(turns=[HistoryTurn(role="user", text="q")], pending=pending)

    session.open_conversation("c9")
    view.findChild(ConfirmCard).decided.emit(True, False)

    stream.answer_confirmation.assert_called_once_with("c9", {"call_id": "t1", "approved": True, "always_allow": False})


def test_send_takes_the_attachment_along_once(session: ChatSession, stream: Mock) -> None:
    attachment = Attachment(name="Copied text", text="Bonjour tout le monde")
    session.attach(attachment)

    session.send("Translate this")
    session._finish()
    session.send("Thanks")

    assert [c.args[2] for c in stream.send.call_args_list] == [attachment, None]


def test_send_tells_the_bar_the_attachment_was_used(session: ChatSession) -> None:
    changes: list[object] = []
    session.attachment_changed.connect(changes.append)
    session.attach(Attachment(name="Copied text", text="Bonjour"))

    session.send("Translate this")

    assert changes[-1] is None


def test_a_failed_history_load_does_not_keep_sending_into_that_chat(
    session: ChatSession, api: Mock, stream: Mock
) -> None:
    api.conversation_view.side_effect = NimbusError("Chat not found")
    session.open_conversation("gone")

    session.send("hello")

    stream.send.assert_called_once_with("hello", None, None)


def test_opening_the_running_chat_while_it_is_on_screen_keeps_the_live_reply(
    session: ChatSession, view: ChatView, api: Mock
) -> None:
    session.send("hi")
    session._handle_event("started", _started("c1"))
    live = view.column

    session.open_conversation("c1")

    assert view.column is live
    api.conversation_view.assert_not_called()


def test_history_that_loads_after_a_message_was_sent_goes_above_it(
    session: ChatSession, mocker: MockerFixture, view: ChatView
) -> None:
    pending: list[Any] = []
    mocker.patch("ui.chat.chat_session.run_in_background", side_effect=lambda _fn, ok, _err=None: pending.append(ok))
    session.open_conversation("c5")
    session.send("newer question")

    pending[0](ConversationView(turns=[HistoryTurn(role="user", text="older question")]))

    layout = view.column._layout
    widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
    texts = [w.findChild(QLabel, "UserText").text() for w in widgets if isinstance(w, UserBubble)]
    assert texts == ["older question", "newer question"]
