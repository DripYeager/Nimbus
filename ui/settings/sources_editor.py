"""
The "what should Nimbus learn?" editor: source folders (with names-only or full-contents
reading), file types, a size limit and exclude patterns, optionally with live indexing
controls. Owns editing these settings in memory; saving them and scrolling are the caller's job.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from models.schema import FileCategory, SourceSummary
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.settings.index_panel import IndexPanel
from ui.settings.label_roles import styled_label
from ui.settings.section_layout import GAP, GROUP_SPACING, SettingsCard, divider, group_header, two_state_icon
from ui.settings.source_row import SourceRow
from ui.theme.line_icons import line_icon
from ui.theme.tokens import ICON_SIZE, TEXT, TEXT_MUTED, TEXT_ON_ORANGE

# (label, icon) per file type; "&&" because a single & would become a keyboard mnemonic.
CATEGORY_CHIPS: dict[FileCategory, tuple[str, str]] = {
    FileCategory.DOCUMENTS: ("Documents", "file-text"),
    FileCategory.PDFS: ("PDFs", "file"),
    FileCategory.SPREADSHEETS: ("Spreadsheets", "file-spreadsheet"),
    FileCategory.SLIDES: ("Slides", "presentation"),
    FileCategory.TEXT: ("Text && Markdown", "notebook-pen"),
    FileCategory.CODE: ("Code", "app-window"),
    FileCategory.EMAIL: ("Email", "mail"),
}
CATEGORY_COLUMNS = 4
CHIP_HEIGHT = 32
MIN_FILE_SIZE_MB = 1
MAX_FILE_SIZE_MB = 2048
DEFAULT_FILE_SIZE_MB = 50
SIZE_BOX_WIDTH = 110
EXCLUDE_BOX_HEIGHT = 88
EXCLUDE_PLACEHOLDER = "One pattern per line, e.g.\n*.iso\nArchive"
FOLDERS_HINT = "Switch off “Read contents” to keep a folder searchable by file name only."
NO_FOLDERS_TEXT = "No folders yet — add one so Nimbus has something to learn."


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


def _category_chip(label: str, icon: str) -> QPushButton:
    """A checkable pill for one file type; orange with dark ink while selected."""
    chip = QPushButton(label)
    chip.setObjectName("TypeChip")
    chip.setFixedHeight(CHIP_HEIGHT)
    chip.setCheckable(True)
    chip.setIcon(two_state_icon(icon, TEXT_MUTED, TEXT_ON_ORANGE))
    chip.setIconSize(QSize(ICON_SIZE - 2, ICON_SIZE - 2))
    chip.setCursor(Qt.CursorShape.PointingHandCursor)
    return chip


def _add_folder_button() -> QPushButton:
    button = QPushButton("Add folder")
    button.setObjectName("AddFolderButton")
    button.setIcon(line_icon("folder-plus", TEXT_MUTED, ICON_SIZE, hover_color=TEXT))
    button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class SourcesEditor(QWidget):
    """Edits sources, file_categories, max_file_size_mb and exclude_patterns."""

    def __init__(self, api: ApiClient, parent: QWidget | None = None, *, show_index_controls: bool = False) -> None:
        super().__init__(parent)
        self._api = api
        self._rows: list[SourceRow] = []
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(GAP)
        self._empty_label = styled_label(NO_FOLDERS_TEXT, "muted")
        self._category_chips = {category: _category_chip(*chip) for category, chip in CATEGORY_CHIPS.items()}
        self._size_box = QSpinBox()
        self._size_box.setRange(MIN_FILE_SIZE_MB, MAX_FILE_SIZE_MB)
        self._size_box.setSuffix(" MB")
        self._size_box.setValue(DEFAULT_FILE_SIZE_MB)
        self._size_box.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._size_box.setFixedWidth(SIZE_BOX_WIDTH)
        self._exclude_box = QPlainTextEdit()
        self._exclude_box.setPlaceholderText(EXCLUDE_PLACEHOLDER)
        self._exclude_box.setFixedHeight(EXCLUDE_BOX_HEIGHT)
        self._index_panel = IndexPanel(api) if show_index_controls else None
        self._build_layout()

    def _build_layout(self) -> None:
        """Index card (if any), then folders, file types and limits, each under its own title."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GAP)
        if self._index_panel is not None:
            layout.addWidget(group_header("Index"))
            layout.addWidget(self._index_panel)
            layout.addSpacing(GROUP_SPACING - GAP)
        layout.addWidget(group_header("Folders", FOLDERS_HINT))
        layout.addWidget(self._empty_label)
        layout.addLayout(self._rows_layout)
        add_button = _add_folder_button()
        add_button.clicked.connect(self._choose_folder)
        layout.addWidget(add_button)
        layout.addSpacing(GROUP_SPACING - GAP)
        layout.addWidget(group_header("File types to read", "Other files are still found by name."))
        layout.addWidget(self._build_category_card())
        layout.addSpacing(GROUP_SPACING - GAP)
        layout.addWidget(group_header("Limits"))
        layout.addWidget(self._build_limits_card())
        layout.addStretch(1)

    def _build_category_card(self) -> SettingsCard:
        card = SettingsCard()
        grid = QGridLayout()
        grid.setSpacing(GAP)
        for index, chip in enumerate(self._category_chips.values()):
            grid.addWidget(chip, index // CATEGORY_COLUMNS, index % CATEGORY_COLUMNS)
        card.body.addLayout(grid)
        return card

    def _build_limits_card(self) -> SettingsCard:
        card = SettingsCard()
        size_row = QHBoxLayout()
        size_row.addWidget(styled_label("Skip files larger than"), 1)
        size_row.addWidget(self._size_box)
        card.body.addLayout(size_row)
        card.body.addWidget(divider())
        card.body.addWidget(styled_label("Skip these names or patterns, one per line"))
        card.body.addWidget(self._exclude_box)
        return card

    def load(self, values: dict[str, Any]) -> None:
        """Fills every field from saved settings, then fetches folder counts in the background."""
        for row in list(self._rows):
            self._remove_row(row)
        for source in values.get("sources", []):
            self._add_row(str(source["path"]), bool(source.get("include_contents", True)))
        enabled = set(values.get("file_categories", list(FileCategory)))
        for category, chip in self._category_chips.items():
            chip.setChecked(category.value in enabled)
        self._size_box.setValue(int(values.get("max_file_size_mb", DEFAULT_FILE_SIZE_MB)))
        self._exclude_box.setPlainText("\n".join(values.get("exclude_patterns", [])))
        run_in_background(self._api.source_summaries, self._show_counts)

    def collect(self) -> dict[str, Any]:
        """The edited values as settings updates."""
        patterns = [line.strip() for line in self._exclude_box.toPlainText().splitlines() if line.strip()]
        return {
            "sources": [row.to_setting() for row in self._rows],
            "file_categories": [c.value for c, chip in self._category_chips.items() if chip.isChecked()],
            "max_file_size_mb": self._size_box.value(),
            "exclude_patterns": patterns,
        }

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder for Nimbus to learn")
        if folder and all(_path_key(row.path) != _path_key(folder) for row in self._rows):
            self._add_row(str(Path(folder)), include_contents=True)

    def _add_row(self, path: str, include_contents: bool) -> None:
        row = SourceRow(path, include_contents)
        row.remove_requested.connect(self._remove_row)
        self._rows.append(row)
        self._rows_layout.addWidget(row)
        self._empty_label.hide()

    def _remove_row(self, row: SourceRow) -> None:
        self._rows.remove(row)
        self._rows_layout.removeWidget(row)
        row.deleteLater()
        self._empty_label.setVisible(not self._rows)

    def _show_counts(self, summaries: list[SourceSummary]) -> None:
        """Puts each folder's file counts under it; folders the engine hasn't seen keep their note."""
        by_path = {_path_key(summary.path): summary for summary in summaries}
        for row in self._rows:
            summary = by_path.get(_path_key(row.path))
            if summary is not None:
                row.counts_label.setText(describe_source_counts(summary))
