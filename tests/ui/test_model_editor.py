from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QMessageBox
from pytest_mock import MockerFixture

from models.api import ProviderTestResult, SettingsView
from models.chat import ProviderConfig
from ui.api_client import ApiClient
from ui.settings.model_editor import LOCAL_PRIVACY_NOTE, SAVED_KEY_PLACEHOLDER, ModelEditor

YES = QMessageBox.StandardButton.Yes
NO = QMessageBox.StandardButton.No


def _view(provider: str = "ollama", has_key: bool = False) -> SettingsView:
    values = {
        "llm_provider": provider,
        "ollama_host": "http://localhost:11434",
        "ollama_model": "llama3.1:8b",
        "openai_model": "gpt-5-mini",
        "anthropic_model": "claude-haiku-5-5",
        "compatible_model": "",
        "compatible_base_url": "",
    }
    return SettingsView(values=values, has_api_key={"anthropic": has_key}, data_dir="C:/data", is_cloud=False)


@pytest.fixture
def api(mocker: MockerFixture) -> Mock:
    mocker.patch(
        "ui.settings.model_editor.run_in_background",
        side_effect=lambda fn, ok, err=None: ok(fn()),
    )
    return mocker.Mock(spec=ApiClient)


def _pick(editor: ModelEditor, provider: str) -> None:
    editor._provider_box.setCurrentIndex(editor._provider_box.findData(provider))


def test_collect_round_trips_loaded_values(api: Mock) -> None:
    editor = ModelEditor(api)
    view = _view()
    editor.load(view)
    updates, key = editor.collect()
    assert updates == view.values
    assert key is None


def test_load_shows_local_privacy_note(api: Mock) -> None:
    editor = ModelEditor(api)
    editor.load(_view())
    assert editor._privacy_label.text() == LOCAL_PRIVACY_NOTE


def test_provider_switch_to_cloud_reverts_when_declined(api: Mock, mocker: MockerFixture) -> None:
    question = mocker.patch("ui.settings.model_editor.QMessageBox.question", return_value=NO)
    editor = ModelEditor(api)
    editor.load(_view())
    _pick(editor, "openai")
    question.assert_called_once()
    assert editor.provider() == "ollama"


def test_provider_switch_to_cloud_applies_when_confirmed(api: Mock, mocker: MockerFixture) -> None:
    mocker.patch("ui.settings.model_editor.QMessageBox.question", return_value=YES)
    editor = ModelEditor(api)
    editor.load(_view(has_key=True))
    _pick(editor, "anthropic")
    assert editor.provider() == "anthropic"
    assert editor._key_edit.placeholderText() == SAVED_KEY_PLACEHOLDER
    assert "sent to Anthropic" in editor._privacy_label.text()


def test_provider_switch_between_cloud_providers_skips_warning(api: Mock, mocker: MockerFixture) -> None:
    question = mocker.patch("ui.settings.model_editor.QMessageBox.question", return_value=YES)
    editor = ModelEditor(api)
    editor.load(_view(provider="openai"))
    _pick(editor, "anthropic")
    question.assert_not_called()


def test_collect_returns_typed_key_and_model(api: Mock, mocker: MockerFixture) -> None:
    mocker.patch("ui.settings.model_editor.QMessageBox.question", return_value=YES)
    editor = ModelEditor(api)
    editor.load(_view())
    _pick(editor, "openai")
    editor._key_edit.setText("  sk-test  ")
    editor._model_box.setEditText("gpt-5")
    updates, key = editor.collect()
    assert (updates["llm_provider"], updates["openai_model"], key) == ("openai", "gpt-5", "sk-test")


def test_collect_keeps_model_typed_before_switching(api: Mock, mocker: MockerFixture) -> None:
    mocker.patch("ui.settings.model_editor.QMessageBox.question", return_value=YES)
    editor = ModelEditor(api)
    editor.load(_view())
    editor._model_box.setEditText("qwen3:8b")
    _pick(editor, "openai")
    assert editor.collect()[0]["ollama_model"] == "qwen3:8b"


def test_test_connection_fills_models_and_keeps_typed_text(api: Mock) -> None:
    api.test_provider.return_value = ProviderTestResult(ok=True, message="Connected", models=["a", "b"])
    editor = ModelEditor(api)
    editor.load(_view())
    editor._test_connection()
    api.test_provider.assert_called_once_with(
        ProviderConfig(name="ollama", model="llama3.1:8b", api_key=None, base_url="http://localhost:11434")
    )
    assert [editor._model_box.itemText(i) for i in range(editor._model_box.count())] == ["a", "b"]
    assert editor._model_box.currentText() == "llama3.1:8b"
    assert editor._test_status.text() == "✓ Connected"


def test_test_connection_shows_failure_as_error(api: Mock) -> None:
    api.test_provider.return_value = ProviderTestResult(ok=False, message="Ollama isn't running")
    editor = ModelEditor(api)
    editor.load(_view())
    editor._test_connection()
    assert editor._test_status.property("role") == "error"


def test_test_connection_shows_call_error(api: Mock, mocker: MockerFixture) -> None:
    def failing(fn: Any, ok: Any, err: Any = None) -> None:
        err("Couldn't reach Nimbus's engine.")

    mocker.patch("ui.settings.model_editor.run_in_background", side_effect=failing)
    editor = ModelEditor(api)
    editor.load(_view())
    editor._test_connection()
    assert editor._test_status.text() == "Couldn't reach Nimbus's engine."
    assert editor._test_button.isEnabled()
