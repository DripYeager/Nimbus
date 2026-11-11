"""
Push-to-talk for the message box: the microphone button (or Ctrl+M) listens once on a
background thread and drops what was said into the box, ready to edit or send. When Windows'
online speech setting is off, it offers to open that settings page. Owns the listening flow
only; recognizing speech is core/speech.py's job.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QMessageBox, QWidget

from core.speech import PRIVACY_MESSAGE, PRIVACY_SETTINGS_URL, listen_once
from ui.background_call import run_in_background
from ui.chat.chat_input import ChatInput

OPEN_SETTINGS_QUESTION = "\n\nOpen the Windows Speech settings now?"


class VoiceInput(QObject):
    """One listening session at a time; the button is disabled while it runs."""

    def __init__(self, chat_input: ChatInput, dialog_parent: QWidget) -> None:
        super().__init__()
        self._input = chat_input
        self._dialog_parent = dialog_parent
        self._listening = False

    def connect_signals(self) -> None:
        self._input.voice_requested.connect(self.listen)

    def is_listening(self) -> bool:
        return self._listening

    def listen(self) -> None:
        if self._listening:
            return
        self._listening = True
        self._input.set_listening(True)
        run_in_background(listen_once, self._heard, self._failed)

    def _heard(self, text: str) -> None:
        self._done()
        self._input.add_dictation(text)

    def _failed(self, message: str) -> None:
        self._done()
        if message == PRIVACY_MESSAGE:
            self._offer_privacy_settings()
        else:
            self._input.show_hint(message)

    def _done(self) -> None:
        self._listening = False
        self._input.set_listening(False)

    def _offer_privacy_settings(self) -> None:
        answer = QMessageBox.question(self._dialog_parent, "Voice input", PRIVACY_MESSAGE + OPEN_SETTINGS_QUESTION)
        if answer == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl(PRIVACY_SETTINGS_URL))
