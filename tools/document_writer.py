"""
Writes the new files the assistant creates on request: plain text and Markdown as they are,
Word documents from simple Markdown (headings, bullet and numbered lists, **bold**, tables),
and spreadsheets from CSV text (Excel gets a bold header, real numbers and sized columns).
Never overwrites anything: a name that's taken gets " (2)", " (3)"... Owns file writing only;
which folder is allowed is the toolbox's job.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from core.exceptions import ToolError

DOCUMENT_SUFFIXES = frozenset({".txt", ".md", ".docx"})
SPREADSHEET_SUFFIXES = frozenset({".xlsx", ".csv"})
INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MAX_NAME_CHARS = 120
MAX_COPIES = 999
HEADING = re.compile(r"^(#{1,3})\s+(.*)")
BULLET = re.compile(r"^\s*[-*•]\s+(.*)")
NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)")
TABLE_ROW = re.compile(r"^\s*\|(.*)\|\s*$")
TABLE_RULE = re.compile(r"^[\s|:-]+$")
BOLD = re.compile(r"(\*\*[^*]+\*\*)")
NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
HEADER_FILL = PatternFill("solid", fgColor="FFE0B3")
MAX_COLUMN_WIDTH = 60


def unique_path(folder: Path, file_name: str, allowed: frozenset[str]) -> Path:
    """A free path for file_name in folder, with an allowed extension."""
    name = INVALID_NAME_CHARS.sub("", file_name).strip().strip(".")[:MAX_NAME_CHARS]
    stem, suffix = Path(name).stem, Path(name).suffix.lower()
    if not stem:
        raise ToolError("The file needs a name, like trip-plan.docx.")
    if suffix not in allowed:
        raise ToolError(f"Can't create a {suffix or 'nameless'} file here. Use one of: {', '.join(sorted(allowed))}.")
    candidate = folder / f"{stem}{suffix}"
    for copy in range(2, MAX_COPIES):
        if not candidate.exists():
            return candidate
        candidate = folder / f"{stem} ({copy}){suffix}"
    raise ToolError(f"Too many files named {stem}{suffix} in {folder}.")


def write_document(path: Path, content: str) -> None:
    """Writes text or Markdown as is, or a Word document built from the Markdown."""
    _write(path, lambda: _save_docx(path, content) if path.suffix == ".docx" else _save_text(path, content))


def write_spreadsheet(path: Path, csv_text: str, sheet_name: str = "Sheet1") -> int:
    """Writes CSV text as a .csv or .xlsx file. Returns the number of data rows."""
    rows = [row for row in csv.reader(io.StringIO(csv_text.strip())) if any(cell.strip() for cell in row)]
    if not rows:
        raise ToolError("The spreadsheet has no rows. Send the table as CSV text, header row first.")
    _write(path, lambda: _save_csv(path, rows) if path.suffix == ".csv" else _save_xlsx(path, rows, sheet_name))
    return len(rows) - 1


def _write(path: Path, save: object) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        save()  # type: ignore[operator]
    except OSError as e:
        raise ToolError(f"Couldn't write {path}: {e}. Check the folder is writable.") from e


def _save_text(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _save_csv(path: Path, rows: list[list[str]]) -> None:
    # utf-8-sig so Excel opens accented text correctly when the user double-clicks it.
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle).writerows(rows)


def _save_docx(path: Path, markdown: str) -> None:
    document = Document()
    lines = markdown.strip().splitlines()
    index = 0
    while index < len(lines):
        if TABLE_ROW.match(lines[index]):
            index = _add_table(document, lines, index)
            continue
        _add_line(document, lines[index])
        index += 1
    document.save(str(path))


def _add_line(document: DocxDocument, line: str) -> None:
    """One Markdown line as a heading, list item or paragraph; blank lines are skipped."""
    if not line.strip():
        return
    if heading := HEADING.match(line):
        document.add_heading(heading.group(2).strip(), level=len(heading.group(1)))
    elif bullet := BULLET.match(line):
        _add_runs(document.add_paragraph(style="List Bullet"), bullet.group(1))
    elif numbered := NUMBERED.match(line):
        _add_runs(document.add_paragraph(style="List Number"), numbered.group(1))
    else:
        _add_runs(document.add_paragraph(), line.strip())


def _add_runs(paragraph: object, text: str) -> None:
    """The text with **bold** spans set in bold."""
    for part in BOLD.split(text):
        if part:
            bold = part.startswith("**") and part.endswith("**")
            paragraph.add_run(part.strip("*") if bold else part).bold = bold  # type: ignore[attr-defined]


def _add_table(document: DocxDocument, lines: list[str], start: int) -> int:
    """A Markdown table as a Word table with a bold header; returns the line after it."""
    rows: list[list[str]] = []
    index = start
    while index < len(lines) and (match := TABLE_ROW.match(lines[index])):
        if not TABLE_RULE.match(lines[index]):
            rows.append([cell.strip() for cell in match.group(1).split("|")])
        index += 1
    width = max(len(row) for row in rows)
    table = document.add_table(rows=len(rows), cols=width, style="Table Grid")
    for row_index, row in enumerate(rows):
        for column, value in enumerate(row):
            run = table.cell(row_index, column).paragraphs[0].add_run(value)
            run.bold = row_index == 0
    return index


def _save_xlsx(path: Path, rows: list[list[str]], sheet_name: str) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = INVALID_NAME_CHARS.sub("", sheet_name)[:31] or "Sheet1"
    for row in rows:
        sheet.append([_cell_value(value) for value in row])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
    for column in sheet.columns:
        longest = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(MAX_COLUMN_WIDTH, longest + 2)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    workbook.save(str(path))


def _cell_value(value: str) -> str | int | float:
    """Numbers become real numbers so Excel can sum and sort them; everything else stays text."""
    cleaned = value.strip().replace(",", "")
    if NUMBER.match(cleaned):
        return float(cleaned) if "." in cleaned else int(cleaned)
    return value.strip()
