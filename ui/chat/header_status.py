"""
Keeps the chat header's status current while the window is open: indexing progress every few
seconds, and the Local / Cloud badge only when the window opens or Settings are saved (nothing
else changes it, so there's no need to ask every poll). Owns the polling only; drawing is the
header's job.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer

from models.schema import IndexStatus
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.chat.chat_header import ChatHeader

STATUS_POLL_MS = 2000


class HeaderStatus(QObject):
    """start() when the window shows, stop() when it hides; show() takes pushed updates too."""

    def __init__(self, api: ApiClient, header: ChatHeader, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._header = header
        self._privacy_stale = True
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)

    def start(self) -> None:
        self.timer.start(STATUS_POLL_MS)
        self.refresh_privacy()

    def stop(self) -> None:
        self.timer.stop()

    def poll(self) -> None:
        run_in_background(self._fetch, lambda result: self.show(*result), lambda _: None)

    def refresh_privacy(self) -> None:
        """Re-reads the Local / Cloud setting on the next poll (after a save, say)."""
        self._privacy_stale = True
        self.poll()

    def show(self, status: IndexStatus, is_cloud: bool | None) -> None:
        self._header.set_status(status)
        if is_cloud is not None:
            self._privacy_stale = False
            self._header.set_privacy(is_cloud)

    def _fetch(self) -> tuple[IndexStatus, bool | None]:
        is_cloud = self._api.settings().is_cloud if self._privacy_stale else None
        return self._api.index_status(), is_cloud
