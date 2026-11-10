"""
Turns an attachment into text the model can read: a file's contents (images and scanned PDFs
through OCR, like the indexer), or the text itself, cut to a size that fits comfortably in a
prompt. Reads only what the user explicitly attached; it never writes anything.
"""

from __future__ import annotations

from pathlib import Path

from core.attachment_format import with_attachment
from core.document_parser import extract_document_text
from core.exceptions import ParsingError
from models.chat import Attachment

MAX_ATTACHMENT_CHARS = 12_000
TRUNCATED_NOTE = "\n[The rest was cut to keep the question short.]"
NO_TEXT_NOTE = "[No readable text was found in this.]"


def attach(text: str, attachment: Attachment) -> str:
    """The user's message with the attachment's text appended."""
    return with_attachment(text, attachment.name, _body(attachment))


def _body(attachment: Attachment) -> str:
    """The attachment's text, trimmed to MAX_ATTACHMENT_CHARS."""
    if attachment.path:
        path = Path(attachment.path)
        if not path.is_file():
            raise ParsingError(f"Couldn't find {path}. It may have been moved or deleted.")
        content = extract_document_text(path)
    else:
        content = attachment.text or ""
    content = content.strip()
    if not content:
        return NO_TEXT_NOTE
    if len(content) > MAX_ATTACHMENT_CHARS:
        return content[:MAX_ATTACHMENT_CHARS] + TRUNCATED_NOTE
    return content
