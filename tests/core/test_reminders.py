from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from core.exceptions import ToolError
from core.reminders import ReminderStore, resolve_due

NOW = datetime(2026, 11, 11, 14, 0)


@pytest.fixture
def store(tmp_path: Path) -> ReminderStore:
    reminders = ReminderStore(tmp_path / "reminders.db")
    yield reminders
    reminders.close()


def test_take_due_hands_out_each_due_reminder_once(store: ReminderStore) -> None:
    store.add("Call Priya", NOW - timedelta(minutes=1))
    store.add("Later thing", NOW + timedelta(hours=1))

    first, second = store.take_due(NOW), store.take_due(NOW)

    assert ([r.text for r in first], second) == (["Call Priya"], [])


def test_pending_lists_upcoming_reminders_soonest_first(store: ReminderStore) -> None:
    store.add("Second", NOW + timedelta(hours=2))
    store.add("First", NOW + timedelta(hours=1))

    assert [r.text for r in store.pending()] == ["First", "Second"]


def test_cancel_removes_only_a_pending_reminder(store: ReminderStore) -> None:
    reminder = store.add("Dentist", NOW + timedelta(hours=1))

    assert (store.cancel(reminder.id), store.cancel(reminder.id), store.pending()) == (True, False, [])


def test_reminders_survive_a_restart(tmp_path: Path) -> None:
    first = ReminderStore(tmp_path / "r.db")
    first.add("Survive", NOW + timedelta(days=1))
    first.close()
    second = ReminderStore(tmp_path / "r.db")

    assert [r.text for r in second.pending()] == ["Survive"]
    second.close()


@pytest.mark.parametrize(
    ("at", "expected"),
    [
        ("15:00", datetime(2026, 11, 11, 15, 0)),
        ("3 pm", datetime(2026, 11, 11, 15, 0)),
        ("3:30 PM", datetime(2026, 11, 11, 15, 30)),
        ("09:00", datetime(2026, 11, 12, 9, 0)),
        ("2026-11-12 09:30", datetime(2026, 11, 12, 9, 30)),
        ("2026-11-12T09:30", datetime(2026, 11, 12, 9, 30)),
    ],
)
def test_resolve_due_reads_times_and_dates(at: str, expected: datetime) -> None:
    assert resolve_due(at, None, NOW) == expected


def test_resolve_due_counts_minutes_from_now() -> None:
    assert resolve_due(None, 20, NOW) == NOW + timedelta(minutes=20)


def test_resolve_due_reads_a_time_that_names_its_zone() -> None:
    zoned = "2026-11-12T04:00:00+00:00"
    expected = datetime.fromisoformat(zoned).astimezone().replace(tzinfo=None)

    assert resolve_due(zoned, None, NOW) == expected
    assert resolve_due("2026-11-12T04:00:00Z", None, NOW) == expected


@pytest.mark.parametrize(
    ("at", "minutes"), [(None, None), ("", None), ("tea time", None), (None, 0), ("2026-11-10 09:00", None)]
)
def test_resolve_due_rejects_missing_unreadable_or_past_times(at: str | None, minutes: int | None) -> None:
    with pytest.raises(ToolError):
        resolve_due(at, minutes, NOW)
