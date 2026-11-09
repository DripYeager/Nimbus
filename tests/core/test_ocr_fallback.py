from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

import core.ocr_fallback as ocr_module
from core.exceptions import ParsingError
from core.ocr_fallback import MAX_OCR_PAGES, _get_engine, _ocr_page, extract_text_with_ocr

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _fake_pdf_document(mocker: MockerFixture, page_count: int) -> MagicMock:
    fake = mocker.MagicMock()
    fake.__len__.return_value = page_count
    fake.__enter__.return_value = fake
    return fake


def _fake_pdf_with_one_page() -> SimpleNamespace:
    page = SimpleNamespace(render=lambda scale: SimpleNamespace(to_pil=lambda: object()))
    return SimpleNamespace(get_page=lambda index: page)


def test_extract_text_with_ocr_recovers_text_from_a_scanned_pdf() -> None:
    text = extract_text_with_ocr(FIXTURES / "scanned.pdf")

    assert "Only OCR can recover this sentence" in text


def test_extract_text_with_ocr_joins_multiple_pages(mocker: MockerFixture) -> None:
    mocker.patch("core.ocr_fallback.pdfium.PdfDocument", return_value=_fake_pdf_document(mocker, 2))
    mocker.patch("core.ocr_fallback._ocr_page", side_effect=["page one", "page two"])

    assert extract_text_with_ocr(Path("multi.pdf")) == "page one\n\npage two"


def test_extract_text_with_ocr_skips_blank_pages(mocker: MockerFixture) -> None:
    mocker.patch("core.ocr_fallback.pdfium.PdfDocument", return_value=_fake_pdf_document(mocker, 2))
    mocker.patch("core.ocr_fallback._ocr_page", side_effect=["", "found this"])

    assert extract_text_with_ocr(Path("mostly-blank.pdf")) == "found this"


def test_extract_text_with_ocr_stops_after_the_page_cap(mocker: MockerFixture) -> None:
    mocker.patch("core.ocr_fallback.pdfium.PdfDocument", return_value=_fake_pdf_document(mocker, MAX_OCR_PAGES + 10))
    ocr_page = mocker.patch("core.ocr_fallback._ocr_page", return_value="text")

    extract_text_with_ocr(Path("scanned-book.pdf"))

    assert ocr_page.call_count == MAX_OCR_PAGES


def test_extract_text_with_ocr_raises_parsing_error_for_a_missing_file() -> None:
    with pytest.raises(ParsingError):
        extract_text_with_ocr(FIXTURES / "does-not-exist.pdf")


def test_ocr_page_joins_the_detected_lines(mocker: MockerFixture) -> None:
    mocker.patch("core.ocr_fallback._get_engine", return_value=lambda image: SimpleNamespace(txts=("line 1", "line 2")))

    assert _ocr_page(_fake_pdf_with_one_page(), 0) == "line 1\nline 2"


def test_ocr_page_returns_empty_when_nothing_is_detected(mocker: MockerFixture) -> None:
    mocker.patch("core.ocr_fallback._get_engine", return_value=lambda image: SimpleNamespace(txts=None))

    assert _ocr_page(_fake_pdf_with_one_page(), 0) == ""


def test_ocr_page_raises_parsing_error_when_rendering_fails(mocker: MockerFixture) -> None:
    broken_page = SimpleNamespace(render=mocker.Mock(side_effect=RuntimeError("boom")))

    with pytest.raises(ParsingError):
        _ocr_page(SimpleNamespace(get_page=lambda index: broken_page), 0)


def test_get_engine_loads_the_model_once(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> None:
    monkeypatch.setattr(ocr_module, "_engine", None)
    engine_cls = mocker.patch("core.ocr_fallback.RapidOCR")

    first = _get_engine()

    assert _get_engine() is first
    engine_cls.assert_called_once()
