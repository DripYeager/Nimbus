"""
Converts a file to Markdown text: markdown/plain-text files are read directly, MarkItDown
handles every other format by default, and Docling takes over for PDFs whose layout MarkItDown
flattens too much to be usable. Does not chunk, embed, or touch the vector store; it only turns
a file into text.
"""

from __future__ import annotations

import os

# Docling's layout model tries to JIT-compile itself via torch.compile, which needs an MSVC
# compiler most machines - especially a no-admin corporate laptop - won't have. Must be set
# before docling (and the torch it pulls in) is imported.
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

from pathlib import Path  # noqa: E402

from docling.datamodel.base_models import InputFormat  # noqa: E402
from docling.datamodel.pipeline_options import PdfPipelineOptions  # noqa: E402
from docling.document_converter import DocumentConverter, PdfFormatOption  # noqa: E402
from markitdown import MarkItDown, UnsupportedFormatException  # noqa: E402

from core.exceptions import ParsingError, UnsupportedFileTypeError  # noqa: E402
from core.logger import get_logger  # noqa: E402
from core.ocr_fallback import extract_text_with_ocr  # noqa: E402
from models.schema import ParsedDocument  # noqa: E402

logger = get_logger(__name__)

MIN_TEXT_LENGTH = 100
PLAIN_TEXT_EXTENSIONS = frozenset({".md", ".txt"})


def parse_document(path: Path) -> ParsedDocument:
    """Parses one file, escalating a thin-looking PDF from MarkItDown to Docling before giving up."""
    markdown_text = _extract_text(path)
    if path.suffix.lower() == ".pdf" and len(markdown_text) < MIN_TEXT_LENGTH:
        markdown_text = _parse_with_docling(path)
    return ParsedDocument(markdown_text=markdown_text, needs_ocr=len(markdown_text) < MIN_TEXT_LENGTH)


def _extract_text(path: Path) -> str:
    """Routes markdown/plain-text files to a direct read, everything else to MarkItDown."""
    if path.suffix.lower() in PLAIN_TEXT_EXTENSIONS:
        return _read_plain_text(path)
    return _parse_with_markitdown(path)


def _read_plain_text(path: Path) -> str:
    """Reads markdown/text files directly — no conversion needed, and MarkItDown's own plain-text
    converter decodes with the system codepage (cp1252 on Windows) instead of UTF-8, raising
    UnicodeDecodeError on any smart quote, em dash, or other non-ASCII character."""
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as e:
        raise ParsingError(f"Couldn't read {path}: {e}") from e


def extract_document_text(path: Path) -> str:
    """Parses a file to text, escalating to OCR too when even Docling's result is too thin."""
    parsed = parse_document(path)
    if parsed.needs_ocr and path.suffix.lower() == ".pdf":
        return extract_text_with_ocr(path)
    return parsed.markdown_text


def _parse_with_markitdown(path: Path) -> str:
    """Runs MarkItDown, the default parser for every supported file type."""
    try:
        result = MarkItDown().convert(str(path))
    except UnsupportedFormatException as e:
        raise UnsupportedFileTypeError(f"No MarkItDown converter is available for {path}: {e}") from e
    except Exception as e:
        raise ParsingError(f"MarkItDown couldn't read {path}: {e}") from e
    return result.text_content.strip()


def _parse_with_docling(path: Path) -> str:
    """Runs Docling for its layout/table structure only — OCR is handled by our own
    ocr_fallback module, so it's turned off here to avoid loading a second OCR engine."""
    pipeline_options = PdfPipelineOptions(do_ocr=False)
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)})
    try:
        result = converter.convert(str(path))
    except Exception as e:
        raise ParsingError(f"Docling couldn't read {path}: {e}") from e
    return result.document.export_to_markdown().strip()
