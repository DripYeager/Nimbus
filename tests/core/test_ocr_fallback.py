from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image
from pytest_mock import MockerFixture

import core.ocr_fallback as ocr_module
from core.exceptions import ParsingError
from core.ocr_fallback import MAX_OCR_PAGES, _fit, _get_engine, _ocr_page, extract_text_with_ocr

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(autouse=True)
def _fresh_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_module, "_engine", None)
    monkeypatch.setattr(ocr_module, "_engine_checked", False)


def _windows_ocr_available() -> bool:
    return ocr_module.OcrEngine.try_create_from_user_profile_languages() is not None


def _fake_pdf(mocker: MockerFixture, page_count: int) -> MagicMock:
    pdf = mocker.MagicMock()
    pdf.__len__.return_value = page_count
    pdf.__enter__.return_value = pdf
    mocker.patch("core.ocr_fallback.pdfium.PdfDocument", return_value=pdf)
    return pdf


def _engine_with_pages(mocker: MockerFixture, texts: list[str]) -> None:
    mocker.patch("core.ocr_fallback._get_engine", return_value=object())
    mocker.patch("core.ocr_fallback._ocr_page", side_effect=texts)


@pytest.mark.skipif(not _windows_ocr_available(), reason="Windows has no OCR language installed here")
def test_extract_text_with_ocr_recovers_text_from_a_scanned_pdf() -> None:
    text = extract_text_with_ocr(FIXTURES / "scanned.pdf")

    assert "Only OCR can recover this sentence" in text


def test_extract_text_with_ocr_joins_multiple_pages(mocker: MockerFixture) -> None:
    _fake_pdf(mocker, page_count=2)
    _engine_with_pages(mocker, ["page one", "page two"])

    assert extract_text_with_ocr(Path("scan.pdf")) == "page one\n\npage two"


def test_extract_text_with_ocr_skips_blank_pages(mocker: MockerFixture) -> None:
    _fake_pdf(mocker, page_count=3)
    _engine_with_pages(mocker, ["first", "", "third"])

    assert extract_text_with_ocr(Path("scan.pdf")) == "first\n\nthird"


def test_extract_text_with_ocr_stops_after_the_page_cap(mocker: MockerFixture) -> None:
    _fake_pdf(mocker, page_count=MAX_OCR_PAGES + 10)
    _engine_with_pages(mocker, ["x"] * MAX_OCR_PAGES)

    extract_text_with_ocr(Path("book.pdf"))

    assert ocr_module._ocr_page.call_count == MAX_OCR_PAGES


def test_extract_text_with_ocr_returns_empty_without_an_ocr_language(mocker: MockerFixture) -> None:
    mocker.patch("core.ocr_fallback._get_engine", return_value=None)
    opened = mocker.patch("core.ocr_fallback.pdfium.PdfDocument")

    assert extract_text_with_ocr(Path("scan.pdf")) == ""
    opened.assert_not_called()


def test_extract_text_with_ocr_raises_parsing_error_for_a_missing_file(mocker: MockerFixture) -> None:
    mocker.patch("core.ocr_fallback._get_engine", return_value=object())

    with pytest.raises(ParsingError):
        extract_text_with_ocr(Path("does-not-exist.pdf"))


def test_ocr_page_joins_the_recognized_lines(mocker: MockerFixture) -> None:
    page = mocker.MagicMock()
    page.render.return_value.to_pil.return_value = Image.new("RGB", (40, 20), "white")
    pdf = mocker.MagicMock()
    pdf.get_page.return_value = page
    engine = mocker.MagicMock()

    async def recognize(bitmap: object) -> SimpleNamespace:
        return SimpleNamespace(lines=[SimpleNamespace(text="line 1"), SimpleNamespace(text="line 2")])

    engine.recognize_async.side_effect = recognize

    assert _ocr_page(engine, pdf, 0) == "line 1\nline 2"
    page.close.assert_called_once()


def test_ocr_page_raises_parsing_error_when_rendering_fails(mocker: MockerFixture) -> None:
    pdf = mocker.MagicMock()
    pdf.get_page.return_value.render.side_effect = RuntimeError("bad page")

    with pytest.raises(ParsingError, match="page 1"):
        _ocr_page(mocker.MagicMock(), pdf, 0)


def test_fit_shrinks_a_page_larger_than_the_engine_accepts() -> None:
    image = _fit(Image.new("RGB", (4000, 2000)), max_dimension=1000)

    assert image.size == (1000, 500)


def test_fit_leaves_a_normal_page_alone() -> None:
    image = _fit(Image.new("RGB", (800, 600)), max_dimension=1000)

    assert image.size == (800, 600)


def test_get_engine_creates_the_engine_once(mocker: MockerFixture) -> None:
    create = mocker.patch("core.ocr_fallback.OcrEngine.try_create_from_user_profile_languages", return_value="engine")

    assert _get_engine() == "engine"
    assert _get_engine() == "engine"
    create.assert_called_once()


def test_get_engine_logs_once_when_windows_has_no_ocr_language(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    mocker.patch("core.ocr_fallback.OcrEngine.try_create_from_user_profile_languages", return_value=None)

    assert _get_engine() is None
    assert _get_engine() is None
    assert sum("Windows OCR isn't available" in r.getMessage() for r in caplog.records) == 1
