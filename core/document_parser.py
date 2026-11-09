"""
Converts a file to plain/Markdown text. Plain-text files are read directly, PDFs go through
pdfium's fast text layer, and every other format goes through MarkItDown. Flags documents whose
text layer is too thin so the OCR fallback can take over. Does not chunk, embed, or touch the
vector store; it only turns a file into text.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

# MarkItDown pulls in magika, which calls load_dotenv() on import and would copy whatever .env
# sits in the working directory into os.environ for the whole process. Nimbus reads .env through
# its own settings loader only.
os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")

import pypdfium2 as pdfium  # noqa: E402
from markitdown import MarkItDown, UnsupportedFormatException  # noqa: E402

from core.exceptions import ParsingError, UnsupportedFileTypeError  # noqa: E402
from core.logger import get_logger  # noqa: E402
from core.ocr_fallback import extract_text_with_ocr  # noqa: E402
from models.schema import ParsedDocument  # noqa: E402

logger = get_logger(__name__)

MIN_TEXT_LENGTH = 100
PLAIN_TEXT_EXTENSIONS = frozenset({".md", ".markdown", ".txt", ".log", ".csv", ".json", ".xml", ".yaml", ".yml"})

_markitdown: MarkItDown | None = None
_markitdown_lock = threading.Lock()


def parse_document(path: Path) -> ParsedDocument:
    """Parses one file and reports whether its text is too thin to be useful without OCR."""
    suffix = path.suffix.lower()
    if suffix in PLAIN_TEXT_EXTENSIONS:
        text = _read_plain_text(path)
    elif suffix == ".pdf":
        text = _read_pdf_text_layer(path)
    else:
        text = _parse_with_markitdown(path)
    return ParsedDocument(markdown_text=text, needs_ocr=len(text) < MIN_TEXT_LENGTH)


def extract_document_text(path: Path) -> str:
    """Parses a file to text, escalating a scanned-looking PDF to OCR."""
    parsed = parse_document(path)
    if parsed.needs_ocr and path.suffix.lower() == ".pdf":
        logger.info("Text layer too thin, running OCR", extra={"path": str(path)})
        return extract_text_with_ocr(path)
    return parsed.markdown_text


def _read_plain_text(path: Path) -> str:
    """Reads text files directly as UTF-8 — MarkItDown's own plain-text converter decodes with
    the system codepage (cp1252 on Windows) and chokes on smart quotes and em dashes."""
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as e:
        raise ParsingError(f"Couldn't read {path}: {e}") from e


def _read_pdf_text_layer(path: Path) -> str:
    """Pulls the embedded text layer out of every page — far faster than layout analysis, and
    exactly as good for search, which doesn't care about columns or tables."""
    try:
        pdf = pdfium.PdfDocument(str(path))
    except Exception as e:
        raise ParsingError(f"Couldn't open PDF {path}: {e}. It may be encrypted or damaged.") from e
    with pdf:
        pages = [_read_pdf_page(pdf, i) for i in range(len(pdf))]
    return "\n\n".join(page for page in pages if page).strip()


def _read_pdf_page(pdf: pdfium.PdfDocument, index: int) -> str:
    """Text of one PDF page, or empty if the page has no text layer."""
    page = pdf.get_page(index)
    try:
        return page.get_textpage().get_text_range().strip()
    finally:
        page.close()


def _get_markitdown() -> MarkItDown:
    """Builds MarkItDown once — constructing it loads every converter plugin."""
    global _markitdown
    with _markitdown_lock:
        if _markitdown is None:
            _markitdown = MarkItDown()
        return _markitdown


def _parse_with_markitdown(path: Path) -> str:
    """Runs MarkItDown, the parser for every office/ebook/email format."""
    try:
        result = _get_markitdown().convert(str(path))
    except UnsupportedFormatException as e:
        raise UnsupportedFileTypeError(f"No converter is available for {path}: {e}") from e
    except Exception as e:
        raise ParsingError(f"Couldn't read {path}: {e}") from e
    return result.text_content.strip()
