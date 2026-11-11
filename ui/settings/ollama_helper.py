"""
The Ollama setup card on the Model page: says whether Ollama is installed, running and has the
chosen model, and offers the one button that gets you to the next step, Get Ollama, Start
Ollama, or Download the model (with live progress). Below that it suggests the model that fits
this PC's RAM and graphics card, with a button to use it. Owns that card's display and polling;
the work itself happens in the engine (core/ollama_setup.py, core/model_advisor.py).
"""

from __future__ import annotations

from PyQt6.QtCore import QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QHideEvent, QShowEvent
from PyQt6.QtWidgets import QHBoxLayout, QProgressBar, QPushButton, QVBoxLayout, QWidget

from models.api import ModelRecommendation, OllamaStatus
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.settings.label_roles import set_variant, styled_label
from ui.settings.section_layout import CARD_ROW_SPACING, SettingsCard
from ui.theme.energy import EnergyOrb

DOWNLOAD_PAGE = "https://ollama.com/download/windows"
POLL_MS = 1500
ORB_SIZE = 22
PROGRESS_STEPS = 1000


def describe_recommendation(recommendation: ModelRecommendation) -> str:
    """The suggestion line: which model, why, and for what hardware."""
    status = "already downloaded" if recommendation.installed else f"about {recommendation.size_gb:.1f} GB"
    return f"Suggested for this PC: {recommendation.model} ({status}). {recommendation.reason}"


def describe_ollama(status: OllamaStatus, model: str) -> tuple[str, str, str | None]:
    """(headline, detail, button text or None) for one status, the card's whole copy."""
    if status.pulling:
        percent = f" · {status.pull_percent:.0f}%" if status.pull_percent is not None else ""
        return f"Downloading {status.pulling}{percent}", "This runs once; you can keep using Nimbus.", None
    if status.pull_error:
        return "The download didn't finish", status.pull_error, f"Retry {model}"
    if not status.installed:
        return (
            "Ollama isn't installed",
            "It's a free app that runs models on this PC. It installs for your user only; no admin needed.",
            "Get Ollama",
        )
    if not status.running:
        return "Ollama is installed but not running", "Start it and Nimbus will connect on its own.", "Start Ollama"
    if not model:
        return "Ollama is running", "Pick a model below, then download it here.", None
    if not status.has_model:
        return (
            f"{model} isn't downloaded yet",
            "About 4 to 5 GB for an 8B model. One click, no terminal.",
            f"Download {model}",
        )
    return "Ready", f"Ollama is running and {model} is downloaded. Everything stays on this PC.", None


class OllamaHelper(SettingsCard):
    """Polls the engine while visible and keeps the card in sync with the setup state. Emits
    model_chosen(name) when the user takes the suggested model."""

    model_chosen = pyqtSignal(str)

    def __init__(self, api: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("accent", "orange")
        self._api = api
        self._model = ""
        self._status: OllamaStatus | None = None
        self._is_checking = False
        self._orb = EnergyOrb(ORB_SIZE, self)
        self._headline = styled_label("Checking Ollama…")
        self._headline.setObjectName("RowTitle")
        self._detail = styled_label("", "muted", wrap=True)
        self._action = QPushButton(self)
        set_variant(self._action, "primary")
        self._action.clicked.connect(self._act)
        self._action.hide()
        self._progress = QProgressBar(self)
        self._progress.setObjectName("FolderProgress")
        self._progress.setRange(0, PROGRESS_STEPS)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(4)
        self._progress.hide()
        self._suggestion = styled_label("", "muted", wrap=True)
        self._suggestion.hide()
        self._use_suggestion = QPushButton(self)
        self._use_suggestion.clicked.connect(self._take_suggestion)
        self._use_suggestion.hide()
        self._recommendation: ModelRecommendation | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self.check)
        self._build_layout()

    def watch(self, model: str) -> None:
        """Tracks model (the one picked on the Model page) and checks right away."""
        self._model = model.strip()
        self._refresh_suggestion()
        self.check()

    def check(self) -> None:
        if self._is_checking:
            return
        self._is_checking = True
        run_in_background(lambda: self._api.ollama_status(self._model), self._show, self._show_error)

    def showEvent(self, event: QShowEvent) -> None:
        """Polls only while the card is on screen."""
        super().showEvent(event)
        self._timer.start()
        if self._recommendation is None:
            run_in_background(self._api.ollama_recommendation, self._show_recommendation, lambda _: None)

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self._timer.stop()

    def _build_layout(self) -> None:
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self._headline)
        text.addWidget(self._detail)
        row = QHBoxLayout()
        row.setSpacing(CARD_ROW_SPACING)
        row.addWidget(self._orb)
        row.addLayout(text, 1)
        row.addWidget(self._action)
        self.body.addLayout(row)
        self.body.addWidget(self._progress)
        suggestion = QHBoxLayout()
        suggestion.setSpacing(CARD_ROW_SPACING)
        suggestion.addWidget(self._suggestion, 1)
        suggestion.addWidget(self._use_suggestion)
        self.body.addLayout(suggestion)

    def _show(self, status: OllamaStatus) -> None:
        """Renders one status; the orb pulses while something is still to be done."""
        self._is_checking = False
        self._status = status
        headline, detail, button = describe_ollama(status, self._model)
        self._headline.setText(headline)
        self._detail.setText(detail)
        self._action.setVisible(button is not None)
        self._action.setText(button or "")
        self._progress.setVisible(status.pulling is not None)
        self._progress.setValue(int((status.pull_percent or 0) * PROGRESS_STEPS / 100))
        busy = status.pulling is not None or not (status.running and status.has_model)
        if busy:
            self._orb.start()
        else:
            self._orb.stop()

    def _show_recommendation(self, recommendation: ModelRecommendation) -> None:
        self._recommendation = recommendation
        self._refresh_suggestion()

    def _refresh_suggestion(self) -> None:
        """Shows the suggestion, with a button only when it isn't the model already picked."""
        recommendation = self._recommendation
        self._suggestion.setVisible(recommendation is not None)
        if recommendation is None:
            return
        self._suggestion.setText(describe_recommendation(recommendation))
        self._suggestion.setToolTip(f"Based on this PC: {recommendation.hardware}")
        already_picked = self._model.lower() == recommendation.model.lower()
        self._use_suggestion.setText(f"Use {recommendation.model}")
        self._use_suggestion.setVisible(not already_picked)

    def _take_suggestion(self) -> None:
        if self._recommendation is not None:
            self.model_chosen.emit(self._recommendation.model)

    def _show_error(self, message: str) -> None:
        self._is_checking = False
        self._headline.setText("Couldn't check Ollama")
        self._detail.setText(message)

    def _act(self) -> None:
        """Does whatever the current button says."""
        status = self._status
        if status is None:
            return
        if not status.installed:
            QDesktopServices.openUrl(QUrl(DOWNLOAD_PAGE))
        elif not status.running:
            run_in_background(self._api.start_ollama, self._show, self._show_error)
        else:
            run_in_background(lambda: self._api.pull_ollama_model(self._model), self._show, self._show_error)
