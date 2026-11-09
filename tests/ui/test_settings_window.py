from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core.exceptions import NimbusError
from models.api import SettingsView, UsageView
from models.schema import IndexStatus
from ui.api_client import ApiClient
from ui.settings.settings_window import SettingsWindow

MODULES = ("settings_window", "sources_editor", "model_editor", "general_tab", "index_panel")
VALUES: dict[str, Any] = {
    "sources": [{"path": "C:/Users/me/Documents", "include_contents": True}],
    "file_categories": ["pdfs"],
    "max_file_size_mb": 50,
    "exclude_patterns": [],
    "llm_provider": "ollama",
    "ollama_host": "http://localhost:11434",
    "ollama_model": "llama3.1:8b",
    "openai_model": "gpt-5-mini",
    "anthropic_model": "claude-haiku-5-5",
    "compatible_model": "",
    "compatible_base_url": "",
    "hotkey": "<ctrl>+<space>",
    "daily_llm_call_cap": None,
    "auto_approved_tools": [],
}


def _run_now(fn: Any, ok: Any, err: Any = None) -> None:
    """Runs a background call inline, routing NimbusError to the error callback like the real one."""
    try:
        result = fn()
    except NimbusError as e:
        if err is not None:
            err(str(e))
        return
    ok(result)


@pytest.fixture
def api(mocker: MockerFixture) -> Mock:
    for module in MODULES:
        mocker.patch(f"ui.settings.{module}.run_in_background", side_effect=_run_now)
    mocker.patch("ui.settings.general_tab.is_autostart_enabled", return_value=False)
    fake = mocker.Mock(spec=ApiClient)
    fake.settings.return_value = SettingsView(values=VALUES, has_api_key={}, data_dir="C:/data", is_cloud=False)
    fake.source_summaries.return_value = []
    fake.index_status.return_value = IndexStatus()
    fake.usage.return_value = UsageView(calls_today=0, daily_cap=None)
    return fake


@pytest.fixture
def window(api: Mock) -> Iterator[SettingsWindow]:
    dialog = SettingsWindow(api)
    dialog.open_settings()
    yield dialog
    dialog.close()


def test_open_settings_loads_saved_values(window: SettingsWindow, api: Mock) -> None:
    api.settings.assert_called_once()
    assert window._save_button.isEnabled()


def test_save_writes_all_tabs_and_emits_saved(window: SettingsWindow, api: Mock) -> None:
    saved = Mock()
    window.saved.connect(saved)
    window._save()
    api.update_settings.assert_called_once_with(VALUES)
    api.set_api_key.assert_not_called()
    saved.assert_called_once()
    assert not window.isVisible()


def test_save_stores_new_api_key(window: SettingsWindow, api: Mock, mocker: MockerFixture) -> None:
    mocker.patch.object(window._model, "collect", return_value=({"llm_provider": "openai"}, "sk-new"))
    mocker.patch.object(window._model, "provider", return_value="openai")
    window._save()
    api.set_api_key.assert_called_once_with("openai", "sk-new")


def test_save_error_keeps_dialog_open(window: SettingsWindow, api: Mock) -> None:
    api.update_settings.side_effect = NimbusError("Couldn't save settings.")
    window._save()
    assert window.isVisible()
    assert window._error_label.text() == "Couldn't save settings."
    assert window._save_button.isEnabled()


def test_load_error_keeps_save_disabled(api: Mock) -> None:
    api.settings.side_effect = NimbusError("Couldn't reach Nimbus's engine.")
    dialog = SettingsWindow(api)
    dialog.open_settings()
    assert not dialog._save_button.isEnabled()
    assert dialog._error_label.text() == "Couldn't reach Nimbus's engine."
    dialog.close()


def test_show_tab_selects_named_tab(api: Mock) -> None:
    assert SettingsWindow(api, initial_tab="General")._tabs.currentIndex() == 2
