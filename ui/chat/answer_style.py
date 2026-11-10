"""
House style for answers on screen: no em or en dashes. Models, small local ones especially,
use them even when asked not to, so they're rewritten before display: a number range becomes
"4 to 5" and any other dash becomes a comma. Code blocks are left exactly as written. Pure
text; nothing is drawn here.
"""

from __future__ import annotations

import re

CODE_FENCE = "```"
# Written as escapes (en dash, em dash) so the characters themselves never appear in the source.
DASHES = "–—"
_RANGE_DASH = re.compile(rf"(?<=\d)\s*[{DASHES}]\s*(?=\d)")
_LEADING_DASH = re.compile(rf"^[ \t]*[{DASHES}][ \t]*", re.MULTILINE)
_DASH = re.compile(rf"\s*[{DASHES}]\s*")


def remove_dashes(markdown: str) -> str:
    """markdown with every em/en dash outside code blocks rewritten."""
    parts = markdown.split(CODE_FENCE)
    # Even-numbered parts are outside fences; odd ones are code.
    for index in range(0, len(parts), 2):
        parts[index] = _rewrite(parts[index])
    return CODE_FENCE.join(parts)


def _rewrite(text: str) -> str:
    text = _RANGE_DASH.sub(" to ", text)
    text = _LEADING_DASH.sub("", text)
    return _DASH.sub(", ", text)
