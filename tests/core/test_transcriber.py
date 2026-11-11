from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from pytest_mock import MockerFixture

import core.transcriber as transcriber_module
from core.exceptions import SpeechError
from core.transcriber import NOTHING_HEARD_MESSAGE, SAMPLE_RATE, Transcriber, get_transcriber

SPEECH = np.zeros(SAMPLE_RATE * 2, dtype=np.float32)


@pytest.fixture
def model(mocker: MockerFixture) -> Mock:
    fake = mocker.Mock()
    fake.transcribe.return_value = ([SimpleNamespace(text=" Open "), SimpleNamespace(text="the report. ")], None)
    mocker.patch("core.transcriber.WhisperModel", return_value=fake)
    return fake


def test_transcribe_joins_the_spoken_segments(model: Mock) -> None:
    assert Transcriber("base.en", 1).transcribe(SPEECH) == "Open the report."


def test_transcribe_asks_for_english_with_silence_trimmed(model: Mock) -> None:
    Transcriber("base.en", 1).transcribe(SPEECH)

    assert model.transcribe.call_args.kwargs == {"language": "en", "beam_size": 1, "vad_filter": True}


def test_transcribe_refuses_a_click_too_short_to_be_speech(model: Mock) -> None:
    with pytest.raises(SpeechError, match=NOTHING_HEARD_MESSAGE):
        Transcriber("base.en", 1).transcribe(np.zeros(100, dtype=np.float32))
    model.transcribe.assert_not_called()


def test_transcribe_says_so_when_nothing_was_recognised(model: Mock) -> None:
    model.transcribe.return_value = ([], None)

    with pytest.raises(SpeechError, match=NOTHING_HEARD_MESSAGE):
        Transcriber("base.en", 1).transcribe(SPEECH)


def test_load_explains_a_failed_download(mocker: MockerFixture) -> None:
    mocker.patch("core.transcriber.WhisperModel", side_effect=OSError("offline"))

    with pytest.raises(SpeechError, match="needs internet access"):
        Transcriber("base.en", 1).load()


def test_load_happens_once(model: Mock, mocker: MockerFixture) -> None:
    transcriber = Transcriber("base.en", 1)

    transcriber.load()
    transcriber.load()

    assert (transcriber.is_ready(), transcriber_module.WhisperModel.call_count) == (True, 1)  # type: ignore[attr-defined]


def test_get_transcriber_is_shared(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcriber_module, "_transcriber", None)

    assert get_transcriber() is get_transcriber()
