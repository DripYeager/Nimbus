"""
How an attachment travels inside a saved user message: its text wrapped in an <attachment>
block after what the user typed, so the model sees it on every later turn too. Also takes the
block back out, so a chat window can show a short tag instead of pages of text. Pure text.
"""

from __future__ import annotations

import re

OPEN_TAG = '<attachment name="{name}">'
CLOSE_TAG = "</attachment>"
_BLOCK = re.compile(r'\s*<attachment name="([^"]*)">.*?</attachment>', re.DOTALL)


def with_attachment(text: str, name: str, body: str) -> str:
    """The user's message followed by the attachment block."""
    safe_name = name.replace('"', "'")
    return f"{text}\n\n{OPEN_TAG.format(name=safe_name)}\n{body}\n{CLOSE_TAG}"


def split_attachments(content: str) -> tuple[str, list[str]]:
    """(what the user typed, names of anything attached)."""
    names = _BLOCK.findall(content)
    return _BLOCK.sub("", content).strip(), names
