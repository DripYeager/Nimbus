"""
Last-resort text extraction for scanned/image-only PDFs: renders each page with pdfium and reads
it with the OCR engine built into Windows (Windows.Media.Ocr), so there's nothing to download or
install and no admin rights needed. Only called when document_parser finds too little text;
never the default path.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image
from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter

from core.exceptions import ParsingError
from core.logger import get_logger

logger = get_logger(__name__)

# Past this, a scanned book would hold up the index queue for little search value.
MAX_OCR_PAGES = 40
RENDER_SCALE = 2.0

_engine: OcrEngine | None = None
_engine_checked = False
_engine_lock = threading.Lock()


def extract_text_with_ocr(path: Path) -> str:
    """OCRs the first MAX_OCR_PAGES pages of a PDF and returns their text, page by page.
    Returns "" when Windows has no OCR language installed (logged once)."""
    engine = _get_engine()
    if engine is None:
        return ""
    try:
        pdf = pdfium.PdfDocument(str(path))
    except Exception as e:
        raise ParsingError(f"Couldn't open {path} for OCR: {e}") from e
    with pdf:
        page_texts = [_ocr_page(engine, pdf, i) for i in range(min(len(pdf), MAX_OCR_PAGES))]
    return "\n\n".join(text for text in page_texts if text)


def _get_engine() -> OcrEngine | None:
    """The OCR engine for the user's display languages, created once."""
    global _engine, _engine_checked
    with _engine_lock:
        if not _engine_checked:
            _engine_checked = True
            _engine = OcrEngine.try_create_from_user_profile_languages()
            if _engine is None:
                logger.warning(
                    "Windows OCR isn't available for your languages, so scanned PDFs will only be "
                    "searchable by name. Add a language with OCR support in Windows Settings > Language."
                )
        return _engine


def _ocr_page(engine: OcrEngine, pdf: pdfium.PdfDocument, index: int) -> str:
    """Renders one page and returns its recognized lines."""
    try:
        page = pdf.get_page(index)
        try:
            image = page.render(scale=RENDER_SCALE).to_pil()
        finally:
            page.close()
        return asyncio.run(_recognize(engine, _fit(image, OcrEngine.max_image_dimension)))
    except Exception as e:
        raise ParsingError(f"OCR failed on page {index + 1} of {pdf}: {e}") from e


def _fit(image: Image.Image, max_dimension: int) -> Image.Image:
    """Shrinks a page bigger than the engine accepts, keeping its aspect ratio."""
    if max(image.size) > max_dimension:
        image.thumbnail((max_dimension, max_dimension))
    return image


async def _recognize(engine: OcrEngine, image: Image.Image) -> str:
    """Hands the pixels to Windows as a BGRA bitmap and joins the recognized lines."""
    writer = DataWriter()
    writer.write_bytes(image.convert("RGBA").tobytes("raw", "BGRA"))
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        writer.detach_buffer(), BitmapPixelFormat.BGRA8, image.width, image.height, BitmapAlphaMode.PREMULTIPLIED
    )
    result = await engine.recognize_async(bitmap)
    return "\n".join(line.text for line in result.lines)
