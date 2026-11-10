from __future__ import annotations

from pytest_mock import MockerFixture

from ui.api_client import ApiClient
from ui.settings.settings_save import save_settings


def test_save_settings_skips_key_when_none(mocker: MockerFixture) -> None:
    api = mocker.Mock(spec=ApiClient)
    save_settings(api, {"hotkey": "<ctrl>+<space>"}, "ollama", None)
    api.update_settings.assert_called_once_with({"hotkey": "<ctrl>+<space>"})
    api.set_api_key.assert_not_called()


def test_save_settings_stores_typed_key(mocker: MockerFixture) -> None:
    api = mocker.Mock(spec=ApiClient)
    save_settings(api, {}, "openai", "sk-new")
    api.set_api_key.assert_called_once_with("openai", "sk-new")
