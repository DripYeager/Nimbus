"""
Last-resort text extraction for scanned/image-only PDFs — rasterizes each page and runs local OCR.
Only called when document_parser reports too little extracted text; never the default path.
"""

from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
from rapidocr import RapidOCR

from core.exceptions import ParsingError
from core.logger import get_logger

logger = get_logger(__name__)

# OCR runs at roughly a second per page on a laptop CPU; past this, a scanned book would hold
# up the whole index queue for many minutes for little search value.
MAX_OCR_PAGES = 40

_engine: RapidOCR | None = None


def _get_engine() -> RapidOCR:
    """Loads the OCR engine once and reuses it across calls — model load is the expensive part."""
    global _engine
    if _engine is None:
        _engine = RapidOCR()
    return _engine


def extract_text_with_ocr(path: Path) -> str:
    """Rasterizes the first MAX_OCR_PAGES pages of a PDF and OCRs them, returning the joined text."""
    try:
        pdf = pdfium.PdfDocument(str(path))
    except Exception as e:
        raise ParsingError(f"Couldn't open {path} for OCR: {e}") from e
    with pdf:
        page_texts = [_ocr_page(pdf, i) for i in range(min(len(pdf), MAX_OCR_PAGES))]
    return "\n\n".join(text for text in page_texts if text)


def _ocr_page(pdf: pdfium.PdfDocument, page_index: int) -> str:
    """Renders one page to an image at 2x scale and runs OCR over it."""
    try:
        image = pdf.get_page(page_index).render(scale=2).to_pil()
        result = _get_engine()(image)
    except Exception as e:
        raise ParsingError(f"OCR failed on page {page_index} of {pdf}: {e}") from e
    return "\n".join(result.txts) if result.txts else ""
