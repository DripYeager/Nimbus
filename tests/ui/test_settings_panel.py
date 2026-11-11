from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from core.exceptions import NimbusError
from models.api import SettingsView, UsageView
from models.schema import IndexStatus
from ui.api_client import ApiClient
from ui.settings.settings_panel import SAVED_TEXT, SettingsPanel

MODULES = ("settings_panel", "sources_editor", "model_editor", "general_tab", "index_panel", "connections_tab")
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
    "code_memory_limit_mb": 1536,
    "auto_approved_tools": [],
    "share_with_mcp_apps": False,
    "mcp_servers": [{"name": "memory", "command": "npx", "args": ["-y", "server-memory"], "env": {}, "enabled": True}],
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
    fake.mcp_servers.return_value = []
    return fake


@pytest.fixture
def panel(api: Mock) -> SettingsPanel:
    page = SettingsPanel(api)
    page.load()
    return page


def test_settings_panel_starts_with_save_disabled(api: Mock) -> None:
    assert not SettingsPanel(api)._save_button.isEnabled()


def test_load_fetches_saved_values_and_enables_save(panel: SettingsPanel, api: Mock) -> None:
    api.settings.assert_called_once()
    assert panel._save_button.isEnabled()


def test_load_error_keeps_save_disabled(api: Mock) -> None:
    api.settings.side_effect = NimbusError("Couldn't reach Nimbus's engine.")
    page = SettingsPanel(api)
    page.load()
    assert not page._save_button.isEnabled()
    assert page._status.text() == "Couldn't reach Nimbus's engine."


def test_save_writes_all_sections_and_emits_saved(panel: SettingsPanel, api: Mock) -> None:
    saved = Mock()
    panel.saved.connect(saved)
    panel._save()
    api.update_settings.assert_called_once_with(VALUES)
    api.set_api_key.assert_not_called()
    saved.assert_called_once()


def test_save_success_shows_saved_in_bar(panel: SettingsPanel) -> None:
    panel._save()
    assert panel._status.text() == SAVED_TEXT
    assert panel._status.property("state") == "success"


def test_save_stores_new_api_key(panel: SettingsPanel, api: Mock, mocker: MockerFixture) -> None:
    mocker.patch.object(panel._model, "collect", return_value=({"llm_provider": "openai"}, "sk-new"))
    mocker.patch.object(panel._model, "provider", return_value="openai")
    panel._save()
    api.set_api_key.assert_called_once_with("openai", "sk-new")


def test_save_error_shows_message_and_reenables_save(panel: SettingsPanel, api: Mock) -> None:
    api.update_settings.side_effect = NimbusError("Couldn't save settings.")
    saved = Mock()
    panel.saved.connect(saved)
    panel._save()
    assert panel._status.text() == "Couldn't save settings."
    assert panel._save_button.isEnabled()
    saved.assert_not_called()


def test_discard_reloads_saved_values(panel: SettingsPanel, api: Mock) -> None:
    panel._discard_button.click()
    assert api.settings.call_count == 2


def test_show_section_selects_named_section(panel: SettingsPanel) -> None:
    panel.show_section("general")
    assert panel._stack.currentIndex() == 2
    assert panel._nav.checkedId() == 2


def test_show_section_ignores_unknown_name(panel: SettingsPanel) -> None:
    panel.show_section("model")
    panel.show_section("nonsense")
    assert panel._stack.currentIndex() == 1


def test_nav_click_switches_section(panel: SettingsPanel) -> None:
    panel._nav.button(1).click()
    assert panel._stack.currentIndex() == 1
