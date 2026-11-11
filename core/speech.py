"""
Push-to-talk voice input: listens to the microphone once, until the speaker pauses, and returns
what was said, using the speech recognizer built into Windows (Windows.Media.SpeechRecognition),
so there's nothing to download or install. Windows' dictation runs on Microsoft's online speech
service and only works once "Online speech recognition" is turned on in Windows privacy
settings; every failure comes back as a SpeechError with a message fit to show. Owns listening
only; what happens to the text is the caller's business.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from winrt.windows.media.speechrecognition import SpeechRecognitionResultStatus, SpeechRecognizer

from core.exceptions import SpeechError
from core.logger import get_logger

logger = get_logger(__name__)

# How long to wait for the first word, and how long a pause ends the sentence.
INITIAL_SILENCE = timedelta(seconds=6)
END_SILENCE = timedelta(seconds=1.2)
# Windows' error for "Online speech recognition is turned off".
PRIVACY_NOT_ACCEPTED = -2147199735
PRIVACY_SETTINGS_URL = "ms-settings:privacy-speech"
PRIVACY_MESSAGE = (
    "Voice input uses Windows' online speech recognition, which is turned off on this PC. "
    "Turn on Online speech recognition in Settings > Privacy & security > Speech, then try again."
)
STATUS_MESSAGES: dict[SpeechRecognitionResultStatus, str] = {
    SpeechRecognitionResultStatus.MICROPHONE_UNAVAILABLE: (
        "No microphone is available. Plug one in, or check Settings > Privacy & security > Microphone."
    ),
    SpeechRecognitionResultStatus.NETWORK_FAILURE: "Windows couldn't reach its speech service. Check your connection.",
    SpeechRecognitionResultStatus.AUDIO_QUALITY_FAILURE: "The audio was too quiet or noisy to understand. Try again.",
    SpeechRecognitionResultStatus.TOPIC_LANGUAGE_NOT_SUPPORTED: (
        "Windows speech recognition doesn't support your display language yet."
    ),
}
NOTHING_HEARD_MESSAGE = "Didn't catch anything. Click the microphone and start speaking."


def listen_once() -> str:
    """
    Records one utterance and returns its text.

    Raises:
        SpeechError: Speech is unavailable (privacy setting, no microphone, offline), or
            nothing was said.
    """
    try:
        status, text = asyncio.run(_recognize())
    except OSError as e:
        if getattr(e, "winerror", None) == PRIVACY_NOT_ACCEPTED:
            raise SpeechError(PRIVACY_MESSAGE) from e
        logger.warning("Speech recognition failed", extra={"error": str(e)})
        raise SpeechError(f"Voice input isn't available right now: {e}") from e
    return _text_or_error(status, text)


def is_privacy_error(error: SpeechError) -> bool:
    """True when turning on Windows' online speech setting would fix it."""
    return str(error) == PRIVACY_MESSAGE


def _text_or_error(status: SpeechRecognitionResultStatus, text: str) -> str:
    if status == SpeechRecognitionResultStatus.SUCCESS and text.strip():
        return text.strip()
    if status in STATUS_MESSAGES:
        raise SpeechError(STATUS_MESSAGES[status])
    raise SpeechError(NOTHING_HEARD_MESSAGE)


async def _recognize() -> tuple[SpeechRecognitionResultStatus, str]:
    recognizer = SpeechRecognizer()
    await recognizer.compile_constraints_async()
    recognizer.timeouts.initial_silence_timeout = INITIAL_SILENCE
    recognizer.timeouts.end_silence_timeout = END_SILENCE
    result = await recognizer.recognize_async()
    return result.status, result.text or ""
