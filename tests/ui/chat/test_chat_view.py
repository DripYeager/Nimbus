from __future__ import annotations

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication, QPushButton

from models.chat import ChatMessage
from ui.chat.chat_view import SUGGESTIONS, ChatView
from ui.chat.message_widgets import AssistantMessage, ConfirmCard, UserBubble


@pytest.fixture
def view() -> ChatView:
    return ChatView()


def _flush_deletes() -> None:
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def _messages(view: ChatView) -> list[str]:
    """The conversation's widgets in display order, by type name."""
    layout = view._layout
    widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
    return [type(w).__name__ for w in widgets if w is not None]


def test_chat_view_starts_on_the_welcome_page(view: ChatView) -> None:
    assert view.currentIndex() == 0


def test_chat_view_forwards_suggestion_clicks(view: ChatView) -> None:
    clicked: list[str] = []
    view.suggestion_clicked.connect(clicked.append)
    chip = next(b for b in view.widget(0).findChildren(QPushButton) if b.text() == SUGGESTIONS[0])

    chip.click()

    assert clicked == [SUGGESTIONS[0]]


def test_add_user_message_switches_to_the_conversation(view: ChatView) -> None:
    view.add_user_message("hello")

    assert view.currentIndex() == 1
    assert _messages(view) == ["UserBubble"]


def test_current_reply_is_created_once_and_reused(view: ChatView) -> None:
    first = view.current_reply

    assert view.current_reply is first
    assert _messages(view) == ["AssistantMessage"]


def test_end_reply_starts_a_new_reply_next_time(view: ChatView) -> None:
    first = view.current_reply

    view.end_reply()

    assert view.current_reply is not first


def test_add_user_message_closes_the_previous_reply(view: ChatView) -> None:
    first = view.current_reply

    view.add_user_message("next question")

    assert view.current_reply is not first
    assert _messages(view) == ["AssistantMessage", "UserBubble", "AssistantMessage"]


def test_add_confirmation_appends_a_card(view: ChatView) -> None:
    card = view.add_confirmation("Open Notepad")

    assert isinstance(card, ConfirmCard)
    assert _messages(view) == ["ConfirmCard"]


def test_clear_returns_to_the_welcome_page_and_empties_the_chat(view: ChatView) -> None:
    view.add_user_message("hello")
    view.current_reply.append_text("hi")

    view.clear()
    _flush_deletes()

    assert view.currentIndex() == 0
    assert _messages(view) == []
    assert view._content.findChildren(UserBubble) == []


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

    reply = view._content.findChild(AssistantMessage)
    assert reply._markdown == "**Done**"


def test_stick_to_bottom_scrolls_to_the_newest_content(view: ChatView) -> None:
    bar = view._scroll.verticalScrollBar()
    bar.setRange(0, 500)

    view._stick_to_bottom(0, 500)
    QApplication.processEvents()

    assert bar.value() == 500
