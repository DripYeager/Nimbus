from __future__ import annotations

from datetime import datetime, timedelta

from models.api import DueReminder
from ui.reminder_poller import REMINDER_TITLE, ReminderPoller, describe_reminder

NOW = datetime(2026, 11, 11, 15, 0)


def test_describe_reminder_on_time_is_just_the_text() -> None:
    assert describe_reminder(DueReminder(text="Call Priya", due=NOW), NOW) == "Call Priya"


def test_describe_reminder_says_when_it_was_meant_for_if_late() -> None:
    late = describe_reminder(DueReminder(text="Call Priya", due=NOW - timedelta(hours=2)), NOW)

    assert late == "Call Priya (was due at 13:00)"


def test_deliver_shows_each_reminder(qapp: object) -> None:
    shown: list[tuple[str, str]] = []
    poller = ReminderPoller(api=None, show=lambda title, text: shown.append((title, text)))  # type: ignore[arg-type]

    poller._deliver([DueReminder(text="Stretch", due=datetime.now())])

    assert shown == [(REMINDER_TITLE, "Stretch")]
