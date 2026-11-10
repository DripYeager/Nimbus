from __future__ import annotations

import pytest
from PyQt6.QtCore import QAbstractAnimation, Qt
from PyQt6.QtTest import QTest

from ui.chat.chat_input import FIELD_PADDING_PX, LINE_HEIGHT_PX, MAX_LINES, MIN_LINES, SEND_TIP, STOP_TIP, ChatInput


@pytest.fixture
def chat_input() -> ChatInput:
    return ChatInput()


@pytest.fixture
def sent(chat_input: ChatInput) -> list[str]:
    messages: list[str] = []
    chat_input.submitted.connect(messages.append)
    return messages


def test_enter_submits_the_trimmed_text(chat_input: ChatInput, sent: list[str]) -> None:
    chat_input.set_text("  Find my resume \n")

    QTest.keyClick(chat_input._field, Qt.Key.Key_Return)

    assert sent == ["Find my resume"]


def test_enter_clears_the_field_after_sending(chat_input: ChatInput, sent: list[str]) -> None:
    chat_input.set_text("Find my resume")

    QTest.keyClick(chat_input._field, Qt.Key.Key_Return)

    assert chat_input._field.toPlainText() == ""


def test_keypad_enter_submits(chat_input: ChatInput, sent: list[str]) -> None:
    chat_input.set_text("hello")

    QTest.keyClick(chat_input._field, Qt.Key.Key_Enter)

    assert sent == ["hello"]


def test_shift_enter_does_not_send(chat_input: ChatInput, sent: list[str]) -> None:
    chat_input.set_text("first")

    QTest.keyClick(chat_input._field, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)

    assert sent == []


def test_shift_enter_adds_a_line_break(chat_input: ChatInput) -> None:
    chat_input.set_text("first")
    chat_input._field.moveCursor(chat_input._field.textCursor().MoveOperation.End)

    QTest.keyClick(chat_input._field, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)

    assert chat_input._field.toPlainText() == "first\n"


def test_enter_ignores_blank_text(chat_input: ChatInput, sent: list[str]) -> None:
    chat_input.set_text("   ")

    QTest.keyClick(chat_input._field, Qt.Key.Key_Return)

    assert sent == []


def test_send_button_submits(chat_input: ChatInput, sent: list[str]) -> None:
    chat_input.set_text("hello")

    chat_input._send.click()

    assert sent == ["hello"]


def test_set_busy_blocks_sending_and_keeps_the_text(chat_input: ChatInput, sent: list[str]) -> None:
    chat_input.set_busy(True)
    chat_input.set_text("queued question")

    QTest.keyClick(chat_input._field, Qt.Key.Key_Return)

    assert (sent, chat_input._field.toPlainText()) == ([], "queued question")


def test_set_busy_turns_the_send_button_into_stop(chat_input: ChatInput) -> None:
    chat_input.set_busy(True)

    assert (chat_input.is_busy(), chat_input._send.toolTip()) == (True, STOP_TIP)


def test_set_busy_false_turns_the_button_back_into_send(chat_input: ChatInput) -> None:
    chat_input.set_busy(True)

    chat_input.set_busy(False)

    assert (chat_input.is_busy(), chat_input._send.toolTip()) == (False, SEND_TIP)


def test_button_click_while_busy_requests_a_stop(chat_input: ChatInput) -> None:
    stops: list[None] = []
    sent: list[str] = []
    chat_input.stop_requested.connect(lambda: stops.append(None))
    chat_input.submitted.connect(sent.append)
    chat_input.set_text("typed ahead")
    chat_input.set_busy(True)

    chat_input._send.click()

    assert (stops, sent) == ([None], [])


def test_set_busy_pulses_the_aura(chat_input: ChatInput) -> None:
    chat_input.set_busy(True)

    assert chat_input._aura.state() == QAbstractAnimation.State.Running


def test_set_busy_twice_replaces_the_running_aura(chat_input: ChatInput) -> None:
    chat_input.set_busy(True)
    first = chat_input._aura

    chat_input.set_busy(True)

    assert (first.state(), chat_input._aura.state()) == (
        QAbstractAnimation.State.Stopped,
        QAbstractAnimation.State.Running,
    )


def test_set_busy_false_stops_the_glow(chat_input: ChatInput) -> None:
    chat_input.set_busy(True)

    chat_input.set_busy(False)

    assert (chat_input.glow, chat_input._aura) == (0.0, None)


def test_set_busy_false_reenables_sending(chat_input: ChatInput, sent: list[str]) -> None:
    chat_input.set_busy(True)

    chat_input.set_busy(False)
    chat_input.set_text("hello")
    chat_input._send.click()

    assert sent == ["hello"]


def test_fit_height_starts_at_one_line(chat_input: ChatInput) -> None:
    assert chat_input._field.height() == MIN_LINES * LINE_HEIGHT_PX + FIELD_PADDING_PX


def test_fit_height_grows_with_extra_lines(chat_input: ChatInput) -> None:
    chat_input.set_text("one\ntwo\nthree")

    assert chat_input._field.height() == 3 * LINE_HEIGHT_PX + FIELD_PADDING_PX


def test_fit_height_stops_growing_at_max_lines(chat_input: ChatInput) -> None:
    chat_input.set_text("\n".join(f"line {i}" for i in range(MAX_LINES * 3)))

    assert chat_input._field.height() == MAX_LINES * LINE_HEIGHT_PX + FIELD_PADDING_PX
