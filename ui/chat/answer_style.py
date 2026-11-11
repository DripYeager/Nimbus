"""
House style for answers on screen. Models, small local ones especially, leave things a reader
shouldn't see, so they're cleaned before display and copying:
- stray markup from their own training: <tool_code>, <tool_call>, <think> blocks and special
  tokens like <|im_end|>, including a block still open while the answer streams in;
- em and en dashes: a number range becomes "4 to 5" and any other dash becomes a comma.
Code blocks are left exactly as written. Pure text; nothing is drawn here.
"""

from __future__ import annotations

import re

CODE_FENCE = "```"
# Written as escapes (en dash, em dash) so the characters themselves never appear in the source.
DASHES = "\u2013\u2014"
_RANGE_DASH = re.compile(rf"(?<=\d)\s*[{DASHES}]\s*(?=\d)")
_LEADING_DASH = re.compile(rf"^[ \t]*[{DASHES}][ \t]*", re.MULTILINE)
_DASH = re.compile(rf"\s*[{DASHES}]\s*")
STRAY_TAGS = ("tool_code", "tool_call", "tool_response", "think", "function_call")
_TAG_NAMES = "|".join(STRAY_TAGS)
_CLOSED_BLOCK = re.compile(rf"<({_TAG_NAMES})>.*?</\1>", re.DOTALL | re.IGNORECASE)
# A block whose closing tag hasn't streamed in yet hides everything after its opening tag.
_OPEN_BLOCK = re.compile(rf"<({_TAG_NAMES})>.*\Z", re.DOTALL | re.IGNORECASE)
_LONE_TAG = re.compile(rf"</?({_TAG_NAMES})>", re.IGNORECASE)
_SPECIAL_TOKEN = re.compile(r"<\|[^|>]{1,40}\|>")
_EXTRA_BLANK_LINES = re.compile(r"\n{3,}")


def clean_answer(markdown: str) -> str:
    """markdown as it should be shown: stray model markup removed, dashes rewritten."""
    parts = markdown.split(CODE_FENCE)
    # Even-numbered parts are outside fences; odd ones are code.
    for index in range(0, len(parts), 2):
        parts[index] = _rewrite_dashes(_strip_markup(parts[index]))
    return CODE_FENCE.join(parts).strip()


def _strip_markup(text: str) -> str:
    text = _CLOSED_BLOCK.sub("", text)
    text = _OPEN_BLOCK.sub("", text)
    text = _LONE_TAG.sub("", text)
    text = _SPECIAL_TOKEN.sub("", text)
    return _EXTRA_BLANK_LINES.sub("\n\n", text)


def _rewrite_dashes(text: str) -> str:
    text = _RANGE_DASH.sub(" to ", text)
    text = _LEADING_DASH.sub("", text)
    return _DASH.sub(", ", text)
