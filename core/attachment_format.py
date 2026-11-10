"""
How an attachment travels inside a saved user message: its text wrapped in an <attachment>
block after what the user typed, so the model sees it on every later turn too. The block also
records where an attached file lives, so a chat window can show a preview (a screenshot's
thumbnail, say) when the chat is reopened. Takes the block back out for display. Pure text.
"""

from __future__ import annotations

import re
from typing import NamedTuple

CLOSE_TAG = "</attachment>"
_BLOCK = re.compile(r'\s*<attachment name="([^"]*)"(?: path="([^"]*)")?>.*?</attachment>', re.DOTALL)


class AttachedItem(NamedTuple):
    """What a chat window needs to show an attachment: its name, and its file if it has one."""

    name: str
    path: str | None = None


def with_attachment(text: str, name: str, body: str, path: str | None = None) -> str:
    """The user's message followed by the attachment block."""
    attributes = f'name="{_safe(name)}"' + (f' path="{_safe(path)}"' if path else "")
    return f"{text}\n\n<attachment {attributes}>\n{body}\n{CLOSE_TAG}"


def has_attachment(content: str) -> bool:
    return _BLOCK.search(content) is not None


def split_attachments(content: str) -> tuple[str, list[AttachedItem]]:
    """(what the user typed, everything attached to it)."""
    items = [AttachedItem(name, path or None) for name, path in _BLOCK.findall(content)]
    return _BLOCK.sub("", content).strip(), items


def _safe(value: str) -> str:
    """Keeps a value from closing its own quotes."""
    return value.replace('"', "'")
