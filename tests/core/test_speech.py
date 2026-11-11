from __future__ import annotations

import pytest
from pytest_mock import MockerFixture
from winrt.windows.media.speechrecognition import SpeechRecognitionResultStatus as Status

from core.exceptions import SpeechError
from core.speech import (
    NOTHING_HEARD_MESSAGE,
    PRIVACY_MESSAGE,
    PRIVACY_NOT_ACCEPTED,
    STATUS_MESSAGES,
    is_privacy_error,
    listen_once,
)


def _recognized(mocker: MockerFixture, status: Status, text: str) -> None:
    async def fake() -> tuple[Status, str]:
        return status, text

    mocker.patch("core.speech._recognize", side_effect=fake)


def test_listen_once_returns_what_was_said(mocker: MockerFixture) -> None:
    _recognized(mocker, Status.SUCCESS, " what's on my calendar today ")

    assert listen_once() == "what's on my calendar today"


def test_listen_once_says_so_when_nothing_was_heard(mocker: MockerFixture) -> None:
    _recognized(mocker, Status.SUCCESS, "")

    with pytest.raises(SpeechError, match=NOTHING_HEARD_MESSAGE):
        listen_once()


def test_listen_once_explains_a_missing_microphone(mocker: MockerFixture) -> None:
    _recognized(mocker, Status.MICROPHONE_UNAVAILABLE, "")

    with pytest.raises(SpeechError) as raised:
        listen_once()

    assert str(raised.value) == STATUS_MESSAGES[Status.MICROPHONE_UNAVAILABLE]


def test_listen_once_explains_the_windows_privacy_setting(mocker: MockerFixture) -> None:
    error = OSError("policy")
    error.winerror = PRIVACY_NOT_ACCEPTED  # type: ignore[attr-defined]
    mocker.patch("core.speech._recognize", side_effect=error)

    with pytest.raises(SpeechError) as raised:
        listen_once()

    assert is_privacy_error(raised.value)
    assert str(raised.value) == PRIVACY_MESSAGE


def test_listen_once_wraps_other_windows_errors(mocker: MockerFixture) -> None:
    mocker.patch("core.speech._recognize", side_effect=OSError("device busy"))

    with pytest.raises(SpeechError, match="isn't available"):
        listen_once()
