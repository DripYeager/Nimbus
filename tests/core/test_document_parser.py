from __future__ import annotations

from pathlib import Path

import pytest
from markitdown import UnsupportedFormatException
from pytest_mock import MockerFixture

import core.document_parser as parser_module
from core.document_parser import _get_markitdown, extract_document_pages, extract_document_text, parse_document
from core.exceptions import ParsingError, UnsupportedFileTypeError
from models.schema import ParsedDocument

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_document_extracts_text_from_a_docx() -> None:
    assert "Nimbus Test Document" in parse_document(FIXTURES / "sample.docx").markdown_text


def test_parse_document_extracts_text_from_a_pptx() -> None:
    assert "Nimbus Test Slide" in parse_document(FIXTURES / "sample.pptx").markdown_text


def test_parse_document_extracts_text_from_an_xlsx() -> None:
    assert "Widget" in parse_document(FIXTURES / "sample.xlsx").markdown_text


def test_parse_document_reads_a_digital_pdf_from_its_text_layer(mocker: MockerFixture) -> None:
    markitdown_spy = mocker.patch("core.document_parser._parse_with_markitdown")

    result = parse_document(FIXTURES / "sample.pdf")

    assert "Nimbus Test PDF" in result.markdown_text
    markitdown_spy.assert_not_called()


def test_parse_document_flags_a_scanned_pdf_for_ocr() -> None:
    assert parse_document(FIXTURES / "scanned.pdf").needs_ocr is True


def test_parse_document_raises_parsing_error_for_a_damaged_pdf(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"this is not really a pdf")

    with pytest.raises(ParsingError):
        parse_document(broken)


def test_parse_document_raises_parsing_error_for_a_missing_docx() -> None:
    with pytest.raises(ParsingError):
        parse_document(FIXTURES / "does-not-exist.docx")


def test_parse_document_reads_a_txt_file_without_markitdown(tmp_path: Path, mocker: MockerFixture) -> None:
    markitdown_spy = mocker.patch("core.document_parser._parse_with_markitdown")
    note = tmp_path / "note.txt"
    note.write_text("  plain ascii text \n", encoding="utf-8")

    assert parse_document(note).markdown_text == "plain ascii text"
    markitdown_spy.assert_not_called()


def test_parse_document_reads_non_ascii_markdown_as_utf8(tmp_path: Path) -> None:
    notes = tmp_path / "notes.md"
    notes.write_text("Smart quotes: “Hello” — an em dash too. " * 5, encoding="utf-8")

    result = parse_document(notes)

    assert "“Hello” —" in result.markdown_text
    assert result.needs_ocr is False


def test_parse_document_flags_thin_text_as_needing_ocr(tmp_path: Path) -> None:
    note = tmp_path / "short.txt"
    note.write_text("too short", encoding="utf-8")

    assert parse_document(note).needs_ocr is True


def test_parse_document_raises_parsing_error_for_a_missing_text_file(tmp_path: Path) -> None:
    with pytest.raises(ParsingError):
        parse_document(tmp_path / "does-not-exist.md")


def test_parse_document_raises_unsupported_file_type_error_when_no_converter_fits(mocker: MockerFixture) -> None:
    converter = mocker.patch("core.document_parser._get_markitdown").return_value
    converter.convert.side_effect = UnsupportedFormatException("no converter found")

    with pytest.raises(UnsupportedFileTypeError):
        parse_document(Path("model.blend"))


def test_get_markitdown_builds_the_converter_once(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> None:
    monkeypatch.setattr(parser_module, "_markitdown", None)
    markitdown_cls = mocker.patch("core.document_parser.MarkItDown")

    first = _get_markitdown()

    assert _get_markitdown() is first
    markitdown_cls.assert_called_once()


def test_extract_document_text_returns_the_parsed_text_directly() -> None:
    assert "Nimbus Test Document" in extract_document_text(FIXTURES / "sample.docx")


def test_extract_document_text_escalates_a_thin_pdf_to_ocr(mocker: MockerFixture) -> None:
    mocker.patch("core.document_parser._read_pdf_pages", return_value=["", ""])
    ocr_spy = mocker.patch("core.document_parser.extract_pages_with_ocr", return_value=["recovered text", ""])

    assert extract_document_text(Path("scan.PDF")) == "recovered text"
    ocr_spy.assert_called_once_with(Path("scan.PDF"))


def test_extract_document_text_does_not_ocr_a_thin_non_pdf(mocker: MockerFixture) -> None:
    mocker.patch("core.document_parser.parse_document", return_value=ParsedDocument(markdown_text="", needs_ocr=True))
    ocr_spy = mocker.patch("core.document_parser.extract_pages_with_ocr")

    assert extract_document_text(Path("note.txt")) == ""
    ocr_spy.assert_not_called()


def test_extract_document_pages_numbers_pdf_pages_and_skips_blank_ones(mocker: MockerFixture) -> None:
    mocker.patch("core.document_parser._read_pdf_pages", return_value=["intro " * 20, "", "terms " * 20])

    pages = extract_document_pages(Path("contract.pdf"))

    assert [page.number for page in pages] == [1, 3]


def test_extract_document_pages_keeps_ocr_page_numbers(mocker: MockerFixture) -> None:
    mocker.patch("core.document_parser._read_pdf_pages", return_value=["", ""])
    mocker.patch("core.document_parser.extract_pages_with_ocr", return_value=["", "scanned page two"])

    pages = extract_document_pages(Path("scan.pdf"))

    assert [(page.number, page.text) for page in pages] == [(2, "scanned page two")]


def test_extract_document_pages_gives_other_formats_one_unnumbered_page(mocker: MockerFixture) -> None:
    mocker.patch(
        "core.document_parser.parse_document", return_value=ParsedDocument(markdown_text="notes", needs_ocr=False)
    )

    assert [(p.number, p.text) for p in extract_document_pages(Path("a.docx"))] == [(None, "notes")]


def test_extract_document_pages_is_empty_for_a_file_without_text(mocker: MockerFixture) -> None:
    mocker.patch("core.document_parser.parse_document", return_value=ParsedDocument(markdown_text="", needs_ocr=True))

    assert extract_document_pages(Path("empty.txt")) == []


def test_parse_document_reads_images_with_ocr(tmp_path: Path, mocker: MockerFixture) -> None:
    ocr = mocker.patch("core.document_parser.extract_text_from_image", return_value="whiteboard notes")
    photo = tmp_path / "board.JPG"
    photo.write_bytes(b"jpeg")

    result = parse_document(photo)

    ocr.assert_called_once_with(photo)
    assert (result.markdown_text, result.needs_ocr) == ("whiteboard notes", False)
