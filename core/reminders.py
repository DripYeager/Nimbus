"""
Reminders the user asked for ("remind me at 3 pm to call Priya"): kept in a small SQLite file so
they survive a restart, and handed out once each when they fall due, which is when the tray shows
the notification. Also turns the times a model writes ("15:00", "2026-11-12 09:30", "in 20
minutes") into a moment. Owns storage and timing only; showing the notification is the tray's job.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from core.exceptions import ToolError

SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    due REAL NOT NULL,
    delivered INTEGER NOT NULL DEFAULT 0
);
"""
# A time a few seconds in the past still counts: the model may take a moment to answer.
PAST_GRACE = timedelta(minutes=1)
TIME_FORMATS = ("%H:%M", "%I:%M %p", "%I %p", "%I:%M%p", "%I%p")


@dataclass(frozen=True)
class Reminder:
    id: int
    text: str
    due: datetime


class ReminderStore:
    """Thread-safe: the agent adds reminders while the tray collects due ones."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._lock = threading.Lock()

    def add(self, text: str, due: datetime) -> Reminder:
        with self._lock, self._conn:
            cursor = self._conn.execute("INSERT INTO reminders (text, due) VALUES (?, ?)", (text, due.timestamp()))
        return Reminder(int(cursor.lastrowid or 0), text, due)

    def pending(self) -> list[Reminder]:
        """Reminders that haven't been shown yet, soonest first."""
        with self._lock:
            rows = self._conn.execute("SELECT id, text, due FROM reminders WHERE delivered = 0 ORDER BY due").fetchall()
        return [Reminder(row[0], row[1], datetime.fromtimestamp(row[2])) for row in rows]

    def cancel(self, reminder_id: int) -> bool:
        """Removes a pending reminder; False if there was none with that number."""
        with self._lock, self._conn:
            cursor = self._conn.execute("DELETE FROM reminders WHERE id = ? AND delivered = 0", (reminder_id,))
        return cursor.rowcount > 0

    def take_due(self, now: datetime | None = None) -> list[Reminder]:
        """Reminders whose time has come, each handed out only once."""
        moment = (now or datetime.now()).timestamp()
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT id, text, due FROM reminders WHERE delivered = 0 AND due <= ? ORDER BY due", (moment,)
            ).fetchall()
            self._conn.executemany("UPDATE reminders SET delivered = 1 WHERE id = ?", [(row[0],) for row in rows])
        return [Reminder(row[0], row[1], datetime.fromtimestamp(row[2])) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def resolve_due(at: str | None, in_minutes: int | None, now: datetime | None = None) -> datetime:
    """When a reminder should go off, from a clock time or date, or a number of minutes.

    Raises:
        ToolError: Neither was given, the time can't be read, or it's in the past.
    """
    current = now or datetime.now()
    if in_minutes is not None:
        if in_minutes <= 0:
            raise ToolError("The reminder needs a time in the future.")
        return current + timedelta(minutes=in_minutes)
    if not at or not at.strip():
        raise ToolError("Say when: a time like 15:00, a date and time like 2026-11-12 09:30, or in_minutes.")
    due = _parse(at.strip(), current)
    if due < current - PAST_GRACE:
        raise ToolError(f"{due:%A %d %B at %H:%M} has already passed. Give a time in the future.")
    return due


def _parse(text: str, now: datetime) -> datetime:
    """A full date and time, or a clock time today (tomorrow if that time has passed)."""
    try:
        return datetime.fromisoformat(text.replace("/", "-"))
    except ValueError:
        pass
    for pattern in TIME_FORMATS:
        try:
            clock = datetime.strptime(text.upper(), pattern).time()
        except ValueError:
            continue
        due = datetime.combine(now.date(), clock)
        return due if due >= now - PAST_GRACE else due + timedelta(days=1)
    raise ToolError(f"Couldn't read the time {text!r}. Use 15:00 or 2026-11-12 09:30.")
