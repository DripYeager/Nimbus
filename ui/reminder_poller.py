"""
Asks the engine every few seconds for reminders that have fallen due and shows each as a
Windows notification from the tray. One that came due while Nimbus was closed still shows, at
the next start, with the time it was meant for. Owns polling and wording only; reminders are
stored and timed by the engine.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from PyQt6.QtCore import QObject, QTimer

from models.api import DueReminder
from ui.api_client import ApiClient
from ui.background_call import run_in_background

POLL_MS = 20_000
REMINDER_TITLE = "Reminder"
# Later than this and the notification says when it was meant for.
LATE_AFTER = timedelta(minutes=2)


def describe_reminder(reminder: DueReminder, now: datetime | None = None) -> str:
    """The notification text, with the intended time when it's showing late."""
    current = now or datetime.now()
    if current - reminder.due.replace(tzinfo=None) > LATE_AFTER:
        return f"{reminder.text} (was due at {reminder.due:%H:%M})"
    return reminder.text


class ReminderPoller(QObject):
    """show(title, text) is called on the GUI thread for each due reminder."""

    def __init__(self, api: ApiClient, show: Callable[[str, str], None]) -> None:
        super().__init__()
        self._api = api
        self._show = show
        self._busy = False
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self.check)

    def start(self) -> None:
        self._timer.start()
        self.check()

    def stop(self) -> None:
        self._timer.stop()

    def check(self) -> None:
        if self._busy:
            return
        self._busy = True
        run_in_background(self._api.due_reminders, self._deliver, self._failed)

    def _deliver(self, reminders: list[DueReminder]) -> None:
        self._busy = False
        for reminder in reminders:
            self._show(REMINDER_TITLE, describe_reminder(reminder))

    def _failed(self, _message: str) -> None:
        # The engine may still be starting; the next poll tries again.
        self._busy = False
