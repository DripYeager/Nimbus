"""
The "what should Nimbus learn?" editor: source folders (with names-only or full-contents
reading), file types, a size limit and exclude patterns, optionally with live indexing
controls. Owns editing these settings in memory; saving them is the caller's job.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from models.schema import FileCategory, SourceSummary
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.settings.index_panel import IndexPanel
from ui.settings.label_roles import styled_label

CATEGORY_LABELS: dict[FileCategory, str] = {
    FileCategory.DOCUMENTS: "Documents",
    FileCategory.PDFS: "PDFs",
    FileCategory.SPREADSHEETS: "Spreadsheets",
    FileCategory.SLIDES: "Slides",
    FileCategory.TEXT: "Text && Markdown",
    FileCategory.CODE: "Code",
    FileCategory.EMAIL: "Email",
}
CATEGORY_COLUMNS = 4
MIN_FILE_SIZE_MB = 1
MAX_FILE_SIZE_MB = 2048
DEFAULT_FILE_SIZE_MB = 50
EXCLUDE_BOX_HEIGHT = 72
SECTION_GAP = 8
SCROLLBAR_GUTTER = 12
EXCLUDE_PLACEHOLDER = "One pattern per line, e.g.\n*.iso\nArchive"
FOLDERS_HINT = "Unticked “Read contents” keeps a folder searchable by file name only."
NEW_FOLDER_COUNTS = "Counted after you save"


def _path_key(path: str) -> str:
    """Compares folder paths the way Windows does: case-insensitive, ~ expanded."""
    return os.path.normcase(str(Path(path).expanduser()))


def describe_source_counts(summary: SourceSummary) -> str:
    """The muted counts line under a folder, e.g. "1,240 files · 980 read"."""
    if not summary.exists:
        return "Folder not found"
    text = f"{summary.file_count:,} files"
    if summary.include_contents:
        text += f" · {summary.indexed_count:,} read"
    return text


class _SourceRow(QFrame):
    """One folder: its path, the read-contents switch, its counts and a remove button."""

    remove_requested = pyqtSignal(object)

    def __init__(self, path: str, include_contents: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self.contents_box = QCheckBox("Read contents")
        self.contents_box.setChecked(include_contents)
        self.counts_label = styled_label(NEW_FOLDER_COUNTS, "muted")
        remove_button = QPushButton("Remove")
        remove_button.setProperty("variant", "danger")
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        text_column = QVBoxLayout()
        text_column.setSpacing(2)
        text_column.addWidget(styled_label(path))
        text_column.addWidget(self.counts_label)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.addLayout(text_column, 1)
        layout.addWidget(self.contents_box)
        layout.addWidget(remove_button)

    def to_setting(self) -> dict[str, Any]:
        return {"path": self.path, "include_contents": self.contents_box.isChecked()}


class SourcesEditor(QWidget):
    """Edits sources, file_categories, max_file_size_mb and exclude_patterns."""

    def __init__(self, api: ApiClient, parent: QWidget | None = None, *, show_index_controls: bool = False) -> None:
        super().__init__(parent)
        self._api = api
        self._rows: list[_SourceRow] = []
        self._rows_layout = QVBoxLayout()
        self._category_boxes = {category: QCheckBox(label) for category, label in CATEGORY_LABELS.items()}
        self._size_box = QSpinBox()
        self._size_box.setRange(MIN_FILE_SIZE_MB, MAX_FILE_SIZE_MB)
        self._size_box.setSuffix(" MB")
        self._size_box.setValue(DEFAULT_FILE_SIZE_MB)
        self._exclude_box = QPlainTextEdit()
        self._exclude_box.setPlaceholderText(EXCLUDE_PLACEHOLDER)
        self._exclude_box.setFixedHeight(EXCLUDE_BOX_HEIGHT)
        self._index_panel = IndexPanel(api) if show_index_controls else None
        self._build_layout()

    def _build_layout(self) -> None:
        """Index strip (if any) pinned on top; folders, file types and limits scroll beneath it."""
        outer = QVBoxLayout(self)
        if self._index_panel is not None:
            outer.addWidget(styled_label("Index", "section"))
            outer.addWidget(self._index_panel)
            outer.addSpacing(SECTION_GAP)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self._build_scrolling_content())
        # setWidget turns auto-fill on, which paints the platform palette over the night theme.
        scroll.widget().setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)
        outer.addWidget(scroll, 1)

    def _build_scrolling_content(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, SCROLLBAR_GUTTER, 0)
        layout.addWidget(styled_label("Folders", "section"))
        layout.addWidget(styled_label(FOLDERS_HINT, "muted", wrap=True))
        layout.addLayout(self._rows_layout)
        add_button = QPushButton("Add folder…")
        add_button.clicked.connect(self._choose_folder)
        layout.addWidget(add_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(SECTION_GAP)
        layout.addWidget(styled_label("File types to read", "section"))
        layout.addLayout(self._build_category_grid())
        layout.addSpacing(SECTION_GAP)
        layout.addLayout(self._build_limits_row())
        layout.addWidget(styled_label("Skip these (one name or pattern per line)", "muted"))
        layout.addWidget(self._exclude_box)
        layout.addStretch(1)
        return content

    def _build_category_grid(self) -> QGridLayout:
        grid = QGridLayout()
        for index, box in enumerate(self._category_boxes.values()):
            grid.addWidget(box, index // CATEGORY_COLUMNS, index % CATEGORY_COLUMNS)
        return grid

    def _build_limits_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(styled_label("Skip files larger than"))
        row.addWidget(self._size_box)
        row.addStretch(1)
        return row

    def load(self, values: dict[str, Any]) -> None:
        """Fills every field from saved settings, then fetches folder counts in the background."""
        for row in list(self._rows):
            self._remove_row(row)
        for source in values.get("sources", []):
            self._add_row(str(source["path"]), bool(source.get("include_contents", True)))
        enabled = set(values.get("file_categories", list(FileCategory)))
        for category, box in self._category_boxes.items():
            box.setChecked(category.value in enabled)
        self._size_box.setValue(int(values.get("max_file_size_mb", DEFAULT_FILE_SIZE_MB)))
        self._exclude_box.setPlainText("\n".join(values.get("exclude_patterns", [])))
        run_in_background(self._api.source_summaries, self._show_counts)

    def collect(self) -> dict[str, Any]:
        """The edited values as settings updates."""
        patterns = [line.strip() for line in self._exclude_box.toPlainText().splitlines() if line.strip()]
        return {
            "sources": [row.to_setting() for row in self._rows],
            "file_categories": [c.value for c, box in self._category_boxes.items() if box.isChecked()],
            "max_file_size_mb": self._size_box.value(),
            "exclude_patterns": patterns,
        }

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder for Nimbus to learn")
        if folder and all(_path_key(row.path) != _path_key(folder) for row in self._rows):
            self._add_row(str(Path(folder)), include_contents=True)

    def _add_row(self, path: str, include_contents: bool) -> None:
        row = _SourceRow(path, include_contents)
        row.remove_requested.connect(self._remove_row)
        self._rows.append(row)
        self._rows_layout.addWidget(row)

    def _remove_row(self, row: _SourceRow) -> None:
        self._rows.remove(row)
        self._rows_layout.removeWidget(row)
        row.deleteLater()

    def _show_counts(self, summaries: list[SourceSummary]) -> None:
        """Puts each folder's file counts under it; folders the engine hasn't seen keep their note."""
        by_path = {_path_key(summary.path): summary for summary in summaries}
        for row in self._rows:
            summary = by_path.get(_path_key(row.path))
            if summary is not None:
                row.counts_label.setText(describe_source_counts(summary))
