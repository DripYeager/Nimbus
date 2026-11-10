from __future__ import annotations

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from core.attachment_format import with_attachment
from models.chat import ChatMessage
from ui.chat.chat_view import ChatView
from ui.chat.empty_state import SUGGESTIONS, EmptyState
from ui.chat.message_cards import ConfirmCard
from ui.chat.message_widgets import AssistantMessage, UserBubble


@pytest.fixture
def view() -> ChatView:
    return ChatView()


def _flush_deletes() -> None:
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def _messages(view: ChatView) -> list[str]:
    """The conversation's widgets in display order, by type name."""
    layout = view.column._layout
    widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
    return [type(w).__name__ for w in widgets if w is not None]


def test_chat_view_starts_on_the_welcome_page(view: ChatView) -> None:
    assert isinstance(view.currentWidget(), EmptyState)


def test_chat_view_forwards_suggestion_clicks(view: ChatView) -> None:
    clicked: list[str] = []
    view.suggestion_clicked.connect(clicked.append)
    text = SUGGESTIONS[0][1]
    card = next(b for b in view.widget(0).findChildren(QPushButton) if b.text() == text)

    card.click()

    assert clicked == [text]


def test_add_user_message_switches_to_the_conversation(view: ChatView) -> None:
    view.add_user_message("hello")

    assert (view.currentIndex(), _messages(view)) == (1, ["UserBubble"])


def test_current_reply_is_created_once_and_reused(view: ChatView) -> None:
    first = view.current_reply

    assert view.current_reply is first
    assert _messages(view) == ["AssistantMessage"]


def test_begin_reply_shows_the_thinking_state(view: ChatView) -> None:
    view.begin_reply()

    assert not view.current_reply._thinking.isHidden()


def test_end_reply_removes_a_reply_that_stayed_empty(view: ChatView) -> None:
    view.add_user_message("hello")
    view.begin_reply()

    view.end_reply()
    _flush_deletes()

    assert (_messages(view), view.column.findChildren(AssistantMessage)) == (["UserBubble"], [])


def test_end_reply_keeps_a_reply_with_text(view: ChatView) -> None:
    view.begin_reply()
    view.current_reply.append_text("Hi there")

    view.end_reply()

    assert _messages(view) == ["AssistantMessage"]


def test_end_reply_keeps_a_reply_with_only_a_tool_step(view: ChatView) -> None:
    view.begin_reply()
    view.current_reply.show_tool("t1", "Opened Notepad", "done")

    view.end_reply()

    assert _messages(view) == ["AssistantMessage"]


def test_end_reply_keeps_a_reply_with_only_an_error(view: ChatView) -> None:
    view.begin_reply()
    view.current_reply.show_error("Model offline")

    view.end_reply()

    assert _messages(view) == ["AssistantMessage"]


def test_end_reply_stops_the_thinking_state(view: ChatView) -> None:
    view.begin_reply()
    reply = view.current_reply
    reply.append_text("Hi")
    reply.start_thinking()

    view.end_reply()

    assert reply._thinking.isHidden()


def test_end_reply_starts_a_new_reply_next_time(view: ChatView) -> None:
    first = view.current_reply
    first.append_text("Hi")

    view.end_reply()

    assert view.current_reply is not first


def test_end_reply_without_a_reply_does_nothing(view: ChatView) -> None:
    view.end_reply()

    assert (_messages(view), view.currentIndex()) == ([], 0)


def test_add_user_message_closes_the_previous_reply(view: ChatView) -> None:
    first = view.current_reply
    first.append_text("Answer")

    view.add_user_message("next question")

    assert view.current_reply is not first
    assert _messages(view) == ["AssistantMessage", "UserBubble", "AssistantMessage"]


def test_add_confirmation_appends_a_card(view: ChatView) -> None:
    card = view.add_confirmation("Open Notepad")

    assert isinstance(card, ConfirmCard)
    assert _messages(view) == ["ConfirmCard"]


def test_add_confirmation_closes_the_current_reply(view: ChatView) -> None:
    first = view.current_reply
    first.show_tool("t1", "Looking for Notepad", "done")

    view.add_confirmation("Open Notepad")

    assert view.current_reply is not first


def test_add_confirmation_drops_an_empty_thinking_reply(view: ChatView) -> None:
    view.begin_reply()

    view.add_confirmation("Open Notepad")
    _flush_deletes()

    assert _messages(view) == ["ConfirmCard"]


def test_clear_returns_to_the_welcome_page_and_empties_the_chat(view: ChatView) -> None:
    view.add_user_message("hello")
    view.current_reply.append_text("hi")

    view.clear()
    _flush_deletes()

    assert (view.currentIndex(), _messages(view), view.column.findChildren(UserBubble)) == (0, [], [])


def test_load_history_renders_user_and_assistant_turns(view: ChatView) -> None:
    view.add_user_message("old chat")
    messages = [
        ChatMessage(role="user", content="Find my resume"),
        ChatMessage(role="assistant", content="Here it is."),
        ChatMessage(role="user", content="Thanks"),
    ]

    view.load_history(messages)

    assert _messages(view) == ["UserBubble", "AssistantMessage", "UserBubble"]


def test_load_history_skips_blank_assistant_turns(view: ChatView) -> None:
    view.load_history([ChatMessage(role="user", content="Open Notepad"), ChatMessage(role="assistant", content=" ")])

    assert _messages(view) == ["UserBubble"]


def test_load_history_shows_the_assistant_text(view: ChatView) -> None:
    view.load_history([ChatMessage(role="assistant", content="**Done**")])

    assert view.column.findChild(AssistantMessage)._markdown == "**Done**"


def test_stick_to_bottom_scrolls_to_the_newest_content(view: ChatView) -> None:
    bar = view._scroll.verticalScrollBar()
    bar.setRange(0, 500)

    view._stick_to_bottom(0, 500)
    QApplication.processEvents()

    assert bar.value() == 500


def test_detach_hands_back_the_running_column_and_shows_a_fresh_one(view: ChatView) -> None:
    view.add_user_message("hi")
    running = view.column

    detached = view.detach()

    assert (detached is running, view.column is running, view.currentIndex()) == (True, False, 0)


def test_detached_column_still_takes_new_messages(view: ChatView) -> None:
    view.add_user_message("hi")
    detached = view.detach()

    detached.current_reply.append_text("Still streaming")

    assert (detached.current_reply.has_text(), view.currentIndex()) == (True, 0)


def test_attach_puts_a_detached_column_back(view: ChatView) -> None:
    view.add_user_message("hi")
    detached = view.detach()

    view.attach(detached)

    assert (view.column is detached, view.currentIndex()) == (True, 1)


def test_load_history_shows_a_tag_instead_of_attached_text(view: ChatView) -> None:
    content = with_attachment("Summarize it", "report.pdf", "pages and pages of text")

    view.load_history([ChatMessage(role="user", content=content)])

    labels = [label.text() for label in view.column.findChildren(QLabel)]
    assert "Summarize it" in labels
    assert any(text.endswith("report.pdf") for text in labels)
    assert not any("pages and pages" in text for text in labels)
