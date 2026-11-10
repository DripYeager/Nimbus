"""
Everything that hands Nimbus something to ask about: the clipboard offer when the window
appears, a file from File Explorer's right-click menu, and a screen capture. Wires the
attachment bar to the chat session; the window decides when each happens.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QGuiApplication

from models.chat import Attachment
from ui.chat.attachment_bar import COPIED_TEXT_NAME, SCREENSHOT_NAME, AttachmentBar
from ui.chat.chat_session import ChatSession

# Shorter than this is a word or a number, not something worth asking about.
MIN_CLIPBOARD_CHARS = 20


class AttachmentFlow(QObject):
    """Keeps the bar and the session's attachment in step."""

    def __init__(self, bar: AttachmentBar, session: ChatSession) -> None:
        super().__init__()
        self._bar = bar
        self._session = session
        self._offered_text = ""
        self._attached: Attachment | None = None

    def connect_signals(self) -> None:
        self._bar.offer_accepted.connect(self._accept_offer)
        self._bar.offer_dismissed.connect(self._bar.clear)
        self._bar.removed.connect(lambda: self._session.attach(None))
        self._bar.suggestion_clicked.connect(self._session.send)
        self._session.attachment_changed.connect(self._show)

    def offer_clipboard(self) -> None:
        """Offers fresh copied text once. Skips text Nimbus copied itself (an answer) and
        anything already offered, so dismissing it sticks."""
        clipboard = QGuiApplication.clipboard()
        text = clipboard.text().strip()
        if len(text) < MIN_CLIPBOARD_CHARS or text == self._offered_text or clipboard.ownsClipboard():
            return
        if self._attached is not None:
            return
        self._offered_text = text
        self._bar.offer_clipboard(len(text))

    def attach_file(self, path: str) -> None:
        self._session.attach(Attachment(name=Path(path).name, path=path))

    def attach_screenshot(self, path: Path) -> None:
        self._session.attach(Attachment(name=SCREENSHOT_NAME, path=str(path)))

    def _accept_offer(self) -> None:
        self._session.attach(Attachment(name=COPIED_TEXT_NAME, text=self._offered_text))

    def _show(self, attachment: Attachment | None) -> None:
        self._attached = attachment
        self._bar.show_attachment(attachment)
