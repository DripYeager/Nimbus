from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import numpy as np
import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from pytest_mock import MockerFixture

from core.transcriber import Transcriber
from ui.chat.chat_input import LISTENING_TIP, MIC_TIP, ChatInput
from ui.chat.voice_input import FIRST_USE_HINT, TRANSCRIBING_HINT, VoiceInput


class FakeRecorder(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.recording = False
        self.starts = 0

    def is_recording(self) -> bool:
        return self.recording

    def start(self) -> None:
        self.recording, self.starts = True, self.starts + 1

    def stop(self) -> None:
        self.recording = False
        self.finished.emit(np.ones(16_000, dtype=np.float32))


@pytest.fixture
def chat_input(qapp: object) -> ChatInput:
    return ChatInput()


@pytest.fixture
def pending(mocker: MockerFixture) -> list[Any]:
    """Background calls are captured, so a test can finish them when it likes."""
    calls: list[Any] = []
    mocker.patch("ui.chat.voice_input.run_in_background", side_effect=lambda fn, ok, err: calls.append((fn, ok, err)))
    return calls


@pytest.fixture
def transcriber(mocker: MockerFixture) -> Mock:
    fake = mocker.Mock(spec=Transcriber)
    fake.is_ready.return_value = True
    fake.transcribe.return_value = "find my resume"
    return fake


@pytest.fixture
def recorder(qapp: object) -> FakeRecorder:
    return FakeRecorder()


@pytest.fixture
def voice(chat_input: ChatInput, recorder: FakeRecorder, transcriber: Mock) -> VoiceInput:
    voice = VoiceInput(chat_input, recorder, transcriber)  # type: ignore[arg-type]
    voice.connect_signals()
    return voice


def test_listen_starts_recording(voice: VoiceInput, chat_input: ChatInput, pending: list[Any]) -> None:
    voice.listen()

    assert (voice.is_listening(), chat_input._mic.toolTip()) == (True, LISTENING_TIP)


def test_listen_again_stops_early_and_transcribes(voice: VoiceInput, chat_input: ChatInput, pending: list[Any]) -> None:
    voice.listen()

    voice.listen()

    assert (voice.is_listening(), chat_input._field.placeholderText()) == (False, TRANSCRIBING_HINT)
    assert len(pending) == 1


def test_the_words_go_into_the_box(
    voice: VoiceInput, chat_input: ChatInput, transcriber: Mock, pending: list[Any]
) -> None:
    chat_input.set_text("Please")
    voice.listen()
    voice.listen()
    work, done, _ = pending[0]

    done(work())

    assert (chat_input._field.toPlainText(), chat_input._mic.toolTip()) == ("Please find my resume", MIC_TIP)


def test_the_first_use_loads_the_model_while_the_user_talks(
    voice: VoiceInput, chat_input: ChatInput, transcriber: Mock, pending: list[Any]
) -> None:
    transcriber.is_ready.return_value = False

    voice.listen()

    assert pending[0][0] == transcriber.load
    assert chat_input._field.placeholderText() == FIRST_USE_HINT


def test_no_new_recording_while_transcribing(voice: VoiceInput, recorder: FakeRecorder, pending: list[Any]) -> None:
    voice.listen()
    voice.listen()

    voice.listen()

    assert recorder.starts == 1


def test_a_failure_shows_its_reason(voice: VoiceInput, chat_input: ChatInput, recorder: FakeRecorder) -> None:
    voice.listen()

    recorder.failed.emit("No microphone was found.")

    assert (chat_input._field.placeholderText(), chat_input._mic.toolTip()) == ("No microphone was found.", MIC_TIP)
