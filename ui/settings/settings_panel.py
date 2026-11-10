"""
The Settings page shown inside the chat window: a navigation rail (Sources, Model, General),
the chosen section in a scroll area, and a bottom bar with Discard and Save. Loads the saved
settings on request and writes every section's changes in one background call. Owns the page
and the save flow; each section owns its own fields, and the host window owns the header.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from models.api import SettingsView
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.settings.general_tab import GeneralTab
from ui.settings.label_roles import set_state
from ui.settings.model_editor import ModelEditor
from ui.settings.section_layout import (
    CARD_ROW_SPACING,
    GAP,
    GROUP_SPACING,
    section_header,
    two_state_icon,
    wrap_in_scroll_area,
)
from ui.settings.settings_save import save_settings
from ui.settings.sources_editor import SourcesEditor
from ui.theme.tokens import GI_ORANGE, ICON_SIZE, TEXT_MUTED

# (key, nav label, icon, heading, description), in rail order.
SECTIONS: tuple[tuple[str, str, str, str, str], ...] = (
    ("sources", "Sources", "folder-open", "Sources", "The folders Nimbus learns, and what it skips."),
    ("model", "Model", "cpu", "Model", "Which brain writes the answers, and where your questions go."),
    ("general", "General", "settings", "General", "How you summon Nimbus, and what it may do on its own."),
)
SECTION_KEYS = tuple(section[0] for section in SECTIONS)
RAIL_WIDTH = 170
PAGE_MARGIN = 24
SAVED_TEXT = "Saved ✓"
SAVED_FLASH_MS = 2500


class SettingsPanel(QWidget):
    """Edits every user-facing setting. Emits saved after a successful save and back_requested
    when the user is done (the host's back arrow may emit it too)."""

    back_requested = pyqtSignal()
    saved = pyqtSignal()

    def __init__(self, api: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsPanel")
        self._api = api
        self._sources = SourcesEditor(api, show_index_controls=True)
        self._model = ModelEditor(api)
        self._general = GeneralTab(api)
        self._stack = QStackedWidget()
        self._nav = QButtonGroup(self)
        self._status = QLabel()
        self._status.setObjectName("BarStatus")
        self._discard_button = QPushButton("Discard")
        self._discard_button.setProperty("variant", "ghost")
        self._save_button = QPushButton("Save changes")
        self._save_button.setProperty("variant", "primary")
        self._save_button.setEnabled(False)
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(SAVED_FLASH_MS)
        self._build_layout()
        self._connect_signals()
        self.show_section(SECTION_KEYS[0])

    def _build_layout(self) -> None:
        """Rail on the left; the section stack over the bottom bar on the right."""
        editors = (self._sources, self._model, self._general)
        for (_, _, _, heading, description), editor in zip(SECTIONS, editors, strict=True):
            self._stack.addWidget(wrap_in_scroll_area(_section_page(heading, description, editor)))
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self._stack, 1)
        right.addWidget(self._build_bar())
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_rail())
        layout.addLayout(right, 1)

    def _build_rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("SettingsRail")
        rail.setFixedWidth(RAIL_WIDTH)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(CARD_ROW_SPACING, PAGE_MARGIN, CARD_ROW_SPACING, PAGE_MARGIN)
        layout.setSpacing(GAP // 2)
        for index, (_, label, icon, _, _) in enumerate(SECTIONS):
            item = QPushButton(label)
            item.setObjectName("NavItem")
            item.setCheckable(True)
            item.setIcon(two_state_icon(icon, TEXT_MUTED, GI_ORANGE))
            item.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
            item.setCursor(Qt.CursorShape.PointingHandCursor)
            self._nav.addButton(item, index)
            layout.addWidget(item)
        layout.addStretch(1)
        return rail

    def _build_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("SettingsBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(PAGE_MARGIN, CARD_ROW_SPACING, PAGE_MARGIN, CARD_ROW_SPACING)
        layout.setSpacing(GAP)
        layout.addWidget(self._status, 1)
        layout.addWidget(self._discard_button)
        layout.addWidget(self._save_button)
        return bar

    def _connect_signals(self) -> None:
        self._nav.idClicked.connect(self._stack.setCurrentIndex)
        self._discard_button.clicked.connect(self.load)
        self._save_button.clicked.connect(self._save)
        self._status_timer.timeout.connect(lambda: self._show_status("", "muted"))

    def show_section(self, name: str) -> None:
        """Switches to "sources", "model" or "general"; unknown names leave the page where it is."""
        if name in SECTION_KEYS:
            index = SECTION_KEYS.index(name)
            self._nav.button(index).setChecked(True)
            self._stack.setCurrentIndex(index)

    def load(self) -> None:
        """Fetches the saved settings in the background and fills every section; Save stays
        disabled until they arrive, so half-empty sections can't be written back."""
        self._show_status("Loading…", "muted")
        self._save_button.setEnabled(False)
        run_in_background(self._api.settings, self._fill, self._show_load_error)

    def _fill(self, view: SettingsView) -> None:
        self._sources.load(view.values)
        self._model.load(view)
        self._general.load(view.values)
        self._show_status("", "muted")
        self._save_button.setEnabled(True)

    def _save(self) -> None:
        """Writes all sections' changes and the new API key (if any) in one background call."""
        model_updates, api_key = self._model.collect()
        updates: dict[str, Any] = {**self._sources.collect(), **model_updates, **self._general.collect()}
        provider = self._model.provider()
        self._show_status("Saving…", "muted")
        self._save_button.setEnabled(False)
        run_in_background(
            lambda: save_settings(self._api, updates, provider, api_key), self._on_saved, self._show_error
        )

    def _on_saved(self, _: object) -> None:
        self._save_button.setEnabled(True)
        self._show_status(SAVED_TEXT, "success")
        self._status_timer.start()
        self.saved.emit()

    def _show_load_error(self, message: str) -> None:
        """Leaves Save disabled: saving half-loaded sections would overwrite real settings with blanks."""
        self._show_status(message, "error")

    def _show_error(self, message: str) -> None:
        self._save_button.setEnabled(True)
        self._show_status(message, "error")

    def _show_status(self, text: str, tone: str) -> None:
        """The bar's one-line message: muted progress, a green confirmation or a red error."""
        self._status_timer.stop()
        self._status.setText(text)
        self._status.setToolTip(text)
        set_state(self._status, tone)


def _section_page(heading: str, description: str, editor: QWidget) -> QWidget:
    """A section's heading over its editor, padded to the page margins."""
    page = QWidget()
    page.setObjectName("SettingsPage")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN)
    layout.setSpacing(GROUP_SPACING)
    layout.addWidget(section_header(heading, description))
    layout.addWidget(editor, 1)
    return page
