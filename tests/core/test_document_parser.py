from __future__ import annotations

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from core.document_parser import parse_document
from core.exceptions import ParsingError

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
