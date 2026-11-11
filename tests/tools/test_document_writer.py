from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document
from openpyxl import load_workbook

from core.exceptions import ToolError
from tools.document_writer import (
    DOCUMENT_SUFFIXES,
    SPREADSHEET_SUFFIXES,
    unique_path,
    write_document,
    write_spreadsheet,
)

MARKDOWN = """# Trip plan

Leave on **Friday** morning.

## Packing
- Passport
- Charger

1. Book the hotel
2. Rent a car

| City | Nights |
|---|---|
| Ajmer | 2 |
"""


def test_unique_path_keeps_a_free_name(tmp_path: Path) -> None:
    assert unique_path(tmp_path, "plan.docx", DOCUMENT_SUFFIXES) == tmp_path / "plan.docx"


def test_unique_path_uses_the_last_free_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tools.document_writer.MAX_COPIES", 2)
    (tmp_path / "plan.docx").write_bytes(b"mine")

    assert unique_path(tmp_path, "plan.docx", DOCUMENT_SUFFIXES) == tmp_path / "plan (2).docx"


def test_unique_path_renames_a_windows_device_name(tmp_path: Path) -> None:
    assert unique_path(tmp_path, "nul.txt", DOCUMENT_SUFFIXES).name == "nul_.txt"


def test_unique_path_never_reuses_an_existing_file(tmp_path: Path) -> None:
    (tmp_path / "plan.docx").write_bytes(b"mine")
    (tmp_path / "plan (2).docx").write_bytes(b"mine too")

    assert unique_path(tmp_path, "plan.docx", DOCUMENT_SUFFIXES) == tmp_path / "plan (3).docx"


def test_unique_path_strips_characters_windows_forbids(tmp_path: Path) -> None:
    assert unique_path(tmp_path, 'Q3: "final"?.xlsx', SPREADSHEET_SUFFIXES).name == "Q3 final.xlsx"


@pytest.mark.parametrize("name", ["plan.exe", "plan", ".docx"])
def test_unique_path_rejects_other_or_missing_extensions(tmp_path: Path, name: str) -> None:
    with pytest.raises(ToolError):
        unique_path(tmp_path, name, DOCUMENT_SUFFIXES)


def test_write_document_writes_text_as_is(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"

    write_document(path, "  hello\nworld  ")

    assert path.read_text(encoding="utf-8") == "hello\nworld\n"


def test_write_document_builds_a_real_word_file_from_markdown(tmp_path: Path) -> None:
    path = tmp_path / "trip.docx"

    write_document(path, MARKDOWN)

    document = Document(str(path))
    styles = [(p.style.name, p.text) for p in document.paragraphs if p.text]
    assert ("Heading 1", "Trip plan") in styles
    assert ("List Bullet", "Passport") in styles
    assert ("List Number", "Book the hotel") in styles
    assert [cell.text for cell in document.tables[0].rows[1].cells] == ["Ajmer", "2"]


def test_write_document_makes_double_starred_text_bold(tmp_path: Path) -> None:
    path = tmp_path / "trip.docx"

    write_document(path, "Leave on **Friday** morning.")

    runs = Document(str(path)).paragraphs[0].runs
    assert [(r.text, bool(r.bold)) for r in runs] == [("Leave on ", False), ("Friday", True), (" morning.", False)]


def test_write_spreadsheet_makes_an_excel_file_with_real_numbers(tmp_path: Path) -> None:
    path = tmp_path / "budget.xlsx"

    rows = write_spreadsheet(path, 'Item,Cost\nHotel,4500\nCar,"1,200.50"\n', "Budget")

    sheet = load_workbook(path)["Budget"]
    assert rows == 2
    assert [c.value for c in sheet[1]] == ["Item", "Cost"]
    assert (sheet["B2"].value, sheet["B3"].value) == (4500, 1200.5)
    assert sheet["A1"].font.bold and sheet.freeze_panes == "A2"


def test_write_spreadsheet_writes_csv(tmp_path: Path) -> None:
    path = tmp_path / "budget.csv"

    write_spreadsheet(path, "Item,Cost\nHotel,4500")

    assert path.read_text(encoding="utf-8-sig").splitlines() == ["Item,Cost", "Hotel,4500"]


def test_write_document_makes_bold_text_inside_a_heading(tmp_path: Path) -> None:
    path = tmp_path / "trip.docx"

    write_document(path, "# Pack **this**")

    runs = [run for run in Document(str(path)).paragraphs[0].runs if run.text]
    assert [(run.text, bool(run.bold)) for run in runs] == [("Pack ", False), ("this", True)]


def test_write_document_ignores_a_separator_line_that_is_not_a_table(tmp_path: Path) -> None:
    path = tmp_path / "notes.docx"

    write_document(path, "Hello\n|---|\nThere")

    document = Document(str(path))
    assert document.tables == []
    assert [paragraph.text for paragraph in document.paragraphs if paragraph.text] == ["Hello", "There"]


def test_write_spreadsheet_keeps_a_short_comma_as_text_and_cleans_the_sheet_name(tmp_path: Path) -> None:
    path = tmp_path / "codes.xlsx"

    write_spreadsheet(path, 'Code\n"1,2"', "Q1 [draft]")

    sheet = load_workbook(path).active
    assert sheet.title == "Q1 draft"
    assert sheet["A2"].value == "1,2"


def test_write_spreadsheet_refuses_an_empty_table(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="no rows"):
        write_spreadsheet(tmp_path / "empty.xlsx", "  \n ")


def test_write_spreadsheet_keeps_leading_zeros_as_text(tmp_path: Path) -> None:
    path = tmp_path / "ids.xlsx"

    write_spreadsheet(path, "Id,Zip,Price\n007,02134,0.5")

    sheet = load_workbook(path).active
    assert [sheet["A2"].value, sheet["B2"].value, sheet["C2"].value] == ["007", "02134", 0.5]


def test_write_spreadsheet_keeps_long_card_numbers_exact(tmp_path: Path) -> None:
    path = tmp_path / "cards.xlsx"

    write_spreadsheet(path, "Card,Amount\n4111111111111111111,1,200")

    sheet = load_workbook(path).active
    assert sheet["A2"].value == "4111111111111111111"


def test_write_spreadsheet_never_ends_a_sheet_name_in_an_apostrophe(tmp_path: Path) -> None:
    path = tmp_path / "named.xlsx"
    name = "a" * 30 + "'b"

    write_spreadsheet(path, "x\n1", name)

    assert not load_workbook(path).active.title.endswith("'")
