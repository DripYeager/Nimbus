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


def test_write_spreadsheet_refuses_an_empty_table(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="no rows"):
        write_spreadsheet(tmp_path / "empty.xlsx", "  \n ")
