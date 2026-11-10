from __future__ import annotations

from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QAbstractAnimation, QUrl
from PyQt6.QtGui import QIcon, QImage
from PyQt6.QtWidgets import QLabel
from pytest_mock import MockerFixture

from models.schema import SourceRef
from ui.chat.message_cards import SourceCard, ToolStep
from ui.chat.message_widgets import (
    COPIED_FEEDBACK_MS,
    COPY_ICON_SIZE,
    MAX_SOURCE_CARDS,
    USER_BUBBLE_MAX_WIDTH,
    AnswerText,
    AssistantMessage,
    UserBubble,
    _copy_icon,
    _text_width,
)
from ui.theme.energy import ORB_REST_GLOW
from ui.theme.line_icons import line_icon
from ui.theme.tokens import SUCCESS


@pytest.fixture
def open_url(mocker: MockerFixture) -> Mock:
    """Clicking a link must never open a real browser in tests."""
    return mocker.patch("ui.chat.message_widgets.QDesktopServices.openUrl")


@pytest.fixture
def clipboard(mocker: MockerFixture) -> Mock:
    """Keeps tests off the real clipboard."""
    fake = mocker.Mock()
    mocker.patch("ui.chat.message_widgets.QGuiApplication.clipboard", return_value=fake)
    return fake


@pytest.fixture
def reply() -> AssistantMessage:
    return AssistantMessage()


def _source(name: str) -> SourceRef:
    return SourceRef(file_name=name, file_path=f"C:/Docs/{name}", score=0.5)


def _image(icon: QIcon) -> QImage:
    return icon.pixmap(COPY_ICON_SIZE, COPY_ICON_SIZE).toImage()


def test_user_bubble_shows_the_text() -> None:
    bubble = UserBubble("Find my resume")

    assert [label.text() for label in bubble.findChildren(QLabel)] == ["Find my resume"]


def test_user_bubble_caps_the_text_width() -> None:
    bubble = UserBubble("word " * 200)

    assert bubble.findChild(QLabel).minimumWidth() < USER_BUBBLE_MAX_WIDTH


def test_answer_text_opens_clicked_links(open_url: Mock) -> None:
    answer = AnswerText()

    answer.anchorClicked.emit(QUrl("https://example.com"))

    open_url.assert_called_once_with(QUrl("https://example.com"))


def test_answer_text_grows_with_its_content() -> None:
    answer = AnswerText()
    answer.resize(300, 50)
    answer.setMarkdown("one line")
    short = answer.height()

    answer.setMarkdown("\n\n".join(f"paragraph {i}" for i in range(20)))

    assert answer.height() > short


def test_assistant_message_starts_hidden_apart_from_the_author(reply: AssistantMessage) -> None:
    assert (reply._thinking.isHidden(), reply._answer.isHidden(), reply._copy.isHidden()) == (True, True, True)


def test_start_thinking_shows_the_thinking_label(reply: AssistantMessage) -> None:
    reply.start_thinking()

    assert (reply._thinking.isHidden(), reply._thinking.is_animating()) == (False, True)


def test_start_thinking_pulses_the_avatar(reply: AssistantMessage) -> None:
    reply.start_thinking()

    assert reply._avatar._pulse.state() == QAbstractAnimation.State.Running


def test_stop_thinking_hides_the_label_and_rests_the_avatar(reply: AssistantMessage) -> None:
    reply.start_thinking()

    reply.stop_thinking()

    assert (reply._thinking.isHidden(), reply._avatar.glow) == (True, ORB_REST_GLOW)


def test_append_text_hides_the_thinking_label_on_the_first_token(reply: AssistantMessage) -> None:
    reply.start_thinking()

    reply.append_text("Hi")

    assert reply._thinking.isHidden()


def test_append_text_accumulates_streamed_tokens(reply: AssistantMessage) -> None:
    reply.append_text("**Hel")
    reply.append_text("lo**")

    assert (reply._markdown, reply._answer.toPlainText()) == ("**Hello**", "Hello")


def test_append_text_reveals_the_answer_and_copy_button(reply: AssistantMessage) -> None:
    reply.append_text("Hi")

    assert (reply._answer.isHidden(), reply._copy.isHidden()) == (False, False)


def test_set_text_replaces_previous_text(reply: AssistantMessage) -> None:
    reply.append_text("draft")

    reply.set_text("final")

    assert reply._answer.toPlainText() == "final"


def test_has_text_ignores_whitespace(reply: AssistantMessage) -> None:
    reply.append_text("  \n")

    assert not reply.has_text()


def test_is_empty_is_true_for_a_fresh_thinking_reply(reply: AssistantMessage) -> None:
    reply.start_thinking()

    assert reply.is_empty()


def test_is_empty_is_false_once_text_arrives(reply: AssistantMessage) -> None:
    reply.append_text("Hi")

    assert not reply.is_empty()


def test_is_empty_is_false_with_a_tool_step(reply: AssistantMessage) -> None:
    reply.show_tool("t1", "Searching files", "running")

    assert not reply.is_empty()


def test_is_empty_is_false_with_sources(reply: AssistantMessage) -> None:
    reply.set_sources([_source("a.txt")])

    assert not reply.is_empty()


def test_is_empty_is_false_with_an_error(reply: AssistantMessage) -> None:
    reply.show_error("Model offline")

    assert not reply.is_empty()


def test_show_tool_adds_one_step_per_call(reply: AssistantMessage) -> None:
    reply.show_tool("t1", "Searching files", "running")
    reply.show_tool("t2", "Opening Notepad", "running")

    assert len(reply.findChildren(ToolStep)) == 2


def test_show_tool_updates_an_existing_step_in_place(reply: AssistantMessage) -> None:
    reply.show_tool("t1", "Searching files", "running")

    reply.show_tool("t1", "Searched files", "done")

    step = reply._steps["t1"]
    assert (len(reply.findChildren(ToolStep)), step._text.text(), step._text.property("status")) == (
        1,
        "Searched files",
        "done",
    )


def test_set_sources_caps_the_number_of_cards(reply: AssistantMessage) -> None:
    reply.set_sources([_source(f"file{i}.txt") for i in range(MAX_SOURCE_CARDS + 3)])

    assert len(reply.findChildren(SourceCard)) == MAX_SOURCE_CARDS


def test_show_error_adds_an_error_line(reply: AssistantMessage) -> None:
    reply.show_error("Model offline")

    assert reply.findChild(QLabel, "ErrorLine").text() == "Model offline"


def test_show_error_stops_the_thinking_state(reply: AssistantMessage) -> None:
    reply.start_thinking()

    reply.show_error("Model offline")

    assert reply._thinking.isHidden()


def test_copy_button_copies_the_markdown(reply: AssistantMessage, clipboard: Mock) -> None:
    reply.append_text("**Bold** answer")

    reply._copy.click()

    clipboard.setText.assert_called_once_with("**Bold** answer")


def test_copy_button_shows_the_check_icon(reply: AssistantMessage, clipboard: Mock) -> None:
    reply.append_text("answer")

    reply._copy.click()

    assert _image(reply._copy.icon()) == _image(line_icon("check", SUCCESS, COPY_ICON_SIZE))


def test_copy_button_restores_the_copy_icon_after_the_feedback(reply: AssistantMessage, clipboard: Mock) -> None:
    reply.append_text("answer")
    reply._copy.click()
    assert reply._copied_reset.isActive()
    assert reply._copied_reset.interval() == COPIED_FEEDBACK_MS

    reply._copied_reset.timeout.emit()

    assert _image(reply._copy.icon()) == _image(_copy_icon())


def test_text_width_measures_the_longest_line() -> None:
    assert _text_width("a\nmuch longer line", 14) == _text_width("much longer line", 14)


def test_text_width_is_zero_for_empty_text() -> None:
    assert _text_width("", 14) == 0
