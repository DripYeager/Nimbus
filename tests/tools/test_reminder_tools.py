from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from core.exceptions import ToolError
from core.reminders import ReminderStore
from tools.reminder_tools import ReminderToolbox, describe_time


@pytest.fixture
def toolbox(tmp_path: Path) -> ReminderToolbox:
    return ReminderToolbox(ReminderStore(tmp_path / "reminders.db"))


def test_set_reminder_confirms_the_time(toolbox: ReminderToolbox) -> None:
    result = toolbox.set_reminder({"text": "Check the oven", "in_minutes": 20})

    assert result.content.startswith("Reminder 1 set for") and "Check the oven" in result.content


def test_set_reminder_needs_text(toolbox: ReminderToolbox) -> None:
    with pytest.raises(ToolError):
        toolbox.set_reminder({"text": " ", "in_minutes": 5})


def test_list_then_cancel(toolbox: ReminderToolbox) -> None:
    toolbox.set_reminder({"text": "Call Priya", "in_minutes": 30})

    listed = toolbox.list_reminders({}).content
    toolbox.cancel({"number": 1})

    assert "1. " in listed and "Call Priya" in listed
    assert toolbox.list_reminders({}).content == "No reminders are coming up."


def test_cancel_unknown_number_explains(toolbox: ReminderToolbox) -> None:
    with pytest.raises(ToolError, match="no upcoming reminder number 9"):
        toolbox.cancel({"number": 9})


def test_describe_time_says_today_and_tomorrow() -> None:
    now = datetime.now()
    later_today = now.replace(hour=23, minute=59)

    assert describe_time(later_today) == "today at 23:59"
    assert describe_time(now + timedelta(days=1)).startswith("tomorrow at")
