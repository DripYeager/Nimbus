from __future__ import annotations

from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QLabel, QPushButton
from pytest_mock import MockerFixture

from models.schema import SourceRef
from ui.chat.message_widgets import (
    MAX_SOURCE_CARDS,
    USER_BUBBLE_MAX_WIDTH,
    AnswerText,
    AssistantMessage,
    ConfirmCard,
    EmptyState,
    UserBubble,
    _text_width,
)


@pytest.fixture
def open_url(mocker: MockerFixture) -> Mock:
    """Clicking a link or a source card must never open a real file or browser in tests."""
    return mocker.patch("ui.chat.message_widgets.QDesktopServices.openUrl")


@pytest.fixture
def reply() -> AssistantMessage:
    return AssistantMessage()


def _source(name: str) -> SourceRef:
    return SourceRef(file_name=name, file_path=f"C:/Docs/{name}", score=0.5)


def _source_cards(reply: AssistantMessage) -> list[QPushButton]:
    return [b for b in reply.findChildren(QPushButton) if b.objectName() == "SourceCard"]


def test_user_bubble_shows_the_text() -> None:
    bubble = UserBubble("Find my resume")

    assert [label.text() for label in bubble.findChildren(QLabel)] == ["Find my resume"]


def test_user_bubble_caps_the_bubble_width() -> None:
    bubble = UserBubble("word " * 200)

    label = bubble.findChild(QLabel)
    assert label.minimumWidth() < USER_BUBBLE_MAX_WIDTH


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


def test_append_text_accumulates_streamed_tokens(reply: AssistantMessage) -> None:
    reply.append_text("**Hel")
    reply.append_text("lo**")

    assert reply._answer.toPlainText() == "Hello"


def test_append_text_reveals_the_answer(reply: AssistantMessage) -> None:
    reply.append_text("Hi")

    assert not reply._answer.isHidden()


def test_set_text_replaces_previous_text(reply: AssistantMessage) -> None:
    reply.append_text("draft")

    reply.set_text("final")

    assert reply._answer.toPlainText() == "final"


def test_has_text_ignores_whitespace(reply: AssistantMessage) -> None:
    reply.append_text("  \n")

    assert not reply.has_text()


def test_show_tool_adds_a_chip_with_its_status_icon(reply: AssistantMessage) -> None:
    reply.show_tool("t1", "Searching files", "running")

    assert reply._chips["t1"].text() == "⏳  Searching files"


def test_show_tool_updates_an_existing_chip(reply: AssistantMessage) -> None:
    reply.show_tool("t1", "Searching files", "running")

    reply.show_tool("t1", "Searched files", "failed")

    chip = reply._chips["t1"]
    assert (chip.text(), chip.property("status")) == ("⚠  Searched files", "failed")
    assert len(reply.findChildren(QLabel, "ToolChip")) == 1


def test_show_tool_uses_a_bullet_for_unknown_status(reply: AssistantMessage) -> None:
    reply.show_tool("t1", "Thinking", "mystery")

    assert reply._chips["t1"].text().startswith("•")


def test_set_sources_caps_the_number_of_cards(reply: AssistantMessage) -> None:
    reply.set_sources([_source(f"file{i}.txt") for i in range(MAX_SOURCE_CARDS + 3)])

    assert len(_source_cards(reply)) == MAX_SOURCE_CARDS


def test_set_sources_card_opens_its_file(reply: AssistantMessage, open_url: Mock) -> None:
    reply.set_sources([_source("a.txt"), _source("b.txt")])

    _source_cards(reply)[1].click()

    open_url.assert_called_once_with(QUrl.fromLocalFile("C:/Docs/b.txt"))


def test_show_error_adds_an_error_line(reply: AssistantMessage) -> None:
    reply.show_error("Model offline")

    assert reply.findChild(QLabel, "ErrorLine").text() == "⚠  Model offline"


@pytest.mark.parametrize(
    ("button_text", "expected"), [("Allow", (True, False)), ("Always allow", (True, True)), ("Don't", (False, False))]
)
def test_confirm_card_reports_the_choice(button_text: str, expected: tuple[bool, bool]) -> None:
    card = ConfirmCard("Open Notepad")
    decisions: list[tuple[bool, bool]] = []
    card.decided.connect(lambda approved, always: decisions.append((approved, always)))

    next(b for b in card.findChildren(QPushButton) if b.text() == button_text).click()

    assert decisions == [expected]


def test_confirm_card_locks_after_one_answer() -> None:
    card = ConfirmCard("Open Notepad")
    decisions: list[tuple[bool, bool]] = []
    card.decided.connect(lambda approved, always: decisions.append((approved, always)))
    buttons = card.findChildren(QPushButton)

    buttons[0].click()
    buttons[2].click()

    assert len(decisions) == 1
    assert not any(b.isEnabled() for b in buttons)


def test_confirm_card_shows_the_description() -> None:
    card = ConfirmCard("Open Notepad")

    assert any("Open Notepad" in label.text() for label in card.findChildren(QLabel))


def test_text_width_measures_the_longest_line() -> None:
    assert _text_width("a\nmuch longer line", 14) == _text_width("much longer line", 14)


def test_text_width_is_zero_for_empty_text() -> None:
    assert _text_width("", 14) == 0


def test_empty_state_emits_the_clicked_suggestion() -> None:
    empty = EmptyState(["Find my resume", "Open Notepad"])
    clicked: list[str] = []
    empty.suggestion_clicked.connect(clicked.append)

    next(b for b in empty.findChildren(QPushButton) if b.text() == "Open Notepad").click()

    assert clicked == ["Open Notepad"]
