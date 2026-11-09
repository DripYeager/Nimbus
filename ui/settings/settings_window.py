"""
The Settings dialog: Sources, Model and General tabs over one Save button. Loads the saved
settings when shown and writes every tab's changes in one background call. Owns the dialog
and the save flow; each tab owns its own fields.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTabWidget, QVBoxLayout, QWidget

from models.api import SettingsView
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.settings.general_tab import GeneralTab
from ui.settings.label_roles import styled_label
from ui.settings.model_editor import ModelEditor
from ui.settings.sources_editor import SourcesEditor
from ui.theme.icons import app_icon
from ui.theme.painting import CloudGlyph

WINDOW_TITLE = "Nimbus Settings"
MIN_WIDTH = 720
MIN_HEIGHT = 560
HEADER_GLYPH_SIZE = 40
CONTENT_MARGIN = 20
TAB_NAMES = ("Sources", "Model", "General")


class SettingsWindow(QDialog):
    """Edits every user-facing setting. Emits saved after a successful save."""

    saved = pyqtSignal()

    def __init__(self, api: ApiClient, initial_tab: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._sources = SourcesEditor(api, show_index_controls=True)
        self._model = ModelEditor(api)
        self._general = GeneralTab(api)
        self._tabs = QTabWidget()
        self._error_label = styled_label("", "error", wrap=True)
        self._save_button = QPushButton("Save")
        self._save_button.setProperty("variant", "primary")
        self._save_button.setDefault(True)
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self._build_layout()
        self.show_tab(initial_tab)

    def _build_layout(self) -> None:
        """Header, tabs, footer."""
        for name, tab in zip(TAB_NAMES, (self._sources, self._model, self._general), strict=True):
            self._tabs.addTab(tab, name)
        header = QHBoxLayout()
        header.addWidget(CloudGlyph(HEADER_GLYPH_SIZE))
        header.addWidget(styled_label("Settings", "title"))
        header.addStretch(1)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        self._save_button.clicked.connect(self._save)
        footer = QHBoxLayout()
        footer.addWidget(self._error_label, 1)
        footer.addWidget(cancel_button)
        footer.addWidget(self._save_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN)
        layout.addLayout(header)
        layout.addWidget(self._tabs, 1)
        layout.addLayout(footer)

    def show_tab(self, name: str | None) -> None:
        """Switches to the tab with this name; unknown or missing names leave it where it is."""
        if name in TAB_NAMES:
            self._tabs.setCurrentIndex(TAB_NAMES.index(name))

    def open_settings(self) -> None:
        """Shows the dialog (or raises it if it's already open); showing reloads saved values."""
        self.show()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._error_label.clear()
        self._save_button.setEnabled(False)
        run_in_background(self._api.settings, self._load, self._show_load_error)

    def _load(self, view: SettingsView) -> None:
        self._sources.load(view.values)
        self._model.load(view)
        self._general.load(view.values)
        self._save_button.setEnabled(True)

    def _save(self) -> None:
        """Writes all tabs' changes and the new API key (if any) in one background call."""
        model_updates, api_key = self._model.collect()
        updates: dict[str, Any] = {**self._sources.collect(), **model_updates, **self._general.collect()}
        provider = self._model.provider()

        def write() -> None:
            self._api.update_settings(updates)
            if api_key:
                self._api.set_api_key(provider, api_key)

        self._error_label.clear()
        self._save_button.setEnabled(False)
        run_in_background(write, self._on_saved, self._show_error)

    def _on_saved(self, _: object) -> None:
        self._save_button.setEnabled(True)
        self.saved.emit()
        self.accept()

    def _show_load_error(self, message: str) -> None:
        """Leaves Save disabled: saving half-loaded tabs would overwrite real settings with blanks."""
        self._error_label.setText(message)

    def _show_error(self, message: str) -> None:
        self._save_button.setEnabled(True)
        self._error_label.setText(message)
