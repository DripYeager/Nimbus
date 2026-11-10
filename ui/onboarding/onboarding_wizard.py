"""
The first-run wizard: says hello, then asks which folders to learn, which model to use and how
to summon Nimbus, and saves all of it in one go. Owns the first-run flow and its navigation;
the editors it shows are the same ones the Settings page uses.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from core.exceptions import AutostartError
from core.logger import get_logger
from models.api import SettingsView
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.onboarding.step_progress import StepProgress
from ui.onboarding.welcome_hero import WelcomeHero
from ui.settings.general_tab import apply_autostart
from ui.settings.hotkey_edit import HotkeyEdit
from ui.settings.label_roles import styled_label
from ui.settings.model_editor import ModelEditor
from ui.settings.section_layout import (
    CARD_ROW_SPACING,
    GAP,
    GROUP_SPACING,
    SettingsCard,
    ToggleRow,
    divider,
    labelled_row,
    section_header,
    wrap_in_scroll_area,
)
from ui.settings.settings_save import save_settings
from ui.settings.sources_editor import SourcesEditor
from ui.theme.energy import EnergyOrb
from ui.theme.fonts import use_display_font
from ui.theme.icons import app_icon

logger = get_logger(__name__)

WIZARD_WIDTH = 780
WIZARD_HEIGHT = 620
PAGE_MARGIN = 32
STEP_TITLE_PX = 30
HERO_TITLE_PX = 40
FINISH_ORB_SIZE = 112
TEXT_COLUMN_WIDTH = 520
STEP_CAPTIONS = ["Welcome", "Folders", "Model", "Hotkey", "Done"]
WELCOME_TEXT = (
    "I'm a private assistant for your files and apps. Ask me to find a document, sum up a PDF, "
    "or open something, from anywhere, with a single hotkey. I learn your folders in the "
    "background, and you stay in charge of what I read and where your questions go."
)
FINISH_TEXT = (
    "Nimbus is ready to use right now. It will keep learning your folders quietly in the "
    "background (file names first, then their contents), so answers get better over the next "
    "few minutes. You can change any of this later in Settings."
)
SAVE_FAILED_TITLE = "Couldn't finish setup"


def _centred_text(text: str, role: str) -> QHBoxLayout:
    """A fixed-width wrapped paragraph centred in a row; aligned widgets lose height-for-width,
    which clips wrapped text, so the centring comes from stretches instead."""
    label = styled_label(text, role, wrap=True)
    label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    label.setFixedWidth(TEXT_COLUMN_WIDTH)
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(label)
    row.addStretch(1)
    return row


def _display_heading(text: str, pixel_size: int) -> QLabel:
    heading = QLabel(text)
    heading.setObjectName("HeroTitle")
    heading.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    use_display_font(heading, pixel_size)
    return heading


def _step(title: str, subtitle: str, body: QWidget) -> QWidget:
    """A step with its display-font heading over a scrolling body."""
    content = QWidget()
    content.setObjectName("OnboardingStep")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(PAGE_MARGIN, GAP, PAGE_MARGIN, PAGE_MARGIN)
    layout.setSpacing(GROUP_SPACING)
    layout.addWidget(section_header(title, subtitle, STEP_TITLE_PX))
    layout.addWidget(body, 1)
    return wrap_in_scroll_area(content)


class OnboardingWizard(QWidget):
    """First-run setup in its own window. Emits completed once everything has been saved."""

    completed = pyqtSignal()

    def __init__(self, api: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("OnboardingWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Welcome to Nimbus")
        self.setWindowIcon(app_icon())
        self.resize(WIZARD_WIDTH, WIZARD_HEIGHT)
        self._api = api
        self._is_loaded = False
        self._sources = SourcesEditor(api)
        self._model = ModelEditor(api)
        self._hotkey_edit = HotkeyEdit()
        self._autostart_row = ToggleRow("Start Nimbus when I sign in", icon="monitor", hint="Ready in the tray.")
        self._autostart_row.switch.setChecked(True)
        self._finish_orb = EnergyOrb(FINISH_ORB_SIZE)
        self._progress = StepProgress(STEP_CAPTIONS)
        self._stack = QStackedWidget()
        self._step_caption = QLabel()
        self._step_caption.setObjectName("StepCaption")
        self._back_button = QPushButton("Back")
        self._back_button.setProperty("variant", "ghost")
        self._next_button = QPushButton()
        self._next_button.setProperty("variant", "primary")
        self._build_layout()
        self._back_button.clicked.connect(lambda: self._go_to(self._stack.currentIndex() - 1))
        self._next_button.clicked.connect(self._advance)
        self._go_to(0)

    def _build_layout(self) -> None:
        """Step tracker on top, the current step in the middle, Back/Next in a footer bar."""
        for page in self._build_steps():
            self._stack.addWidget(page)
        tracker = QVBoxLayout()
        tracker.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN - GAP, PAGE_MARGIN, GAP)
        tracker.addWidget(self._progress)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(tracker)
        layout.addWidget(self._stack, 1)
        layout.addWidget(self._build_footer())

    def _build_steps(self) -> list[QWidget]:
        return [
            self._welcome_step(),
            _step("What should I learn?", "Pick the folders I may look through.", self._sources),
            _step("Which brain should I use?", "This is the model that writes my answers.", self._model),
            _step(
                "How do you call me?", "Press the keys you'd like to summon me with, from any app.", self._hotkey_card()
            ),
            self._finish_step(),
        ]

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("WizardFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(PAGE_MARGIN, CARD_ROW_SPACING, PAGE_MARGIN, CARD_ROW_SPACING)
        layout.setSpacing(GAP)
        layout.addWidget(self._step_caption, 1)
        layout.addWidget(self._back_button)
        layout.addWidget(self._next_button)
        return footer

    def _welcome_step(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(PAGE_MARGIN, GAP, PAGE_MARGIN, PAGE_MARGIN)
        layout.setSpacing(GAP * 2)
        layout.addWidget(WelcomeHero())
        layout.addSpacing(GAP)
        layout.addWidget(_display_heading("Hi, I'm Nimbus!", HERO_TITLE_PX))
        layout.addLayout(_centred_text(WELCOME_TEXT, "muted"))
        layout.addStretch(1)
        return page

    def _hotkey_card(self) -> QWidget:
        card = SettingsCard()
        hint = styled_label("Click the key, then press a new chord.", "muted")
        card.body.addLayout(labelled_row("keyboard", "Summon hotkey", hint, self._hotkey_edit))
        card.body.addWidget(divider())
        card.body.addWidget(self._autostart_row)
        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.addWidget(card)
        holder_layout.addStretch(1)
        return holder

    def _finish_step(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(PAGE_MARGIN, GAP, PAGE_MARGIN, PAGE_MARGIN)
        layout.setSpacing(GAP * 2)
        layout.addStretch(1)
        layout.addWidget(self._finish_orb, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(_display_heading("All set!", HERO_TITLE_PX))
        layout.addLayout(_centred_text(FINISH_TEXT, "muted"))
        layout.addStretch(2)
        return page

    def current_step(self) -> int:
        """The index of the step on screen, 0 for the welcome step."""
        return self._stack.currentIndex()

    def step_count(self) -> int:
        return self._stack.count()

    def _go_to(self, index: int) -> None:
        """Shows step index and relabels the footer for it."""
        last = self._stack.count() - 1
        index = max(0, min(index, last))
        self._stack.setCurrentIndex(index)
        self._progress.set_step(index)
        self._back_button.setVisible(index > 0)
        self._next_button.setText("Let's go" if index == 0 else "Finish" if index == last else "Next")
        self._step_caption.setText(f"Step {index + 1} of {last + 1}")
        if index == last:
            self._finish_orb.start()
        else:
            self._finish_orb.stop()

    def _advance(self) -> None:
        if self.current_step() == self._stack.count() - 1:
            self.accept()
        else:
            self._go_to(self.current_step() + 1)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._is_loaded:
            run_in_background(self._api.settings, self._load, self._show_load_error)

    def _load(self, view: SettingsView) -> None:
        """Starts every step from the engine's defaults."""
        self._is_loaded = True
        self._sources.load(view.values)
        self._model.load(view)
        self._hotkey_edit.set_hotkey(str(view.values.get("hotkey", "")))

    def _show_load_error(self, message: str) -> None:
        QMessageBox.warning(self, SAVE_FAILED_TITLE, message)

    def collect(self) -> tuple[dict[str, Any], str | None]:
        """Everything chosen across the steps, plus a newly entered API key (or None)."""
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
        self._next_button.setEnabled(False)
        run_in_background(
            lambda: save_settings(self._api, updates, provider, api_key), self._on_saved, self._show_save_error
        )

    def _on_saved(self, _: object) -> None:
        self._apply_autostart_choice()
        self.completed.emit()
        self.close()

    def _apply_autostart_choice(self) -> None:
        """A failed shortcut shouldn't undo a finished setup, say so and carry on."""
        try:
            apply_autostart(self._autostart_row.switch.isChecked())
        except AutostartError as e:
            logger.warning("Couldn't apply autostart after onboarding", extra={"error": str(e)})
            QMessageBox.warning(self, "Start at sign-in", str(e))

    def _show_save_error(self, message: str) -> None:
        self._next_button.setEnabled(True)
        QMessageBox.warning(self, SAVE_FAILED_TITLE, message)
