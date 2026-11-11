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
LEADING_ZERO = re.compile(r"^-?0\d")
# Excel keeps 15 significant digits; a longer card number or ID would be silently rounded.
MAX_EXACT_DIGITS = 15
# "1,200.50" is one number; "1,2" is not, so only groups of three digits count as separators.
THOUSANDS = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")
# Windows refuses to create a file whose name is one of these, with any extension.
WINDOWS_DEVICES = frozenset(
    {"con", "prn", "aux", "nul", *(f"com{n}" for n in range(1, 10)), *(f"lpt{n}" for n in range(1, 10))}
)
HEADER_FILL = PatternFill("solid", fgColor="FFE0B3")
MAX_COLUMN_WIDTH = 60
MAX_SHEET_TITLE = 31


def unique_path(folder: Path, file_name: str, allowed: frozenset[str]) -> Path:
    """A free path for file_name in folder, with an allowed extension."""
    name = INVALID_NAME_CHARS.sub("", file_name).strip().strip(".")[:MAX_NAME_CHARS]
    stem, suffix = Path(name).stem, Path(name).suffix.lower()
    if not stem:
        raise ToolError("The file needs a name, like trip-plan.docx.")
    if suffix not in allowed:
        raise ToolError(f"Can't create a {suffix or 'nameless'} file here. Use one of: {', '.join(sorted(allowed))}.")
    if stem.lower() in WINDOWS_DEVICES:
        # "nul.txt" can't be created at all; a trailing underscore makes it an ordinary name.
        stem = f"{stem}_"
    candidate = folder / f"{stem}{suffix}"
    copy = 2
    while candidate.exists():
        if copy > MAX_COPIES:
            raise ToolError(f"Too many files named {stem}{suffix} in {folder}.")
        candidate = folder / f"{stem} ({copy}){suffix}"
        copy += 1
    return candidate


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
        paragraph = document.add_heading(level=len(heading.group(1)))
        _add_runs(paragraph, heading.group(2).strip())
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
    if not rows:
        # A separator line on its own ("|---|") is not a table; skip it instead of crashing.
        return index
    width = max(len(row) for row in rows)
    table = document.add_table(rows=len(rows), cols=width, style="Table Grid")
    for row_index, row in enumerate(rows):
        for column, value in enumerate(row):
            paragraph = table.cell(row_index, column).paragraphs[0]
            _add_runs(paragraph, value)
            if row_index == 0:
                for run in paragraph.runs:
                    run.bold = True
    return index


def _save_xlsx(path: Path, rows: list[list[str]], sheet_name: str) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = _sheet_title(sheet_name)
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


def _sheet_title(name: str) -> str:
    """A sheet name Excel will accept. Brackets and a leading apostrophe are legal in a file
    name but not in a sheet title, and "History" is reserved."""
    cleaned = INVALID_NAME_CHARS.sub("", name).replace("[", "").replace("]", "")
    # Strip again after cutting: the cut can leave an apostrophe at the end.
    cleaned = cleaned.strip().strip("'")[:MAX_SHEET_TITLE].strip().strip("'")
    if not cleaned or cleaned.lower() == "history":
        return "Sheet1"
    return cleaned


def _cell_value(value: str) -> str | int | float:
    """Numbers become real numbers so Excel can sum and sort them; everything else stays text.
    Commas count only as thousands separators ("1,200"), so a value like "1,2" stays text."""
    text = value.strip()
    if THOUSANDS.match(text):
        text = text.replace(",", "")
    # "007", a zip code or an employee ID would lose its leading zeros as a number.
    if LEADING_ZERO.match(text) or sum(char.isdigit() for char in text) > MAX_EXACT_DIGITS:
        return value.strip()
    if NUMBER.match(text):
        return float(text) if "." in text else int(text)
    return value.strip()
