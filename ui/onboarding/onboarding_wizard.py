"""
The first-run wizard: says hello, then asks which folders to learn, which model to use and how
to summon Nimbus, and saves all of it in one go. Owns the first-run flow; the editors it shows
are the same ones the Settings window uses.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPaintEvent, QShowEvent
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget, QWizard, QWizardPage

from core.exceptions import AutostartError
from core.logger import get_logger
from models.api import SettingsView
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.settings.general_tab import apply_autostart
from ui.settings.hotkey_edit import HotkeyEdit
from ui.settings.label_roles import set_variant, styled_label
from ui.settings.model_editor import ModelEditor
from ui.settings.sources_editor import SourcesEditor
from ui.theme.icons import app_icon
from ui.theme.painting import paint_cloud

logger = get_logger(__name__)

WIZARD_WIDTH = 760
WIZARD_HEIGHT = 560
HERO_WIDTH = 220
HERO_HEIGHT = 140
PAGE_MARGIN = 24
WELCOME_TEXT_WIDTH = 520
WELCOME_TEXT = (
    "I'm a private assistant for your files and apps. Ask me to find a document, sum up a PDF, "
    "or open something — from anywhere, with a single hotkey. I learn your folders in the "
    "background, and you stay in charge of what I read and where your questions go."
)
FINISH_TEXT = (
    "Nimbus is ready to use right now. It will keep learning your folders quietly in the "
    "background — file names first, then their contents — so answers get better over the next "
    "few minutes. You can change any of this later in Settings."
)
SAVE_FAILED_TITLE = "Couldn't finish setup"


class _CloudHero(QWidget):
    """The big golden cloud on the welcome page."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(HERO_WIDTH, HERO_HEIGHT)

    def paintEvent(self, event: QPaintEvent) -> None:
        paint_cloud(QPainter(self), QRectF(self.rect()))


def _night_page() -> tuple[QWizardPage, QVBoxLayout]:
    """A blank page that paints the night background; QWizardPage ignores stylesheet
    backgrounds unless asked to."""
    page = QWizardPage()
    page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    layout = QVBoxLayout(page)
    layout.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, 0)
    return page, layout


def _page(title: str, subtitle: str = "") -> tuple[QWizardPage, QVBoxLayout]:
    """A wizard page with its title and optional subtitle already laid out."""
    page, layout = _night_page()
    layout.addWidget(styled_label(title, "title"))
    if subtitle:
        layout.addWidget(styled_label(subtitle, "muted", wrap=True))
    layout.addSpacing(8)
    return page, layout


class OnboardingWizard(QWizard):
    """First-run setup. Emits completed once everything has been saved."""

    completed = pyqtSignal()

    def __init__(self, api: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._is_loaded = False
        self._sources = SourcesEditor(api)
        self._model = ModelEditor(api)
        self._hotkey_edit = HotkeyEdit()
        self._autostart_box = QCheckBox("Start Nimbus when I sign in")
        self._autostart_box.setChecked(True)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setWindowTitle("Welcome to Nimbus")
        self.setWindowIcon(app_icon())
        self.resize(WIZARD_WIDTH, WIZARD_HEIGHT)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage)
        for page in self._build_pages():
            self.addPage(page)
        for button in (QWizard.WizardButton.NextButton, QWizard.WizardButton.FinishButton):
            set_variant(self.button(button), "primary")

    def _build_pages(self) -> list[QWizardPage]:
        return [
            self._welcome_page(),
            self._wrap("What should I learn?", "Pick the folders I may look through.", self._sources),
            self._wrap("Which brain should I use?", "This is the model that writes my answers.", self._model),
            self._hotkey_page(),
            self._finish_page(),
        ]

    def _welcome_page(self) -> QWizardPage:
        page, layout = _night_page()
        layout.addStretch(1)
        layout.addWidget(_CloudHero(), 0, Qt.AlignmentFlag.AlignHCenter)
        greeting = styled_label("Hi, I'm Nimbus.", "title")
        greeting.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(greeting)
        explanation = styled_label(WELCOME_TEXT, "muted", wrap=True)
        explanation.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        explanation.setFixedWidth(WELCOME_TEXT_WIDTH)
        # A centring row rather than an alignment flag: aligned widgets lose height-for-width,
        # which clips the wrapped paragraph.
        centred = QHBoxLayout()
        centred.addStretch(1)
        centred.addWidget(explanation)
        centred.addStretch(1)
        layout.addLayout(centred)
        layout.addStretch(1)
        return page

    def _wrap(self, title: str, subtitle: str, editor: QWidget) -> QWizardPage:
        page, layout = _page(title, subtitle)
        layout.addWidget(editor, 1)
        return page

    def _hotkey_page(self) -> QWizardPage:
        page, layout = _page("How do you call me?", "Press the keys you'd like to summon me with, from any app.")
        layout.addWidget(self._hotkey_edit)
        layout.addSpacing(12)
        layout.addWidget(self._autostart_box)
        layout.addStretch(1)
        return page

    def _finish_page(self) -> QWizardPage:
        page, layout = _page("All set")
        layout.addWidget(styled_label(FINISH_TEXT, wrap=True))
        layout.addStretch(1)
        return page

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._is_loaded:
            run_in_background(self._api.settings, self._load, self._show_load_error)

    def _load(self, view: SettingsView) -> None:
        """Starts every page from the engine's defaults."""
        self._is_loaded = True
        self._sources.load(view.values)
        self._model.load(view)
        self._hotkey_edit.set_hotkey(str(view.values.get("hotkey", "")))

    def _show_load_error(self, message: str) -> None:
        QMessageBox.warning(self, SAVE_FAILED_TITLE, message)

    def collect(self) -> tuple[dict[str, Any], str | None]:
        """Everything chosen across the pages, plus a newly entered API key (or None)."""
        model_updates, api_key = self._model.collect()
        updates: dict[str, Any] = {**self._sources.collect(), **model_updates, "onboarding_complete": True}
        hotkey = self._hotkey_edit.hotkey()
        if hotkey:
            updates["hotkey"] = hotkey
        return updates, api_key

    def accept(self) -> None:
        """Finish: saves in the background and only closes once the engine has the settings."""
        updates, api_key = self.collect()
        provider = self._model.provider()

        def write() -> None:
            self._api.update_settings(updates)
            if api_key:
                self._api.set_api_key(provider, api_key)

        self.button(QWizard.WizardButton.FinishButton).setEnabled(False)
        run_in_background(write, self._on_saved, self._show_save_error)

    def _on_saved(self, _: object) -> None:
        self._apply_autostart_choice()
        self.completed.emit()
        super().accept()

    def _apply_autostart_choice(self) -> None:
        """A failed shortcut shouldn't undo a finished setup — say so and carry on."""
        try:
            apply_autostart(self._autostart_box.isChecked())
        except AutostartError as e:
            logger.warning("Couldn't apply autostart after onboarding", extra={"error": str(e)})
            QMessageBox.warning(self, "Start at sign-in", str(e))

    def _show_save_error(self, message: str) -> None:
        self.button(QWizard.WizardButton.FinishButton).setEnabled(True)
        QMessageBox.warning(self, SAVE_FAILED_TITLE, message)
