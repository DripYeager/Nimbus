"""
Tools that create new files on request: documents (.txt, .md, .docx) and spreadsheets (.xlsx,
.csv). A file goes in the folder the user asks for, by full path or by name ("Downloads",
"Desktop\\Reports", or a folder inside one they shared), and only falls back to
Documents\\Nimbus when they didn't say. It never replaces an existing file and, like every
action that writes, waits for the user's approval, which shows the exact path first. Owns
choosing the folder and describing the result; the writing is document_writer's job.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from models.chat import ToolResult
from tools.document_writer import (
    DOCUMENT_SUFFIXES,
    INVALID_NAME_CHARS,
    SPREADSHEET_SUFFIXES,
    unique_path,
    write_document,
    write_spreadsheet,
)
from tools.file_tools import source_ref_for
from tools.registry import Tool, ToolRegistry, object_schema, string_param, tool_spec

DEFAULT_OUTPUT_DIR = Path("~/Documents/Nimbus")
_FOLDER = string_param(
    "Where to save it, as a path. If the user wants a new folder, put it at the end of the path, "
    "e.g. Downloads\\LLM Notes makes a new LLM Notes folder inside Downloads. Empty only if they didn't say"
)
CREATE_DOCUMENT = tool_spec(
    "create_document",
    "Create a new text, Markdown or Word file. A Word document is always .docx. Write the content as "
    "Markdown: # headings, - bullets, 1. numbered items, **bold**, and | tables |.",
    object_schema(
        {
            "file_name": string_param("Name with extension: .docx for Word, .txt or .md, e.g. trip-plan.docx"),
            "content": string_param("The full text, in Markdown"),
            "folder": _FOLDER,
        },
        ["file_name", "content", "folder"],
    ),
)
CREATE_SPREADSHEET = tool_spec(
    "create_spreadsheet",
    "Create a new Excel (.xlsx) or CSV file from a table. Give the table as CSV text with the "
    "header row first; numbers become real numbers in Excel.",
    object_schema(
        {
            "file_name": string_param("Name with extension: .xlsx or .csv, e.g. budget.xlsx"),
            "csv": string_param("The table as CSV text, header row first"),
            "sheet_name": string_param("Optional sheet name for Excel"),
            "folder": _FOLDER,
        },
        ["file_name", "csv", "folder"],
    ),
)


class CreateToolbox:
    """shared_roots lists the user's shared folders, so a bare folder name can be found inside
    them as well as in their home folder."""

    def __init__(self, shared_roots: Callable[[], list[Path]], output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
        self._shared_roots = shared_roots
        self._output_dir = output_dir.expanduser()

    def register(self, registry: ToolRegistry) -> None:
        registry.register(Tool(CREATE_DOCUMENT, self.create_document, self.describe, True))
        registry.register(Tool(CREATE_SPREADSHEET, self.create_spreadsheet, self.describe, True))

    def create_document(self, args: dict[str, Any]) -> ToolResult:
        path = unique_path(self.target_folder(args), str(args["file_name"]), DOCUMENT_SUFFIXES)
        write_document(path, str(args["content"]))
        return _created(path, "")

    def create_spreadsheet(self, args: dict[str, Any]) -> ToolResult:
        path = unique_path(self.target_folder(args), str(args["file_name"]), SPREADSHEET_SUFFIXES)
        rows = write_spreadsheet(path, str(args["csv"]), str(args.get("sheet_name") or "Sheet1"))
        detail = "" if rows == 0 else f" with {rows} row{'' if rows == 1 else 's'}"
        return _created(path, detail)

    def target_folder(self, args: dict[str, Any]) -> Path:
        """The asked-for folder. The schema asks for any new folder as the end of that path, which
        small models get right far more often than a separate field; a new_folder some models
        still send is honoured too."""
        base = self.folder_for(args.get("folder"))
        # One plain folder name only: separators and reserved characters can't smuggle in a path.
        name = INVALID_NAME_CHARS.sub("", str(args.get("new_folder") or "")).strip().strip(".")
        # Models often name the new folder in both fields; that means one folder, not two.
        if not name or base.name.lower() == name.lower():
            return base
        return base / name

    def folder_for(self, requested: object) -> Path:
        """Where the file goes. A full path is used as is (created if missing). A name is looked
        up under the home folder first ("Downloads"), then inside each shared folder
        ("Reports" in Documents), and is otherwise created under the home folder.

        A path can name a folder that doesn't exist yet ("Reports\\Notes"). The longest prefix
        that does exist decides the root, so Notes is created inside the shared Reports folder
        rather than a new Reports folder in the home directory."""
        text = str(requested or "").strip()
        if not text:
            return self._output_dir
        raw = Path(text).expanduser()
        if raw.is_absolute():
            return raw.resolve()
        # ".." would let a relative path climb out of the folder the user named.
        parts = [part for part in raw.parts if part not in (".", "..")]
        if not parts:
            return self._output_dir
        best: tuple[int, Path] | None = None
        for root in (Path.home(), *self._shared_roots()):
            for length in range(len(parts), 0, -1):
                if (root / Path(*parts[:length])).is_dir():
                    # Equal-length matches keep the earlier root, so the home folder wins a tie.
                    if best is None or length > best[0]:
                        best = (length, root)
                    break
        base = best[1] if best is not None else Path.home()
        return (base / Path(*parts)).resolve()

    def describe(self, args: dict[str, Any]) -> str:
        """What the approval card says: the exact folder, so nothing lands somewhere unexpected."""
        return f"Create “{args.get('file_name', 'a file')}” in {self.target_folder(args)}"


def _created(path: Path, detail: str) -> ToolResult:
    return ToolResult(content=f"Created {path.name}{detail} at {path}.", sources=[source_ref_for(path)])
