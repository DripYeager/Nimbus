"""
Turns an IndexStatus into the short progress line shown in the tray and the chat header.
Pure formatting; does not fetch status.
"""

from __future__ import annotations

from models.schema import IndexStatus


def describe_status(status: IndexStatus) -> str:
    """One line describing indexing progress."""
    if status.is_paused:
        return "Indexing paused"
    if status.pending_files:
        done = status.indexed_files + status.failed_files
        return f"Learning your files · {done:,} of {status.content_files:,}"
    if status.is_scanning:
        return "Looking for new files…"
    return f"Ready · {status.cataloged_files:,} files known"
