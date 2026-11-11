"""
Reminder tools: set one ("remind me at 3 pm to call Priya", "in 20 minutes, check the oven"),
list the ones still to come, and cancel one. Setting a reminder only writes to Nimbus's own data,
so it doesn't ask first. Owns the tools' wording; storage and timing live in core/reminders.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.exceptions import ToolError
from core.reminders import Reminder, ReminderStore, resolve_due
from models.chat import ToolResult
from tools.registry import Tool, ToolRegistry, integer_param, object_schema, string_param, tool_spec

SET_REMINDER = tool_spec(
    "set_reminder",
    "Set a reminder that pops up as a Windows notification at a time. Give either 'at' (a local time like "
    "15:00 or a date and time like 2026-11-12 09:30) or 'in_minutes'.",
    object_schema(
        {
            "text": string_param("What to remind the user about, e.g. Call Priya"),
            "at": string_param("Local time (15:00) or date and time (2026-11-12 09:30)"),
            "in_minutes": integer_param("Minutes from now, instead of 'at'"),
        },
        ["text"],
    ),
)
LIST_REMINDERS = tool_spec("list_reminders", "List the reminders that haven't gone off yet.", object_schema({}))
CANCEL_REMINDER = tool_spec(
    "cancel_reminder",
    "Cancel a reminder by its number (from list_reminders).",
    object_schema({"number": integer_param("The reminder's number")}, ["number"]),
)


class ReminderToolbox:
    def __init__(self, store: ReminderStore) -> None:
        self._store = store

    def register(self, registry: ToolRegistry) -> None:
        registry.register(Tool(SET_REMINDER, self.set_reminder, lambda a: f"Set a reminder: {a.get('text', '')}"))
        registry.register(Tool(LIST_REMINDERS, self.list_reminders, lambda a: "Checked your reminders"))
        registry.register(Tool(CANCEL_REMINDER, self.cancel, lambda a: f"Cancelled reminder {a.get('number')}"))

    def set_reminder(self, args: dict[str, Any]) -> ToolResult:
        text = str(args.get("text", "")).strip()
        if not text:
            raise ToolError("The reminder needs some text.")
        minutes = args.get("in_minutes")
        due = resolve_due(args.get("at"), int(minutes) if minutes not in (None, "") else None)
        reminder = self._store.add(text, due)
        return ToolResult(content=f"Reminder {reminder.id} set for {describe_time(due)}: {text}")

    def list_reminders(self, args: dict[str, Any]) -> ToolResult:
        pending = self._store.pending()
        if not pending:
            return ToolResult(content="No reminders are coming up.")
        return ToolResult(content="\n".join(_line(reminder) for reminder in pending))

    def cancel(self, args: dict[str, Any]) -> ToolResult:
        number = int(args["number"])
        if not self._store.cancel(number):
            raise ToolError(f"There's no upcoming reminder number {number}.")
        return ToolResult(content=f"Cancelled reminder {number}.")


def describe_time(moment: datetime) -> str:
    """ "today at 15:00", "tomorrow at 09:30" or "Friday 14 November at 18:00"."""
    today = datetime.now().date()
    if moment.date() == today:
        return f"today at {moment:%H:%M}"
    if moment.date() == today + timedelta(days=1):
        return f"tomorrow at {moment:%H:%M}"
    return f"{moment:%A %d %B} at {moment:%H:%M}"


def _line(reminder: Reminder) -> str:
    return f"{reminder.id}. {describe_time(reminder.due)}: {reminder.text}"
