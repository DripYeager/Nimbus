"""
Data shapes returned by the system and note tools: a machine status snapshot and a saved-note hit.
Does not gather any of this data, tools/system_tools.py and tools/note_tools.py fill these in.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

NOTE_PREVIEW_CHARS = 200


class SystemStatus(BaseModel):
    """A point-in-time read of the machine. Battery fields are None on desktops without one."""

    battery_percent: float | None = None
    is_plugged_in: bool | None = None
    disk_free_gb: float
    disk_total_gb: float
    cpu_percent: float
    memory_percent: float
    local_time: str
    uptime_hours: float


class NoteMatch(BaseModel):
    path: str
    title: str
    modified_at: datetime
    preview: str = Field(default="", max_length=NOTE_PREVIEW_CHARS)
