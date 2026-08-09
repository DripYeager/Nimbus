from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from core.exceptions import ParsingError
from core.ocr_fallback import extract_text_with_ocr

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_extract_text_with_ocr_recovers_text_from_a_scanned_pdf() -> None:
    text = extract_text_with_ocr(FIXTURES / "scanned.pdf")
    assert "Nimbus Scanned Fixture" in text
    assert "Only OCR can recover this sentence" in text


def _fake_pdf_document(mocker: MockerFixture, page_count: int) -> object:
    fake = mocker.MagicMock()
    fake.__len__.return_value = page_count
    fake.__enter__.return_value = fake
    return fake


def test_extract_text_with_ocr_joins_multiple_pages(mocker: MockerFixture) -> None:
    mocker.patch("core.ocr_fallback.pdfium.PdfDocument", return_value=_fake_pdf_document(mocker, 2))
    mocker.patch("core.ocr_fallback._ocr_page", side_effect=["page one", "page two"])
    text = extract_text_with_ocr(Path("multi.pdf"))
    assert text == "page one\n\npage two"


def test_extract_text_with_ocr_skips_blank_pages(mocker: MockerFixture) -> None:
    mocker.patch("core.ocr_fallback.pdfium.PdfDocument", return_value=_fake_pdf_document(mocker, 2))
    mocker.patch("core.ocr_fallback._ocr_page", side_effect=["", "found this"])
    text = extract_text_with_ocr(Path("mostly-blank.pdf"))
    assert text == "found this"


def test_extract_text_with_ocr_raises_parsing_error_for_a_missing_file() -> None:
    with pytest.raises(ParsingError):
        extract_text_with_ocr(FIXTURES / "does-not-exist.pdf")


def test_ocr_page_raises_parsing_error_when_the_engine_fails(mocker: MockerFixture) -> None:
    from core.ocr_fallback import _ocr_page

    broken_page = SimpleNamespace(render=mocker.Mock(side_effect=RuntimeError("boom")))
    fake_pdf = SimpleNamespace(get_page=lambda i: broken_page)
    with pytest.raises(ParsingError):
        _ocr_page(fake_pdf, 0)


def test_ocr_page_returns_empty_string_when_nothing_is_detected(mocker: MockerFixture) -> None:
    from core.ocr_fallback import _ocr_page

    fake_image = object()
    fake_page = SimpleNamespace(render=lambda scale: SimpleNamespace(to_pil=lambda: fake_image))
    fake_pdf = SimpleNamespace(get_page=lambda i: fake_page)
    mocker.patch("core.ocr_fallback._get_engine", return_value=lambda img: SimpleNamespace(txts=None))
    assert _ocr_page(fake_pdf, 0) == ""
