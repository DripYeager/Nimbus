from __future__ import annotations

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from core.document_parser import extract_document_text, parse_document
from core.exceptions import ParsingError
from models.schema import ParsedDocument

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_document_extracts_text_from_a_docx() -> None:
    result = parse_document(FIXTURES / "sample.docx")
    assert "Nimbus Test Document" in result.markdown_text
    assert not result.needs_ocr


def test_parse_document_extracts_text_from_a_pptx() -> None:
    result = parse_document(FIXTURES / "sample.pptx")
    assert "Nimbus Test Slide" in result.markdown_text
    assert not result.needs_ocr


def test_parse_document_extracts_text_from_an_xlsx() -> None:
    result = parse_document(FIXTURES / "sample.xlsx")
    assert "Widget" in result.markdown_text
    assert not result.needs_ocr


def test_parse_document_extracts_text_from_a_digital_pdf_without_docling(mocker: MockerFixture) -> None:
    docling_spy = mocker.patch("core.document_parser._parse_with_docling")
    result = parse_document(FIXTURES / "sample.pdf")
    assert "Nimbus Test PDF" in result.markdown_text
    assert not result.needs_ocr
    docling_spy.assert_not_called()


def test_parse_document_falls_back_to_docling_for_a_thin_pdf(mocker: MockerFixture) -> None:
    mocker.patch("core.document_parser._parse_with_markitdown", return_value="short")
    mocker.patch("core.document_parser._parse_with_docling", return_value="a" * 200)
    result = parse_document(Path("report.pdf"))
    assert result.markdown_text == "a" * 200
    assert not result.needs_ocr


def test_parse_document_flags_needs_ocr_when_docling_is_also_thin(mocker: MockerFixture) -> None:
    mocker.patch("core.document_parser._parse_with_markitdown", return_value="short")
    mocker.patch("core.document_parser._parse_with_docling", return_value="still short")
    result = parse_document(Path("scanned.pdf"))
    assert result.needs_ocr


def test_parse_document_flags_needs_ocr_for_a_thin_non_pdf_without_trying_docling(mocker: MockerFixture) -> None:
    mocker.patch("core.document_parser._parse_with_markitdown", return_value="short")
    docling_spy = mocker.patch("core.document_parser._parse_with_docling")
    result = parse_document(Path("note.txt"))
    assert result.needs_ocr
    docling_spy.assert_not_called()


def test_parse_document_raises_parsing_error_for_a_missing_file() -> None:
    with pytest.raises(ParsingError):
        parse_document(FIXTURES / "does-not-exist.docx")


def test_extract_document_text_returns_the_parsed_text_directly() -> None:
    assert "Nimbus Test Document" in extract_document_text(FIXTURES / "sample.docx")


def test_extract_document_text_escalates_a_thin_pdf_to_ocr(mocker: MockerFixture) -> None:
    mocker.patch(
        "core.document_parser.parse_document", return_value=ParsedDocument(markdown_text="", needs_ocr=True)
    )
    ocr_spy = mocker.patch("core.document_parser.extract_text_with_ocr", return_value="recovered text")
    result = extract_document_text(Path("scan.pdf"))
    ocr_spy.assert_called_once_with(Path("scan.pdf"))
    assert result == "recovered text"


def test_extract_document_text_does_not_ocr_a_thin_non_pdf(mocker: MockerFixture) -> None:
    mocker.patch("core.document_parser.parse_document", return_value=ParsedDocument(markdown_text="", needs_ocr=True))
    ocr_spy = mocker.patch("core.document_parser.extract_text_with_ocr")
    result = extract_document_text(Path("note.txt"))
    ocr_spy.assert_not_called()
    assert result == ""
