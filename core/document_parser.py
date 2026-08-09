"""
Converts a file to Markdown text — MarkItDown handles everything by default, Docling
takes over for PDFs whose layout MarkItDown flattens too much to be usable.
Does not chunk, embed, or touch the vector store; it only turns a file into text.
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
from markitdown import MarkItDown  # noqa: E402

from core.exceptions import ParsingError  # noqa: E402
from core.logger import get_logger  # noqa: E402
from models.schema import ParsedDocument  # noqa: E402

logger = get_logger(__name__)

MIN_TEXT_LENGTH = 100


def parse_document(path: Path) -> ParsedDocument:
    """Parses one file, escalating a thin-looking PDF from MarkItDown to Docling before giving up."""
    markdown_text = _parse_with_markitdown(path)
    if path.suffix.lower() == ".pdf" and len(markdown_text) < MIN_TEXT_LENGTH:
        markdown_text = _parse_with_docling(path)
    return ParsedDocument(markdown_text=markdown_text, needs_ocr=len(markdown_text) < MIN_TEXT_LENGTH)


def _parse_with_markitdown(path: Path) -> str:
    """Runs MarkItDown, the default parser for every supported file type."""
    try:
        result = MarkItDown().convert(str(path))
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
