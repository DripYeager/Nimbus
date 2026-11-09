"""
The "which brain should Nimbus use?" editor: provider, its connection fields, the model, a
connection test, and a plain statement of where questions go. Owns editing model settings in
memory; saving them and storing the API key are the caller's job.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from models.api import ProviderTestResult, SettingsView
from models.chat import ProviderConfig, ProviderName
from ui.api_client import ApiClient
from ui.background_call import run_in_background
from ui.settings.label_roles import set_role, styled_label

PROVIDER_LABELS: dict[ProviderName, str] = {
    "ollama": "Ollama — runs on this PC, private",
    "openai": "OpenAI",
    "anthropic": "Anthropic — Claude",
    "openai_compatible": "Custom OpenAI-compatible server",
}
PROVIDER_DISPLAY_NAMES: dict[ProviderName, str] = {
    "ollama": "Ollama",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "openai_compatible": "your custom server",
}
MODEL_SETTING_KEYS: dict[ProviderName, str] = {
    "ollama": "ollama_model",
    "openai": "openai_model",
    "anthropic": "anthropic_model",
    "openai_compatible": "compatible_model",
}
LOCAL_PROVIDER: ProviderName = "ollama"
LOCAL_PRIVACY_NOTE = "Answers are generated on this PC. Nothing leaves your machine."
CLOUD_PRIVACY_NOTE = "Questions and the file excerpts needed to answer them are sent to {provider}."
SAVED_KEY_PLACEHOLDER = "Saved — leave blank to keep it"
NEW_KEY_PLACEHOLDER = "Paste your API key"
CLOUD_WARNING_TITLE = "Use a cloud model?"
CLOUD_WARNING = (
    "With {provider}, your questions and the parts of your files needed to answer them leave "
    "this PC and are processed by {provider}.\n\nSwitch anyway?"
)


class ModelEditor(QWidget):
    """Edits the provider settings and collects a newly typed API key."""

    def __init__(self, api: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._values: dict[str, Any] = {}
        self._has_api_key: dict[str, bool] = {}
        self._current: ProviderName = LOCAL_PROVIDER
        self._provider_box = QComboBox()
        for name, label in PROVIDER_LABELS.items():
            self._provider_box.addItem(label, name)
        self._host_edit = QLineEdit()
        self._base_url_edit = QLineEdit()
        self._base_url_edit.setPlaceholderText("http://localhost:8000/v1")
        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._model_box = QComboBox()
        self._model_box.setEditable(True)
        self._test_button = QPushButton("Test connection")
        self._test_status = styled_label("", "muted", wrap=True)
        self._privacy_label = styled_label("", "muted", wrap=True)
        self._form = QFormLayout()
        self._build_layout()
        self._provider_box.currentIndexChanged.connect(self._on_provider_picked)
        self._test_button.clicked.connect(self._test_connection)

    def _build_layout(self) -> None:
        """Provider and its fields in a form, then the test row and the privacy note."""
        self._form.addRow("Provider", self._provider_box)
        self._form.addRow("Ollama address", self._host_edit)
        self._form.addRow("Server URL", self._base_url_edit)
        self._form.addRow("API key", self._key_edit)
        self._form.addRow("Model", self._model_box)
        test_row = QHBoxLayout()
        test_row.addWidget(self._test_button)
        test_row.addWidget(self._test_status, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(self._form)
        layout.addLayout(test_row)
        layout.addSpacing(8)
        layout.addWidget(self._privacy_label)
        layout.addStretch(1)

    def provider(self) -> ProviderName:
        return self._provider_box.currentData()

    def load(self, view: SettingsView) -> None:
        """Fills the fields from saved settings without triggering the cloud warning."""
        self._values = dict(view.values)
        self._has_api_key = dict(view.has_api_key)
        self._host_edit.setText(str(self._values.get("ollama_host", "")))
        self._base_url_edit.setText(str(self._values.get("compatible_base_url", "")))
        self._current = self._values.get("llm_provider", LOCAL_PROVIDER)
        self._provider_box.blockSignals(True)
        self._provider_box.setCurrentIndex(self._provider_box.findData(self._current))
        self._provider_box.blockSignals(False)
        self._show_provider(self._current)

    def collect(self) -> tuple[dict[str, Any], str | None]:
        """
        The edited model settings, plus the API key the user typed.

        Returns:
            (updates, api_key) — api_key is None when the field was left blank, so a key
            that's already saved is kept rather than wiped.
        """
        self._remember_model()
        updates = {
            "llm_provider": self.provider(),
            "ollama_host": self._host_edit.text().strip(),
            "compatible_base_url": self._base_url_edit.text().strip(),
        }
        for key in MODEL_SETTING_KEYS.values():
            if key in self._values:
                updates[key] = self._values[key]
        return updates, self._key_edit.text().strip() or None

    def _on_provider_picked(self) -> None:
        """Confirms a move off the local model, then swaps the fields to the new provider."""
        picked = self.provider()
        if self._current == LOCAL_PROVIDER and picked != LOCAL_PROVIDER and not self._confirm_cloud(picked):
            self._provider_box.blockSignals(True)
            self._provider_box.setCurrentIndex(self._provider_box.findData(self._current))
            self._provider_box.blockSignals(False)
            return
        self._remember_model(self._current)
        self._current = picked
        self._key_edit.clear()
        self._test_status.clear()
        self._show_provider(picked)

    def _confirm_cloud(self, provider: ProviderName) -> bool:
        message = CLOUD_WARNING.format(provider=PROVIDER_DISPLAY_NAMES[provider])
        return QMessageBox.question(self, CLOUD_WARNING_TITLE, message) == QMessageBox.StandardButton.Yes

    def _remember_model(self, provider: ProviderName | None = None) -> None:
        """Keeps the typed model per provider, so switching back and forth loses nothing."""
        self._values[MODEL_SETTING_KEYS[provider or self.provider()]] = self._model_box.currentText().strip()

    def _show_provider(self, provider: ProviderName) -> None:
        """Shows only the fields this provider uses and its privacy note."""
        self._form.setRowVisible(self._host_edit, provider == LOCAL_PROVIDER)
        self._form.setRowVisible(self._base_url_edit, provider == "openai_compatible")
        self._form.setRowVisible(self._key_edit, provider != LOCAL_PROVIDER)
        has_key = self._has_api_key.get(provider, False)
        self._key_edit.setPlaceholderText(SAVED_KEY_PLACEHOLDER if has_key else NEW_KEY_PLACEHOLDER)
        self._model_box.clear()
        self._model_box.setEditText(str(self._values.get(MODEL_SETTING_KEYS[provider], "")))
        if provider == LOCAL_PROVIDER:
            self._privacy_label.setText(LOCAL_PRIVACY_NOTE)
        else:
            self._privacy_label.setText(CLOUD_PRIVACY_NOTE.format(provider=PROVIDER_DISPLAY_NAMES[provider]))

    def _test_connection(self) -> None:
        config = self._unsaved_config()
        self._test_button.setEnabled(False)
        self._test_status.setText("Testing…")
        set_role(self._test_status, "muted")
        run_in_background(lambda: self._api.test_provider(config), self._show_test_result, self._show_test_error)

    def _unsaved_config(self) -> ProviderConfig:
        """What's typed right now — the user hasn't necessarily saved any of it yet."""
        provider = self.provider()
        base_url = {"ollama": self._host_edit.text(), "openai_compatible": self._base_url_edit.text()}.get(provider)
        return ProviderConfig(
            name=provider,
            model=self._model_box.currentText().strip(),
            api_key=self._key_edit.text().strip() or None,
            base_url=base_url.strip() if base_url else None,
        )

    def _show_test_result(self, result: ProviderTestResult) -> None:
        """Offers the provider's models in the dropdown, keeping whatever the user typed."""
        self._test_button.setEnabled(True)
        typed = self._model_box.currentText()
        self._model_box.clear()
        self._model_box.addItems(result.models)
        self._model_box.setEditText(typed)
        self._test_status.setText(f"✓ {result.message}" if result.ok else result.message)
        set_role(self._test_status, "muted" if result.ok else "error")

    def _show_test_error(self, message: str) -> None:
        self._test_button.setEnabled(True)
        self._test_status.setText(message)
        set_role(self._test_status, "error")
