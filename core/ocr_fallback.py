"""
Reads text out of pictures with the OCR engine built into Windows (Windows.Media.Ocr), so
there's nothing to download or install and no admin rights needed. Two callers: scanned PDFs
whose text layer is too thin (each page is rendered with pdfium first), and image files such as
screenshots and photos of whiteboards.
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
# Smaller than this is an icon or a thumbnail, not something with readable text.
MIN_IMAGE_SIDE_PX = 200
# Images whose short side is under this are enlarged (at most MAX_ENLARGE_FACTOR times) first.
SMALL_IMAGE_SIDE_PX = 600
MAX_ENLARGE_FACTOR = 4

_engine: OcrEngine | None = None
_engine_checked = False
_engine_lock = threading.Lock()


def extract_text_with_ocr(path: Path) -> str:
    """OCRs the first MAX_OCR_PAGES pages of a PDF and returns their text, page by page.
    Returns "" when Windows has no OCR language installed (logged once)."""
    return "\n\n".join(text for text in extract_pages_with_ocr(path) if text)


def extract_pages_with_ocr(path: Path) -> list[str]:
    """Each of the first MAX_OCR_PAGES pages' OCR text, in page order ("" for a blank page).
    Empty when Windows has no OCR language installed."""
    engine = _get_engine()
    if engine is None:
        return []
    try:
        pdf = pdfium.PdfDocument(str(path))
    except Exception as e:
        raise ParsingError(f"Couldn't open {path} for OCR: {e}") from e
    with pdf:
        return [_ocr_page(engine, pdf, i) for i in range(min(len(pdf), MAX_OCR_PAGES))]


def extract_text_from_image(path: Path, skip_icons: bool = True) -> str:
    """OCRs one image file. Returns "" when Windows has no OCR language installed, and, with
    skip_icons, for images too small to be anything but an icon (right for indexing a folder;
    a screenshot the user boxed on purpose is read however small it is)."""
    try:
        with Image.open(path) as opened:
            image = opened.convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError) as e:
        raise ParsingError(f"Couldn't open image {path}: {e}") from e
    if skip_icons and min(image.size) < MIN_IMAGE_SIDE_PX:
        return ""
    engine = _get_engine()
    if engine is None:
        return ""
    try:
        return asyncio.run(_recognize(engine, _fit(_enlarge_small(image), OcrEngine.max_image_dimension)))
    except Exception as e:
        raise ParsingError(f"OCR failed on {path}: {e}") from e


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


def _enlarge_small(image: Image.Image) -> Image.Image:
    """Scales a small capture up: OCR misses text only a few pixels tall, so a crop of a
    single line reads far better at two or three times the size."""
    shortest = min(image.size)
    if shortest >= SMALL_IMAGE_SIDE_PX:
        return image
    factor = min(MAX_ENLARGE_FACTOR, -(-SMALL_IMAGE_SIDE_PX // max(shortest, 1)))
    return image.resize((image.width * factor, image.height * factor), Image.Resampling.LANCZOS)


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
