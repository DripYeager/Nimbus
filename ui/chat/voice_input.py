"""
Push-to-talk for the message box: the microphone button (or Ctrl+M) records until the speaker
pauses, or until it's clicked again, then a local Whisper model transcribes it on a background
thread and the words land in the box, ready to edit or send. Nothing leaves the PC. Owns the
listening flow only; capture is ui/voice_recorder.py's job and transcription core/transcriber.py's.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QObject

from core.transcriber import Transcriber, get_transcriber
from ui.background_call import run_in_background
from ui.chat.chat_input import ChatInput
from ui.voice_recorder import VoiceRecorder

TRANSCRIBING_HINT = "Turning your words into text…"
FIRST_USE_HINT = "Listening… (the first time, the speech model downloads once, about 150 MB)"


class VoiceInput(QObject):
    """Idle, recording or transcribing; one at a time."""

    def __init__(
        self, chat_input: ChatInput, recorder: VoiceRecorder | None = None, transcriber: Transcriber | None = None
    ) -> None:
        super().__init__()
        self._input = chat_input
        self._recorder = recorder or VoiceRecorder()
        self._transcriber = transcriber or get_transcriber()
        self._transcribing = False

    def connect_signals(self) -> None:
        self._input.voice_requested.connect(self.listen)
        self._recorder.finished.connect(self._recorded)
        self._recorder.failed.connect(self._failed)

    def is_listening(self) -> bool:
        return self._recorder.is_recording()

    def listen(self) -> None:
        """Starts recording; a second press while recording stops early."""
        if self._recorder.is_recording():
            self._recorder.stop()
            return
        if self._transcribing:
            return
        if not self._transcriber.is_ready():
            self._input.show_hint(FIRST_USE_HINT)
            # Loads (or downloads) the model while the user talks, so it's ready when they stop.
            run_in_background(self._transcriber.load, lambda _: None, lambda _: None)
        self._input.set_listening(True)
        self._recorder.start()

    def _recorded(self, samples: np.ndarray) -> None:
        self._input.set_listening(False)
        self._transcribing = True
        self._input.show_hint(TRANSCRIBING_HINT)
        run_in_background(lambda: self._transcriber.transcribe(samples), self._heard, self._failed)

    def _heard(self, text: str) -> None:
        self._transcribing = False
        self._input.clear_hint()
        self._input.add_dictation(text)

    def _failed(self, message: str) -> None:
        self._transcribing = False
        self._input.set_listening(False)
        self._input.show_hint(message)
