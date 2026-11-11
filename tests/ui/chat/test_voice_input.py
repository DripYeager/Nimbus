from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QMessageBox, QWidget
from pytest_mock import MockerFixture

from core.speech import PRIVACY_MESSAGE, PRIVACY_SETTINGS_URL
from ui.chat.chat_input import LISTENING_TIP, MIC_TIP, ChatInput
from ui.chat.voice_input import VoiceInput


@pytest.fixture
def chat_input(qapp: object) -> ChatInput:
    return ChatInput()


@pytest.fixture
def pending(mocker: MockerFixture) -> list[Any]:
    """Captures each background call's callbacks so a test can finish it when it likes."""
    calls: list[Any] = []
    mocker.patch("ui.chat.voice_input.run_in_background", side_effect=lambda fn, ok, err: calls.append((ok, err)))
    return calls


@pytest.fixture
def voice(chat_input: ChatInput) -> VoiceInput:
    voice = VoiceInput(chat_input, QWidget())
    voice.connect_signals()
    return voice


def test_listen_shows_the_listening_state(voice: VoiceInput, chat_input: ChatInput, pending: list[Any]) -> None:
    voice.listen()

    assert (voice.is_listening(), chat_input._mic.toolTip()) == (True, LISTENING_TIP)


def test_listen_runs_only_one_session_at_a_time(voice: VoiceInput, pending: list[Any]) -> None:
    voice.listen()
    voice.listen()

    assert len(pending) == 1


def test_mic_button_starts_listening(voice: VoiceInput, chat_input: ChatInput, pending: list[Any]) -> None:
    chat_input._mic.click()

    assert voice.is_listening()


def test_heard_text_goes_after_what_was_typed(voice: VoiceInput, chat_input: ChatInput, pending: list[Any]) -> None:
    chat_input.set_text("Find")
    voice.listen()

    pending[0][0]("my resume")

    assert (chat_input._field.toPlainText(), chat_input._mic.toolTip()) == ("Find my resume", MIC_TIP)


def test_a_failure_shows_its_reason_in_the_box(voice: VoiceInput, chat_input: ChatInput, pending: list[Any]) -> None:
    voice.listen()

    pending[0][1]("No microphone is available.")

    assert (chat_input._field.placeholderText(), voice.is_listening()) == ("No microphone is available.", False)


def test_the_privacy_setting_error_offers_to_open_windows_settings(
    voice: VoiceInput, pending: list[Any], mocker: MockerFixture
) -> None:
    mocker.patch("ui.chat.voice_input.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes)
    open_url: Mock = mocker.patch("ui.chat.voice_input.QDesktopServices.openUrl")
    voice.listen()

    pending[0][1](PRIVACY_MESSAGE)

    assert open_url.call_args.args[0].toString() == PRIVACY_SETTINGS_URL
